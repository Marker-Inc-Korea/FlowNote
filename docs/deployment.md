# FlowNote 배포

## 기준

FlowNote의 기본 배포 형태는 사내 단일 서버 PC 운영과 승인된 설치형 클라이언트 배포이다. Windows WPF는 관리자/현장 PC용 기본 클라이언트이고, Android는 승인된 현장 태블릿 또는 러기드 단말용 현장 입력 클라이언트로 추가한다. 클라우드, 외부 접근, 일반 브라우저 직접 사용은 초기 기준이 아니며 별도 협의가 필요한 후속 선택지다.

```text
Server PC
  -> FastAPI server
  -> SQLite DB
  -> local storage/ folder

Client PCs
  -> Windows WPF installed app
  -> local SQLite DB and local Files/ folder
  -> API connection to Server PC when FLOWNOTE_API_BASE_URL is set

Approved Android field devices
  -> Android installed app
  -> document viewing, FieldComment, photos, handover, channel notifications
  -> API connection to Server PC through configured server URL
```

WPF 앱은 로컬 SQLite에 먼저 기록하고 서버 URL이 설정되어 있으면 서버 동기화를 시도한다. 서버 호출 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다.

Android 앱은 현장 입력과 알림 확인을 서버 기준으로 처리한다. 네트워크가 불안정한 구간의 임시 저장은 허용하되, 장기 원천 데이터는 서버 SQLite와 `storage/`에 남기는 것을 기준으로 한다. Android 배포는 개인 휴대폰 기본 배포가 아니라 현장 승인 단말 배포를 기준으로 하며, MDM, APK/AAB 배포 방식, 사내 Wi-Fi, 푸시 전달 방식은 구현 단계에서 현장 보안 정책과 함께 확정한다.

## 운영 설치 경로

운영 설치 시 경로는 고객사 서버 PC에서 명시적으로 만든 고정 폴더를 사용한다. 아래 경로는 기준 예시이며, 실제 현장에서는 드라이브만 바꿔도 같은 구조를 유지한다.

```text
C:\FlowNote\
  Server\
    api\                  FastAPI 서버 코드와 Python 실행 환경
    data\                 서버 SQLite
      flownote.sqlite3
    storage\              서버 문서 파일, 첨부, 보고서 파일
    logs\                 서버 실행 로그
    .env                  서버 운영 환경 변수, Git 제외
  Client\
    FlowNote.Windows.App\ WPF 앱 실행 파일, .NET 실행 메타데이터, 의존 DLL
  LocalData\
    flownote.local.sqlite WPF 공통 SQLite
    Files\                WPF 로컬 파일 복사본과 첨부
```

서버 PC에 WPF 앱도 함께 설치해 관리자 작업을 수행하는 경우 `C:\FlowNote\LocalData`를 공통 로컬 데이터 폴더로 사용한다. 현장 클라이언트 PC는 각 PC의 로컬 데이터 폴더를 사용하되, 서버 동기화가 필요한 경우 `FLOWNOTE_API_BASE_URL`만 서버 주소로 맞춘다.

## 설치 산출물 분리

운영 설치 산출물은 실행 파일, 운영 데이터, 로컬 클라이언트 데이터를 분리한다.

| 위치 | 포함 | 포함하지 않음 |
| --- | --- | --- |
| `C:\FlowNote\Server\api` | `services/api/app`, `pyproject.toml`, 운영 Python `.venv` | 테스트 폴더, 개발 DB, 개발 `storage`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, 실제 고객 파일 |
| `C:\FlowNote\Server\.env` | 서버 운영 환경 변수 | Git 추적 대상, 기본 개발 비밀값 |
| `C:\FlowNote\Server\data` | 운영 서버 SQLite와 WAL/SHM 파일 | 클라이언트 로컬 DB |
| `C:\FlowNote\Server\storage` | 서버가 소유하는 문서 원본, 첨부, 보고서 파일 | WPF 로컬 캐시 파일 |
| `C:\FlowNote\Server\logs` | FastAPI 실행 로그, 장애 분석 로그 | 빌드 산출물 |
| `C:\Program Files\FlowNote\Client\FlowNote.Windows.App` | MSI가 설치한 WPF 실행 파일, .NET 실행 메타데이터, 의존 DLL | WPF 로컬 DB, 실제 현장 문서 데이터 |
| `C:\FlowNote\LocalData` | WPF 로컬 SQLite, `Files\` | 서버 SQLite, 서버 `storage` |

현재 저장소 기준으로 서버는 별도 압축 패키지 없이 `services/api/app`과 `pyproject.toml`을 `C:\FlowNote\Server\api`에 복사하고 해당 폴더에서 운영 `.venv`를 만든다. WPF 클라이언트는 MSI로 고정해 설치하며 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`, 로컬 데이터 위치는 `FLOWNOTE_LOCAL_DATA_DIR`로 분리한다. Android 클라이언트의 패키징과 설치 산출물 경로는 아직 구현되지 않았으며, `apps/android/` 구현 단계에서 별도 배포 절차를 추가한다.

## 배포 방식 결정

- WPF 앱은 MSI를 기준 패키징 방식으로 사용한다. MSIX는 서명, 패키지 아이덴티티, 앱 컨테이너 제약을 현장별로 더 검토해야 하므로 초기 운영 배포 기준에서 제외한다.
- MSI는 WPF 실행에 필요한 앱 파일만 설치한다. 로컬 SQLite와 `Files\`는 설치 폴더 아래에 두지 않고 `FLOWNOTE_LOCAL_DATA_DIR`가 가리키는 폴더에 둔다.
- Android 앱은 승인된 현장 단말용 설치 패키지로 배포한다. 개인 휴대폰 기본 배포와 일반 웹 브라우저 접속은 기준이 아니다.
- Windows와 Android의 채널 알림은 후속 구현 범위다. 구현 시 서버 사용자, 클라이언트/단말 승인 상태, 채널 멤버십을 함께 확인해 표시하며, 외부 푸시 서비스를 쓸지 사내망 polling 또는 WebSocket을 쓸지는 현장 네트워크 정책 확정 후 결정한다.
- FastAPI 서버는 Windows 작업 스케줄러의 부팅 시 자동 실행 작업으로 등록한다. Python/FastAPI 프로세스를 Windows 서비스로 직접 등록하려면 별도 서비스 래퍼가 필요하므로, 초기 기준은 Windows 기본 기능만 사용하는 작업 스케줄러 방식으로 고정한다.
- 서버 작업 이름은 기본 `\FlowNote\FlowNoteApi`다. 실행 래퍼는 `C:\FlowNote\Server\scripts\run-flownote-server.ps1`, 로그는 `C:\FlowNote\Server\logs`에 둔다.

## Windows MSI 운영 배포 확정 조건

WPF MSI는 Windows 배포 준비 PC와 최소 1대 이상의 설치 대상 Windows PC에서 실기 검증을 통과하기 전까지 운영 배포 확정 상태로 보지 않는다. macOS 또는 비Windows 개발 환경의 publish 성공은 사전 점검일 뿐이며, `wix`, `msiexec`, `signtool`, WebView2 Runtime, .NET Windows Desktop Runtime 조합은 Windows PC에서 별도 확인한다.

운영 배포 확정 전에는 다음 결과를 [검증 자동화 문서](./verification.md)에 기록한다.

- framework-dependent MSI와 self-contained MSI가 모두 생성된다.
- 두 MSI의 포함 파일 목록에 로컬 SQLite, WAL/SHM, `Data\Files`, `storage`, `logs`, 테스트/샘플/고객 파일이 없다.
- 설치 폴더 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에는 실행 파일과 의존 파일만 있고, 로컬 DB와 `Files\`는 `FLOWNOTE_LOCAL_DATA_DIR`가 가리키는 폴더에만 생성된다.
- .NET Windows Desktop Runtime이 없는 PC에서 framework-dependent MSI의 실행 실패 양상과 self-contained MSI의 실행 결과를 구분해 기록한다.
- WebView2 Runtime 미설치 상태의 PDF 열람 실패 안내와 설치 후 동일 PDF 정상 열람을 기록한다.
- 코드 서명 인증서가 준비된 경우 EXE와 MSI 모두 `signtool verify /pa`를 통과한다.
- 검증 후 `git status --short --untracked-files=all`에 `artifacts`, publish 산출물, MSI, `.wixpdb`, 테스트 산출물이 추적 대상으로 잡히지 않는다.

## 서버 설치 절차

서버 PC에는 Python 3.11 이상을 설치한다. WPF 앱을 같은 PC에서 사용할 경우 .NET Windows Desktop Runtime과 WebView2 Runtime도 준비한다.

1. 운영 폴더를 만든다.

```powershell
New-Item -ItemType Directory -Force C:\FlowNote\Server\api
New-Item -ItemType Directory -Force C:\FlowNote\Server\data
New-Item -ItemType Directory -Force C:\FlowNote\Server\storage
New-Item -ItemType Directory -Force C:\FlowNote\Server\logs
New-Item -ItemType Directory -Force C:\FlowNote\LocalData
```

2. 저장소 또는 배포 준비 PC에서 서버 파일을 복사한다.

```powershell
Copy-Item -Recurse .\services\api\app C:\FlowNote\Server\api\
Copy-Item .\services\api\pyproject.toml C:\FlowNote\Server\api\
```

3. 운영 Python 가상환경을 만들고 의존성을 설치한다.

```powershell
cd C:\FlowNote\Server\api
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

4. `C:\FlowNote\Server\.env`를 만든다. 비밀값은 현장별 긴 난수로 발급하고 저장소에 커밋하지 않는다.

```text
FLOWNOTE_ENV=production
FLOWNOTE_API_HOST=0.0.0.0
FLOWNOTE_API_PORT=5184
FLOWNOTE_DATABASE_URL=sqlite:///C:/FlowNote/Server/data/flownote.sqlite3
FLOWNOTE_DATABASE_ECHO=false
FLOWNOTE_STORAGE_ROOT=C:/FlowNote/Server/storage
FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES=20971520
FLOWNOTE_ACCESS_TOKEN_SECRET=<현장별 긴 비밀값>
FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES=480
FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS=14
FLOWNOTE_SESSION_COOKIE_NAME=flownote_session
```

5. 서버 실행 래퍼를 저장소에서 운영 폴더로 복사하고 작업 스케줄러에 등록한다. 등록 명령은 관리자 PowerShell에서 실행한다.

```powershell
.\scripts\install-flownote-server-task.ps1 -ServerRoot C:\FlowNote\Server -StartNow
```

등록 스크립트는 `run-flownote-server.ps1`을 `C:\FlowNote\Server\scripts`로 복사하고, `C:\FlowNote\Server\.env`를 프로세스 환경변수로 읽은 뒤 `C:\FlowNote\Server\api`에서 uvicorn을 실행한다. `.env`에 값이 없으면 로컬 서버 테스트 기준으로 `FLOWNOTE_API_HOST=127.0.0.1`, `FLOWNOTE_API_PORT=5184`, `FLOWNOTE_DATABASE_URL=sqlite:///C:/FlowNote/Server/data/flownote.sqlite3`, `FLOWNOTE_STORAGE_ROOT=C:\FlowNote\Server\storage`를 기본값으로 둔다. 현장 클라이언트 PC에서 서버 PC로 접속해야 하는 운영 구성은 `.env`에 `FLOWNOTE_API_HOST=0.0.0.0`을 명시한다.

6. 서버 작업을 시작, 중지, 재시작하거나 상태를 확인한다.

```powershell
.\scripts\manage-flownote-server-task.ps1 -Action start
.\scripts\manage-flownote-server-task.ps1 -Action stop
.\scripts\manage-flownote-server-task.ps1 -Action restart
.\scripts\manage-flownote-server-task.ps1 -Action status
```

7. 서버 로그 위치를 확인한다.

```text
C:\FlowNote\Server\logs\flownote-api.out.log
C:\FlowNote\Server\logs\flownote-api.err.log
```

8. 서버 PC에서 상태 URL을 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health/db
```

9. 클라이언트 PC에서 서버 PC 주소로 같은 URL을 확인한다.

```powershell
Invoke-RestMethod http://<서버IP>:5184/api/v1/health
Invoke-RestMethod http://<서버IP>:5184/api/v1/health/db
```

클라이언트 PC에서 URL 확인이 실패하면 서버 실행 여부, Windows 방화벽 인바운드 규칙, 서버 IP, 포트 `5184` 접근 가능 여부를 먼저 확인한다.

## 운영 계정 발급과 변경 절차

서버 계정과 WPF 로컬 계정은 같은 로그인 ID를 쓸 수 있지만 관리 위치가 다르다. 서버 URL이 설정된 WPF는 서버 계정으로 로그인하고, 서버가 401 또는 403을 반환하면 로컬 계정으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 WPF 로컬 계정을 사용한다.

### 최초 서버 관리자 계정

1. 서버 DB 최초 생성 시 FastAPI는 서버 `user_accounts`에 `admin` 계정을 만든다. 이 계정은 최초 서버 관리자 계정이며 WPF 사용자 관리 화면에서 생성하거나 변경하지 않는다.
2. 개발/스모크 테스트용 기본 비밀번호 `1234`는 운영 로그인 전에 반드시 변경한다. 현장 운영자는 서버 PC의 관리자 PowerShell에서 운영 스크립트를 실행해 새 비밀번호를 대화식으로 입력한다. 현재 스크립트는 8자 미만 비밀번호를 거부한다. 새 비밀번호를 명령줄 인자, PowerShell 기록, 서버 로그에 남기지 않는다.

```powershell
cd C:\FlowNote\Server\api
.\.venv\Scripts\python.exe -m app.ops.server_accounts reset-password --username admin
```

스크립트는 기본적으로 `.env` 또는 `FLOWNOTE_DATABASE_URL`의 서버 DB를 사용한다. 운영 DB 위치를 명령에서 명확히 고정해야 하는 경우에는 다음처럼 DB URL만 인자로 넘긴다. 비밀번호 값은 여전히 대화식으로만 입력한다.

```powershell
.\.venv\Scripts\python.exe -m app.ops.server_accounts --database-url sqlite:///C:/FlowNote/Server/data/flownote.sqlite3 reset-password --username admin
```

3. 최초 운영 로그인은 변경된 서버 비밀번호로 WPF에서 수행한다. 현재 구현 범위에서는 WPF 또는 FastAPI가 첫 로그인 후 비밀번호 변경 화면을 강제로 띄우지 않는다. 운영 기준은 “첫 로그인 전 변경”으로 고정하고, `must_change_password` 같은 서버 컬럼과 변경 API, WPF 변경 화면은 후속 범위로 둔다. 운영자는 WPF 첫 서버 로그인 전에 변경 완료 여부, 변경 수행자, 확인자를 운영 기록에 남긴다.
4. 변경 완료 후 기본 비밀번호 `1234`로 WPF 서버 로그인이 실패하는지 확인한다. 이 실패가 서버 401이면 WPF가 로컬 `admin / 1234`로 우회해 성공하면 안 된다.

### 서버 계정과 WPF 로컬 계정

- 서버 계정은 서버 DB의 `user_accounts`에서 관리한다. 서버 로그인, 서버 API 권한, 서버 문서 등록자, 서버 FieldComment 작성자, 서버 감사 이력은 서버 계정을 기준으로 남긴다.
- WPF 로컬 사용자 관리 화면의 사용자 추가, 역할 변경, 비밀번호 변경은 로컬 SQLite 전용이다. 화면 제목, 사용자 목록, 상세 문구는 “로컬” 계정임을 표시해야 하며 서버 계정을 만들거나 수정하지 않는다.
- 서버 URL을 쓰는 운영 PC에서는 서버 계정 권한을 우선한다. 같은 로그인 ID의 로컬 계정 role이 다르더라도 서버 로그인 성공 후 화면 권한과 서버 동기화 작성자 기준은 서버 응답의 role과 사용자 ID다.
- 서버 계정 관리 API와 WPF 서버 계정 관리 연동은 후속 범위다. 그 전까지 운영자는 서버 PC에서 DB 운영 절차로 서버 계정을 발급, 재설정, 비활성화한다.

### 서버 계정 발급

서버 계정 발급은 운영 스크립트의 `create` 명령으로 수행한다. `role` 값은 [데이터 모델 문서의 역할 값](./data-model.md#역할-값) 중 하나만 사용한다.

```powershell
cd C:\FlowNote\Server\api
.\.venv\Scripts\python.exe -m app.ops.server_accounts create --username line-a-admin --display-name "라인 A 관리자" --role line-foreman
```

비밀번호는 `new password`와 `confirm password` 프롬프트에 대화식으로 입력한다. 현재 스크립트는 8자 미만 비밀번호를 거부한다. 스크립트 출력에는 `username`, 서버 `user_id`, 폐기된 세션 수만 표시되며 비밀번호는 출력하지 않는다.

### 비밀번호 재설정

1. 본인 확인과 승인자를 운영 기록에 남긴다.
2. `reset-password` 명령으로 임시 비밀번호를 설정한다.
3. 해당 서버 계정의 기존 활성 `auth_sessions`는 명령 안에서 `REVOKED`로 바뀌고 `revoked_reason`은 `password_reset`으로 남는다.
4. 임시 비밀번호는 운영자와 사용자에게 일회성으로 전달하고, 사용자가 로그인한 뒤 운영자 입회하에 다시 변경한다. 현재 앱 강제 변경 기능은 후속 범위이므로 운영 절차로 통제한다.

```powershell
.\.venv\Scripts\python.exe -m app.ops.server_accounts reset-password --username line-a-admin
```

잠금 계정을 승인 후 재개하면서 비밀번호까지 바꾸는 경우에는 먼저 상태를 `ACTIVE`로 바꾸고 이어서 비밀번호를 재설정한다. 한 번의 비밀번호 재설정으로 잠금/비활성 계정이 자동 활성화되지 않게 하는 것이 기본 운영 기준이다. 운영 승인 기록이 이미 남아 있고 한 번의 명령으로 처리해야 하는 경우에만 `reset-password --activate`를 사용할 수 있으며, 이 옵션은 비밀번호 재설정과 함께 계정을 `ACTIVE`로 바꾼다.

### 비활성 계정, 퇴사, 권한 변경

- 장기 미사용, 퇴사, 권한 회수 계정은 `set-status --status DISABLED`로 변경한다. 스크립트는 `is_active = 0`, `status = 'DISABLED'`로 저장하고 기존 활성 세션을 `REVOKED`로 바꾼다.
- 일시 잠금은 `set-status --status LOCKED`로 구분한다. 재개 시 운영 승인 후 `set-status --status ACTIVE`로 되돌리고 비밀번호 재설정을 함께 수행한다.
- 역할 변경은 `set-role`로 서버 DB의 `role`을 바꾸고, 변경 사유와 승인자를 운영 기록에 남긴다. WPF 로컬 계정이 별도로 필요한 PC라면 로컬 사용자 관리 화면에서도 같은 사용자에 대한 로컬 권한을 별도로 점검한다.
- 퇴사자는 서버 계정과 WPF 로컬 계정을 각각 비활성화한다. 서버 계정 비활성화만으로 오프라인 로컬 로그인 가능성을 제거할 수 없으므로, 로컬 계정 사용 PC 목록을 함께 확인한다.

```powershell
.\.venv\Scripts\python.exe -m app.ops.server_accounts set-status --username line-a-admin --status LOCKED
.\.venv\Scripts\python.exe -m app.ops.server_accounts set-status --username line-a-admin --status DISABLED
.\.venv\Scripts\python.exe -m app.ops.server_accounts set-status --username line-a-admin --status ACTIVE
.\.venv\Scripts\python.exe -m app.ops.server_accounts set-role --username line-a-admin --role document-admin
```

## WPF 설치 절차

WPF 앱은 MSI로 Windows PC에 설치한다. 기본 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`이며, 서버 PC에 관리자용 앱을 함께 설치할 때도 로컬 데이터는 별도 `C:\FlowNote\LocalData`에 둔다.

1. 배포 준비 PC에서 WPF MSI 산출물을 만든다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
```

MSI 패키징은 WiX Toolset CLI를 사용한다. 배포 준비 PC에 `wix` 명령이 없으면 먼저 `dotnet tool install --global wix --version 5.0.2`로 설치한다. 최신 WiX 7은 OSMF EULA 수락 없이는 `wix build`가 실패하므로, WiX 7을 쓰려면 현장 또는 배포 담당자가 라이선스 조건을 확인하고 명시적으로 수락한 뒤 사용한다. 스크립트는 `dotnet publish` 결과와 WiX 중간 파일, MSI를 `artifacts\wpf-msi` 아래에 만들며 이 경로는 Git 제외 대상이다.

MSI에는 WPF 실행 파일, 실행에 필요한 `.deps.json`/`.runtimeconfig.json`, 의존 DLL과 네이티브 런타임 DLL만 포함한다. 패키징 스크립트는 디버그 심볼 `.pdb`와 문서 XML을 제외한다. 로컬 SQLite, WAL/SHM 파일, `Data\Files` 또는 테스트/샘플 등록 파일은 설치 폴더에 포함하지 않는다.

패키징 스크립트는 WiX 소스 생성 전에 MSI 포함 파일 목록을 `artifacts\wpf-msi\FlowNote.Windows.App-<version>-<runtime>.files.txt`에 남긴다. 이 목록에 다음 항목이 하나라도 있으면 MSI 생성을 실패로 처리한다.

- `*.sqlite`, `*.sqlite3`, `*.db`, `*.sqlite-wal`, `*.sqlite-shm`, `*.db-wal`, `*.db-shm`
- `Data\`, `Files\`, `storage\`, `logs\` 계열 경로
- `test`, `smoke`, `sample-registration`, `customer`가 들어간 파일
- PDF, Office, HWP, DWG, 압축 파일, 이미지, TXT/MD 같은 고객 문서 또는 테스트 산출물 확장자

현재 패키징 스크립트 기준 MSI 파일 세트는 `FlowNote.Windows.App.exe`, `.deps.json`, `.runtimeconfig.json`, 앱/코어 DLL, `Microsoft.Data.Sqlite`, `Microsoft.Web.WebView2`, `SQLitePCLRaw`, `PdfPig`, `WebView2Loader.dll`, `e_sqlite3.dll`, `runtimes\win-x64\native\WebView2Loader.dll` 같은 실행 필수 파일만 포함해야 한다. 금지 파일 패턴은 스크립트가 생성 직전에 검사한다.

`package-wpf-msi.ps1`는 publish 폴더를 매번 비운 뒤 새로 publish한다. framework-dependent MSI와 self-contained MSI를 번갈아 만들 때 이전 런타임 파일이 남아 다른 MSI에 섞이면 안 된다.

### .NET Desktop Runtime과 self-contained MSI

기본 `package-wpf-msi.ps1` 명령은 framework-dependent MSI를 만든다. 이 방식은 설치 대상 PC에 FlowNote WPF 대상 프레임워크와 같은 계열의 `.NET Windows Desktop Runtime`이 설치되어 있어야 한다.

설치 대상 PC에서 다음 명령으로 런타임을 확인한다.

```powershell
dotnet --list-runtimes | Select-String "Microsoft.WindowsDesktop.App 10."
```

`dotnet` 명령이 없거나 `Microsoft.WindowsDesktop.App 10.` 런타임이 없으면 framework-dependent MSI만으로는 실행을 보장하지 않는다. 다음 조건 중 하나라도 해당하면 self-contained MSI를 별도 생성한다.

- 현장 PC에 .NET Windows Desktop Runtime을 설치할 수 없거나 설치 여부를 사전에 통제하기 어렵다.
- 현장 PC가 인터넷에 연결되지 않아 런타임 설치를 설치 시점에 처리할 수 없다.
- 클라이언트 설치파일 하나로 앱 실행에 필요한 .NET 런타임까지 고정해야 한다.
- 여러 생산 PC의 .NET 런타임 패치 수준 차이로 장애 분석이 어려운 현장이다.

self-contained MSI는 다음 명령으로 만든다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
```

산출물 이름은 `FlowNote.Windows.App-0.1.0-win-x64-self-contained.msi`처럼 `self-contained` 접미사를 붙인다. self-contained MSI는 .NET 런타임 파일을 함께 담기 때문에 framework-dependent MSI보다 크다. 단, WebView2 Runtime은 self-contained .NET 배포에 포함되지 않으므로 별도 점검과 설치 기준을 유지한다.

Windows가 아닌 배포 준비 PC에서 publish 가능 여부만 확인해야 할 때는 `-EnableWindowsTargeting` 옵션을 추가할 수 있다. 다만 최종 MSI 설치와 실행 검증은 Windows PC에서 수행한다.

### WebView2 Runtime 점검

FlowNote WPF는 문서 미리보기와 뷰어에 WebView2를 사용한다. MSI에는 `Microsoft.Web.WebView2.*.dll`과 `WebView2Loader.dll` 같은 앱 의존 DLL만 포함하고, Microsoft Edge WebView2 Evergreen Runtime 자체는 현장 PC에 별도로 설치되어 있어야 한다.

설치 대상 PC에서는 다음 중 하나로 WebView2 Runtime 설치 여부를 확인한다.

```powershell
Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\*" |
  Where-Object { $_.name -like "*WebView2*" } |
  Select-Object name, pv
```

또는 Windows 제어판의 프로그램 목록에서 `Microsoft Edge WebView2 Runtime`을 확인한다. 설치되어 있지 않으면 Microsoft의 Evergreen Standalone Installer를 현장 배포 파일에 포함해 관리자 권한으로 먼저 설치한다.

WebView2 Runtime이 없거나 손상된 PC에서 FlowNote가 문서 미리보기 또는 뷰어 초기화에 실패하면 사용자 안내는 다음 기준으로 통일한다.

```text
문서 뷰어를 시작할 수 없습니다.
Microsoft Edge WebView2 Runtime 설치 상태를 확인한 뒤 FlowNote를 다시 실행하세요.
문제가 계속되면 현장 관리자에게 설치 점검을 요청하세요.
```

장애 기록에는 PC명, Windows 버전, WebView2 Runtime 설치 여부와 버전, FlowNote MSI 버전, 실행 사용자, 발생 시각을 남긴다.

### 코드 서명과 Windows 경고

운영 배포 MSI와 실행 파일은 코드 서명 인증서로 서명하는 것을 기준으로 한다. 서명은 Windows SDK의 `signtool.exe`를 사용하며, 인증서는 조직 명의의 코드 서명 인증서 또는 현장 내부 CA에서 배포 PC와 설치 PC가 신뢰하는 인증서여야 한다.

서명 순서는 다음 기준을 따른다.

1. `dotnet publish` 후 publish 폴더의 `FlowNote.Windows.App.exe`를 서명한다.
2. 서명된 EXE가 포함되도록 WiX로 MSI를 생성한다.
3. 최종 MSI 파일을 서명한다.
4. `signtool verify /pa`로 EXE와 MSI 서명을 검증한다.
5. 타임스탬프 URL을 사용해 인증서 만료 후에도 서명 시점을 검증할 수 있게 한다.

예시:

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름" `
  -TimestampUrl "http://timestamp.digicert.com"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

인증서 표시 이름 대신 지문으로 지정해야 하면 `-SigningCertificateThumbprint <인증서 SHA1 지문>`을 사용한다. 스크립트 밖에서 수동 서명할 경우 최종 MSI만 서명하면 MSI 안에 포함된 EXE는 미서명 상태로 남을 수 있으므로, EXE 서명 후 MSI를 다시 생성하고 최종 MSI를 서명한다.

미서명 MSI를 현장에 임시 배포해야 하는 경우에는 다음 조건을 모두 만족해야 한다.

- 배포 목적, 배포 대상 PC, MSI 해시, 승인자를 운영 기록에 남긴다.
- 설치 담당자가 Windows SmartScreen 또는 게시자 알 수 없음 경고가 코드 서명 부재 때문임을 사전에 알고 있어야 한다.
- MSI는 내부 공유 위치 또는 이동식 매체에서 무단 교체되지 않도록 해시로 확인한다.
- 외부 고객 운영 배포에는 미서명 MSI를 기본 방식으로 사용하지 않는다.

2. 설치 대상 PC에서 MSI를 관리자 권한으로 설치한다.

```powershell
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

설치 대상 PC에 맞는 .NET Windows Desktop Runtime이 없으면 위 기준에 따라 self-contained MSI를 사용한다. WebView2 Runtime은 문서 미리보기와 뷰어 동작 확인 대상이므로 설치 전 점검에 포함한다.

3. WPF 로컬 데이터 폴더를 만들거나 앱 최초 실행이 만들도록 둔다. 운영 기준 경로는 명시적으로 먼저 만드는 것을 권장한다.

```powershell
New-Item -ItemType Directory -Force C:\FlowNote\LocalData
New-Item -ItemType Directory -Force C:\FlowNote\LocalData\Files
```

4. 환경 변수를 설정한다. 운영 PC에서 지속 적용하려면 시스템 환경 변수로 등록한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
setx FLOWNOTE_API_BASE_URL "http://<서버IP>:5184" /M
setx FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS "300" /M
```

환경 변수 변경 후 이미 열려 있던 PowerShell, 서비스, WPF 앱은 새 값을 읽지 못할 수 있으므로 새 세션에서 실행한다. `FLOWNOTE_LOCAL_DATABASE_PATH`는 특정 DB 파일 경로를 강제로 지정해야 할 때만 사용하며, 일반 운영에서는 `FLOWNOTE_LOCAL_DATA_DIR`만 둔다.

5. PC별 실행 스크립트로만 적용해야 하는 경우에는 시스템 환경 변수 대신 실행 직전에 프로세스 환경 변수를 둔다.

```powershell
$env:FLOWNOTE_LOCAL_DATA_DIR = "C:\FlowNote\LocalData"
$env:FLOWNOTE_API_BASE_URL = "http://<서버IP>:5184"
$env:FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS = "300"
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"
```

6. WPF 앱을 실행해 `C:\FlowNote\LocalData\flownote.local.sqlite`와 `C:\FlowNote\LocalData\Files`가 생성되는지 확인한 뒤 서버 로그인, 문서 목록 조회, 문서 열람, FieldComment 등록을 확인한다.

7. 설치 후 자동 점검 스크립트를 실행한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"
```

self-contained MSI를 설치한 PC는 `-SelfContained`를 추가한다. 코드 서명 인증서로 EXE와 MSI를 서명한 배포 PC에서는 `-CheckSignature`도 함께 사용한다.

## 운영 환경 변수

운영에서는 상대 경로보다 절대 경로를 사용한다. 환경 변수는 Windows 시스템 환경 변수, 서비스 계정 환경 변수, 실행 스크립트, 또는 Git에 포함하지 않는 `.env`에 둔다.

| 구분 | 변수 | 운영 기준 |
| --- | --- | --- |
| 서버 | `FLOWNOTE_DATABASE_URL` | `sqlite:///C:/FlowNote/Server/data/flownote.sqlite3` |
| 서버 | `FLOWNOTE_STORAGE_ROOT` | `C:\FlowNote\Server\storage` |
| 서버 | `FLOWNOTE_ACCESS_TOKEN_SECRET` | 현장별 긴 비밀값. 기본값 사용 금지 |
| 서버 | `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES` | 기본 480분. 현장 보안 정책에 따라 조정 |
| 서버 | `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS` | 기본 14일. 현장 보안 정책에 따라 조정 |
| 서버 | `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES` | 기본 20971520 바이트 |
| WPF | `FLOWNOTE_LOCAL_DATA_DIR` | `C:\FlowNote\LocalData`처럼 DB와 `Files\`를 함께 둘 폴더 |
| WPF | `FLOWNOTE_LOCAL_DATABASE_PATH` | 특정 DB 파일을 직접 지정할 때만 사용. 지정 시 `FLOWNOTE_LOCAL_DATA_DIR`보다 DB 경로 우선 |
| WPF | `FLOWNOTE_API_BASE_URL` | 서버 PC 주소. 예: `http://192.168.0.10:5184` |
| WPF | `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` | 문서 뷰어 자동 닫힘 시간. 5초-3600초로 정규화 |

`FLOWNOTE_LOCAL_DATABASE_PATH`를 지정하면 WPF DB 파일 위치가 그 값으로 고정된다. 다만 로컬 파일 저장 위치는 `FLOWNOTE_LOCAL_DATA_DIR` 기준으로 관리하는 편이 운영자가 백업 대상을 이해하기 쉽다. 운영에서는 특별한 이유가 없으면 `FLOWNOTE_LOCAL_DATA_DIR`만 지정한다.

## 운영 설치 전 점검

### 서버

- 서버 PC 고정 IP 또는 고정 호스트명을 확정한다.
- Python 3.11 이상 설치 여부를 확인한다.
- `C:\FlowNote\Server\api`, `data`, `storage`, `logs` 폴더가 있고 서버 실행 계정에 읽기/쓰기 권한이 있는지 확인한다.
- `C:\FlowNote\Server\.env`에 운영 DB 경로, storage 경로, 토큰 비밀값이 들어 있고 기본 개발 비밀값이 남아 있지 않은지 확인한다.
- Windows 방화벽에서 클라이언트 PC가 접근할 포트 `5184`만 허용한다.
- 실제 고객 파일, 운영 DB, 운영 비밀값을 Git 저장소 또는 배포 준비 폴더에 섞어 두지 않는다.

### 클라이언트

- .NET Windows Desktop Runtime과 WebView2 Runtime 설치 여부를 확인한다.
- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에 WPF 실행 파일, .NET 실행 메타데이터, 의존 DLL이 있는지 확인한다.
- `C:\FlowNote\LocalData`와 `C:\FlowNote\LocalData\Files`를 만들고 앱 실행 사용자에게 읽기/쓰기 권한을 부여한다.
- `FLOWNOTE_LOCAL_DATA_DIR`, `FLOWNOTE_API_BASE_URL`, `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` 설정 방식을 시스템 환경 변수 또는 실행 스크립트 중 하나로 정한다.
- 서버 PC의 `/api/v1/health`, `/api/v1/health/db`를 클라이언트 PC에서 호출할 수 있는지 확인한다.

### 백업

- 서버 SQLite, WAL/SHM 파일, `storage`, `.env`, 로그를 같은 백업 세트로 묶는 기준을 정한다.
- WPF 로컬 SQLite, WAL/SHM 파일, `Files`를 PC별 백업 대상으로 분리한다.
- 백업 저장소 접근권한을 운영자에게만 제한한다.
- 백업 전 서버와 WPF 앱을 종료할 수 있는 시간대를 정한다.

### 복구

- 복구 시 서버 DB와 `storage`는 같은 시점의 백업본을 사용한다.
- 새 서버 PC 경로가 다르면 `.env`의 절대 경로를 먼저 수정한다.
- 서버 복구 후 WPF를 실행하기 전에 `/api/v1/health/db`를 먼저 확인한다.
- WPF 로컬 데이터 복구는 DB와 `Files`를 같은 시점으로 맞춘다.

## 운영 설치 후 점검

### 서버

- 작업 스케줄러의 `\FlowNote\FlowNoteApi` 작업이 실행 중인지 확인한다.
- `http://127.0.0.1:5184/api/v1/health`가 서버 PC에서 성공하는지 확인한다.
- `http://127.0.0.1:5184/api/v1/health/db`가 서버 PC에서 성공하는지 확인한다.
- `http://<서버IP>:5184/api/v1/health`와 `http://<서버IP>:5184/api/v1/health/db`가 클라이언트 PC에서 성공하는지 확인한다.
- `C:\FlowNote\Server\data\flownote.sqlite3`가 생성되었고 서버 실행 계정이 계속 쓸 수 있는지 확인한다.
- `C:\FlowNote\Server\storage`에 테스트 문서 등록 시 파일이 저장되는지 확인한다.
- `C:\FlowNote\Server\logs`에 실행 로그 또는 오류 로그가 남는지 확인한다.
- 최초 서버 관리자 `admin`의 기본 비밀번호 `1234`를 현장 비밀번호로 변경한다.
- WPF 첫 서버 로그인 전에 서버 관리자 비밀번호 변경 완료 여부와 확인자를 운영 기록에 남긴다.
- 기본 비밀번호 `1234`로 서버 로그인이 401로 실패하고, WPF가 같은 ID의 로컬 계정으로 우회해 성공하지 않는지 확인한다.
- 비활성 서버 계정 로그인이 403으로 실패하고, WPF가 로컬 계정으로 우회하지 않는지 확인한다.

### 클라이언트

- WPF 로그인 화면에서 서버 계정으로 로그인한다.
- 서버 계정 로그인 실패가 명확한 401 또는 403이면 로컬 계정으로 자동 전환되지 않는지 확인한다.
- 같은 로그인 ID가 로컬 SQLite에도 있을 때 서버 로그인 성공 후 화면 버튼 권한이 서버 응답 role 기준으로 계산되는지 확인한다.
- 사용자 관리 화면의 창 제목, 목록, 상세 안내가 로컬 SQLite 계정 전용임을 표시하는지 확인한다.
- 문서 목록이 열리고 서버에 등록된 문서가 조회되는지 확인한다.
- 문서를 열어 뷰어가 표시되고 다운로드 차단 정책과 열람 로그가 동작하는지 확인한다.
- WebView2 Runtime 미설치 또는 손상 환경에서는 `문서 뷰어를 시작할 수 없습니다.` 안내가 표시되는지 확인하고, WebView2 Runtime 설치 후 같은 문서가 정상 열람되는지 기록한다.
- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` 기준으로 뷰어 자동 닫힘이 동작하는지 확인한다.
- FieldComment를 등록하고 서버 목록 또는 문서별 FieldComment 조회에서 확인한다.
- 서버 호출 실패 시 로컬 저장이 유지되고 동기화 이력이 남는지 장애 테스트에서 별도로 확인한다.

### 백업

- 설치 직후 기준 백업본을 만든다.
- 백업본에 `C:\FlowNote\Server\data`, `C:\FlowNote\Server\storage`, `C:\FlowNote\Server\.env`, `C:\FlowNote\Server\logs`가 포함되었는지 확인한다.
- WPF를 설치한 PC별로 `C:\FlowNote\LocalData\flownote.local.sqlite`와 `C:\FlowNote\LocalData\Files`가 포함되었는지 확인한다.
- 백업본에 실제 비밀값이 포함되므로 백업 저장소 권한을 확인한다.

### 복구

- 별도 복구 연습 PC 또는 운영자가 지정한 임시 폴더에 서버 `data`와 `storage`를 함께 복원해본다.
- `.env` 경로를 복구 위치에 맞춘 뒤 `/api/v1/health/db`가 성공하는지 확인한다.
- WPF 로컬 DB와 `Files`를 같은 시점으로 복원하고 최근 문서 열람 로그와 최근 FieldComment가 조회되는지 확인한다.
- 복구 테스트 산출물은 로컬 보존 대상이며 사용자가 명시적으로 지시하지 않는 한 삭제하지 않는다.

## 테스트 환경 변수

테스트와 스모크 테스트는 운영 데이터와 분리하되, 생성된 테스트 기록은 삭제하지 않는다.

| 구분 | 변수 | 테스트 기준 |
| --- | --- | --- |
| FastAPI pytest | `FLOWNOTE_TEST_DATABASE_URL` | 테스트 코드의 전용 SQLite URL. 기본값은 `sqlite:///./data/flownote.test.sqlite3` |
| FastAPI pytest | `FLOWNOTE_DATABASE_URL` | 일반 개발 실행 기본값은 `sqlite:///./data/flownote.sqlite3` |
| FastAPI pytest | `FLOWNOTE_STORAGE_ROOT` | 일반 개발 실행 기본값은 `./storage`; 테스트별 하위 폴더 사용 |
| WPF 개발/스모크 | `FLOWNOTE_LOCAL_DATA_DIR` | 지정하지 않으면 저장소 루트 `data/local` 자동 사용 |
| WPF 개발/스모크 | `FLOWNOTE_LOCAL_DATABASE_PATH` | 지정하지 않으면 `data/local/flownote.local.sqlite` 자동 사용 |
| WPF 서버 연동 스모크 | `FLOWNOTE_API_BASE_URL` | 지정하지 않으면 `http://127.0.0.1:5184` 로컬 서버가 실행 중일 때 서버 연동 블록 검증 |

Windows 앱과 Windows 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 함께 사용한다. 매 테스트마다 임시 SQLite를 새로 만들지 않고 누적된 로컬 DB를 기능 검증의 근거로 사용한다.

## 현재 개발 실행

FastAPI:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

Windows WPF:

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
```

WPF에서 서버를 사용하려면 `FLOWNOTE_API_BASE_URL`을 설정한다.

## 운영 백업 점검표

운영 백업은 서버 기준 세트와 WPF PC별 세트를 분리한다. 서버 SQLite와 서버 `storage\`는 서로를 참조하므로 같은 백업 시각의 한 세트로 묶는다. WPF 로컬 SQLite와 WPF `Files\`도 PC별 같은 시각의 한 세트로 묶는다.

### 백업 세트

| 세트 | 필수 포함 대상 | 확인 기준 |
| --- | --- | --- |
| 서버 데이터 세트 | `C:\FlowNote\Server\data\flownote.sqlite3`, 같은 폴더의 `*.sqlite3-wal`, `*.sqlite3-shm`, `*.sqlite-wal`, `*.sqlite-shm` | SQLite 본파일과 WAL/SHM 보조 파일을 같은 시각에 확보한다. |
| 서버 파일 세트 | `C:\FlowNote\Server\storage\` 전체 | 문서 원본, FieldComment 첨부, 보고서 생성 파일이 누락되지 않아야 한다. |
| 서버 운영 세트 | `C:\FlowNote\Server\.env`, 서비스/작업 스케줄러 환경 변수 기록, `C:\FlowNote\Server\logs\` | 비밀값이 포함되므로 백업 저장소 접근권한을 운영 관리자에게 제한한다. |
| WPF PC별 데이터 세트 | `C:\FlowNote\LocalData\flownote.local.sqlite`, 같은 폴더의 `*.sqlite-wal`, `*.sqlite-shm` | PC별 로컬 로그인, 열람 로그, 동기화 큐, 로컬 작업 이력이 포함되어야 한다. |
| WPF PC별 파일 세트 | `C:\FlowNote\LocalData\Files\` 전체 | 로컬 복사 문서와 FieldComment 첨부가 DB와 같은 시각이어야 한다. |

### 백업 실행 전

- 서버 PC의 작업 스케줄러 `\FlowNote\FlowNoteApi`를 중지하거나 파일 잠금이 없는 운영 시간대를 선택한다.
- WPF 앱을 설치한 PC별로 앱을 종료한다.
- 백업 저장소가 운영 DB, 고객 파일, 비밀값을 저장할 수 있는 접근권한과 암호화 정책을 갖췄는지 확인한다.
- 백업 폴더명에는 백업 시각, 서버명 또는 PC명, 대상 세트명을 남긴다. 예: `2026-07-02_2300_Server_data_storage`.

### 백업 실행 후

- 서버 세트에 `data`, `storage`, `.env`, `logs`가 모두 포함되었는지 확인한다.
- WPF PC별 세트에 `flownote.local.sqlite`와 `Files\`가 모두 포함되었는지 확인한다.
- 백업 로그 또는 운영 기록에 백업 시각, 수행자, 대상 PC, 포함 세트, 실패 항목을 남긴다.
- 백업 검증용 임시 복원은 테스트 산출물이므로 사용자가 명시적으로 지시하지 않는 한 삭제하지 않는다.

## 운영 복구 점검표

복구는 서버를 먼저 살리고, 그 다음 WPF 로컬 데이터를 맞춘다. 서버 DB와 서버 `storage\`는 같은 시점의 백업을 우선 사용한다. 다른 시점의 부분 복원은 장애 대응 절차로만 수행하고 정상 복구로 간주하지 않는다.

### 서버 복구 순서

1. 서버 작업 스케줄러 `\FlowNote\FlowNoteApi`를 중지하고 WPF 앱을 종료한다.
2. `C:\FlowNote\Server\data`를 백업본의 서버 데이터 세트로 복원한다.
3. `C:\FlowNote\Server\storage`를 같은 시점의 서버 파일 세트로 복원한다.
4. `.env` 또는 서비스 환경 변수를 복원한다. 새 서버 PC의 절대 경로가 다르면 `FLOWNOTE_DATABASE_URL`과 `FLOWNOTE_STORAGE_ROOT`를 먼저 수정한다.
5. 서버 작업을 시작한 뒤 서버 PC에서 `http://127.0.0.1:5184/api/v1/health`와 `http://127.0.0.1:5184/api/v1/health/db`를 확인한다.
6. WPF 실행 전 서버 계정 로그인이 가능한지 확인한다.

### WPF 복구 순서

1. 대상 PC의 WPF 앱을 종료한다.
2. `C:\FlowNote\LocalData\flownote.local.sqlite`와 WAL/SHM 파일을 PC별 데이터 세트로 복원한다.
3. `C:\FlowNote\LocalData\Files\`를 같은 시점의 PC별 파일 세트로 복원한다.
4. `FLOWNOTE_LOCAL_DATA_DIR`, `FLOWNOTE_LOCAL_DATABASE_PATH`, `FLOWNOTE_API_BASE_URL` 값이 복구 위치와 맞는지 확인한다.
5. WPF 앱을 실행해 로그인, 문서 목록, 문서 열람, FieldComment 등록/조회, 보고서 근거 조회를 확인한다.
6. 복구 후 저장소 루트에서 `.\scripts\verify-preserved-tests.ps1` 또는 운영자가 지정한 동등 점검을 실행한다. 운영 환경에서 전체 개발 테스트를 실행할 수 없으면 최소한 서버 health, DB health, WPF 로그인, 문서 목록, 문서 열람, FieldComment, 보고서 근거 조회를 수동 점검표로 남긴다.

### 부분 복원 장애 대응

| 상황 | 증상 | 대응 기준 |
| --- | --- | --- |
| 서버 DB만 복원하고 `storage\`가 누락됨 | 문서 목록과 메타데이터는 보이지만 파일 열람, 첨부 다운로드, 보고서 파일 접근이 실패한다. | 정상 운영 재개 금지. 같은 시점의 `storage\` 백업을 찾아 재복원한다. 없으면 누락 파일 목록을 장애 기록으로 남기고 해당 문서/첨부/보고서의 열람을 제한한 뒤 재등록 또는 파일 재수집 계획을 세운다. |
| 서버 `storage\`만 복원하고 DB가 누락됨 | 파일은 디스크에 있으나 문서 소유 관계, 버전, 공개 상태, FieldComment 첨부 연결, 보고서 근거를 추적할 수 없다. | 정상 운영 재개 금지. 같은 시점의 서버 DB 백업을 찾아 재복원한다. 없으면 파일을 원천 증거로 보존하고 새 DB에 수동 재등록할 대상을 운영자가 선별한다. 기존 파일을 임의 삭제하거나 덮어쓰지 않는다. |
| 서버 DB와 `storage\` 시점이 다름 | 일부 문서 버전 또는 첨부만 열리지 않거나 DB에 없는 파일이 남는다. | 최신 세트 하나로 다시 맞춘다. 불가피하면 DB 기준으로 누락 파일과 고아 파일 목록을 작성하고, 누락 항목은 열람 제한, 고아 파일은 보존 폴더로 격리한다. |
| WPF DB만 복원하고 `Files\`가 누락됨 | 로컬 문서 목록, 열람 로그, 동기화 큐는 있으나 로컬 파일 미리보기와 첨부 열람이 실패한다. | 같은 시점의 `Files\`를 재복원한다. 서버에 이미 동기화된 문서는 서버 열람으로 대체할 수 있지만, 로컬 미동기화 파일은 재수집 전까지 보존 장애로 기록한다. |
| WPF `Files\`만 복원하고 DB가 누락됨 | 파일은 있으나 로컬 문서, 첨부, 큐, 열람 이력과 연결되지 않는다. | 같은 시점의 WPF DB를 재복원한다. DB가 없으면 파일은 삭제하지 않고 운영자가 서버 등록 여부와 로컬 재등록 필요 여부를 판단한다. |

## 장애 시 보존 파일

장애 분석 전에는 다음 파일과 폴더를 삭제하지 않는다.

- 서버 SQLite와 WAL/SHM 파일
- 서버 `storage\` 전체
- 서버 로그와 실행 콘솔 출력
- WPF `flownote.local.sqlite`와 WAL/SHM 파일
- WPF `Files\` 전체
- WPF WebView2/앱 로그가 생성된 경우 해당 로그
- 스모크 테스트 로그, 테스트 등록 메모, 렌더링 결과, 테스트 입력/출력 파일

## 커밋 제외와 보존 관계

Git 제외와 로컬 보존은 다른 기준이다. 실제 고객 문서, 운영 DB, 운영 파일 저장소, 비밀값, 개인 로컬 경로, 빌드/배포 산출물은 Git에 올리지 않는다. 그러나 테스트 SQLite, 테스트 파일, 테스트 로그, 스모크 테스트 산출물, 렌더링 결과는 기능 검증 이력이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 로컬에서 삭제하지 않는다.

현재 `.gitignore`는 빌드 산출물, 로그, 일반 SQLite, 운영/고객 파일, 로컬 파일 저장소를 제외하되 `data/local/**/*.sqlite`와 `services/api/data/**/*.sqlite`는 테스트와 개발 검증 DB로 추적될 수 있게 예외를 둔다. 커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 제외한 PDF, 이미지, Excel, TXT, 렌더링 결과, 테스트 로그, `data/local/Files/`, `Data/Files/` 하위 파일이 포함되지 않았는지 확인한다.

## 후속 배포 과제

- HTTPS 또는 사내망 접속 보호
- 현장별 .NET/WebView2 설치 조합에서 self-contained MSI 실기 검증
- 현장별 코드 서명 인증서 발급, 갱신, 폐기 운영 절차
- 서버 계정 관리 UI와 관리자 세션 폐기 UI
- PostgreSQL 전환 조건

## 검증 자동화

표준 검증 순서와 사후 Git 산출물 점검은 [검증 자동화 문서](./verification.md)를 따른다. 저장소 루트에서 `.\scripts\verify-preserved-tests.ps1`을 실행하면 FastAPI pytest 53개 수집/실행, WPF build, WPF smoke, `.gitignore` 산출물 제외 규칙, 실행 전후 `git status` 금지 패턴을 함께 확인한다.
