# Windows App

Windows 영역은 FlowNote의 유일한 활성 클라이언트 개발 위치이다. 클라이언트 앱은 Windows WPF 기반 설치형 앱으로 제작한다.

## 예상 책임

- 관리자 로그인
- 문서 조회와 미리보기
- 지정 파일 또는 폴더 감시
- 변경 감지 파일을 새 버전 업로드 후보로 표시
- 변경 사유와 버전명을 입력한 뒤 업로드 확정

현장 사용자용 뷰어 전용 단말기에는 파일 감시 기능을 넣지 않는다.

## 기술 기준

- UI 프레임워크: WPF
- UI 표시: 네이티브 앱 화면
- 로컬 파일 감시: WPF 네이티브 기능
- 서버 연동: Python FastAPI 서버와 REST API로 통신

## 디렉터리

- `src/FlowNote.Windows.App/`: Windows WPF 앱 진입점
- `src/FlowNote.Windows.Core/`: 파일 감시, API 클라이언트, 로컬 보안 제어 같은 공통 로직
- `docs/`: Windows 앱 구현 메모와 파일 감시 정책

## 현재 구현 상태

현재 `src/FlowNote.Windows.App/`에는 WPF 기반 탐색기형 셸 화면이 있다.

- 상단: 앱 이름과 기본 작업 버튼 영역
- 좌측: 문서 구조 탐색용 트리 영역
- 오른쪽 작업 영역: 검색 입력, 파일 목록, Drag & Drop 업로드 후보 추가
- 하단: 현재 셸 상태 표시 영역
- 시작 화면: 로그인 창. 로그인 성공 후에만 탐색기 화면을 연다.

`src/FlowNote.Windows.Core/Explorer/`에는 화면 바인딩을 위한 임시 탐색기 모델이 있다.

- `ExplorerFolder`: 좌측 트리용 폴더 모델
- `ExplorerDocument`: 중앙 문서 목록용 문서 모델
- `UploadCandidate`: 우측 업로드 후보 목록용 파일 모델
- `ExplorerWorkspace`: WPF 화면에 표시할 탐색기 작업 공간 상태

`src/FlowNote.Windows.Core/Storage/`에는 로컬 SQLite 초기화와 서비스 묶음이 있다.

- 로컬 DB 경로: 앱 빌드 출력 폴더의 `Data\flownote.local.sqlite`
- 소스 시드 DB: `apps/windows/src/FlowNote.Windows.App/Data/flownote.local.sqlite`
- 기본 계정: `admin`
- 기본 비밀번호: `1234`
- 기본 루트 폴더: `Root`
- 루트 아래 기본 폴더: `문서`, `인수인계`, `작업순서`, `사진`
- 기본 폴더 정책: 네 개 기본 폴더는 시스템 폴더로 처리하며 삭제할 수 없다.
- `문서` 하위 기본 분류 폴더: `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서`
- 문서 분류 정책: `문서` 폴더에 파일을 등록하면 파일명과 제목 기준으로 위 분류 폴더 중 하나에 자동 배치한다.
- 폴더별 등록 규칙: `인수인계`와 `사진`은 파일 등록 시 `yyyy-MM-dd` 형식의 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- 폴더별 등록 규칙: `작업순서`는 파일명에서 확장자를 제외한 값을 작업 제목으로 자동 생성한다.

`src/FlowNote.Windows.Core/Auth/`, `Documents/`, `Folders/`에는 로그인, 문서 등록, 폴더 관리 기본 서비스가 있다.

파일 내용 보기는 목록을 더블 클릭했을 때 별도 보기 창으로 연다. 보기 창에서는 텍스트 파일과 사진 파일을 미리 볼 수 있고, 저장된 문서에는 코멘트를 남길 수 있다. 코멘트를 저장하면 문서 본문 아래의 누적 코멘트 영역에 내용이 추가되고 SQLite의 문서 버전도 함께 올라간다.

이 구현은 실제 서버 연동, 업로드 확정 API 호출, 파일 감시, 권한별 다운로드 제어를 포함하지 않는다. Drag & Drop은 파일 목록에 로컬 업로드 후보를 추가하는 단계이며, 후속 작업에서 FastAPI 업로드 계약과 연결한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

스모크 테스트는 `admin / 1234` 로그인, 잘못된 비밀번호 거부, 기본 폴더 자동 생성, `문서` 하위 분류 폴더 자동 생성, 기본 폴더 삭제 차단, 폴더 생성/목록, 문서 등록/목록, 코멘트 저장에 따른 문서 버전 증가, `문서` 파일의 분류 폴더 자동 배치, `인수인계`와 `사진`의 날짜 하위 폴더 생성, `작업순서`의 파일명 기반 작업 제목 생성, 업로드 후보 파일 정보 생성, 업로드 후보의 파일 목록 추가 흐름을 확인한다.
