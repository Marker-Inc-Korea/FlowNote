# 2026-06-24 FastAPI SQLite MVP 초기 구조 작업 결과

## 작업 범위

현재 헬스체크만 있던 FastAPI 서버에 SQLite 기반 MVP 초기 구조를 추가했다.

- DB 설정: `FLOWNOTE_DATABASE_URL`, `FLOWNOTE_TEST_DATABASE_URL`, `FLOWNOTE_DATABASE_ECHO`
- DB 연결 모듈: `services/api/app/db/session.py`
- ORM 스키마 기준: `services/api/app/db/models.py`
- 시작 시 테이블 생성: `services/api/app/db/init_db.py`
- DB 헬스체크: `GET /api/v1/health/db`
- 테스트 DB 경로: `services/api/data/flownote.test.sqlite3`
- 마이그레이션 초안 문서: `services/api/db/migrations/0001_initial_mvp_schema.md`

## 구현 내용

서버 시작 시 SQLAlchemy 엔진을 만들고 SQLite 외래키 검사를 활성화한다. FastAPI lifespan에서 초기 테이블을 생성하고 `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다.

초기 테이블은 회원/역할, 작업자 프로필, 파일 객체, 문서, 문서 버전, 태그, 단말기, 현장 코멘트, 정형 문구, 작업내역, 보고서, 문서 접근 로그를 포함한다. 실제 문서 등록 API와 인증 API는 아직 구현하지 않았고, 이번 작업은 DB 연결과 테이블 생성 기준을 붙이는 단계이다.

## 보존 산출물

- 테스트 SQLite DB: `services/api/data/flownote.test.sqlite3`
- 검증 기록: `services/api/data/verification-2026-06-24.txt`
- 로컬 가상환경: `services/api/.venv`

위 산출물은 로컬 테스트 결과이며 삭제하지 않고 보존했다.

## 검증 결과

작업 위치: `services/api`

| 구분 | 명령 | 결과 |
| --- | --- | --- |
| 개발 설치/빌드 | `.\\.venv\\Scripts\\python -m pip install -e ".[dev]"` | 통과, editable wheel 생성 |
| 정적 검사 | `.\\.venv\\Scripts\\python -m ruff check .` | 통과, `All checks passed!` |
| 컴파일 확인 | `.\\.venv\\Scripts\\python -m compileall app tests` | 통과 |
| 전체 테스트 | `.\\.venv\\Scripts\\python -m pytest -q` | 통과, `2 passed` |

테스트는 앱 시작 시 DB 파일과 MVP 테이블이 생성되는지, `schema_migrations` 기록이 남는지, 최소 문서/버전/현장 코멘트 데이터가 SQLite에 저장되는지 확인한다.

## 남은 작업

- 인증 API와 세션 모델 구현
- 문서 등록/버전 업로드 API 구현
- 파일 저장소 `storage/` 저장 규칙 구현
- Alembic 정식 마이그레이션 환경 구성
- WPF 클라이언트와 FastAPI REST 연동
