# FlowNote 배포

이 문서는 2026-07-21 현재 저장소의 실행 코드와 배포 스크립트 기준이다. 서명, MDM, 현장 인증서처럼 실제 운영 환경에서만 확정 가능한 내용은 후속 점검 항목으로 구분한다.

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
  -> published document metadata, FieldComment, photos, handover receipts, channel notifications
  -> API connection to Server PC through configured server URL
```

WPF 앱은 문서·FieldComment·첨부·접근 로그·보고서 원천을 로컬 SQLite에 먼저 기록하고 서버 URL이 설정되어 있으면 서버 동기화를 시도한다. 이 도메인의 서버 호출 실패는 로컬 저장을 되돌리지 않고 동기화 큐와 이력으로 남긴다. 작업순서는 예외로 FastAPI snapshot을 권위 원천으로 직접 사용하고 로컬 큐에 넣지 않으며, 서버 미연결·조회 실패에서는 확정 변경을 차단한다.

Android 앱은 현장 입력과 알림 확인을 서버 기준으로 처리한다. 네트워크가 불안정할 때 FieldComment와 사진 첨부만 Keystore AES-GCM 보호 outbox에 임시 저장하며, 채널 메시지·인수인계·문서 메타데이터는 outbox 대상이 아니다. 장기 원천 데이터는 서버 SQLite와 `storage/`에 남긴다. 개인 휴대폰은 제외하고 MDM 등록 승인 단말만 배포하며, 채널 알림은 로그인 동안 15초 foreground service가 사내 HTTPS polling으로 복구한다.

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

현재 저장소 기준으로 서버는 별도 압축 패키지 없이 `services/api/app`과 `pyproject.toml`을 `C:\FlowNote\Server\api`에 복사하고 해당 폴더에서 운영 `.venv`를 만든다. WPF 클라이언트는 MSI로 고정해 설치하며 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`, 로컬 데이터 위치는 `FLOWNOTE_LOCAL_DATA_DIR`로 분리한다. Android 개발 APK는 `./gradlew assembleDebug`, 운영 후보는 조직 키 환경변수를 주입한 `./gradlew assembleRelease`로 만든다. 운영 기본 산출물은 MDM/사내 배포용 APK이고 AAB는 관리형 스토어 채택 시에만 선택한다.

## 배포 방식 결정

- WPF 앱은 MSI를 기준 패키징 방식으로 사용한다. MSIX는 서명, 패키지 아이덴티티, 앱 컨테이너 제약을 현장별로 더 검토해야 하므로 초기 운영 배포 기준에서 제외한다.
- MSI는 WPF 실행에 필요한 앱 파일만 설치한다. 로컬 SQLite와 `Files\`는 설치 폴더 아래에 두지 않고 `FLOWNOTE_LOCAL_DATA_DIR`가 가리키는 폴더에 둔다.
- Android 앱은 MDM 앱 allowlist와 조직 키로 서명한 사내 APK를 승인된 현장 단말에 배포한다. 개인 휴대폰 기본 배포와 일반 웹 브라우저 접속은 기준이 아니다.
- WPF는 창 활성 중, Android는 로그인 동안 foreground service로 사내망 HTTPS를 15초 polling한다. Android는 서버 주소+사용자 scope별 cursor를 각 표시 뒤 보존하고 재부팅·단절 뒤 이어간다. access 401은 refresh를 1회 시도하고 거부되면 token과 서비스를 폐기한다. 외부 push 의존은 없고 사내 relay push는 후속 선택지다.
- FastAPI 서버는 Windows 작업 스케줄러의 부팅 시 자동 실행 작업으로 등록한다. Python/FastAPI 프로세스를 Windows 서비스로 직접 등록하려면 별도 서비스 래퍼가 필요하므로, 초기 기준은 Windows 기본 기능만 사용하는 작업 스케줄러 방식으로 고정한다.
- 서버 작업 이름은 기본 `\FlowNote\FlowNoteApi`다. 실행 래퍼는 `C:\FlowNote\Server\scripts\run-flownote-server.ps1`, 로그는 `C:\FlowNote\Server\logs`에 둔다.

## Android 운영 배포와 단말 수명주기

운영 서명키는 조직 소유이며 최소 2인 승인으로 오프라인/HSM 또는 승인된 비밀 저장소에 보관한다. keystore, alias 암호와 key 암호는 `FLOWNOTE_ANDROID_KEYSTORE`, `FLOWNOTE_ANDROID_KEY_ALIAS`, `FLOWNOTE_ANDROID_STORE_PASSWORD`, `FLOWNOTE_ANDROID_KEY_PASSWORD` 환경변수로 빌드 프로세스에만 주입한다. 값과 키 파일은 Git·패키지·일반 로그·증거 폴더에 남기지 않는다. `assembleRelease`는 네 값 중 하나라도 없으면 실패한다. 같은 applicationId 업그레이드와 rollback은 동일 서명 인증서만 허용한다.

MDM 기준은 단말 전체 암호화, 6자리 이상 화면 잠금과 짧은 자동 잠금, 개발자 옵션·USB 디버깅·USB 파일 전송·ADB backup 차단, 알 수 없는 출처 차단, 앱 allowlist, 원격 잠금·초기화, 부팅/강제 중지 후 kiosk 재실행이다. FlowNote foreground service와 사내 HTTPS 주소를 배터리/네트워크 정책에서 허용하고 사용자가 서비스 상태 알림 채널을 차단하지 못하게 한다. 정책 준수 보고서가 없는 단말에는 운영 로그인을 발급하지 않는다.

`deviceId`는 MDM 자산 ID와 1:1인 임의 식별자로 중앙 발급하며 사용자 계정, Android ID, serial, MAC 주소를 그대로 쓰지 않는다. 수명주기는 다음과 같다.

1. MDM 등록과 정책 준수 확인 후 관리자가 `ACTIVE` 단말을 등록한다.
2. 수리·일시 회수는 즉시 `INACTIVE`로 바꿔 access/refresh/재로그인을 막고 MDM에서 격리한다.
3. 분실은 발견 즉시 `INACTIVE`, 모든 해당 세션 폐기 확인, MDM 원격 잠금·초기화, 사고 `run_id`와 마지막 접속 시각 보존 순서로 처리한다.
4. 교체는 기존 단말을 `RETIRED`로 만드는 replace API와 새 임의 `deviceId`를 사용한다. 기존 outbox/Keystore 키를 복사하지 않고 미전송 건은 idempotency key와 서버 원천을 대조해 전송·보존·폐기를 승인한다.
5. 폐기 단말은 `RETIRED`에서 재활성화하지 않으며 MDM wipe 증거와 자산 폐기 기록을 연결한다.

서명 APK 생성 뒤 `scripts/verify-android-release.sh <run_id> <apk> data/local/pilot-evidence`로 인증서 지문과 SHA-256을 보존한다. `--install`은 동일 키 신규 설치/업그레이드를, `--rollback <이전.apk>`는 승인된 이전 versionCode 설치를 수행한다. 시나리오 CSV가 없으면 정상, Doze, 5분 단절, 재부팅, 서버 주소 변경, access token 만료, refresh 거부, 강제 중지 뒤 kiosk 재실행의 8개 `NOT_RUN` 행과 측정/허용 시간 열을 만든다. 정확히 한 대의 승인 단말 연결, 현재/이전 APK의 동일 인증서, `PENDING`/`FAILED` outbox 0건, 서버/API·로컬 schema 하위 호환성과 rollback 승인 없이는 실행하지 않는다. 이전 APK는 새 암호화 outbox를 해석하지 못할 수 있으므로 미전송 항목이 있으면 rollback을 중단한다. 운영 패키지와 모든 실행 증거는 Git 제외 상태로 보존한다.

서명키 분실은 기존 설치 앱 업그레이드 불가 사건으로 처리해 outbox 판정, 앱 제거, 새 키/필요 시 새 applicationId 배포와 새 `deviceId` 등록을 수행한다. 키 유출은 해당 인증서 빌드 허용 중단, MDM blocklist, 영향 버전·단말 파악과 승인된 Android 키 업그레이드 또는 새 applicationId 재배포 절차를 따른다.

## Windows MSI 운영 배포 확정 조건

WPF MSI는 Windows 배포 준비 PC와 최소 1대 이상의 설치 대상 Windows PC에서 실기 검증을 통과하기 전까지 운영 배포 확정 상태로 보지 않는다. macOS 또는 비Windows 개발 환경의 publish 성공은 사전 점검일 뿐이며, `wix`, `msiexec`, `signtool`, WebView2 Runtime, .NET Windows Desktop Runtime 조합은 Windows PC에서 별도 확인한다.

2026-07-14 작업 6의 최신 통합 판정은 `대기`다. FastAPI 96건과 SQLite/Git 무결성은 통과했지만 새 WPF 통합 스모크, Android unit/build/실단말, Windows 설치 PC의 HTTPS·인증서·controlled copy가 같은 실행 ID로 아직 통과하지 않았다. 상세 수치와 증거 위치는 [검증 자동화 문서의 작업 6 기준선](./verification.md#2026-07-14-작업-6-통합-사람형-스모크-기준선)을 따른다.

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
FLOWNOTE_CONTROLLED_COPY_MAX_BYTES=524288000
FLOWNOTE_CONTROLLED_COPY_TICKET_EXPIRES_SECONDS=60
FLOWNOTE_ACCESS_TOKEN_SECRET=<현장별 긴 비밀값>
FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES=480
FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS=14
FLOWNOTE_SESSION_COOKIE_NAME=flownote_session
FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false
FLOWNOTE_AI_PROVIDER=UNCONFIGURED
FLOWNOTE_AI_MODEL=UNCONFIGURED
FLOWNOTE_AI_CUSTOMER_SCOPE=DEFAULT
FLOWNOTE_AI_SITE_SCOPE=DEFAULT
FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=DISABLED
FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED=false
FLOWNOTE_AI_RETENTION_SCHEDULER_ENABLED=true
FLOWNOTE_AI_RETENTION_SCHEDULER_INTERVAL_SECONDS=3600
```

AI 항목은 provider adapter 안전장치와 운영 제어면의 scope 설정이다. 운영 `.env`에서는 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`, `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=DISABLED`, `FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED=false`를 유지한다. generic 네트워크 adapter는 `environment=test`와 `NETWORK_TEST`, 명시 시험 scope, HTTPS endpoint, 환경 변수 자격증명을 모두 요구하므로 운영 배포에서 활성화할 수 없다. provider/model/scope 값이나 provider 자격증명 설정 여부는 기능 활성 허가가 아니다. 후보 read model API와 `system-admin` 전용 운영 제어 API는 호출 플래그와 무관하게 동작한다. provider 자격증명은 `FLOWNOTE_AI_<PROVIDER>_API_KEY` 형식의 서버 환경/비밀 저장소에만 두고 DB·문서·클라이언트 설정에 기록하지 않는다.

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

1. 서버 DB 최초 생성 시 FastAPI는 서버 `user_accounts`에 `admin` 계정을 만든다. 이 계정은 최초 서버 관리자 계정이다. 최초 비밀번호 변경 전에는 서버 PC 운영 스크립트를 사용하고, 이후 계정 운영은 서버 로그인한 WPF 사용자 관리 화면을 사용한다.
2. 개발/스모크 테스트용 기본 비밀번호 `1234`는 운영 로그인 전에 반드시 변경한다. 현장 운영자는 서버 PC의 관리자 PowerShell에서 운영 스크립트를 실행해 새 비밀번호를 대화식으로 입력한다. 현재 스크립트는 8자 미만 비밀번호를 거부한다. 새 비밀번호를 명령줄 인자, PowerShell 기록, 서버 로그에 남기지 않는다.

```powershell
cd C:\FlowNote\Server\api
.\.venv\Scripts\python.exe -m app.ops.server_accounts reset-password --username admin
```

스크립트는 기본적으로 `.env` 또는 `FLOWNOTE_DATABASE_URL`의 서버 DB를 사용한다. 운영 DB 위치를 명령에서 명확히 고정해야 하는 경우에는 다음처럼 DB URL만 인자로 넘긴다. 비밀번호 값은 여전히 대화식으로만 입력한다.

```powershell
.\.venv\Scripts\python.exe -m app.ops.server_accounts --database-url sqlite:///C:/FlowNote/Server/data/flownote.sqlite3 reset-password --username admin
```

3. 최초 운영 로그인은 변경된 서버 비밀번호로 WPF에서 수행한다. 초기 `admin`의 스크립트 변경은 `must_change_password`를 설정하지 않으므로 첫 운영 로그인 전에 변경 완료 여부, 변경 수행자, 확인자를 운영 기록에 남긴다. 이후 WPF/API에서 생성하거나 재설정한 임시 비밀번호 계정은 `must_change_password = true`가 되고 로그인 직후 비밀번호 변경 화면으로 이동한다.
4. 변경 완료 후 기본 비밀번호 `1234`로 WPF 서버 로그인이 실패하는지 확인한다. 이 실패가 서버 401이면 WPF가 로컬 `admin / 1234`로 우회해 성공하면 안 된다.

### 서버 계정과 WPF 로컬 계정

- 서버 계정은 서버 DB의 `user_accounts`에서 관리한다. 서버 로그인, 서버 API 권한, 서버 문서 등록자, 서버 FieldComment 작성자, 서버 감사 이력은 서버 계정을 기준으로 남긴다.
- 서버 로그인한 `admin`, `system-admin`이 여는 사용자 관리 화면은 FastAPI 서버 계정 전용이다. 계정 생성, 표시 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·전체 폐기를 제공한다.
- 서버 미연결 로컬 로그인에서 여는 사용자 관리 화면은 로컬 SQLite 전용이다. 화면 제목, 사용자 목록, 상세 문구는 “로컬” 계정임을 표시하며 서버 계정을 만들거나 수정하지 않는다.
- 서버 URL을 쓰는 운영 PC에서는 서버 계정 권한을 우선한다. 같은 로그인 ID의 로컬 계정 role이 다르더라도 서버 로그인 성공 후 화면 권한과 서버 동기화 작성자 기준은 서버 응답의 role과 사용자 ID다.
- 서버 계정 화면에서 서버 연결이 끊기거나 401/403이 발생해도 로컬 계정 화면으로 자동 전환하지 않는다. 연결 또는 권한을 복구한 뒤 다시 로그인한다.

### 서버 계정 발급

일반 서버 계정은 서버 로그인한 `admin`, `system-admin`이 WPF 사용자 관리 화면에서 발급한다. 8자 이상 임시 비밀번호와 발급 사유를 입력하며, 서버는 비밀번호를 응답·활동 이력·일반 로그에 다시 노출하지 않는다. 발급 계정은 `must_change_password = true`이므로 첫 로그인 직후 본인이 비밀번호를 바꾸고 새 비밀번호로 다시 로그인해야 한다. `admin`은 일반 계정만 운영하고 `system-admin` 계정은 `system-admin`만 생성·조회·변경할 수 있다.

서버 PC 운영 스크립트의 `create` 명령은 WPF/API를 사용할 수 없는 초기·비상 경로다. `role` 값은 [데이터 모델 문서의 역할 값](./data-model.md#역할-값) 중 하나만 사용한다. 이 스크립트는 현재 `must_change_password`를 설정하지 않으므로, 일반 운영 계정 발급에는 사용하지 않는다.

```powershell
cd C:\FlowNote\Server\api
.\.venv\Scripts\python.exe -m app.ops.server_accounts create --username line-a-admin --display-name "라인 A 관리자" --role line-foreman
```

비밀번호는 `new password`와 `confirm password` 프롬프트에 대화식으로 입력한다. 현재 스크립트는 8자 미만 비밀번호를 거부한다. 스크립트 출력에는 `username`, 서버 `user_id`, 폐기된 세션 수만 표시되며 비밀번호는 출력하지 않는다.

### 비밀번호 재설정

1. 본인 확인과 승인자를 운영 기록에 남긴다.
2. WPF 서버 계정 화면에서 8자 이상 임시 비밀번호와 재설정 사유를 입력한다.
3. 서버는 `must_change_password = true`로 바꾸고 해당 계정의 기존 활성 `auth_sessions`를 `REVOKED`, `revoked_reason = password_reset`으로 변경한다.
4. 임시 비밀번호는 사용자에게 일회성으로 전달한다. 사용자는 로그인 직후 강제 변경 화면에서 새 비밀번호로 바꾸며, 변경 성공으로 현재 세션까지 폐기된 뒤 새 비밀번호로 다시 로그인한다.

WPF/API를 사용할 수 없는 비상 상황에서는 아래 운영 스크립트를 사용할 수 있다. 스크립트는 세션을 폐기하지만 `must_change_password`를 설정하지 않으므로 비상 승인과 후속 비밀번호 변경 확인을 별도 운영 기록으로 남긴다.

```powershell
.\.venv\Scripts\python.exe -m app.ops.server_accounts reset-password --username line-a-admin
```

잠금 계정을 승인 후 재개하면서 비밀번호까지 바꾸는 경우에는 먼저 상태를 `ACTIVE`로 바꾸고 이어서 비밀번호를 재설정한다. 한 번의 비밀번호 재설정으로 잠금/비활성 계정이 자동 활성화되지 않게 하는 것이 기본 운영 기준이다. 운영 승인 기록이 이미 남아 있고 한 번의 명령으로 처리해야 하는 경우에만 `reset-password --activate`를 사용할 수 있으며, 이 옵션은 비밀번호 재설정과 함께 계정을 `ACTIVE`로 바꾼다.

### 비활성 계정, 퇴사, 권한 변경

- 장기 미사용, 퇴사, 권한 회수 계정은 WPF 서버 계정 화면에서 `DISABLED`로 변경한다. 일시 잠금은 `LOCKED`, 승인된 재개는 `ACTIVE`로 구분하며 변경 사유를 필수로 남긴다.
- role 변경, 잠금·비활성화는 기존 활성 세션을 같은 트랜잭션에서 폐기한다. 자기 자신 잠금/비활성화, 마지막 활성 `system-admin` 제거, 일반 `admin`의 `system-admin` 계정 운영은 서버가 거부한다.
- WPF/API를 사용할 수 없는 비상 상황에서는 아래 `set-status`, `set-role` 스크립트를 사용할 수 있다. WPF 로컬 계정이 별도로 필요한 PC라면 로컬 사용자 관리 화면에서도 같은 사용자의 로컬 권한을 별도로 점검한다.
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
| 서버 | `FLOWNOTE_CONTROLLED_COPY_MAX_BYTES` | controlled copy 한 건의 최대 크기. 기본 524288000 바이트 |
| 서버 | `FLOWNOTE_CONTROLLED_COPY_TICKET_EXPIRES_SECONDS` | 1회성 티켓 만료 시간. 기본 60초, 서버에서 5~300초로 정규화 |
| 서버 | `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED` | 기본 `false`. 현재 운영에서는 `true` 설정 금지 |
| 서버 | `FLOWNOTE_AI_READINESS_GATE_ENABLED` | 기본 `true`. 현재 scope의 근거·승인 질문·회귀 준비도 미달 시 호출 차단 |
| 서버 | `FLOWNOTE_AI_PROVIDER`, `FLOWNOTE_AI_MODEL` | 승인 row 선택에 사용하는 provider/model scope. 기본 `UNCONFIGURED` |
| 서버 | `FLOWNOTE_AI_CUSTOMER_SCOPE`, `FLOWNOTE_AI_SITE_SCOPE` | 외부 전송 승인을 찾는 고객/현장 scope. 기본 `DEFAULT` |
| 서버 | `FLOWNOTE_AI_PROVIDER_EXCERPT_MAX_CHARS` | provider source 한 건의 최대 발췌 길이. 기본 600자 |
| 서버 | `FLOWNOTE_AI_PROVIDER_MAX_SOURCES` | 질의 한 건의 provider 최대 근거 수. 기본 12건 |
| 서버 | `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE` | 기본 `DISABLED`. `FAKE`, `NETWORK_TEST`는 검증 전용이며 운영 provider 설정이 아님 |
| 서버 | `FLOWNOTE_AI_FAKE_SCENARIOS` | fake adapter의 결정적 시험 시나리오. 기본 `SUCCESS` |
| 서버 | `FLOWNOTE_AI_PROVIDER_ENDPOINT` | `NETWORK_TEST` 전용 HTTPS JSON endpoint. 운영 provider 주소로 사용 금지 |
| 서버 | `FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED` | 기본 `false`. `environment=test`와 함께 있어야 `NETWORK_TEST` 생성 허용 |
| 서버 | `FLOWNOTE_AI_NETWORK_TIMEOUT_SECONDS` | 시험 adapter timeout. 기본 30초, 허용 1~120초 |
| 서버 | `FLOWNOTE_AI_PROVIDER_MAX_ATTEMPTS` | 시험 adapter 최대 시도. 기본 3회, 허용 1~5회 |
| 서버 | `FLOWNOTE_AI_PROVIDER_RESPONSE_MAX_BYTES` | provider 응답 상한. 기본 65536바이트, 허용 1024~1048576바이트 |
| 서버 | `FLOWNOTE_AI_RETENTION_SCHEDULER_ENABLED` | 만료 질의 payload 비식별화와 저장 응답 원문 삭제 스케줄러. 기본 `true` |
| 서버 | `FLOWNOTE_AI_RETENTION_SCHEDULER_INTERVAL_SECONDS` | 자동 보존 실행 간격. 기본 3600초, 허용 60~86400초 |
| 서버 | `FLOWNOTE_ANDROID_VIEW_GRANT_EXPIRES_SECONDS` | Android 본문 열람 grant 만료 시간. 기본 60초, 5~300초로 정규화 |
| 서버 | `FLOWNOTE_ANDROID_VIEW_AUTO_CLOSE_SECONDS` | Android 보안 뷰어 무입력 자동 닫힘 시간. 기본 300초 |
| 서버 | `FLOWNOTE_ANDROID_VIEW_MAX_BYTES` | Android 보안 열람 파일 전체 크기 한도. 기본 52428800바이트(50 MiB) |
| 서버 | `FLOWNOTE_ANDROID_VIEW_MAX_TEXT_BYTES` | Android UTF-8 TXT 열람 크기 한도. 기본 5242880바이트(5 MiB) |
| 서버 | `FLOWNOTE_ANDROID_VIEW_MAX_PDF_PAGES` | Android PDF 열람 페이지 한도. 기본 200쪽 |
| WPF | `FLOWNOTE_LOCAL_DATA_DIR` | `C:\FlowNote\LocalData`처럼 DB와 `Files\`를 함께 둘 폴더 |
| WPF | `FLOWNOTE_LOCAL_DATABASE_PATH` | 특정 DB 파일을 직접 지정할 때만 사용. 지정 시 `FLOWNOTE_LOCAL_DATA_DIR`보다 DB 경로 우선 |
| WPF | `FLOWNOTE_API_BASE_URL` | 서버 PC 주소. 예: `http://192.168.0.10:5184` |
| WPF | `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` | 문서 뷰어 자동 닫힘 시간. 5초-3600초로 정규화 |

`FLOWNOTE_LOCAL_DATABASE_PATH`를 지정하면 WPF DB 파일 위치가 그 값으로 고정된다. 다만 로컬 파일 저장 위치는 `FLOWNOTE_LOCAL_DATA_DIR` 기준으로 관리하는 편이 운영자가 백업 대상을 이해하기 쉽다. 운영에서는 특별한 이유가 없으면 `FLOWNOTE_LOCAL_DATA_DIR`만 지정한다.

`FLOWNOTE_DATABASE_URL`의 서버 SQLite와 WPF 로컬 SQLite는 반드시 서로 다른 파일이어야 한다. 서버와 WPF에 같은 경로를 넣어 하나의 DB를 공유하지 않는다. 기존 WPF schema를 서버 URL로 잘못 지정하면 FastAPI는 서버 테이블 생성 전에 시작을 거부하며, 이미 서버 전용 테이블이 유입된 WPF DB는 아래 검증 자동화 절의 보존 복구 절차를 따른다.

## 운영 설치 전 점검

### 서버

- 서버 PC 고정 IP 또는 고정 호스트명을 확정한다.
- Python 3.11 이상 설치 여부를 확인한다.
- `C:\FlowNote\Server\api`, `data`, `storage`, `logs` 폴더가 있고 서버 실행 계정에 읽기/쓰기 권한이 있는지 확인한다.
- `C:\FlowNote\Server\.env`에 운영 DB 경로, storage 경로, 토큰 비밀값이 들어 있고 기본 개발 비밀값이 남아 있지 않은지 확인한다.
- `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`인지 확인한다. 현재 코드는 운영 provider 연동 완료 상태가 아니다.
- `system-admin`으로 WPF `AI 운영` 화면에 접속해 전역/현장 kill switch가 의도한 상태인지 확인한다. 외부 호출을 준비하지 않은 설치는 기능 플래그뿐 아니라 kill switch도 켠 상태를 유지한다.
- 전송 승인과 활성 프롬프트가 시험 범위·만료일·목적·원천 유형에 맞는지 확인하고, 감사 CSV 내보내기는 현장 정책상 필요한 경우에만 허용한다.
- 만료 보존 작업은 서버 시작과 함께 기본 1시간 간격 스케줄러가 실행한다. 운영 주기와 담당자를 정하고, 즉시 처리가 필요하면 `system-admin`의 API/WPF 실행 기능을 사용한다.
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
- 서버 복구 후 WPF를 실행하기 전에 `/api/v1/health/db`와 `/api/v1/health/sync-manifest`를 먼저 확인한다.
- WPF 로컬 데이터 복구는 DB와 `Files`를 같은 시점으로 맞춘다.

## 운영 설치 후 점검

### 서버

- 작업 스케줄러의 `\FlowNote\FlowNoteApi` 작업이 실행 중인지 확인한다.
- `http://127.0.0.1:5184/api/v1/health`가 서버 PC에서 성공하는지 확인한다.
- `http://127.0.0.1:5184/api/v1/health/db`가 서버 PC에서 성공하는지 확인한다.
- `http://127.0.0.1:5184/api/v1/health/sync-manifest`가 서버 instance/epoch와 contract, cursor를 반환하는지 확인한다.
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
- 서버 로그인한 `admin`, `system-admin`의 사용자 관리 화면이 서버 계정 생성·role/상태 변경·임시 비밀번호 재설정·활성 세션 폐기를 수행하는지 확인한다.
- 로컬 로그인 사용자 관리 화면의 창 제목, 목록, 상세 안내가 로컬 SQLite 계정 전용임을 표시하는지 확인한다.
- 임시 비밀번호 계정이 메인 화면 전에 비밀번호 변경을 강제하고 변경 후 새 비밀번호 재로그인을 요구하는지 확인한다.
- 문서 목록이 열리고 서버에 등록된 문서가 조회되는지 확인한다.
- 문서를 열어 뷰어가 표시되고 다운로드 차단 정책과 열람 로그가 동작하는지 확인한다.
- WebView2 Runtime 미설치 또는 손상 환경에서는 `문서 뷰어를 시작할 수 없습니다.` 안내가 표시되는지 확인하고, WebView2 Runtime 설치 후 같은 문서가 정상 열람되는지 기록한다.
- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` 기준으로 뷰어 자동 닫힘이 동작하는지 확인한다.
- FieldComment를 등록하고 서버 목록 또는 문서별 FieldComment 조회에서 확인한다.
- 서버 호출 실패 시 로컬 저장이 유지되고 동기화 이력이 남는지 장애 테스트에서 별도로 확인한다.
- 서버 URL, instance/epoch 또는 cursor 복구 경계가 달라지면 자동 전송과 알림 polling이 중지되고 `이력 > 서버 재결합` 안내가 표시되는지 확인한다.

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

### 현장 확정 값 기록

아래 값은 파일럿 책임자의 승인과 같은 `run_id`의 실기 증거가 생긴 뒤에만 채운다. 문서의 예시 경로나 개발 기본값을 현장 확정 값으로 복사해 통과 처리하지 않는다. 비밀값, 인증서 개인키, 실제 고객명·사용자명·IP는 이 표가 아니라 승인된 운영 저장소에서 관리한다.

| 항목 | 현장 확정 값 | 승인/증거 | 상태 |
| --- | --- | --- | --- |
| 서버 설치 경로·서비스 계정·자동 시작 방식 | 미확정 | `<run_id>/install/server-*` | 대기 |
| 운영 DNS 이름·API URL·TLS 종단 위치 | 미확정 | `<run_id>/network-and-certificate/network-*` | 대기 |
| 인증서 발급자·SAN·유효기간·갱신 겹침 기간 | 미확정 | `<run_id>/network-and-certificate/certificate-*` | 대기 |
| 허용 방화벽 원천 구간·포트 | 미확정 | `<run_id>/network-and-certificate/firewall-*` | 대기 |
| 시간 원천·허용 오차·현장 시간대 | 미확정 | `<run_id>/network-and-certificate/time-*` | 대기 |
| framework-dependent/self-contained 채택 범위 | 미확정 | `<run_id>/install/wpf-*` | 대기 |
| .NET Desktop Runtime·WebView2 배포 방식/버전 | 미확정 | `<run_id>/install/prerequisites-*` | 대기 |
| EXE/MSI 서명 인증서·hash 전달 경로 | 미확정 | `<run_id>/packages/windows-*` | 대기 |
| 서버 DB+`storage` 백업 주기·보존·RPO/RTO | 미확정 | `<run_id>/approvals/data-protection-*` | 대기 |
| WPF DB+`Files` 백업 주기·보존·RPO/RTO | 미확정 | `<run_id>/approvals/data-protection-*` | 대기 |
| 복구 PC·복구 경로·복구 승인자 | 미확정 | `<run_id>/backup-restore/*` | 대기 |

현장 값이 확정되면 예시 명령과 실제 값이 충돌하지 않는지 검토하고 이 표, 설치 전후 점검표, 파일럿 manifest를 함께 갱신한다. 현장별 선호는 공통 기본값으로 올리지 않고 설정·교육 기록으로 분리한다.

### 서버 복구 순서

1. 서버 작업 스케줄러 `\FlowNote\FlowNoteApi`를 중지하고 WPF 앱을 종료한다.
2. `C:\FlowNote\Server\data`를 백업본의 서버 데이터 세트로 복원한다.
3. `C:\FlowNote\Server\storage`를 같은 시점의 서버 파일 세트로 복원한다.
4. `.env` 또는 서비스 환경 변수를 복원한다. 새 서버 PC의 절대 경로가 다르면 `FLOWNOTE_DATABASE_URL`과 `FLOWNOTE_STORAGE_ROOT`를 먼저 수정한다.
5. 서버 작업을 시작한 뒤 서버 PC에서 `http://127.0.0.1:5184/api/v1/health`, `http://127.0.0.1:5184/api/v1/health/db`, `http://127.0.0.1:5184/api/v1/health/sync-manifest`를 확인하고 복구 전후 instance/epoch/cursor를 기록한다.
6. 복구가 클라이언트가 알고 있던 운영 시점과 다른 명시적 경계라면 `admin` 또는 `system-admin`이 `POST /api/v1/sync/server-epoch/increment`를 한 번 실행한다. 같은 정상 백업을 단순 재기동한 경우에는 임의로 증가시키지 않는다.
7. WPF 실행 전 서버 계정 로그인이 가능한지 확인한다.
8. WPF가 `RECONCILIATION_REQUIRED`를 표시하면 자동 전송·polling이 중지된 상태에서 `이력 > 서버 재결합`의 모든 `REBOUND`/`REQUEUE`/`CONFLICT` 항목과 승인 사유를 검토해 적용한다. 기존 큐·mapping·처리 `message_id`를 삭제하거나 수동 초기화하지 않는다.
9. 승인 적용 뒤 cursor 0 재추적과 `PENDING` 재전송이 재개되는지 확인한다.
10. `scripts\verify-pilot-restore.py`로 복구 전후 `server` 증거를 비교해 테이블별 원천 개수, `storage` 상대경로·크기·SHA-256, `quick_check`, foreign key가 모두 통과했는지 확인한다.

### WPF 복구 순서

1. 대상 PC의 WPF 앱을 종료한다.
2. `C:\FlowNote\LocalData\flownote.local.sqlite`와 WAL/SHM 파일을 PC별 데이터 세트로 복원한다.
3. `C:\FlowNote\LocalData\Files\`를 같은 시점의 PC별 파일 세트로 복원한다.
4. `FLOWNOTE_LOCAL_DATA_DIR`, `FLOWNOTE_LOCAL_DATABASE_PATH`, `FLOWNOTE_API_BASE_URL` 값이 복구 위치와 맞는지 확인한다.
5. WPF 앱을 실행해 로그인, 문서 목록, 문서 열람, FieldComment 등록/조회, 보고서 근거 조회를 확인한다.
6. 복구 후 저장소 루트에서 `.\scripts\verify-preserved-tests.ps1` 또는 운영자가 지정한 동등 점검을 실행한다. 운영 환경에서 전체 개발 테스트를 실행할 수 없으면 최소한 서버 health, DB health, WPF 로그인, 문서 목록, 문서 열람, FieldComment, 보고서 근거 조회를 수동 점검표로 남긴다.
7. `scripts\verify-pilot-restore.py`로 복구 전후 `wpf` 증거를 비교해 테이블별 원천 개수, `Files` 상대경로·크기·SHA-256, `quick_check`, foreign key가 모두 통과했는지 확인한다.

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

현재 `.gitignore`는 빌드 산출물, 로그, SQLite와 WAL/SHM 보조 파일, 운영/고객 파일, 로컬 파일 저장소를 Git에서 제외한다. 테스트와 개발 검증 SQLite도 누적 기록으로 로컬에 보존하지만 추적하거나 커밋하지 않는다. 커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 포함한 DB 파일, PDF, 이미지, Excel, TXT, 렌더링 결과, 테스트 로그, `data/local/Files/`, `Data/Files/` 하위 파일이 포함되지 않았는지 확인한다.

## 후속 배포 과제

- 고객 유사 네트워크의 HTTPS, 방화벽, 서버 주소 변경과 시간 동기화 리허설
- 현장별 .NET/WebView2 설치 조합에서 self-contained MSI 신규 설치·업그레이드·제거·rollback 실기 검증
- 현장별 HTTPS·코드 서명 인증서 발급, 배포, 갱신, 폐기 운영 절차
- Android 운영 서명 APK/AAB, MDM/승인 배포, 단말 분실·교체와 outbox 보호 정책 확정
- 서버 DB+`storage`, WPF DB+`Files`를 별도 PC에서 복구하고 전후 개수·hash를 비교하는 훈련
- PostgreSQL 전환 조건

위 항목은 각각 따로 완료 처리하지 않고 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)의 단일 `run_id`와 완료 판정으로 묶는다. 실제 Windows PC, 승인 Android 단말, 고객 유사 네트워크와 운영 책임자가 없는 개발 환경에서는 `대기`로 유지한다.

## 검증 자동화

표준 검증 순서와 사후 Git 산출물 점검은 [검증 자동화 문서](./verification.md)를 따른다. 저장소 루트의 `.\scripts\verify-preserved-tests.ps1`은 Windows x64와 PowerShell/.NET/Python/JDK/Android SDK/Git 기준을 먼저 확인한 뒤 FastAPI pytest 수집·중복 0·JUnit 실행, WPF Core 테스트·앱 build·통합 smoke, 스모크 전후 WPF 공통 DB 무결성, Android 단위 테스트·debug build, `.gitignore` 제외 규칙과 실행 전후 `git status`/`git ls-files` 금지 산출물을 함께 확인한다. 현재 FastAPI 코드 수집값은 143건이지만 스크립트 guard는 131건이므로, guard를 143건으로 갱신하기 전에는 현재 Windows 통합 기준선을 만들 수 없다.

각 실행은 새 run ID를 사용하고 `data/local/integrated-smoke/<run-id>/`에 환경 정보, 단계별 로그, JUnit/TRX, WPF SQLite 실행 전후 통계·오늘/과거 문서 SQL 증거와 `verification-summary.json`을 보존한다. 통제된 WPF smoke는 `5184` 포트를 점유한 기존 서버를 재사용하지 않으므로 시작 전에 포트를 비운다. 생략 옵션이 없는 실행의 요약 상태가 `PASSED`이고 모든 필수 결과와 무결성 값이 통과한 경우에만 배포 통합 기준선으로 인정한다. 테스트 수집 개수 일치, 비 Windows 부분 실행 또는 `PASSED_PARTIAL` 결과만으로는 배포 검증을 통과한 것이 아니다.

2026-07-20 WPF 공통 DB의 서버형 `controlled_copy_grants` FK 충돌은 `scripts/repair-wpf-controlled-copy-schema.py`로 원본 backup·DDL·row 수·hash를 먼저 보존한 뒤 복구했다. 실제 복구 run `WPF-P0-20260720-0840`은 `quick_check=ok`, FK 위반 0건이며 문서 버전 3,384행의 원천 hash를 유지한다. FastAPI가 WPF 로컬 schema를 서버 DB로 초기화하려는 경우도 `create_all` 전에 거부한다. 2026-07-21 macOS 보조 run `baseline-131-macos-precheck-20260721-001`은 당시 FastAPI 131건 통과만 확인했고 WPF/Android는 `NOT_RUN`이다. 현재 코드는 143건이므로 이 run을 최신 기준선으로 승격하지 않는다. guard 갱신과 새 Windows 무생략 `verification-summary.json=PASSED`가 생성되기 전까지 배포 통합 기준선은 `대기`다.
## DB 복구·초기화 후 운영 절차

1. 모든 WPF를 종료하거나 자동 전송/polling이 중지됐음을 확인한다.
2. 서버 DB와 `storage/`를 같은 백업 시점으로 복원한다. 부분 복원이라면 어떤 영역이 다른 시점인지 기록한다.
3. 서버를 단독 기동해 `quick_check`, foreign key, orphan, 중복 idempotency key, 공개 포인터, report source/file hash 검사를 실행한다.
4. 관리자 계정으로 `POST /api/v1/sync/server-epoch/increment`를 한 번 실행한다. 빈 DB 초기화는 새 instance ID가 생성되므로 별도 epoch 증가가 필수는 아니지만 동일 검사를 수행한다.
5. WPF 한 대를 연결한다. "서버 복구 경계가 감지되어 자동 전송을 중지했습니다" 또는 "다른 서버 연결 또는 빈 DB 초기화 여부를 확인하세요"가 표시되는지 확인한다.
6. 이력 > 서버 재결합에서 새 run을 생성한다. 모든 `REBOUND`, `REQUEUE`, `CONFLICT`와 양쪽 hash를 검토하고 승인 사유를 입력해 적용한다.
7. cursor 0 재추적과 재전송이 끝난 뒤 비종결 큐, mapping orphan, 중복 key, 공개 포인터와 hash 검사를 다시 실행한다. 첫 WPF가 통과한 다음 두 번째 WPF도 별도 run으로 반복한다.

정상 복구, 이전 시점 복구, 빈 DB 초기화, 다른 server instance/잘못된 URL 연결은 각각 새 `run_id`로 기록한다. URL 오입력 때는 승인하지 말고 올바른 URL로 되돌린 후 운영 책임자가 잘못 생성된 실패 run을 보존한다.
