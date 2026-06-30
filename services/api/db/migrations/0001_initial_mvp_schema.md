# 0001 Initial MVP Schema

FastAPI 서버의 첫 SQLite MVP 스키마 설명이다. 실제 테이블 생성 기준은 `services/api/app/db/models.py`이며, 앱 시작 시 `services/api/app/db/init_db.py`가 `Base.metadata.create_all()`로 테이블을 보장한다.

## Version

- `schema_migrations.version`: `0001_initial_mvp_schema`
- 목적: 문서, 파일 객체, 버전, 사용자/권한, 인증 세션, 태그, FieldComment, 첨부, 작업순서, 보고서, 접근 로그, 활동 이력을 위한 MVP 메타데이터 테이블 생성

## Tables

| Table | Purpose |
| --- | --- |
| `schema_migrations` | Applied schema version record |
| `user_accounts` | Login account, password hash, role, status |
| `roles`, `user_roles` | Role reference tables |
| `auth_sessions` | Server auth sessions, access token ID, refresh token hash |
| `operator_profiles` | Field operator/group/proxy identity |
| `file_objects` | Server-local stored file metadata |
| `documents` | Document metadata and latest/published version refs |
| `document_versions` | Version metadata, change reason, latest/published flags |
| `tag_definitions` | Tag dictionary |
| `document_tags` | Document-tag relation |
| `terminal_devices` | Field terminal registry basis |
| `field_comments` | FieldComment source history and review/analysis fields |
| `field_comment_attachments` | FieldComment attachment relation |
| `comment_templates` | Template text for field input |
| `work_records`, `work_record_versions` | Work record basis for later expansion |
| `work_sequence_boards`, `work_sequence_items` | Work sequence boards and items |
| `work_sequence_change_history` | Work sequence changes |
| `work_sequence_notification_candidates` | Work sequence notification candidates |
| `reports`, `report_sources` | Reports and traceable sources |
| `document_access_logs` | Document view/download/auto-close access logs |
| `activity_history` | Server activity history |

## Notes

- Uploaded files are stored under `storage/`; the DB stores metadata and storage keys.
- Creating or uploading a version does not automatically publish the document.
- FieldComment must reference at least one of document, structure item, or work record.
- Current server role values are `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`.
