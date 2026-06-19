# Packages

여러 앱과 서비스가 공유할 수 있는 코드를 보관하는 영역이다.

## 하위 영역

- `shared/`: 공통 도메인 모델, API 계약, 검증 규칙
- `ui/`: WPF/Avalonia 클라이언트에서 참고할 공통 UI 자원, 아이콘, 디자인 토큰

패키지는 WPF/Avalonia 클라이언트와 Python FastAPI 서버 사이에서 실제로 공유할 필요가 생길 때 추가한다. 독립 Web UI를 위한 패키지는 신규 개발하지 않는다.
