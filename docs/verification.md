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
3. `services/api`에서 FastAPI pytest 수집 개수가 50개인지 확인한다.
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

공통 SQLite `data/local/flownote.local.sqlite`에는 2026-07-08 KST 기준 `smoke-102-human-20260708-132307` 실행 기록이 누적되어 있다. 이 기록은 삭제하지 않고 이후 회귀 검증의 기준 데이터로 사용한다.

- 오늘 날짜 폴더 기준으로 `smoke-102-human-20260708-132307 라인A 인수인계`, `라인A 계량기 사진`, `라인B 야간전달` 문서가 등록되었다.
- 라인A 인수인계와 라인B 야간전달 문서는 v2가 `PUBLISHED`로 공개되었고, 라인A 계량기 사진은 FieldComment 첨부 근거 문서로 남았다.
- 과거 날짜 무작위 검증은 기존 `사진/2026-06-29` 문서 `사진당일라인A20260629113103758`의 버전을 v4로 증가시켰다. 과거 날짜 폴더와 문서는 새로 만들지 않았다.
- FieldComment 6건이 추가되었고 검토 상태는 `ANALYZED` 2건, `REVIEWED` 2건, `SELECTED` 2건으로 남았다. 사진 첨부 1건도 `field_comment_attachments`에 연결되었다.
- 보고서 문서 `smoke-102-human-20260708-132307 AI 근거 축적 보고서`가 저장되었고, `report_sources`에는 FieldComment 5건, 문서 3건, 작업순서 이력 1건이 `ai_evidence` 관계로 연결되었다.
- 문서 열람 시작/종료, 자동 닫힘, 다운로드 차단, FieldComment 생성/검토, 작업순서 연결, 보고서 저장 이벤트가 `activity_history`에 21건 남았다.

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
