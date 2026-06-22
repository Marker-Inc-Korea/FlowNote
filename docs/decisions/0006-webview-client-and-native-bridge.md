# 0006. WebView 중심 클라이언트와 네이티브 브릿지

## 상태

Superseded by [0020. 사내 서버형 FastAPI와 Windows WPF 클라이언트 전환](./0020-internal-server-fastapi-native-client.md)

## 과거 결정 요약

이 문서는 과거에 독립 Web UI를 만들고 Android/Windows 앱에서 WebView로 재사용하려던 결정을 기록한 ADR이다.

## 대체 결정

새 방향에서는 독립 Web UI와 WebView 기반 공통 UI를 개발하지 않는다. 프론트엔드는 Windows WPF 앱 하나로 구현하고, 백엔드는 Python FastAPI 서버로 진행한다.

로컬 파일 감시, 파일 선택, 뷰어 자동 닫힘, 다운로드 차단은 앱 네이티브 기능과 서버 감사 로그를 함께 사용해 처리한다.
