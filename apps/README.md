# Apps

FlowNote 클라이언트를 보관하는 영역이다.

클라이언트 UI는 Windows WPF 기반 설치형 네이티브 앱을 기본으로 한다. 독립 Web UI는 신규 개발하지 않으며, 로컬 제어가 필요한 기능은 클라이언트 앱에서 직접 처리한다.

## 역할

- `windows/`: 활성 Windows WPF 클라이언트
- `web/`: 신규 개발 대상이 아닌 과거 웹 UI 보존 영역

## 설계 원칙

- UI/UX 변경 대응은 Windows WPF 클라이언트의 실제 운영 화면을 기준으로 처리한다.
- 클라이언트 앱은 Windows용 하나만 제작한다.
- Android, macOS, Linux 클라이언트는 현재 제품 개발 대상이 아니다.
- 사용자 단말기에 문서 파일이 동기화되는 구조를 피한다.
- 파일 감시, 로컬 파일 선택, 알림 같은 기능은 앱 네이티브 기능으로 제공한다.
- 기존 웹 UI와 이전 Windows 코드는 각각 `web/legacy-react-vite`, `windows/legacy-zsuite`에 보존한다.
