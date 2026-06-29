# API Database

이 폴더는 FlowNote FastAPI 서버의 SQLite 스키마와 마이그레이션 초안을 보관한다.

## 현재 코드 기준

서버 DB는 SQLAlchemy 모델을 기준으로 앱 시작 시 생성된다.

- 연결 모듈: `app/db/session.py`
- ORM 모델: `app/db/models.py`
- 초기화 모듈: `app/db/init_db.py`
- 마이그레이션 초안: `migrations/0001_initial_mvp_schema.md`

앱 시작 시 `Base.metadata.create_all()`로 테이블을 보장하고, `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다. SQLite 기존 DB 호환을 위해 `user_accounts`의 `username`, `role`, `is_active` 컬럼과 역할 제약도 보정한다.

## 주요 테이블

- `user_accounts`, `roles`, `user_roles`
- `operator_profiles`
- `file_objects`
- `documents`, `document_versions`
- `tag_definitions`, `document_tags`
- `terminal_devices`
- `field_notes`, `field_note_attachments`
- `comment_templates`
- `work_records`, `work_record_versions`
- `work_sequence_boards`, `work_sequence_items`
- `work_sequence_change_history`, `work_sequence_notification_candidates`
- `reports`, `report_sources`
- `document_access_logs`
- `activity_history`

## 로컬 경로

- 개발 DB 기본값: `services/api/data/flownote.sqlite3`
- 테스트 DB 기본값: `services/api/data/flownote.test.sqlite3`
- 파일 저장 기본값: `services/api/storage/`

실제 SQLite DB 파일, 테스트 로그, 테스트 업로드 파일은 로컬 검증 산출물이다. 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.
