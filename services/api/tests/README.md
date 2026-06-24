# API Tests

이 폴더는 FlowNote FastAPI 서버 테스트를 둔다.

## 현재 테스트 범위

- 앱 시작 시 SQLite MVP 스키마 생성과 `schema_migrations` 기록
- DB 헬스체크 API
- SQLAlchemy 모델 기준 문서 버전과 FieldNote 저장
- 문서 등록 API의 파일 저장, 문서 메타데이터, 최초 버전, SHA-256, 파일 크기 기록
- 새 문서 버전 등록과 기존 최신 버전 `SUPERSEDED` 처리
- 변경 사유 필수 검증
- 인증 API 구현 전 단계의 사용자 참조 처리
- FieldNote 등록, 목록, 문서별 조회, 관리자 검토/분석 갱신
- FieldNote 대상 문서 필수 검증과 알 수 없는 문서 참조 거부

## 실행

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

테스트 SQLite DB, 테스트 로그, 테스트 업로드 파일은 보존 대상이다. 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.
