# 0022. Windows 단일 클라이언트와 Python 백엔드 고정

## 상태

Accepted

## 배경

저장소에는 과거 Web UI, Android, 공통 네이티브 클라이언트 후보가 함께 남아 있어 실제 구현 대상이 분산되어 보였다. FlowNote의 초기 배포는 생산현장 PC에 설치하는 클라이언트와 사내 서버 PC 1대를 기준으로 하므로, 클라이언트 OS 범위를 명확히 줄일 필요가 있다.

## 결정

- 백엔드는 `services/api`의 Python FastAPI 서버로 구현한다.
- 클라이언트 앱은 `apps/windows`의 Windows WPF 설치형 앱 하나만 제작한다.
- Android, macOS, Linux 클라이언트는 현재 제품 개발 대상이 아니다.
- 독립 Web UI와 WebView 기반 공통 UI는 신규 개발하지 않는다.
- 과거 Web/Node/.NET 코드는 참고 이력 또는 legacy 영역으로만 본다.

## 영향

- 신규 화면과 로컬 기능은 `apps/windows` 기준으로 설계한다.
- `apps/client`와 `apps/android`의 활성 개발 문서는 제거한다.
- API, 배포, MVP, 로드맵 문서는 Python FastAPI와 Windows WPF 기준으로 해석한다.
