# API Database

FastAPI 서버의 SQLite 스키마 설명 영역이다. 실제 생성 기준은 코드이며, 문서는 2026-07-14 현재 모델을 따라간다.

## 현재 코드 기준

- 연결 모듈: `app/db/session.py`
- ORM 모델: `app/db/models.py`
- 초기화 모듈: `app/db/init_db.py`
- 스키마 설명: `migrations/0001_initial_mvp_schema.md`

앱 시작 시 `Base.metadata.create_all()`로 테이블을 보장하고, `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다. 기존 SQLite DB 호환을 위해 일부 컬럼과 제약은 초기화 과정에서 보정한다.

## 주요 테이블

- `schema_migrations`
- `user_accounts`, `roles`, `user_roles`
- `auth_sessions`
- `operator_profiles`
- `file_objects`
- `documents`, `document_versions`
- `tag_definitions`, `document_tags`
- `terminal_devices`
- `field_comments`, `field_comment_attachments`
- `comment_templates`
- `work_records`, `work_record_versions`
- `work_sequence_boards`, `work_sequence_items`
- `work_sequence_change_history`, `work_sequence_notification_candidates`
- `notification_channels`, `notification_channel_members`, `channel_messages`
- `handovers`, `handover_receipts`
- `reports`, `report_sources`
- `ai_search_candidates`
- `ai_search_evaluation_runs`
- `ai_search_evaluation_cases`
- `ai_search_ground_truth_cases`
- `ai_prompt_versions`, `ai_queries`
- `ai_query_evidence_candidates`, `ai_query_citations`
- `ai_call_attempts`, `ai_transfer_approvals`, `ai_sensitive_data_policies`
- `document_access_logs`
- `controlled_copy_grants`
- `activity_history`

`ai_queries` 계열은 운영 provider 구현이 아니라 기본 비활성 외부 호출 경계의 질의, 근거 snapshot, 인용, 호출 시도와 전송 승인 감사 모델이다. `ai_sensitive_data_policies`는 고객·현장별 금칙어와 고객 식별자 정책 버전을 저장하고, 현재 활성 정책을 provider 경계의 원천 필터에 적용한다. `controlled_copy_grants`는 원본 티켓 대신 SHA-256 hash를 저장하고 공개 문서 버전, 사용자, 인증 세션, 선택적 승인 단말, 만료와 소비 상태를 연결한다.

## 로컬 경로

- 개발 DB 기본값: `services/api/data/flownote.sqlite3`
- 테스트 DB 기본값: `services/api/data/flownote.test.sqlite3`
- 파일 저장소 기본값: `services/api/storage/`

실제 SQLite DB, 테스트 로그, 업로드 파일은 검증 산출물이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.
