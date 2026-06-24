# 0001 Initial MVP Schema

이 문서는 FastAPI 서버의 첫 SQLite 스키마 초안이다. 실제 테이블 생성 기준은 `app/db/models.py`의 SQLAlchemy 모델이며, 앱 시작 시 `app/db/init_db.py`가 `Base.metadata.create_all()`로 테이블을 보장한다.

## Version

- `schema_migrations.version`: `0001_initial_mvp_schema`
- 목적: 문서, 파일 객체, 버전, 권한 기초, 현장 코멘트, 작업내역, 보고서 원천 추적을 위한 MVP 메타데이터 테이블 생성

## Tables

| Table | Purpose |
| --- | --- |
| `schema_migrations` | 적용된 스키마 버전 기록 |
| `user_accounts` | 로그인 계정 |
| `roles` | 역할 정의 |
| `user_roles` | 계정과 역할 연결 |
| `operator_profiles` | 실제 작업자, 작업그룹, 대리 등록 주체 |
| `file_objects` | 서버 로컬 저장소의 파일 참조 |
| `documents` | 문서 메타데이터와 공개/최신 버전 포인터 |
| `document_versions` | 문서 버전, 변경 사유, 공개 여부 |
| `tag_definitions` | 설비, 품목, 공정, 오류 유형 등 태그 사전 |
| `document_tags` | 문서와 태그 연결 |
| `terminal_devices` | 현장/관리자 단말기 |
| `field_notes` | 현장 코멘트 원천 이력과 관리자 분석 필드 |
| `field_note_attachments` | 현장 코멘트 사진/첨부 파일 연결 |
| `comment_templates` | 현장 입력용 정형 문구 |
| `work_records` | 작업내역 헤더 |
| `work_record_versions` | 작업내역 버전 |
| `reports` | 관리자 검토 보고서 |
| `report_sources` | 보고서 원천 데이터 추적 |
| `document_access_logs` | 문서 열람과 뷰어 관련 감사 로그 |

## Notes

- SQLite를 우선 사용하고, 동시성 또는 운영 규모가 커지면 PostgreSQL 확장을 고려한다.
- 업로드 파일은 DB에 저장하지 않고 `storage/` 아래 파일 참조만 `file_objects`에 저장한다.
- 새 문서 버전의 `change_reason`은 필수이다.
- `field_notes`는 최소 하나의 연결 대상(`document_id`, `structure_item_id`, `work_record_id`)을 가져야 한다.
- 문서 상태는 `WORKING`, `IN_REVIEW`, `PUBLISHED`, `ARCHIVED`, `DELETED`로 구분한다.
