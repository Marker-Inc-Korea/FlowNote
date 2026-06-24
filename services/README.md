# Services

FlowNote 서버와 백그라운드 작업을 보관하는 영역이다.

## 하위 영역

- `api/`: Python FastAPI 기반 REST API 서버

현재 `api/`는 SQLite MVP 초기 구현으로 문서 등록/버전 등록, 서버 로컬 파일 저장 참조, FieldNote 원천 이력 API를 포함한다. 인증, 권한, 보고서, AI, MES/ERP 연동은 후속 범위이다.

추후 필요하면 문서 인덱싱, 알림 발송, 보고서 생성 같은 작업을 별도 worker로 분리할 수 있다.
