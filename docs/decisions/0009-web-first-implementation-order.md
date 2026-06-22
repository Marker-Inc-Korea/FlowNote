# 0009. Web 우선 구현 단계

## 상태

Superseded by [0020. 사내 서버형 FastAPI와 Windows WPF 클라이언트 전환](./0020-internal-server-fastapi-native-client.md)

## 과거 결정 요약

이 문서는 과거에 Web UI를 1차 구현 대상으로 두고 Android/Windows 앱을 후속 단계로 두려던 결정을 기록한 ADR이다.

## 대체 결정

새 구현 순서는 Python FastAPI 서버와 Windows WPF 클라이언트를 기준으로 다시 잡는다. 독립 Web UI는 신규 개발하지 않는다.

1차 MVP는 Python FastAPI 서버, SQLite 메타데이터 저장, 서버 로컬 storage, 문서/버전/권한/현장 코멘트 API, Windows WPF 클라이언트의 핵심 화면 흐름을 함께 검증하는 방향으로 정의한다.
