# FlowNote 배포

## 기준

FlowNote의 기본 배포 형태는 사내 단일 서버 PC 운영과 Windows WPF 설치형 클라이언트 배포이다. 클라우드, 외부 접근, 일반 브라우저 직접 사용은 초기 기준이 아니며 별도 협의가 필요한 후속 선택지다.

```text
Server PC
  -> FastAPI server
  -> SQLite DB
  -> local storage/ folder

Client PCs
  -> Windows WPF installed app
  -> local SQLite DB and local Files/ folder
  -> API connection to Server PC when FLOWNOTE_API_BASE_URL is set
```

WPF 앱은 로컬 SQLite에 먼저 기록하고 서버 URL이 설정되어 있으면 서버 동기화를 시도한다. 서버 호출 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다.

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
    FlowNote.Windows.App\ WPF 앱 실행 파일과 의존 DLL
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
| `C:\Program Files\FlowNote\Client\FlowNote.Windows.App` | MSI가 설치한 WPF 실행 파일과 의존 DLL | WPF 로컬 DB, 실제 현장 문서 데이터 |
| `C:\FlowNote\LocalData` | WPF 로컬 SQLite, `Files\` | 서버 SQLite, 서버 `storage` |

현재 저장소 기준으로 서버는 별도 압축 패키지 없이 `services/api/app`과 `pyproject.toml`을 `C:\FlowNote\Server\api`에 복사하고 해당 폴더에서 운영 `.venv`를 만든다. WPF 클라이언트는 MSI로 고정해 설치하며 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`, 로컬 데이터 위치는 `FLOWNOTE_LOCAL_DATA_DIR`로 분리한다.

## 배포 방식 결정

- WPF 앱은 MSI를 기준 패키징 방식으로 사용한다. MSIX는 서명, 패키지 아이덴티티, 앱 컨테이너 제약을 현장별로 더 검토해야 하므로 초기 운영 배포 기준에서 제외한다.
- MSI는 앱 실행 파일과 의존 DLL만 설치한다. 로컬 SQLite와 `Files\`는 설치 폴더 아래에 두지 않고 `FLOWNOTE_LOCAL_DATA_DIR`가 가리키는 폴더에 둔다.
- FastAPI 서버는 Windows 작업 스케줄러의 부팅 시 자동 실행 작업으로 등록한다. Python/FastAPI 프로세스를 Windows 서비스로 직접 등록하려면 별도 서비스 래퍼가 필요하므로, 초기 기준은 Windows 기본 기능만 사용하는 작업 스케줄러 방식으로 고정한다.
- 서버 작업 이름은 기본 `\FlowNote\FlowNoteApi`다. 실행 래퍼는 `C:\FlowNote\Server\scripts\run-flownote-server.ps1`, 로그는 `C:\FlowNote\Server\logs`에 둔다.

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

등록 스크립트는 `run-flownote-server.ps1`을 `C:\FlowNote\Server\scripts`로 복사하고, `C:\FlowNote\Server\.env`를 프로세스 환경변수로 읽은 뒤 `C:\FlowNote\Server\api`에서 uvicorn을 실행한다. `.env`에 값이 없으면 `FLOWNOTE_API_HOST=0.0.0.0`, `FLOWNOTE_API_PORT=5184`, `FLOWNOTE_DATABASE_URL=sqlite:///C:/FlowNote/Server/data/flownote.sqlite3`, `FLOWNOTE_STORAGE_ROOT=C:\FlowNote\Server\storage`를 기본값으로 둔다.

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

## WPF 설치 절차

WPF 앱은 MSI로 Windows PC에 설치한다. 기본 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`이며, 서버 PC에 관리자용 앱을 함께 설치할 때도 로컬 데이터는 별도 `C:\FlowNote\LocalData`에 둔다.

1. 배포 준비 PC에서 WPF MSI 산출물을 만든다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
```

MSI 패키징은 WiX Toolset CLI를 사용한다. 배포 준비 PC에 `wix` 명령이 없으면 먼저 `dotnet tool install --global wix`로 설치한다. 스크립트는 `dotnet publish` 결과와 WiX 중간 파일, MSI를 `artifacts\wpf-msi` 아래에 만들며 이 경로는 Git 제외 대상이다.

2. 설치 대상 PC에서 MSI를 관리자 권한으로 설치한다.

```powershell
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

설치 대상 PC에 맞는 .NET Windows Desktop Runtime이 없으면 추후 self-contained MSI를 별도 패키징한다. WebView2 Runtime은 문서 미리보기와 뷰어 동작 확인 대상이므로 설치 전 점검에 포함한다.

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
- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에 WPF 실행 파일과 의존 DLL이 있는지 확인한다.
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
- 최초 운영 계정의 기본 비밀번호를 현장 비밀번호로 변경한다.

### 클라이언트

- WPF 로그인 화면에서 서버 계정으로 로그인한다.
- 문서 목록이 열리고 서버에 등록된 문서가 조회되는지 확인한다.
- 문서를 열어 뷰어가 표시되고 다운로드 차단 정책과 열람 로그가 동작하는지 확인한다.
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
| WPF 서버 연동 스모크 | `FLOWNOTE_API_BASE_URL` | 서버 연동 블록을 검증할 때만 설정 |

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

## 백업 대상

운영 백업은 서버 데이터와 로컬 앱 데이터를 분리해서 수행한다. 백업 전에는 가능하면 서버와 WPF 앱을 종료하거나 파일 잠금이 없는 시간대에 복사한다.

- 서버 SQLite: `C:\FlowNote\Server\data\flownote.sqlite3`
- 서버 SQLite 보조 파일: 같은 폴더의 `*.sqlite3-wal`, `*.sqlite3-shm`, `*.sqlite-wal`, `*.sqlite-shm`
- 서버 파일 저장소: `C:\FlowNote\Server\storage\`
- 서버 운영 설정: `.env` 또는 서비스 환경 변수 내역. 비밀값은 백업 저장소 접근권한을 제한한다.
- 서버 로그: `C:\FlowNote\Server\logs\`
- WPF 공통 SQLite: `C:\FlowNote\LocalData\flownote.local.sqlite`
- WPF SQLite 보조 파일: 같은 폴더의 `*.sqlite-wal`, `*.sqlite-shm`
- WPF 로컬 파일: `C:\FlowNote\LocalData\Files\`

## 복구 순서

- 서버와 WPF 앱을 종료한다.
- 서버 `data`와 `storage`를 같은 시점의 백업본으로 복원한다.
- `.env` 또는 서비스 환경 변수를 복원하되, 새 서버 PC의 절대 경로가 다르면 경로 값을 수정한다.
- WPF 로컬 DB와 `Files\`를 같은 시점의 백업본으로 복원한다.
- 서버를 먼저 실행하고 `/api/v1/health/db`를 확인한다.
- WPF 앱을 실행해 로그인, 문서 목록, 최근 FieldComment, 문서 열람 로그를 확인한다.

서버 DB만 복원하고 `storage\`를 누락하면 문서 메타데이터는 있으나 파일을 열 수 없다. 반대로 `storage\`만 복원하고 DB를 누락하면 파일 소유 관계와 버전 이력을 추적할 수 없다. 두 대상은 같은 백업 세트로 관리한다.

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
- 운영 관리자 계정 발급과 최초 비밀번호 변경 절차
- PostgreSQL 전환 조건

## 검증 자동화

표준 검증 순서와 사후 Git 산출물 점검은 [검증 자동화 문서](./verification.md)를 따른다. 저장소 루트에서 `.\scripts\verify-preserved-tests.ps1`을 실행하면 FastAPI pytest 43개 수집/실행, WPF build, WPF smoke, `.gitignore` 산출물 제외 규칙, 실행 전후 `git status` 금지 패턴을 함께 확인한다.
