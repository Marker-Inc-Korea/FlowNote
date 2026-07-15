# 0001 Initial FlowNote API Schema

FastAPI 서버의 첫 SQLite 스키마 설명이다. 실제 테이블 생성 기준은 2026-07-15 현재 `services/api/app/db/models.py`이며, 앱 시작 시 `services/api/app/db/init_db.py`가 `Base.metadata.create_all()`로 테이블을 보장한다.

## Version

- `schema_migrations.version`: `0001_initial_mvp_schema`
- 목적: 문서, 파일 객체, 버전, 사용자/권한, 인증 세션, 태그, FieldComment, 첨부, 작업순서, 채널/인수인계, 보고서, AI 검색 근거 후보·회귀 평가, 외부 AI 안전장치·감사, controlled copy, 접근 로그, 활동 이력을 위한 서버 메타데이터 테이블 생성

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
| `notification_channels`, `notification_channel_members` | Shared business channels and channel membership |
| `channel_messages` | Traceable channel messages for document, FieldComment, work sequence, report, and handover events |
| `handovers`, `handover_receipts` | Handover records and recipient status |
| `reports`, `report_sources` | Reports and traceable sources |
| `ai_search_candidates` | Traceable evidence candidates for search and summary before AI advice |
| `ai_search_evaluation_runs` | Offline ground-truth regression run and provider-start metrics |
| `ai_search_evaluation_cases` | Expected/actual evidence snapshots, exclusions, and ranking hashes by question |
| `ai_search_ground_truth_cases` | Human-approved scoped question categories, expected/excluded evidence, allowed rank, and as-of criteria |
| `ai_prompt_versions` | Approved immutable prompt versions by allowed purpose |
| `ai_queries` | AI query text/hash, purpose, status, response storage policy, and retention metadata |
| `ai_query_evidence_candidates` | Query-time evidence snapshots independent of later candidate rebuilds |
| `ai_query_citations` | Validated claim-to-evidence citation records |
| `ai_call_attempts` | Sanitized provider/model attempt status and error audit |
| `ai_transfer_approvals` | Customer/site/provider/model scoped external transfer approvals |
| `ai_sensitive_data_policies` | Versioned customer/site deny terms and customer identifiers applied before provider payload creation |
| `ai_operational_policies` | Global/site kill switches, request/concurrency/timeout/cost limits, retention, and audit-export policy |
| `ai_operation_audit_events` | Sanitized approval, prompt, and operational-policy change audit events |
| `ai_retention_audits` | Query-payload de-identification and response-text deletion audit metadata |
| `document_access_logs` | Document view/download/auto-close access logs |
| `controlled_copy_grants` | Hashed one-time token bound to a published version, user, auth session, expiry, size, and hash |
| `activity_history` | Server activity history |

## Notes

- Uploaded files are stored under `storage/`; the DB stores metadata and storage keys.
- Creating or uploading a version does not automatically publish the document.
- Controlled copy can only target the current published version; grants expire quickly and are consumed once.
- FieldComment must reference at least one of document, structure item, or work record.
- External AI calls are disabled by default. A generic HTTPS JSON adapter exists only for explicit `test` scope; no provider-specific production client or production activation is configured.
- The active `ai_sensitive_data_policies` row for a customer/site scope adds deny terms and customer identifiers to the provider-boundary content filter.
- External AI operational policy, approval, prompt lifecycle, audit, and retention APIs are restricted to `system-admin`; provider credentials remain outside these tables.
- Current server role values are `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`.
