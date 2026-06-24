# Database

이 폴더는 Python FastAPI 서버의 SQLite 스키마와 마이그레이션 초안을 둔다.

현재 서버 코드는 SQLAlchemy 모델을 기준으로 시작 시 테이블을 생성한다.

- 연결 모듈: `app/db/session.py`
- ORM 기준 모델: `app/db/models.py`
- 초기화 모듈: `app/db/init_db.py`
- 마이그레이션 초안: `migrations/0001_initial_mvp_schema.md`

로컬 개발 DB 기준:

- 운영 개발 DB: `services/api/data/flownote.sqlite3`
- 테스트 DB: `services/api/data/flownote.test.sqlite3`

실제 SQLite DB 파일과 테스트 기록은 로컬 산출물이므로 커밋 대상이 아니다. 다만 테스트 진행 중 생성된 파일은 삭제하지 않고 보존한다.
