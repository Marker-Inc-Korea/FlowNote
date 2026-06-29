# 0001 Initial MVP Schema

이 문서는 FastAPI 서버의 첫 SQLite MVP 스키마 기준을 설명한다. 실제 테이블 생성 기준은 `services/api/app/db/models.py`의 SQLAlchemy 모델이며, 앱 시작 시 `services/api/app/db/init_db.py`가 `Base.metadata.create_all()`로 테이블을 보장한다.

## Version

- `schema_migrations.version`: `0001_initial_mvp_schema`
- 목적: 문서, 파일 객체, 버전, 사용자/권한 기초, 태그, 현장 코멘트, 첨부, 작업순서판, 작업내역, 보고서, 접근 로그를 위한 MVP 메타데이터 테이블 생성

## Tables

| Table | Purpose |
| --- | --- |
| `schema_migrations` | 적용된 스키마 버전 기록 |
| `user_accounts` | 로그인 계정, 비밀번호 해시, 단일 role, 활성 상태 |
| `roles` | 역할 정의 후보 |
| `user_roles` | 계정과 역할 연결 후보. 현재 API 권한 판단은 `user_accounts.role`을 우선 사용 |
| `operator_profiles` | 실제 작업자, 작업그룹, 대리 등록 주체 |
| `file_objects` | 서버 로컬 `storage/`의 파일 참조와 해시/크기/MIME |
| `documents` | 문서 메타데이터, 상태, 최신 버전, 공개 버전 |
| `document_versions` | 문서 버전, 변경 사유, 최신/공개 여부 |
| `tag_definitions` | 설비, 품목, 공정, 오류 유형, 라인, 위치, 사용자 정의 태그 사전 |
| `document_tags` | 문서와 태그 연결 |
| `terminal_devices` | 현장/관리자 단말기 등록 기준 |
| `field_notes` | 현장 코멘트 원천 이력과 관리자 정리/분석 필드 |
| `field_note_attachments` | FieldNote 사진/첨부 파일 연결 |
| `comment_templates` | 현장 입력용 정형 문구 |
| `work_records` | 작업내역 헤더 |
| `work_record_versions` | 작업내역 버전 |
| `work_sequence_boards` | 관리자 입력 기준 작업순서판 |
| `work_sequence_items` | 작업순서 항목 |
| `work_sequence_change_history` | 작업순서 생성, 항목 추가, 순서/상태 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 변경 알림 이벤트 후보 |
| `reports` | 관리자 보고서 |
| `report_sources` | 보고서 원천 데이터 추적 |
| `document_access_logs` | 문서 열람, 닫힘, 다운로드 차단 등 접근 로그 |
| `activity_history` | 문서 상태 변경, 공개 처리, 작업순서 알림 후보 등 활동 이력 |

## Notes

- SQLite를 우선 사용하고, 운영 규모가 커지면 PostgreSQL 확장을 검토한다.
- 업로드 파일은 DB에 직접 저장하지 않고 `storage/` 아래 파일 참조만 `file_objects`에 저장한다.
- 문서 업로드 저장 키는 `documents/{document_id}/v{version_no}/{uuid}_{safe_filename}` 형식이다.
- 새 문서 버전 등록 시 `change_reason`은 필수이다.
- 문서 업로드와 새 버전 등록은 자동 공개하지 않는다. 공개 버전은 별도 publish API로 지정한다.
- `field_notes`는 `document_id`, `structure_item_id`, `work_record_id` 중 하나 이상의 연결 대상이 필요하다.
- 현재 서버 role 허용값은 `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`이다.
