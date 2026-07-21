# API Database

FastAPI 서버의 SQLite 스키마 설명 영역이다. 실제 생성 기준은 코드이며, 문서는 2026-07-21 현재 모델을 따라간다.

## 현재 코드 기준

- 연결 모듈: `app/db/session.py`
- ORM 모델: `app/db/models.py`
- 초기화 모듈: `app/db/init_db.py`
- 스키마 설명: `migrations/0001_initial_mvp_schema.md`

앱 시작 시 먼저 DB 스키마 소유권을 확인한 뒤 `Base.metadata.create_all()`로 테이블을 보장하고, `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다. 기존 WPF `documents`/`document_versions` 형태를 감지하면 서버 테이블 생성 전에 시작을 거부한다. 기존 서버 SQLite DB 호환을 위해 일부 컬럼과 제약은 초기화 과정에서 보정한다.

## 주요 테이블

2026-07-21 현재 ORM 생성 기준은 다음 52개 테이블이다.

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
- `work_sequence_change_history`, `work_sequence_mutation_receipts`, `work_sequence_notification_candidates`
- `notification_channels`, `notification_channel_members`, `channel_messages`
- `handovers`, `handover_receipts`
- `reports`, `report_sources`
- `ai_search_candidates`
- `ai_search_evaluation_runs`
- `ai_search_evaluation_cases`
- `ai_search_ground_truth_cases`
- `ai_search_ground_truth_provenance`
- `ai_ground_truth_dataset_versions`
- `ai_ground_truth_dataset_cases`
- `ai_evaluation_dataset_bindings`
- `ai_prompt_versions`, `ai_queries`
- `ai_query_evidence_candidates`, `ai_query_citations`
- `ai_call_attempts`, `ai_transfer_approvals`, `ai_sensitive_data_policies`
- `ai_operational_policies`, `ai_provider_onboarding_reviews`, `ai_operation_audit_events`, `ai_retention_audits`
- `document_access_logs`
- `controlled_copy_grants`
- `android_document_view_grants`
- `activity_history`

`ai_queries` 계열은 운영 provider 구현이 아니라 기본 비활성 외부 호출 경계의 질의, 근거 snapshot, 인용, 호출 시도와 전송 승인 감사 모델이다. `ai_sensitive_data_policies`는 고객·현장별 금칙어와 고객 식별자 정책 버전을 저장하고, 현재 활성 정책을 provider 경계의 원천 필터에 적용한다. `ai_operational_policies`는 전역/현장 kill switch, 호출·비용 한도, 보존 기간과 감사 내보내기 허용 여부를 저장한다. `ai_provider_onboarding_reviews`는 provider/model별 계약·보존·학습·지역·TLS·장애·비용·kill switch 체크리스트와 기술·보안·법무·고객의 승인 또는 대기 결정을 version별로 보존한다. `ai_operation_audit_events`는 승인·프롬프트·정책 변경을 정제 메타데이터로 남기고, `ai_retention_audits`는 만료 질의 payload 비식별화와 응답 원문 삭제 결과를 보존한다. `controlled_copy_grants`는 원본 티켓 대신 SHA-256 hash를 저장하고 공개 문서 버전, 사용자, 인증 세션, 선택적 승인 단말, 만료와 소비 상태를 연결한다. `android_document_view_grants`는 승인 단말에 묶인 Android 앱 내부 열람용 1회 grant와 무결성 계약을 보존한다.

`work_sequence_boards.board_revision`은 보드 aggregate 변경을 직렬화한다. `work_sequence_change_history`는 mutation key와 적용 revision을 정확히 한 건씩 보존하고, `work_sequence_mutation_receipts`는 intent hash·결과 revision·change ID·최초 응답 snapshot을 저장해 동일 key 재시도가 새 이력을 만들지 않게 한다.

## 로컬 경로

- 개발 DB 기본값: `services/api/data/flownote.sqlite3`
- 테스트 DB 기본값: `services/api/data/flownote.test.sqlite3`
- 파일 저장소 기본값: `services/api/storage/`

서버 DB 경로는 WPF `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`로 결정되는 로컬 DB 경로와 달라야 한다. 두 DB는 문서 테이블 이름이 일부 같아도 PK와 FK 계약이 다른 독립 스키마다.

실제 SQLite DB, 테스트 로그, 업로드 파일은 검증 산출물이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.
