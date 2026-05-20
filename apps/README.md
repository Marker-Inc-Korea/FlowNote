# Apps

FlowNote 클라이언트를 보관하는 영역이다.

클라이언트 UI는 웹을 기본으로 한다. Android와 Windows 앱은 WebView로 웹 UI를 표시하고, 네이티브 성능이나 로컬 제어가 필요한 기능만 브릿지를 통해 처리한다.

## 역할

- `windows/`: WPF + WebView2 기반 관리자/데스크톱 클라이언트
- `android/`: Kotlin + WebView 기반 현장 사용자 단말기
- `web/`: TypeScript + React + Vite 기반 공통 웹 UI

## 설계 원칙

- UI/UX 변경 대응은 웹 UI 중심으로 빠르게 처리한다.
- 사용자 단말기에 문서 파일이 동기화되는 구조를 피한다.
- 파일 감시, 로컬 파일 선택, 네이티브 알림 같은 기능은 앱 브릿지로 제공한다.
