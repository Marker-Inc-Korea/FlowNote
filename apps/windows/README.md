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
- 중앙: 문서 목록과 검색 입력 영역
- 우측: 선택 문서 상세와 상태/버전/현장 기록 요약 영역
- 하단: 현재 셸 상태 표시 영역
- 시작 화면: 로그인 창. 로그인 성공 후에만 탐색기 화면을 연다.

`src/FlowNote.Windows.Core/Explorer/`에는 화면 바인딩을 위한 임시 탐색기 모델이 있다.

- `ExplorerFolder`: 좌측 트리용 폴더 모델
- `ExplorerDocument`: 중앙 문서 목록용 문서 모델
- `ExplorerWorkspace`: WPF 화면에 표시할 탐색기 작업 공간 상태

`src/FlowNote.Windows.Core/Storage/`에는 로컬 SQLite 초기화와 서비스 묶음이 있다.

- 로컬 DB 경로: `%LOCALAPPDATA%\FlowNote\flownote.local.sqlite`
- 기본 계정: `admin`
- 기본 비밀번호: `1234`
- 기본 루트 폴더: `Root`
- 루트 아래 기본 폴더: `문서`, `인수인계`, `작업순서`, `사진`
- 기본 폴더 정책: 네 개 기본 폴더는 시스템 폴더로 처리하며 삭제할 수 없다.

`src/FlowNote.Windows.Core/Auth/`, `Documents/`, `Folders/`에는 로그인, 문서 등록, 폴더 관리 기본 서비스가 있다.

이 구현은 실제 서버 연동, 실제 파일 업로드, 파일 감시, 권한별 다운로드 제어를 포함하지 않는다. 후속 작업에서 FastAPI 계약과 로컬 기능을 연결한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

스모크 테스트는 `admin / 1234` 로그인, 잘못된 비밀번호 거부, 기본 폴더 자동 생성, 기본 폴더 삭제 차단, 폴더 생성/목록, 문서 등록/목록 흐름을 확인한다.
