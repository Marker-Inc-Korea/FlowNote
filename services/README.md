# Services

FlowNote 서버와 백그라운드 작업을 보관하는 영역이다.

## 하위 영역

- `api/`: Python FastAPI 기반 REST API 서버

추후 필요하면 문서 인덱싱, 알림 발송, 보고서 생성 같은 작업을 별도 worker로 분리할 수 있다.
