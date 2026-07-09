# 검증 자동화

이 문서는 테스트 DB와 산출물 보존 규칙을 지키면서 FlowNote의 현재 검증 순서를 한 번에 실행하는 기준이다. 실패하더라도 SQLite DB, 로그, 테스트 입력 파일, 출력 파일, 렌더링 결과, 스모크 테스트 산출물은 삭제하지 않는다.

## 표준 실행

저장소 루트에서 다음 명령을 실행한다.

```powershell
.\scripts\verify-preserved-tests.ps1
```

스크립트는 다음 순서로 실행한다.

1. `.gitignore`가 알려진 테스트/빌드 산출물 경로를 제외하는지 점검한다.
2. 실행 전 `git status --porcelain=v1 --untracked-files=all`에서 SQLite 예외 외 테스트 산출물, 빌드 결과, 개인 로컬 경로가 잡히지 않는지 점검한다.
3. `services/api`에서 FastAPI pytest 수집 개수가 51개인지 확인한다.
4. `services/api`에서 FastAPI pytest를 실행한다.
5. WPF 앱을 빌드한다.
6. WPF 스모크 테스트를 실행한다.
7. 실행 후 `git status`를 다시 점검한다.

개별 명령은 다음과 같다.

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest
cd ..\..
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
git status --short
```

## WPF 스모크 필수 조건

WPF 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 사용한다. 표준 스크립트는 실행 중 `FLOWNOTE_LOCAL_DATA_DIR`와 `FLOWNOTE_LOCAL_DATABASE_PATH`를 비워 임시 SQLite가 아니라 공통 SQLite에 누적 기록되도록 한다.

현재 스모크 테스트는 다음 항목을 필수로 검증한다.

- 오늘 날짜의 인수인계 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 오늘 날짜의 사진 문서 파일을 만들고, 오늘 날짜 폴더에 등록하고, 문서 목록에서 조회한다.
- 기존 인수인계 또는 사진 날짜 폴더 중 과거 날짜 폴더를 랜덤 선택하고, 그 안의 기존 문서에 버전 코멘트를 추가해 버전 번호가 1 증가했는지 확인한다.
- 과거 날짜 검증은 기존 날짜 폴더와 기존 문서만 대상으로 하며, 과거 날짜 폴더나 과거 날짜 문서를 새로 만들지 않는다.
- TXT/PDF/XLSX/이미지 미리보기 샘플 기준을 확인하고, 각 유형별 열람 종료, 자동 닫힘, 다운로드 차단 로그를 공통 SQLite에 누적한다.
- 실행 출력의 `Preview audit smoke` 줄에 파일 유형, 샘플 파일 경로, 로그 ID가 남는다.
- `FLOWNOTE_API_BASE_URL`이 없더라도 `http://127.0.0.1:5184` 로컬 FastAPI 서버가 실행 중이면 서버 로그인, 문서 등록, 버전, 공개 조회를 검증한다.
- 서버 URL이 없으면 WPF 로컬 계정 fallback이 허용되는지 확인한다.
- 서버 로그인 응답이 401 또는 403이면 같은 로그인 ID의 WPF 로컬 계정으로 우회하지 않는지 확인한다.

과거 날짜 후보가 하나도 없으면 스모크 테스트는 실패한다. 이 경우 DB를 삭제하지 말고 누적 데이터 상태를 확인해 다음 분석에 사용한다.

## 2026-07-08 누적 스모크 기록

공통 SQLite `data/local/flownote.local.sqlite`에는 2026-07-08 15:25 KST 기준 `smoke-102-human-20260708-132307`, `smoke-102-20260708143141`, `102-20260708143304`, `smoke-102-human-20260708-152335` 실행 기록이 누적되어 있다. 이 기록은 삭제하지 않고 이후 회귀 검증의 기준 데이터로 사용한다.

- `smoke-102-human-20260708-132307` 실행에서는 오늘 날짜 폴더 기준으로 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달` 문서가 등록되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 라인A 계량기 사진은 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `사진/2026-06-29` 문서 `사진당일라인A20260629113103758`의 버전을 v4로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- `102-20260708143304` 실행에서는 오늘 날짜 기준 인수인계/사진 문서 12건과 보고서 문서 6건이 추가되었다. 이 중 3건은 v2가 `PUBLISHED`인 공개 문서, 9건은 `WORKING`, 보고서 6건은 `IN_REVIEW` 상태다.
- `102-20260708143304` 실행에서는 FieldComment 24건이 추가되었고 검토 상태는 `ANALYZED` 8건, `REVIEWED` 8건, `SELECTED` 8건으로 남았다. 신호등식 입력도 `green`, `yellow`, `red`가 각각 8건씩 누적되었다.
- `102 사람형 스모크 작업순서 20260708143304` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 작업순서 항목은 `COMPLETED` 1건, `HOLD` 1건으로 남았다. 변경 이력은 보드 생성 1건, 항목 추가 2건, 상태 변경 3건, 보류 사유 변경 1건이다.
- `102 AI 근거 축적 보고서 20260708143304-01`부터 `-06`까지 6개 보고서 문서는 각각 `report_sources` 4건을 보존한다. 전체 source 구성은 FieldComment 12건, 문서 6건, 작업순서 이력 6건이다.
- `smoke-102-human-20260708-152335` 실행은 2026-07-08 15:23 KST에 시작된 사람형 다중 actor 스모크다. 실행 전 누적은 `documents` 1574건, `document_versions` 2308건, `field_comments` 1409건, 검토 준비 FieldComment 226건, `reports` 61건, `report_sources` 237건, `document_view_logs` 2090건, `activity_history` 68415건, `work_sequence_change_history` 580건이었다.
- 같은 실행에서는 오늘 날짜 기준 `라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달`, `AI 근거 축적 보고서` 문서가 추가되었다. 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 사진 문서는 FieldComment 첨부 근거 문서로 남았다.
- 같은 실행의 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-06` 문서 `doc-ba4f93c8dd0d46a19a57b53cd2f211a8`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- 같은 실행에서는 FieldComment 6건이 추가되었고 검토 준비 상태는 `ANALYZED` 2건, `REVIEWED` 2건, `SELECTED` 2건이다. 신호등식 입력은 `green` 3건, `yellow` 3건으로 남았다.
- `102 사람형 스모크 작업순서 20260708-152335` 보드는 `LINE-A`, `2026-07-08` 기준으로 생성되었고, 실행 전후 `work_sequence_change_history`가 580건에서 582건으로 증가했다.
- `smoke-102-human-20260708-152335 AI 근거 축적 보고서` 문서 `doc-e1500f91f8284e03a31c3e2f3c3e96d0`는 `report_sources` 9건을 보존한다.
- 2026-07-08 15:25 KST 기준 누적 테이블 수는 `documents` 1578건, `document_versions` 2315건, `field_comments` 1415건, `field_comment_attachments` 109건, `report_sources` 246건, `notifications` 1557건, `server_sync_queue` 771건, `work_sequence_boards` 116건, `work_sequence_items` 232건, `work_sequence_change_history` 582건, `work_sequence_notification_candidates` 237건이다.
- 2026-07-08 15:25 KST 기준 전체 FieldComment 상태는 `NEW` 1181건, `ANALYZED` 78건, `REVIEWED` 77건, `SELECTED` 77건, `EXCLUDED` 1건, `ARCHIVED` 1건이다. 신호등식 입력 누적은 `green` 302건, `yellow` 162건, `red` 70건이다.

## 2026-07-09 서버 동기화 스모크 기록

2026-07-09 KST에 FastAPI 서버를 `http://127.0.0.1:5184`로 실행한 상태에서 WPF 스모크 테스트를 실행했다. 스모크는 오늘 날짜 인수인계/사진 등록, 과거 날짜 기존 사진 문서 버전 증가, 문서 최초 등록 이후 버전/공개/상태/FieldComment/첨부/접근 로그/보고서 큐 순서 재시도, 서버 ID 매핑 복구, 보고서 중복 재전송 방지를 검증했다.

- 서버 연결 재시도 후 `server_sync_queue`는 `SYNCED` 520건, `FAILED` 284건이다.
- 실패 큐는 선행 문서 미동기화 224건, 로컬 파일 누락 20건, 선행 FieldComment 미동기화 20건, 구 FieldNote 큐 20건으로 분류된다. 서버 URL 미설정 실패는 서버 연결 재시도 후 남아 있지 않다.
- `server_id_mappings`는 648건이며 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다.
- 누적 테이블 수는 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `notifications` 1576건, `server_sync_queue` 804건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `work_sequence_notification_candidates` 239건이다.

## 2026-07-09 사람형 AI 근거 스모크 기록

2026-07-09 08:55 KST에 `smoke-102-human-20260709-085509` 사람형 다중 actor 스모크를 실행했다. 실행은 공통 SQLite `data/local/flownote.local.sqlite`와 `data/local/Files/HumanSmoke102/2026-07-09/smoke-102-human-20260709-085509` 파일 산출물을 사용했고, 실행 로그는 `data/local/human-smoke-102-python-20260709-085509.out.log`와 `.err.log`에 남겼다.

- 생성 계정은 8건이며 `102 A라인 반장 한지훈`, `102 A라인 조장 문서윤`, `102 A라인 작업자 오민재`, `102 A라인 작업자 최가은`, `102 B라인 반장 강태오`, `102 B라인 조장 이나경`, `102 B라인 작업자 박서준`, `102 관리자 김하린`으로 남겼다. 각 계정은 로그인 성공 이력을 `activity_history`에 남겼다.
- 실행 전 누적은 `documents` 1609건, `document_versions` 2355건, `field_comments` 1437건, `field_comment_attachments` 111건, `report_sources` 260건, `document_view_logs` 2144건, `activity_history` 78860건, `work_sequence_boards` 117건, `work_sequence_items` 234건, `work_sequence_change_history` 587건, `notifications` 1576건, `server_sync_queue` 804건이었다.
- 실행 후 누적은 `documents` 1619건, `document_versions` 2366건, `field_comments` 1461건, `field_comment_attachments` 114건, `report_sources` 278건, `document_view_logs` 2156건, `activity_history` 78943건, `work_sequence_boards` 118건, `work_sequence_items` 238건, `work_sequence_change_history` 592건, `notifications` 1586건, `server_sync_queue` 854건이다.
- 오늘 날짜 `2026-07-09` 기준 인수인계 문서 4건과 사진 문서 4건을 추가해 오늘 날짜 폴더 누적은 인수인계 5건, 사진 5건이 되었다. 테스트 파일은 13개가 로컬 `Files` 하위 산출물로 남았다.
- FieldComment는 24건을 추가했고 상태 분포는 `NEW` 12건, `ANALYZED` 4건, `REVIEWED` 4건, `SELECTED` 4건이다. 신호등식 기록은 `green` 8건, `yellow` 8건, `red` 8건으로 남겼다.
- `102 사람형 스모크 작업순서 20260709-085509` 보드 1건과 작업 항목 4건을 추가했다. 작업순서 변경 이력은 5건 증가했다.
- AI 근거 축적 보고서 문서 2건을 만들고 `report_sources` 18건을 연결했다. source 구성은 FieldComment 8건, 문서 6건, 작업순서 이력 4건이다.
- 과거 날짜 무작위 검증은 기존 `인수인계/2026-07-08` 문서 `doc-7485b983de164d9b9aeb56a8385ee7dd`의 버전을 v2에서 v3으로 증가시켰다. 과거 날짜 폴더와 과거 날짜 문서는 새로 만들지 않았다.
- FastAPI pytest는 `services/api`에서 51개 테스트를 실행해 51개 모두 통과했다. 이 실행 환경에는 `dotnet` 명령이 없어 WPF C# 스모크 테스트는 실행하지 못했다.

## 산출물 보존과 Git 점검

테스트가 생성한 DB, 로그, 입력 파일, 출력 파일은 보존한다. 단, Git에는 다음 원칙을 적용한다.

- `data/local/**/*.sqlite`와 `services/api/data/**/*.sqlite`는 테스트/개발 검증 DB로 추적될 수 있다.
- PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/`, `services/api/storage/`, `bin/`, `obj/` 하위 파일은 Git 제외 대상이다.
- 새 테스트 산출물 경로가 생기면 삭제하지 말고 먼저 `.gitignore` 제외 규칙을 추가한다.
- 이미 Git에 잡힌 테스트 산출물은 파일을 삭제하지 말고 `git rm --cached`로 추적만 해제한다.

표준 스크립트의 Git 점검은 금지 패턴이 `git status`나 추적 파일 목록에 잡히면 실패한다. 실패 메시지는 보존 대상 파일을 지우라는 뜻이 아니라 `.gitignore` 보강 또는 추적 해제가 필요하다는 뜻이다.

## WPF MSI 패키징 검증

WPF MSI는 Windows 배포 준비 PC에서 다음 순서로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.files.txt
git status --short --untracked-files=all
```

`.files.txt`에는 앱 실행 파일, `.deps.json`, `.runtimeconfig.json`, 앱 DLL, 의존 DLL, 네이티브 DLL만 있어야 한다. 다음 항목이 포함되면 `package-wpf-msi.ps1`가 실패해야 한다.

- 로컬 SQLite, WAL, SHM, DB 파일
- `Data\`, `Files\`, `storage\`, `logs\` 계열 경로
- `test`, `smoke`, `sample-registration`, `customer`가 들어간 파일
- PDF, Office, HWP, DWG, 이미지, 압축 파일, TXT/MD 같은 고객 파일 또는 테스트 산출물

self-contained 패키지가 필요한 PC는 별도 MSI로 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
Get-Content .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.files.txt
```

설치 후에는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고 앱을 실행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

검증 기준은 다음과 같다.

- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`에는 실행 파일과 의존 파일만 있다.
- `C:\Program Files\FlowNote\Client\FlowNote.Windows.App` 아래에는 `flownote.local.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, `Files\`가 생기지 않는다.
- `C:\FlowNote\LocalData\flownote.local.sqlite`와 `C:\FlowNote\LocalData\Files`가 생성된다.
- .NET Windows Desktop Runtime이 없는 PC에서는 framework-dependent MSI 실행 실패를 기록하고, self-contained MSI 실행 결과를 별도로 기록한다.
- WebView2 Runtime이 없는 PC에서는 문서 뷰어 실패 안내가 표시되는지 확인하고, WebView2 Runtime 설치 후 같은 문서 열람이 성공하는지 기록한다.
- `git status`에서 `artifacts\wpf-msi`, publish 산출물, MSI 파일, `.wixpdb`가 추적 대상으로 잡히지 않는다.

설치 후 자동 점검은 다음 스크립트로 수행한다. 이 스크립트는 MSI 산출물 목록의 금지 패턴, 설치 폴더의 로컬 DB/`Files` 혼입 여부, `FLOWNOTE_LOCAL_DATA_DIR` 기준 로컬 데이터 생성 여부, .NET Windows Desktop Runtime, WebView2 Runtime, 선택적 서명 검증을 확인한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"
```

framework-dependent MSI 실패 양상은 .NET Windows Desktop Runtime이 없는 Windows PC에서 다음 기준으로 남긴다.

- MSI 설치 자체가 성공하더라도 앱 실행 시 .NET Desktop Runtime 요구 오류가 표시되는지 기록한다.
- `dotnet --list-runtimes` 결과에 `Microsoft.WindowsDesktop.App 10.`이 없는 상태임을 기록한다.
- 같은 PC에서 self-contained MSI 설치 후 앱 실행 성공 여부를 별도로 기록한다.

WebView2 Runtime 유무 검증은 같은 PDF 문서로 두 번 수행한다.

- WebView2 Runtime 미설치 또는 제거 상태에서 문서를 열어 `문서 뷰어를 시작할 수 없습니다.` 안내가 표시되는지 확인한다.
- Microsoft Edge WebView2 Runtime 설치 후 같은 문서가 WebView2 PDF 뷰어로 표시되고 저장/인쇄/외부 창 열기 차단이 유지되는지 확인한다.

코드 서명 검증은 서명 인증서가 준비된 배포 준비 PC에서 수행한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

서명 인증서가 준비된 PC에서는 같은 설치 후 점검에 `-CheckSignature`를 추가한다.

```powershell
.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -CheckSignature
```

## Windows MSI 실기 검증 기록

2026-07-08 KST 기준 현재 이 저장소 작업 환경은 macOS이며 `pwsh`, `dotnet`, `wix`, `msiexec`, `signtool`이 없어 Windows MSI 실기 검증을 완료할 수 없다. 아래 기록은 Windows 배포 준비 PC와 설치 대상 PC에서 채운 뒤 운영 배포 확정 근거로 사용한다. 실제 실행 전까지 MSI 운영 배포 상태는 `대기`다.

### 실행 명령

배포 준비 PC에서 기본 MSI와 self-contained MSI를 모두 생성한다.

```powershell
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64
.\scripts\package-wpf-msi.ps1 -ProductVersion 0.1.0 -Runtime win-x64 -SelfContained
```

설치 대상 PC에서는 `FLOWNOTE_LOCAL_DATA_DIR`를 설치 폴더 밖으로 지정하고, 앱을 한 번 실행해 로컬 DB와 `Files\` 생성까지 확인한 뒤 자동 점검을 수행한다.

```powershell
setx FLOWNOTE_LOCAL_DATA_DIR "C:\FlowNote\LocalData" /M
$env:FLOWNOTE_LOCAL_DATA_DIR = "C:\FlowNote\LocalData"
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

msiexec /x .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
msiexec /i .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64-self-contained.msi
& "C:\Program Files\FlowNote\Client\FlowNote.Windows.App\FlowNote.Windows.App.exe"

.\scripts\verify-wpf-msi-install.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -SelfContained `
  -InstallFolder "C:\Program Files\FlowNote\Client\FlowNote.Windows.App" `
  -LocalDataDir "C:\FlowNote\LocalData"

git status --short --untracked-files=all
```

서명 인증서가 준비된 경우에는 `-Sign`으로 패키징하고 EXE와 MSI를 모두 검증한다.

```powershell
.\scripts\package-wpf-msi.ps1 `
  -ProductVersion 0.1.0 `
  -Runtime win-x64 `
  -Sign `
  -SigningCertificateSubjectName "FlowNote 코드서명 인증서 표시 이름"

signtool verify /pa .\artifacts\wpf-msi\publish\FlowNote.Windows.App\FlowNote.Windows.App.exe
signtool verify /pa .\artifacts\wpf-msi\FlowNote.Windows.App-0.1.0-win-x64.msi
```

### 결과 표

| 항목 | 상태 | 기록할 증거 |
| --- | --- | --- |
| 기본 MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| self-contained MSI 생성 | 대기 | MSI 경로, 파일 크기, `Get-FileHash` SHA256 |
| 기본 MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| self-contained MSI 포함 파일 금지 패턴 0건 | 대기 | `.files.txt` 경로, 금지 패턴 검사 결과 |
| 설치 폴더에 실행 파일과 의존 파일만 존재 | 대기 | `verify-wpf-msi-install.ps1` 출력 |
| 로컬 DB와 `Files\`가 `C:\FlowNote\LocalData`에만 생성 | 대기 | `verify-wpf-msi-install.ps1` 출력, 실제 경로 |
| .NET Windows Desktop Runtime 없는 PC의 framework-dependent 실행 실패 양상 | 대기 | `dotnet --list-runtimes` 결과, 오류 메시지 또는 스크린샷 설명 |
| 같은 PC의 self-contained MSI 실행 결과 | 대기 | 실행 성공/실패, 오류 메시지 |
| WebView2 Runtime 미설치 상태 PDF 열람 안내 | 대기 | 안내 문구, PC명, Windows 버전 |
| WebView2 Runtime 설치 후 같은 PDF 정상 열람 | 대기 | WebView2 버전, 열람 결과, 다운로드/인쇄/외부 창 차단 유지 여부 |
| 코드 서명 검증 | 선택 | 인증서 주체 또는 지문, `signtool verify /pa` 결과 |
| Git 산출물 제외 확인 | 대기 | `git status --short --untracked-files=all` 출력 |

### 배포 판정

다음 조건을 모두 만족하면 Windows WPF MSI 운영 배포 조건을 충족한 것으로 본다.

- 기본 MSI와 self-contained MSI가 모두 생성된다.
- MSI 포함 파일 목록에 SQLite, WAL/SHM, `Data\Files`, `storage`, `logs`, 테스트/샘플/고객 파일이 없다.
- 설치 폴더에는 실행 파일과 의존 파일만 있고, 로컬 DB와 `Files\`는 지정한 LocalData 경로에만 생성된다.
- framework-dependent MSI는 .NET Windows Desktop Runtime 필요 조건을 명확히 드러내고, 런타임 없는 PC에는 self-contained MSI를 배포 기준으로 선택할 수 있다.
- WebView2 Runtime 유무에 따른 안내와 설치 후 정상 PDF 열람이 확인된다.
- 서명 인증서가 준비된 배포에서는 EXE와 MSI가 모두 `signtool verify /pa`를 통과한다.
- Git 상태에 빌드/배포 산출물과 테스트 산출물이 추적 대상으로 잡히지 않는다.

## 현재 비Windows 환경 확인

2026-07-08 KST 기준 현재 macOS 개발 환경에서는 `wix`, `pwsh`, `dotnet`, `msiexec`, `signtool`이 없어 실제 MSI 생성과 설치 검증은 수행하지 못했다. 대신 다음 항목을 확인했다.

- `dotnet publish` framework-dependent: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet publish` self-contained: `-p:EnableWindowsTargeting=true`, `win-x64`, 성공
- `dotnet build` WPF 앱: 성공, 경고 0개
- `dotnet build` WPF 스모크 테스트: 성공, NuGet 취약성 데이터 조회 경고 2개
- `artifacts/wpf-msi` 하위 파일명 기준 금지 패턴 검사: 0건

위 항목은 이전 비Windows 사전 점검 기록이며, 운영 배포 확정 근거로는 부족하다. 남은 실기 검증은 Windows 배포 준비 PC 또는 현장 검증 PC에서 `package-wpf-msi.ps1` 기본 MSI와 `-SelfContained` MSI를 실제 생성하고, 위 설치 후 점검 스크립트와 수동 WebView2 열람 확인으로 완료한다.
