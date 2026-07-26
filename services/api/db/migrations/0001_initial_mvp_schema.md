# 0001 Initial FlowNote API Schema

FastAPI 서버의 첫 SQLite 스키마 설명이다. 실제 테이블 생성 기준은 2026-07-26 현재 `services/api/app/db/models.py`와 역할별 `models_*.py`다. 앱 시작 시 `services/api/app/db/init_db.py`가 기존 WPF 로컬 스키마가 아닌지 먼저 확인한 뒤 `Base.metadata.create_all()`로 서버 테이블을 보장한다.

## Version

- `schema_migrations.version`: `0001_initial_mvp_schema`
- 목적: 문서, 파일 객체, 버전, 사용자/권한, 인증 세션, 태그, FieldComment, 첨부, 작업순서, 채널/인수인계, 보고서, 서버 복구 reconciliation, AI 검색 근거 후보·회귀 평가, 외부 AI 안전장치·감사, controlled copy, 접근 로그, 활동 이력을 위한 서버 메타데이터 테이블 생성

## Tables

| Table | Purpose |
| --- | --- |
| `schema_migrations` | Applied schema version record |
| `server_identity` | Singleton server instance ID, explicit recovery epoch, and schema/API contract range |
| `reconciliation_runs` | WPF inventory reconciliation run, recovery boundary, cursors, status, and administrator approval |
| `reconciliation_items` | Per-queue-item verdict, proposed/resolved action, server mapping/hash, and resolution audit |
| `user_accounts` | Login account, password hash, role, status |
| `roles`, `user_roles` | Role reference tables |
| `auth_sessions` | Server auth sessions, access token ID, refresh token hash |
| `operator_profiles` | Field operator/group/proxy identity |
| `file_objects` | Server-local stored file metadata |
| `documents` | Document metadata and latest/published version refs |
| `document_versions` | Version metadata, change reason, latest/published flags |
| `document_mutation_receipts` | Publish/status/tag mutation key, intent hash, applied revision, and first response snapshot |
| `tag_definitions` | Tag dictionary |
| `document_tags` | Document-tag relation |
| `terminal_devices` | Field terminal registry basis |
| `field_comments` | FieldComment source history, review/analysis fields, and server-authoritative `review_revision` |
| `field_comment_attachments` | FieldComment attachment relation |
| `field_comment_review_mutation_receipts` | Review mutation key, intent hash, result revision, and first response snapshot |
| `comment_templates` | Template text for field input |
| `work_records`, `work_record_versions` | Work record basis for later expansion |
| `work_sequence_boards`, `work_sequence_items` | Work sequence boards, aggregate `board_revision`, ordered items, and hold reasons |
| `work_sequence_change_history` | One change row per mutation key with the applied board revision |
| `work_sequence_mutation_receipts` | Mutation intent hash, result revision/change ID, and first response snapshot for idempotent retries |
| `work_sequence_notification_candidates` | Work sequence notification candidates |
| `notification_channels`, `notification_channel_members` | Shared business channels and channel membership |
| `channel_messages` | Traceable channel messages for document, FieldComment, work sequence, report, and handover events |
| `handovers`, `handover_receipts` | Handover records and recipient status |
| `reports`, `report_sources` | Reports with aggregate revision/content/source-set hashes and traceable fixed source versions/hashes |
| `report_mutation_receipts` | Report mutation key, intent/hash result, generated document/version, and first response snapshot |
| `ai_search_candidates` | Traceable evidence candidates for search and summary before AI advice |
| `ai_search_evaluation_runs` | Offline ground-truth regression run and provider-start metrics |
| `ai_search_evaluation_cases` | Expected/actual evidence snapshots, exclusions, and ranking hashes by question |
| `ai_search_ground_truth_cases` | Human-approved scoped question categories, expected/excluded evidence, allowed rank, and as-of criteria |
| `ai_search_ground_truth_provenance` | Ground-truth classification, readiness track, frozen snapshot hash, and independent two-person approval |
| `ai_ground_truth_dataset_versions` | Immutable scoped dataset version, lifecycle, coverage, replacement, and approval history |
| `ai_ground_truth_dataset_cases` | Frozen case composition and case snapshot hashes for a dataset version |
| `ai_evaluation_dataset_bindings` | One-to-one binding from an evaluation run to its approved dataset snapshot |
| `ai_prompt_versions` | Approved immutable prompt versions by allowed purpose |
| `ai_queries` | AI query text/hash, purpose, status, response storage policy, and retention metadata |
| `ai_query_legal_holds` | Query preservation order, authority reference, active/released state, and placement/release audit |
| `ai_query_evidence_candidates` | Query-time evidence snapshots independent of later candidate rebuilds |
| `ai_query_citations` | Validated claim-to-evidence citation records |
| `ai_call_attempts` | Sanitized provider/model attempt status and error audit |
| `ai_transfer_approvals` | Customer/site/provider/model scoped external transfer approvals |
| `ai_sensitive_data_policies` | Versioned customer/site deny terms and customer identifiers applied before provider payload creation |
| `ai_operational_policies` | Global/site kill switches, request/concurrency/timeout/cost limits, retention, and audit-export policy |
| `ai_provider_onboarding_reviews` | Versioned provider contract/security/legal/customer checklist and start decision |
| `ai_operation_audit_events` | Sanitized approval, prompt, and operational-policy change audit events |
| `ai_retention_audits` | Query-payload de-identification and response-text deletion audit metadata |
| `document_access_logs` | Document view/download/auto-close access logs |
| `controlled_copy_grants` | Hashed one-time token bound to a published version, user, auth session, expiry, size, and hash |
| `android_document_view_grants` | Hashed one-time Android secure-view token bound to the user, auth session, approved device, published version, media limits, expiry, size, and hash |
| `activity_history` | Server activity history |

## Notes

- Uploaded files are stored under `storage/`; the DB stores metadata and storage keys.
- Creating or uploading a version does not automatically publish the document.
- Controlled copy can only target the current published version; grants expire quickly and are consumed once.
- FieldComment must reference at least one of document, structure item, or work record.
- Document publish/status/tag writes, FieldComment review writes, and report saves use domain revisions plus immutable mutation receipts; each receipt commits with its aggregate mutation.
- Sync manifest identifies the server installation and explicit recovery epoch. Reconciliation records classify WPF queue inventory without rewriting domain source rows and require administrator approval for every proposed action.
- External AI calls are disabled by default. A generic HTTPS JSON adapter exists only for explicit `test` scope; no provider-specific production client or production activation is configured.
- The active `ai_sensitive_data_policies` row for a customer/site scope adds deny terms and customer identifiers to the provider-boundary content filter.
- External AI operational policy, approval, prompt lifecycle, audit, and retention APIs are restricted to `system-admin`; provider credentials remain outside these tables.
- Active `ai_query_legal_holds` rows prevent scheduled, bulk manual, and single-query expiry until a `system-admin` records a release.
- Current server role values are `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`.
