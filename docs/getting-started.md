# FlowNote 처음 실행하기

## 목적과 범위

이 문서는 공개 저장소를 처음 받은 사람이 실제 운영 정보나 고정 비밀번호 없이 FlowNote의 소스, FastAPI 서버와 각 클라이언트 빌드를 확인하는 순서다. 로컬 API 평가는 기능 탐색과 개발용이며, 고객 현장의 운영 배포나 HTTPS 연동 검증을 대신하지 않는다.

가장 빠른 확인 경로는 다음과 같다.

1. Git에서 저장소를 받는다.
2. Git 제외 `.env`와 무작위 비밀값을 만든다.
3. FastAPI를 loopback에서 시작하고 health와 OpenAPI를 확인한다.
4. 사용하는 플랫폼에 맞춰 Windows 또는 Android 앱을 빌드한다.
5. 실제 클라이언트 연결은 신뢰할 수 있는 HTTPS 주소를 준비한 뒤 확인한다.

## 1. 준비물

- Git
- Python 3.11 이상
- Windows 앱 빌드: Windows와 .NET 10 SDK
- Android 앱 빌드: JDK 17과 Android SDK 35

저장소의 예시 주소 `https://flownote.example`은 연결되지 않는 예약 도메인이다. 실제 서버 주소, 인증서, 계정, 토큰과 고객 데이터는 저장소에 추가하지 않는다.

## 2. 로컬 평가 설정 만들기

저장소 루트에서 다음 명령을 한 번 실행한다.

Windows PowerShell:

```powershell
py -3.11 .\scripts\bootstrap_local_evaluation.py
```

macOS 또는 Linux:

```bash
python3 scripts/bootstrap_local_evaluation.py
```

이 도구는 `services/api/.env.example`을 기준으로 다음 작업만 한다.

- Git에서 제외되는 `services/api/.env`를 새로 만든다.
- 첫 `admin`용 무작위 임시 비밀번호와 긴 access token 비밀값을 생성한다.
- 외부 AI 호출을 비활성 상태로 유지한다.
- 기존 `.env`가 있으면 덮어쓰지 않고 종료한다.
- 사용자 지정 출력도 `.env` 또는 Git 제외 `*.env.local` 이름만 허용한다.
- POSIX 파일시스템에서는 소유자만 읽고 쓸 수 있도록 권한을 `0600`으로 제한한다.

화면에 나온 초기 비밀번호는 공개 채널이나 로그에 옮기지 않는다. `.env`, SQLite와 `storage/`는 로컬에 보존되지만 Git 추적 대상은 아니다.

## 3. FastAPI 설치와 시작

Windows PowerShell:

```powershell
cd services\api
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184
```

macOS 또는 Linux:

```bash
cd services/api
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 5184
```

첫 시작에는 Git 제외 `services/api/data/flownote.sqlite3`와 `services/api/storage/`를 사용한다. 빈 DB인데 초기 관리자 비밀번호가 없으면 안전하게 시작을 거부한다.

다른 터미널에서 다음 응답을 확인한다.

Windows PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health
Invoke-RestMethod http://127.0.0.1:5184/api/v1/health/db
```

macOS 또는 Linux:

```bash
curl --fail http://127.0.0.1:5184/api/v1/health
curl --fail http://127.0.0.1:5184/api/v1/health/db
```

두 요청이 `status: ok`를 반환하면 브라우저에서 `http://127.0.0.1:5184/docs`를 열어 API 계약을 살펴볼 수 있다. `POST /api/v1/auth/login`에 사용자 `admin`과 생성된 비밀번호를 입력하면 서버가 비밀번호 변경 필요 상태로 로그인 세션을 발급한다. 반환된 access token으로 `POST /api/v1/auth/change-password`를 먼저 실행해야 다른 보호 API를 사용할 수 있다. 변경 뒤 `services/api/.env`의 `FLOWNOTE_INITIAL_ADMIN_PASSWORD` 값은 비운다. 기존 관리자 계정이 있는 DB는 이 값 없이 다시 시작할 수 있다.

서버를 종료할 때는 실행 중인 터미널에서 `Ctrl+C`를 사용한다. 평가 DB와 파일은 다음 실행에 이어서 사용하며 임의로 초기화하지 않는다.

## 4. 소스 검증

공개 제외 파일과 문서 링크:

```bash
python3 scripts/check_public_tree.py
```

FastAPI:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests ..\..\scripts\bootstrap_local_evaluation.py ..\..\scripts\test_bootstrap_local_evaluation.py ..\..\scripts\check_public_tree.py ..\..\scripts\test_check_public_tree.py ..\..\scripts\reset_local_test_data.py ..\..\scripts\test_reset_local_test_data.py ..\..\scripts\seed-ai-ground-truth-48.py
```

macOS 또는 Linux에서는 `python.exe` 대신 `.venv/bin/python`을 사용한다.

Windows WPF:

```powershell
dotnet test .\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
```

Android:

```bash
cd apps/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
./gradlew lintDebug --warning-mode=fail
```

debug APK와 교차 빌드는 개발 확인용이다. Windows MSI 서명, Android 조직 키 서명과 MDM 적용은 실제 도입 단계에서 별도로 검증한다.

## 5. 클라이언트 연결 조건

Windows와 Android 클라이언트는 문서와 현장 데이터를 다루므로 HTTPS만 허용한다. `http://127.0.0.1:5184` 로컬 평가는 API 확인용이며 클라이언트의 보안 정책을 우회하는 주소가 아니다.

클라이언트까지 연결하려면 다음 조건이 필요하다.

- FastAPI 앞에 신뢰 가능한 인증서의 HTTPS reverse proxy를 둔다.
- Windows는 필요할 때 `FLOWNOTE_API_BASE_URL`에 승인된 HTTPS 주소를 지정한다.
- Android는 앱 설정에서 승인된 HTTPS 주소와 관리자가 등록한 단말 ID를 저장한다.
- `admin` 또는 `system-admin`이 Windows의 사용자·승인 단말 화면에서 계정과 Android 단말을 준비한다.

실제 서버 설치, 자동 시작, 백업·복구와 HTTPS 확인은 [서버 설치·운영 매뉴얼](./manuals/server-operations.md)을 따른다. 운영 환경에는 로컬 평가 `.env`를 복사하지 말고 현장별 비밀값과 절대경로를 새로 설정한다.

## 6. 막힐 때 확인할 곳

| 증상 | 확인할 문서 |
| --- | --- |
| 첫 실행에서 관리자 비밀번호 오류 | [서버 설치·운영 매뉴얼](./manuals/server-operations.md#9-최초-관리자와-계정-운영) |
| DB 또는 storage 경로 오류 | [배포 기준](./deployment.md) |
| Windows 서버 주소·인증서 오류 | [공통 장애 대응](./manuals/troubleshooting.md) |
| Android 승인 단말 403 | [Android 현장 사용 매뉴얼](./manuals/android-field-guide.md) |
| 공개 저장소에 넣으면 안 되는 파일 | [오픈소스 공개 기준](./open-source-release.md) |

문제가 재현되면 비밀값, 실제 주소, 고객 데이터와 로컬 절대경로를 제거한 최소 정보만 공유한다.
