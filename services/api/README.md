# API Service

FlowNote FastAPI 서버는 SQLite 기반 현재 REST API를 제공한다. 운영 기본 경로는 `/api/v1`이며, 파일은 서버 로컬 `storage/`에 저장한다. 보호 API는 Bearer access token과 `auth_sessions` 상태를 함께 검증한다.

이 목록은 2026-07-30 현재 OpenAPI에 등록된 132개 method/path 조합 기준이다. 외부 AI API는 provider 중립 adapter와 기본 비활성 안전장치·운영 제어·감사 경계를 제공한다. 네트워크 adapter는 `test` 환경의 별도 명시 설정에서만 생성되며 운영 기본값은 비활성이다. controlled copy와 Android secure view는 서버에 저장된 현재 공개 버전만 각 계약에 따라 1회 스트리밍한다.

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service and environment check |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/health/db` | Database health check |
| GET | `/api/v1/health/sync-manifest` | Database health and server instance/epoch/contract manifest |
| GET | `/api/v1/sync/manifest` | Server instance/epoch/contract and notification high-water cursor |
| POST | `/api/v1/sync/reconciliation-runs` | Classify a WPF queue inventory for administrator review |
| GET | `/api/v1/sync/reconciliation-runs/{run_id}` | Read a reconciliation run and all item verdicts |
| POST | `/api/v1/sync/reconciliation-runs/{run_id}/apply` | Approve every proposed action and close the run |
| POST | `/api/v1/sync/server-epoch/increment` | Increment the explicit server recovery epoch with audit history |
| POST | `/api/v1/auth/login` | Login and token issue |
| POST | `/api/v1/auth/refresh` | Refresh token rotation |
| POST | `/api/v1/auth/logout` | Revoke current session |
| GET | `/api/v1/auth/me` | Current user lookup |
| POST | `/api/v1/auth/change-password` | Required/self password change and session revocation |
| GET | `/api/v1/server-accounts` | Server account list |
| POST | `/api/v1/server-accounts` | Create server account with one-time temporary password input |
| PATCH | `/api/v1/server-accounts/{user_id}` | Change display name, role, or status |
| POST | `/api/v1/server-accounts/{user_id}/password-reset` | Reset temporary password and revoke sessions |
| GET | `/api/v1/server-accounts/{user_id}/sessions` | Active account sessions |
| POST | `/api/v1/server-accounts/{user_id}/sessions/revoke` | Revoke active account sessions |
| POST | `/api/v1/server-accounts/{user_id}/sessions/{session_id}/revoke` | Revoke one account session |
| GET | `/api/v1/terminal-devices` | Approved terminal device list |
| POST | `/api/v1/terminal-devices` | Register approved terminal device |
| GET | `/api/v1/terminal-devices/{device_id}` | Terminal device detail |
| GET | `/api/v1/terminal-devices/{device_id}/last-seen` | Terminal device last successful login |
| PATCH | `/api/v1/terminal-devices/{device_id}` | Update terminal device metadata |
| PATCH | `/api/v1/terminal-devices/{device_id}/status` | Change terminal device status |
| POST | `/api/v1/terminal-devices/{device_id}/replace` | Retire and replace terminal device |
| POST | `/api/v1/documents` | Register document and first version |
| GET | `/api/v1/documents` | Document list |
| GET | `/api/v1/documents/published` | Published document list |
| GET | `/api/v1/documents/{document_id}` | Document detail |
| GET | `/api/v1/documents/{document_id}/published` | Published version |
| PUT | `/api/v1/documents/{document_id}/tags` | Replace document tags with base revision and optional mutation key |
| PATCH | `/api/v1/documents/{document_id}/status` | Change document status with base revision and optional mutation key |
| GET | `/api/v1/documents/{document_id}/versions` | Version list |
| POST | `/api/v1/documents/{document_id}/versions` | Register new version; optional multipart `idempotencyKey` returns the existing version on retry |
| PATCH | `/api/v1/documents/{document_id}/versions/{version_id}/status` | Change version status |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/publish` | Publish selected version with base revision and optional mutation key |
| DELETE | `/api/v1/documents/{document_id}` | Soft-delete a document using its base revision and change reason |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/controlled-copy` | Issue one-time controlled copy grant for the current published version |
| GET | `/api/v1/controlled-copies/{token}` | Stream the session-bound controlled copy once |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/android-view-grants` | Issue an approved-device Android secure view grant |
| GET | `/api/v1/android-document-views/{token}/stream` | Stream the device/session-bound Android body once |
| POST | `/api/v1/documents/{document_id}/access-logs` | Register access log |
| GET | `/api/v1/documents/{document_id}/access-logs` | Access log list |
| GET | `/api/v1/tags` | Tag list |
| POST | `/api/v1/tags` | Tag create |
| POST | `/api/v1/field-comments` | FieldComment create |
| GET | `/api/v1/field-comments` | FieldComment list |
| GET | `/api/v1/field-comments/{comment_id}` | FieldComment detail |
| PATCH | `/api/v1/field-comments/{comment_id}` | Review/analyze FieldComment |
| POST | `/api/v1/field-comments/bulk-review` | Bulk assignment, due date, and review-state update |
| POST | `/api/v1/field-comments/bulk-review/preview` | Read-only validation of per-item transitions and failure reasons for up to 200 comments |
| POST | `/api/v1/field-comments/bulk-review/execute` | Partial-success bulk review with per-item base revision and mutation receipt |
| GET | `/api/v1/field-comments/{comment_id}/audit` | Review audit snapshots with source hash |
| GET | `/api/v1/field-comments/{comment_id}/traceability` | FieldComment, audit, report-source, and generated-document traceability |
| GET | `/api/v1/field-comments/quality-workbench` | Stale, weak-evidence, and missing-source review workbench |
| GET | `/api/v1/field-comments/quality-metrics` | Status, signal, actor, line, error, and report-link quality metrics |
| POST | `/api/v1/field-comments/{comment_id}/attachments` | Attachment create; optional multipart `idempotencyKey` returns the existing attachment on retry |
| GET | `/api/v1/field-comments/{comment_id}/attachments` | Attachment list |
| GET | `/api/v1/documents/{document_id}/field-comments` | FieldComments by document |
| POST | `/api/v1/work-sequence-boards` | Create board with required `idempotencyKey` |
| GET | `/api/v1/work-sequence-boards` | List boards with optional `lineCode` and `status` filters |
| GET | `/api/v1/work-sequence-boards/{board_id}` | Board snapshot with ordered items and `board_revision` |
| POST | `/api/v1/work-sequence-boards/{board_id}/items` | Add item with mutation key and base board revision |
| PUT | `/api/v1/work-sequence-boards/{board_id}/items/order` | Reorder the complete item set with mutation key and base revision |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/items/{item_id}/status` | Change item status/hold reason with mutation key and base revision |
| GET | `/api/v1/work-sequence-boards/{board_id}/history` | Change history with mutation key and applied revision |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | Notification candidates |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | Change notification candidate status |
| POST | `/api/v1/notification-channels` | Create notification channel |
| GET | `/api/v1/notification-channels` | List channels visible to current user |
| GET | `/api/v1/notification-channels/{channel_id}` | Channel detail |
| POST | `/api/v1/notification-channels/{channel_id}/members` | Add or reactivate channel member |
| GET | `/api/v1/notification-channels/{channel_id}/members` | Channel member list |
| PATCH | `/api/v1/notification-channels/{channel_id}/members/{member_id}` | Change member role or status |
| POST | `/api/v1/notification-channels/{channel_id}/messages` | Create channel message; a repeated `FIELD_COMMENT_EVENT` for the same channel and FieldComment returns the existing message |
| GET | `/api/v1/notification-channels/{channel_id}/messages` | Channel message list |
| GET | `/api/v1/notifications` | Current user notification list; `X-FlowNote-Notification-Cursor` server high-water header |
| PATCH | `/api/v1/notifications/{message_id}/read` | Mark channel message as read |
| POST | `/api/v1/handovers` | Create handover and receipts |
| GET | `/api/v1/handovers` | List visible handovers |
| GET | `/api/v1/handovers/{handover_id}` | Handover detail |
| PATCH | `/api/v1/handovers/{handover_id}/receipts/{receipt_id}` | Update handover receipt status |
| POST | `/api/v1/reports/drafts` | Create report draft |
| POST | `/api/v1/reports` | Save report |
| GET | `/api/v1/reports` | Report list |
| GET | `/api/v1/reports/{report_id}` | Report detail |
| GET | `/api/v1/reports/{report_id}/sources` | Report source list after current source-state and channel-permission revalidation |
| POST | `/api/v1/ai-search/candidates/rebuild` | Rebuild traceable AI search evidence candidates |
| GET | `/api/v1/ai-search/candidates` | List AI search evidence candidates |
| GET | `/api/v1/ai-search/quality` | Candidate counts, exclusion reasons, and FieldComment review readiness |
| POST | `/api/v1/ai-search/ground-truth-cases` | Save the first approval and provenance for a scoped regression question; the case remains inactive |
| POST | `/api/v1/ai-search/ground-truth-cases/{ground_truth_case_id}/second-approval` | Revalidate the frozen evidence snapshot and activate it with a different second approver |
| GET | `/api/v1/ai-search/ground-truth-cases` | List active approved questions for the current scope; `includePending=true` also returns inactive cases awaiting second approval |
| GET | `/api/v1/ai-search/ground-truth-datasets` | List immutable scoped ground-truth dataset versions and coverage |
| POST | `/api/v1/ai-search/ground-truth-datasets` | Create a draft dataset version from approved ground-truth cases |
| GET | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}` | Read a dataset version, its cases, coverage, and approval history |
| PUT | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}/cases` | Replace the case composition of a draft dataset version |
| POST | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}/transition` | Submit, review, approve, supersede, or retire a dataset version |
| GET | `/api/v1/ai-search/field-readiness/sample-plan` | Read the server-fixed 24-cell sample plan and evaluation evidence |
| POST | `/api/v1/ai-search/field-readiness/sample-reviews` | Record a 24-cell independent field-readiness sample review or third-person consensus |
| GET | `/api/v1/ai-search/field-readiness/sample-reviews` | List immutable sample reviews and disagreement/consensus status |
| GET | `/api/v1/ai-search/readiness` | Read separate `FIELD_READINESS` and `SMOKE_REGRESSION` readiness, approval/evaluation state, and sanitized operator actions; only the field track can satisfy provider-start gates |
| POST | `/api/v1/ai-search/evaluations` | Persist offline ground-truth evidence, exclusion, and ranking regression results |
| GET | `/api/v1/ai-search/evaluations` | List stored evaluation runs with an optional dataset-version filter |
| GET | `/api/v1/ai-search/evaluations/{run_id}` | Read a stored evaluation run and optionally compare it with another run |
| POST | `/api/v1/ai/queries` | Create an evidence search/summary request through the disabled-by-default safety boundary |
| GET | `/api/v1/ai/queries/{query_id}` | Read sanitized AI query status and evidence snapshot |
| GET | `/api/v1/ai-operations/approvals` | List scoped external-transfer approvals (`system-admin`) |
| POST | `/api/v1/ai-operations/approvals` | Create a scoped external-transfer approval (`system-admin`) |
| POST | `/api/v1/ai-operations/approvals/{approval_id}/revoke` | Revoke an approval immediately |
| GET | `/api/v1/ai-operations/provider-reviews` | List provider due-diligence checklists and four-party start decisions |
| POST | `/api/v1/ai-operations/provider-reviews` | Record an immutable provider review version as approved, pending, or rejected |
| GET | `/api/v1/ai-operations/prompts` | List immutable prompt versions |
| POST | `/api/v1/ai-operations/prompts` | Create an immutable prompt version |
| POST | `/api/v1/ai-operations/prompts/{prompt_version_id}/review` | Mark a draft prompt reviewed |
| POST | `/api/v1/ai-operations/prompts/{prompt_version_id}/approve` | Approve a reviewed prompt |
| POST | `/api/v1/ai-operations/prompts/{prompt_version_id}/activate` | Activate an approved prompt and retire the previous active version for the purpose |
| POST | `/api/v1/ai-operations/prompts/{prompt_version_id}/retire` | Retire a prompt version |
| GET | `/api/v1/ai-operations/policies` | Read global/site kill switch, limits, retention, and export policy |
| PUT | `/api/v1/ai-operations/policies` | Update global/site kill switch, limits, retention, and export policy |
| GET | `/api/v1/ai-operations/audit/queries` | Read sanitized query/evidence/citation/call metadata |
| GET | `/api/v1/ai-operations/audit/events` | Read AI operational change events |
| GET | `/api/v1/ai-operations/audit/export` | Export policy-controlled sanitized query audit CSV |
| POST | `/api/v1/ai-operations/retention/run` | Manually redact expired query payloads and delete expired response text |
| GET | `/api/v1/ai-operations/retention/audit` | Read retention processing metadata |
| GET | `/api/v1/ai-operations/queries/{query_id}` | Read scoped query retention state, state tag, legal-hold history, and linked audits |
| POST | `/api/v1/ai-operations/queries/{query_id}/expire` | Immediately expire one query in the configured customer/site scope |
| POST | `/api/v1/ai-operations/queries/{query_id}/legal-holds` | Place a reasoned legal/audit preservation hold on a scoped query |
| POST | `/api/v1/ai-operations/legal-holds/{hold_id}/release` | Release a preservation hold without deleting its history |

## Auth

The server uses HMAC-signed Bearer access tokens plus the `auth_sessions` table. Login creates a session. Refresh rotates the access token ID and refresh token hash. Logout revokes the session.

The pilot server is a single customer/site boundary. Optional `X-FlowNote-Customer-Scope` and `X-FlowNote-Site-Scope` headers, plus optional login/refresh body scopes, must match the configured boundary. A mismatch is audited and rejected with `404 SCOPE_NOT_FOUND` before resource lookup. Login, refresh, and current-user responses return the effective server scope.

Document write responses carry the server-authoritative aggregate `revision`. Version registration, status changes, publish, tag replacement, and soft delete compare the caller's base revision and relevant latest/published version before committing. Publish, status, and tag mutations store the normalized intent and first successful response in `document_mutation_receipts` within the same transaction. Replaying the same mutation key and intent returns that response without another revision or audit event; reusing the key for another intent returns a structured HTTP 409 conflict. WPF reads the document back after a successful response and marks the queue `SYNCED` only after the authoritative status, published version, tags, and revision agree.

Development defaults such as `admin / 1234` and the default token secret are local development values only.

Server account lifecycle APIs require `admin` or `system-admin`. Temporary passwords are request-only sensitive values, force a password change after first login, and are never returned. The `python -m app.ops.server_accounts` command remains an emergency/server-console path.

`GET /api/v1/tags` is currently readable without authentication. Creating tags and all document, FieldComment, access log, work sequence, report, and AI search candidate endpoints use the authentication and role policies described in [docs/api.md](../../docs/api.md).

Work sequence reads require an authenticated user and writes use the document-write role policy. The server is authoritative for the board aggregate: meaningful item add, reorder, and status mutations conditionally advance `board_revision`, store exactly one change-history row and one `work_sequence_mutation_receipts` row in the same transaction, and return `WORK_SEQUENCE_STALE_REVISION` when another client wins the base revision. Retrying the same intent with the same mutation key returns the stored first response; reusing the key for another intent returns `IDEMPOTENCY_KEY_REUSED`. No-op reorder or status requests are rejected without consuming a revision.

FieldComment review writes use the server-authoritative `review_revision`. A caller can send `baseReviewRevision` and `mutationKey`; WPF always sends both. One conditional update advances the revision, and the review change plus `field_comment_review_mutation_receipts` row commit together. Replaying the same key and intent returns the first response snapshot, while stale revisions and key reuse return structured 409 conflicts. Attachment uploads can also bind multipart `parentCommentId` and `fileSha256`; parent, request hash, and stored-file hash mismatches are rejected without retaining a new attachment/file row.

When `FLOWNOTE_FIELD_COMMENT_INDEPENDENT_REVIEW_REQUIRED=true`, a red-signal or conflicting FieldComment cannot move to `REVIEWED`, `SELECTED`, `EXCLUDED`, or `ARCHIVED` when the decision actor is the same user recorded in `analyzed_by`.

Report saves validate and freeze every source version and source hash, calculate normalized content and source-set SHA-256 values, and conditionally advance `report_revision` for an existing draft. The report, all sources, optional generated document/version, aggregate hashes, and `report_mutation_receipts` row commit in one transaction. Stale/orphan sources, stale report revision, client/server hash mismatch, and mutation-key reuse return structured 409 conflicts.

## Local Development

```powershell
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

Useful settings:

- `FLOWNOTE_ENVIRONMENT` or `FLOWNOTE_ENV`: default `local`
- `FLOWNOTE_API_HOST`: default `127.0.0.1`
- `FLOWNOTE_API_PORT`: default `5184`
- `FLOWNOTE_DATABASE_URL`: default `sqlite:///./data/flownote.sqlite3`
- `FLOWNOTE_TEST_DATABASE_URL`: default `sqlite:///./data/flownote.test.sqlite3`
- `FLOWNOTE_DATABASE_ECHO`: default `false`
- `FLOWNOTE_STORAGE_ROOT`: default `./storage`
- `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES`: default `20971520`
- `FLOWNOTE_CONTROLLED_COPY_MAX_BYTES`: default `524288000`
- `FLOWNOTE_CONTROLLED_COPY_TICKET_EXPIRES_SECONDS`: default `60`, normalized to `5`-`300`
- `FLOWNOTE_ANDROID_VIEW_GRANT_EXPIRES_SECONDS`: default `60`, normalized to `5`-`300`
- `FLOWNOTE_ANDROID_VIEW_AUTO_CLOSE_SECONDS`: default `300`
- `FLOWNOTE_ANDROID_VIEW_MAX_BYTES`: default `52428800` (50 MiB)
- `FLOWNOTE_ANDROID_VIEW_MAX_TEXT_BYTES`: default `5242880` (5 MiB)
- `FLOWNOTE_ANDROID_VIEW_MAX_PDF_PAGES`: default `200`
- `FLOWNOTE_SESSION_COOKIE_NAME`: default `flownote_session`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`: default `480`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`: default `14`
- `FLOWNOTE_CUSTOMER_SCOPE`: single-customer server boundary; falls back to `FLOWNOTE_AI_CUSTOMER_SCOPE`
- `FLOWNOTE_SITE_SCOPE`: single-site server boundary; falls back to `FLOWNOTE_AI_SITE_SCOPE`
- `FLOWNOTE_FIELD_COMMENT_INDEPENDENT_REVIEW_REQUIRED`: default `true`
- `FLOWNOTE_RESTORE_FAULT_CODE`: default empty; 복구 장애 실기 전용이며 `partial_restore`, `old_database_new_files`, `missing_file`, `wrong_server_epoch`만 허용
- `FLOWNOTE_RESTORE_BLOCK_REASON`: default empty; 복구 장애 차단 사유
- `FLOWNOTE_RESTORE_PILOT_RUN_ID`: default empty; 장애 실기 run ID
- `FLOWNOTE_RESTORE_BACKUP_SET_ID`: default empty; 복구에 사용한 익명 backup set ID
- `FLOWNOTE_RESTORE_APPROVAL_ID`: default empty; 복구 승인 ID
- `FLOWNOTE_RESTORE_RESPONSIBLE_OWNER`: default empty; 담당자 역할 ID
- `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED`: default `false`
- `FLOWNOTE_AI_READINESS_GATE_ENABLED`: default `true`; 현재 고객·현장·DB scope의 근거/승인 질문/회귀 기준 미달 시 운영 provider 호출 차단
- `FLOWNOTE_AI_PROVIDER`: default `UNCONFIGURED`
- `FLOWNOTE_AI_MODEL`: default `UNCONFIGURED`
- `FLOWNOTE_AI_CUSTOMER_SCOPE`: default `DEFAULT`
- `FLOWNOTE_AI_SITE_SCOPE`: default `DEFAULT`
- `FLOWNOTE_AI_PROVIDER_EXCERPT_MAX_CHARS`: default `600`, constrained to `100`-`4000`
- `FLOWNOTE_AI_PROVIDER_MAX_SOURCES`: default `12`, constrained to `1`-`100`
- `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE`: default `DISABLED`; `FAKE` 또는 명시적 시험용 `NETWORK_TEST`만 허용
- `FLOWNOTE_AI_FAKE_SCENARIOS`: default `SUCCESS`; fake adapter 결정적 시나리오 목록
- `FLOWNOTE_AI_PROVIDER_ENDPOINT`: `NETWORK_TEST` 전용 HTTPS JSON endpoint
- `FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED`: default `false`; `environment=test`와 함께 있어야 네트워크 adapter 생성
- `FLOWNOTE_AI_NETWORK_TIMEOUT_SECONDS`: default `30`, constrained to `1`-`120`
- `FLOWNOTE_AI_PROVIDER_MAX_ATTEMPTS`: default `3`, constrained to `1`-`5`; timeout, 429, 5xx만 재시도
- `FLOWNOTE_AI_PROVIDER_RESPONSE_MAX_BYTES`: default `65536`, constrained to `1024`-`1048576`
- `FLOWNOTE_AI_RETENTION_SCHEDULER_ENABLED`: default `true`; 서버 lifespan에서 만료 보존 작업을 주기 실행
- `FLOWNOTE_AI_RETENTION_SCHEDULER_INTERVAL_SECONDS`: default `3600`, constrained to `60`-`86400`

`FLOWNOTE_DATABASE_URL`은 FastAPI 서버 전용 DB를 가리켜야 하며 WPF의 `FLOWNOTE_LOCAL_DATA_DIR`/`FLOWNOTE_LOCAL_DATABASE_PATH`와 같은 SQLite 파일을 사용하지 않는다. 초기화는 기존 WPF `documents`/`document_versions` 열 구성을 감지하면 `Base.metadata.create_all()` 전에 `RuntimeError`로 중단해 서버 테이블을 추가하지 않는다.

`FLOWNOTE_RESTORE_FAULT_CODE`를 설정하면 나머지 복구 식별자 네 개도 모두 있어야 한다. 하나라도 빠지거나 지원하지 않는 장애 코드이면 sync manifest가 `503`으로 실패한다. 이 값은 별도 PC 복구 실기에서 WPF 차단·재결합 증거를 묶는 표지이며 운영 원본 데이터에 장애를 만드는 기능이 아니다. 승인 뒤에는 서버를 정상 종료하고 `FLOWNOTE_RESTORE_*` 값을 제거해 다시 시작해야 정상 manifest가 반환된다. 익명 ID와 담당자 역할 ID만 사용하고 고객명, 담당자 실명, 경로와 비밀값은 기록하지 않는다.

## Verification

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

As of 2026-07-31, the current code and `scripts/verify-preserved-tests.ps1` guards agree on 160 FastAPI tests, 84 WPF Core tests, and 24 Android tests. The increase from 155 to 160 FastAPI node IDs comes from four parameterized restore-fault cases and one incomplete-restore-context case. The current macOS component verification collected 160 total and 160 unique FastAPI node IDs with zero duplicates, and its JUnit result passed 160/160. The script now preserves the raw collection, duplicate list, exit codes, and JUnit totals, and reports the current step, expected and actual values, preserved evidence, and a new `RunId` command when collection, JUnit, or toolchain checks fail. This is not an integrated baseline because the Windows x64 collection/TRX comparison, shared-DB smoke, Android build, and all checks have not run twice under one clean source commit.

The ORM also includes `ai_sensitive_data_policies`; the active customer/site policy extends the provider-boundary deny terms and customer identifiers. There is no management API for that sensitive-data policy. The generic network adapter is restricted to explicit test scope and remains disabled by default; provider-specific production activation is not configured. The separate `ai_operational_policies` API manages kill switches, limits, retention periods, and audit-export permission. Query and retention audit operations are restricted to the configured customer/site scope. The server lifespan runs expired-query retention on the configured interval, while `system-admin` can run scoped bulk retention, expire one query, or place and release a reasoned legal hold. An active hold blocks all three expiry paths. WPF mutations send a stable `operationKey` and the latest detail `stateTag`; duplicate/lost-response retries return the original result, while stale, already-expired, already-released, and concurrent operations return `409`. Legal-hold rows and linked audit history are never deleted by release or expiry.

Test SQLite DBs, logs, upload files, and generated sample files are preserved unless the user explicitly asks to delete them.
