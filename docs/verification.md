# 테스트와 검증 방법

이 문서는 공개 저장소를 처음 받은 사람이 FlowNote의 소스 검증을 재현하는 방법을 설명한다. 저장소에는 테스트 코드와 실행 방법만 포함하며, 실행하면서 생긴 SQLite, 업로드 파일, 로그, JUnit·TRX, 화면 캡처, APK·MSI 같은 결과물은 포함하지 않는다.

현재 저장소는 로컬 테스트 데이터가 없는 초기 상태를 기준으로 한다. 아래 명령을 실행하면 각 도구가 필요한 시험 데이터를 새로 만들 수 있다. 테스트 결과는 실행한 환경과 커밋에만 해당하며, 과거 통과 기록을 현재 코드의 통과로 간주하지 않는다.

## 1. 검증 범위

FlowNote 검증은 다음 단계로 나뉜다.

| 단계 | 목적 | 서버 연결 | 기본 공개 검증 |
| --- | --- | --- | --- |
| 공개 파일 검사 | 비밀정보·운영 데이터·생성 파일·깨진 문서 링크 확인 | 불필요 | 필수 |
| FastAPI 단위·회귀 | API, 권한, 데이터 모델과 SQLite 동작 확인 | 불필요 | 필수 |
| Windows Core·빌드 | 로컬 저장소, 동기화, 업무 규칙과 WPF 컴파일 확인 | 불필요 | 필수 |
| Android 단위·빌드·lint | API 계약, outbox, 보안 열람과 Android 컴파일 확인 | 불필요 | 필수 |
| 로컬 API 평가 | 공개 소스의 설정 생성과 최초 기동 확인 | loopback만 사용 | 선택 |
| 운영 HTTPS 스모크 | 설치형 클라이언트와 승인 서버의 실제 연동 확인 | 승인된 HTTPS 서버 필요 | 운영 도입 시 수행 |
| 실단말·패키지 검증 | Android 단말, MSI·서명, MDM과 현장망 확인 | 현장 환경 필요 | 운영 도입 시 수행 |

외부 AI provider 호출은 현재 완료 기능 검증 범위가 아니다. AI 관련 테스트는 후속 연구를 위한 후보·근거·승인·차단 계약을 검증하며, 실제 외부 AI 서비스의 품질이나 운영 완료를 뜻하지 않는다.

## 2. 필요한 도구

개별 검증에는 해당 구성요소의 도구만 설치하면 된다.

| 구성요소 | 요구 도구 |
| --- | --- |
| 공개 파일 검사 | Git, Python 3.11 이상 |
| FastAPI | Python 3.11 이상 |
| Windows WPF | Windows, .NET SDK 10.x, Windows Desktop Runtime 10.x |
| Android | JDK 17, Android SDK Platform 35, Build Tools 35.0.0 |
| 통합 스모크 | 64비트 Windows, PowerShell 5.1 이상, 위 도구 전체, 승인된 HTTPS 서버 |

버전 확인 예시는 다음과 같다.

```powershell
git --version
py -3.11 --version
dotnet --version
java -version
javac -version
```

```bash
git --version
python3 --version
java -version
javac -version
```

Android 검증 전에는 `ANDROID_HOME` 또는 `ANDROID_SDK_ROOT`가 SDK 경로를 가리키고, JDK 17의 `java`와 `javac`가 같은 `JAVA_HOME` 아래에 있는지 확인한다.

## 3. 테스트 데이터 초기화

### 초기화 대상

초기화 도구는 저장소 안에서 생성된 다음 항목만 정리한다.

- 루트 `data/` 또는 `Data/`의 로컬 SQLite, 업로드, 스모크 증거와 테스트 결과
- `services/api/data/`의 테스트 SQLite와 `services/api/storage/`의 테스트 업로드
- WPF 앱이 만든 `apps/windows/src/FlowNote.Windows.App/Data/`
- `tmp/`, `artifacts/`, `storage/`, `_workspace/`와 표준 결과 폴더
- Python 테스트 캐시, .NET `bin/`·`obj/`·`TestResults/`, Android 로컬 build·Gradle 캐시

다음 항목은 삭제하지 않는다.

- `services/api/tests/`, Windows 테스트 프로젝트, Android 테스트 소스
- `.env`, `.env.local`과 기타 로컬 환경 설정
- `.venv`와 개발자가 설치한 의존성
- `services/api/data/.gitkeep`, `services/api/storage/.gitkeep`
- `.git/`과 추적 중인 소스·문서

앱, API 서버, 테스트 러너가 실행 중이면 먼저 정상 종료한다. SQLite WAL을 사용하는 프로세스가 남아 있으면 초기화가 실패하거나 실행 중인 프로그램이 오류를 낼 수 있다.

삭제 대상을 먼저 확인한다.

```powershell
py -3.11 .\scripts\reset_local_test_data.py
```

```bash
python3 scripts/reset_local_test_data.py
```

목록이 맞을 때만 실제 초기화를 수행한다.

```powershell
py -3.11 .\scripts\reset_local_test_data.py --apply
```

```bash
python3 scripts/reset_local_test_data.py --apply
```

초기화 후 `git status --short`에 소스 변경이 새로 나타나면 중단한다. 정상적인 초기화는 Git에서 제외된 파일만 삭제하므로 추적 파일 상태를 바꾸지 않는다.

## 4. 공개 파일 검사

저장소 루트에서 다음 명령을 실행한다.

```powershell
py -3.11 .\scripts\check_public_tree.py
py -3.11 -m unittest scripts/test_check_public_tree.py
py -3.11 -m unittest scripts/test_bootstrap_local_evaluation.py
py -3.11 -m unittest scripts/test_reset_local_test_data.py
```

```bash
python3 scripts/check_public_tree.py
python3 -m unittest scripts/test_check_public_tree.py
python3 -m unittest scripts/test_bootstrap_local_evaluation.py
python3 -m unittest scripts/test_reset_local_test_data.py
```

공개 파일 검사는 Git 추적 파일과 Git에서 제외되지 않은 새 파일을 함께 확인한다.

- SQLite·DB·로그·키·인증서·APK·AAB·MSI가 공개 대상에 없는지 확인한다.
- `.env`와 빌드·의존성 폴더가 포함되지 않았는지 확인한다.
- private key 표식과 머신 로컬 파일 URI를 검사한다.
- `flownote.*` 주소가 `.example` 또는 `.invalid` 예약 도메인인지 확인한다.
- Markdown 상대 링크가 저장소 안의 실제 파일을 가리키는지 확인한다.

검사가 실패하면 표시된 파일을 바로 커밋하지 않는다. 실제 데이터는 삭제하거나 Git 추적만 해제하고, 공개 가능한 합성 fixture가 필요하면 테스트 실행 중 생성하도록 바꾼다.

## 5. FastAPI 단위·회귀 테스트

### Windows PowerShell

```powershell
cd services\api
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ruff check app tests ..\..\scripts\bootstrap_local_evaluation.py ..\..\scripts\test_bootstrap_local_evaluation.py ..\..\scripts\check_public_tree.py ..\..\scripts\test_check_public_tree.py ..\..\scripts\reset_local_test_data.py ..\..\scripts\test_reset_local_test_data.py ..\..\scripts\seed-ai-ground-truth-48.py
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest
```

### macOS·Linux

```bash
cd services/api
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m ruff check app tests ../../scripts/bootstrap_local_evaluation.py ../../scripts/test_bootstrap_local_evaluation.py ../../scripts/check_public_tree.py ../../scripts/test_check_public_tree.py ../../scripts/reset_local_test_data.py ../../scripts/test_reset_local_test_data.py ../../scripts/seed-ai-ground-truth-48.py
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest
```

`--collect-only`는 테스트를 실행하지 않고 node ID를 수집한다. 중복 없이 수집되고 실제 pytest가 실패·오류·건너뜀 없이 종료 코드 0을 반환해야 한다. 표준 통합 스크립트의 현재 guard는 FastAPI 215건이며 테스트를 추가하거나 삭제하면 실제 수집 결과와 함께 guard도 갱신한다.

테스트는 `services/api/data/flownote.test.sqlite3`, 추가 migration 시험 DB와 `services/api/storage/` 아래 합성 파일을 만들 수 있다. 이 파일은 Git에서 제외되며 실제 고객 데이터가 아니다. 실행 후 다시 초기 상태가 필요하면 저장소 루트로 돌아가 초기화 도구를 실행한다.

특정 실패를 좁힐 때는 실제로 수집된 node ID를 지정한다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_documents_api.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_documents_api.py::<수집된_테스트_이름> -q
```

실패한 전체 테스트를 무조건 재실행하기 전에 첫 traceback, HTTP 응답 본문과 SQLite lock 여부를 확인한다.

## 6. Windows WPF 검증

Windows에서 저장소 루트를 기준으로 실행한다.

```powershell
dotnet test .\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj -p:TreatWarningsAsErrors=true
```

Core 테스트는 로컬 SQLite, 서버 scope 분리, sync queue, 멱등성, 문서 미리보기, 권한과 사용자 안내 같은 서버 비연결 로직을 확인한다. 앱 빌드는 WPF 화면과 프로젝트 참조가 현재 .NET 계약으로 컴파일되는지 확인한다. 표준 통합 스크립트의 현재 WPF Core guard는 120건이다.

`NU1900`처럼 NuGet 취약성 feed를 조회하지 못한 경고는 테스트 통과와 별개다. 네트워크가 허용된 환경에서 audit를 다시 실행하고, feed를 확인하지 못한 상태를 취약성 없음으로 기록하지 않는다.

macOS·Linux에서 WPF 코드를 교차 빌드할 때는 다음 옵션을 사용할 수 있지만, 이 결과는 실제 Windows UI 실행을 대신하지 않는다.

```bash
dotnet test apps/windows/src/FlowNote.Windows.Core.Tests/FlowNote.Windows.Core.Tests.csproj
dotnet build apps/windows/src/FlowNote.Windows.App/FlowNote.Windows.App.csproj -p:EnableWindowsTargeting=true -p:TreatWarningsAsErrors=true
```

## 7. Android 검증

macOS·Linux:

```bash
cd apps/android
./gradlew testDebugUnitTest assembleDebug lintDebug --warning-mode=fail
```

Windows PowerShell:

```powershell
cd apps\android
.\gradlew.bat testDebugUnitTest assembleDebug lintDebug --warning-mode=fail
```

현재 표준 guard는 단위 테스트 39건이다. JUnit의 total과 passed가 일치하고 failure·error·skipped가 0이어야 한다. `assembleDebug`와 `lintDebug`도 같은 소스에서 성공해야 한다.

debug APK는 개발 검증용이다. 운영 배포에는 조직 소유 키, 승인된 서명 절차와 MDM 정책이 필요하며 실제 키와 APK를 저장소에 넣지 않는다. 카메라·파일 선택, foreground service, 재부팅, Doze, 사내 인증서와 보안 뷰어는 승인 단말에서 별도 확인한다.

## 8. 공개 소스 로컬 API 평가

이 절은 처음 받은 소스가 loopback에서 기동되는지 확인하는 개발자 평가 절차다. 운영 배포나 운영 HTTPS 스모크가 아니다.

저장소 루트에서 Git 제외 `.env`를 만든다. 기존 파일은 덮어쓰지 않는다.

```powershell
py -3.11 .\scripts\bootstrap_local_evaluation.py
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
python3 scripts/bootstrap_local_evaluation.py
cd services/api
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서 확인한다.

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/health/db
curl --fail http://127.0.0.1:8000/openapi.json
```

평가가 끝나면 `Ctrl+C`로 서버를 정상 종료한다. 생성된 `.env`는 초기화 도구가 지우지 않으므로 계속 사용할지 직접 판단한다. 로컬 DB와 storage만 지우려면 초기화 도구의 dry-run 목록을 확인한 뒤 `--apply`를 사용한다.

## 9. 운영 HTTPS 통합 스모크

통합 스모크는 일반 기여자가 공개 소스 확인을 위해 실행할 필요가 없다. Windows 설치형 클라이언트와 승인 Android 단말을 실제 도입 환경에 연결할 때 수행한다.

필수 조건은 다음과 같다.

- 64비트 Windows와 PowerShell 5.1 이상
- Python 3.11 가상환경과 FastAPI 개발 의존성
- .NET SDK·Windows Desktop Runtime 10.x
- JDK 17, Android SDK Platform 35·Build Tools 35.0.0
- Git 상태가 깨끗한 동일 소스 커밋
- `https://flownote.example`이 아닌 승인된 HTTPS API 주소
- 파일에 저장하지 않고 현재 프로세스에만 주입한 전용 스모크 계정
- 서버에 이미 존재하는 과거 날짜 사진 또는 인수인계 문서 1건
- 승인된 Android 실단말 검증 시 정확히 연결된 대상 단말 1대

자격 증명은 아래 이름으로 현재 PowerShell 프로세스에만 주입한다. 실제 값은 문서, 명령 기록, `.env`와 Git에 남기지 않는다.

```powershell
$env:FLOWNOTE_API_BASE_URL = "https://flownote.example.invalid" # 실제 실행 때 승인 주소로 교체
$env:FLOWNOTE_SMOKE_ADMIN_USERNAME = "<전용 계정>"
$env:FLOWNOTE_SMOKE_ADMIN_PASSWORD = "<보안 입력 경로에서 받은 값>"
```

예시 주소는 연결되지 않도록 의도한 값이다. 실제 주소를 넣은 뒤 옵션 없이 실행해야 전체 기준선 후보가 된다.

```powershell
.\scripts\verify-preserved-tests.ps1 -RunId "integration-<고유 실행 ID>"
```

승인 Android 실단말 계측까지 포함할 때만 다음을 사용한다.

```powershell
.\scripts\verify-preserved-tests.ps1 -RunId "integration-<고유 실행 ID>" -RunAndroidDeviceSmoke
```

`Skip*` 옵션을 사용한 실행은 원인 진단용 부분 실행이며 전체 통과 기준선이 아니다. 실행 ID는 재사용하지 않는다. 스크립트는 다음 항목을 순서대로 확인한다.

1. 도구와 환경 버전
2. `.gitignore`와 공개 금지 산출물
3. 실행 전 Git 상태
4. FastAPI 수집·중복·JUnit 결과
5. WPF Core 수집·TRX와 앱 빌드
6. WPF 공통 SQLite의 실행 전 무결성
7. 승인 HTTPS 서버 health와 WPF 통합 스모크
8. 오늘 날짜 사진·인수인계 등록과 목록 조회
9. 기존 과거 문서 한 건의 버전 증가
10. WPF 공통 SQLite의 실행 후 무결성과 멱등키·매핑 중복
11. Android 단위 테스트와 debug 빌드
12. 선택한 승인 실단말 계측 테스트
13. 실행 후 Git 상태와 금지 추적·스테이징 파일

운영 서버 DB, storage와 서버 로그는 개발 PC로 복사하지 않는다. 클라이언트 쪽 JUnit·TRX·로그·SQLite 증거는 `data/local/integrated-smoke/<run-id>/`에 생성되며 Git에서 제외된다. 공개용 작업을 마친 뒤 이 자료가 더 필요하지 않으면 초기화 도구로 삭제한다.

## 10. 결과 판정

각 단계는 다음 기준으로 판정한다.

| 상태 | 의미 |
| --- | --- |
| 통과 | 명령 종료 코드 0, 기대 수집 수 일치, 실패·오류·건너뜀 0 |
| 실패 | assertion, 컴파일, lint, 무결성 또는 공개 파일 검사 실패 |
| 환경 대기 | 요구 SDK·운영 HTTPS·승인 단말처럼 현재 환경에 없는 조건 |
| 미실행 | 명령을 실행하지 않았거나 부분 실행에서 제외함 |

실행하지 않은 항목을 통과로 기록하지 않는다. 단위 테스트 통과는 운영 서버 연동, 실제 Windows UI, Android 실단말, 서명 패키지와 현장 UX 승인을 대신하지 않는다.

실패할 때는 다음 순서로 확인한다.

1. 실패한 명령과 첫 원인 traceback 또는 compiler error
2. 요구 도구 버전과 환경 변수 존재 여부
3. 실행 중인 API·앱·테스트 프로세스와 SQLite lock
4. Git에서 제외되지 않은 생성 파일 존재 여부
5. 같은 node ID 또는 구성요소의 단독 재현
6. 원인 수정 뒤 전체 구성요소 재실행

## 11. 공개 전 최종 확인

테스트가 끝난 뒤 다음 순서로 마무리한다.

```powershell
py -3.11 .\scripts\reset_local_test_data.py
py -3.11 .\scripts\reset_local_test_data.py --apply
py -3.11 .\scripts\check_public_tree.py
git status --short
git ls-files
```

```bash
python3 scripts/reset_local_test_data.py
python3 scripts/reset_local_test_data.py --apply
python3 scripts/check_public_tree.py
git status --short
git ls-files
```

마지막으로 다음을 직접 확인한다.

- SQLite, 로그, 테스트 업로드, 실제 문서와 빌드 결과가 추적되거나 스테이징되지 않았다.
- `.env`, 토큰, 비밀번호, 키, 인증서와 실제 서버 주소가 없다.
- `services/api/data/`와 `services/api/storage/`에는 `.gitkeep`만 남았다.
- 테스트 코드는 삭제되지 않았고 깨끗한 clone에서 fixture를 다시 만들 수 있다.
- 문서의 명령, 경로와 요구 버전이 현재 프로젝트 파일과 일치한다.

Git 이력에 과거 운영 데이터나 비밀정보가 발견되면 현재 파일에서 삭제하는 것만으로 충분하지 않다. 원격 이력 재작성은 기존 clone과 협업자에게 영향을 주므로 저장소 소유자의 명시적 승인 아래 수행하거나, 검증된 현재 스냅샷으로 공개용 새 저장소를 만드는 방식을 사용한다.
