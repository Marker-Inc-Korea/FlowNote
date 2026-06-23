# 0022. Windows 단일 클라이언트와 Python 백엔드 고정

## 상태

Accepted

## 배경

FlowNote의 초기 배포는 생산현장 PC에 설치하는 클라이언트와 사내 서버 PC 1대를 기준으로 하므로, 클라이언트 OS 범위를 명확히 줄일 필요가 있다.

## 결정

- 백엔드는 `services/api`의 Python FastAPI 서버로 구현한다.
- 클라이언트 앱은 `apps/windows`의 Windows WPF 설치형 앱 하나만 제작한다.
- 클라이언트 화면과 로컬 기능은 Windows WPF 앱을 기준으로 구현한다.

## 영향

- 신규 화면과 로컬 기능은 `apps/windows` 기준으로 설계한다.
- API, 배포, MVP, 로드맵 문서는 Python FastAPI와 Windows WPF 기준으로 해석한다.
