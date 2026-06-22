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
- `legacy-zsuite/`: 이전 Windows 코드 보존 영역
