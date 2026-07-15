# API Service

FlowNote FastAPI 서버는 SQLite 기반 현재 REST API를 제공한다. 운영 기본 경로는 `/api/v1`이며, 파일은 서버 로컬 `storage/`에 저장한다. 보호 API는 Bearer access token과 `auth_sessions` 상태를 함께 검증한다.

이 목록은 2026-07-14 현재 `app/api/v1/router.py`에 등록된 라우터 기준이다. 외부 AI API는 운영 provider 구현이 아니라 기본 비활성 안전장치·감사 경계이며, controlled copy는 서버에 저장된 현재 공개 버전만 1회 스트리밍한다.

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service and environment check |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/health/db` | Database health check |
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
| PUT | `/api/v1/documents/{document_id}/tags` | Replace document tags |
| PATCH | `/api/v1/documents/{document_id}/status` | Change document status |
| GET | `/api/v1/documents/{document_id}/versions` | Version list |
| POST | `/api/v1/documents/{document_id}/versions` | Register new version; optional multipart `idempotencyKey` returns the existing version on retry |
| PATCH | `/api/v1/documents/{document_id}/versions/{version_id}/status` | Change version status |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/publish` | Publish selected version |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/controlled-copy` | Issue one-time controlled copy grant for the current published version |
| GET | `/api/v1/controlled-copies/{token}` | Stream the session-bound controlled copy once |
| POST | `/api/v1/documents/{document_id}/access-logs` | Register access log |
| GET | `/api/v1/documents/{document_id}/access-logs` | Access log list |
| GET | `/api/v1/tags` | Tag list |
| POST | `/api/v1/tags` | Tag create |
| POST | `/api/v1/field-comments` | FieldComment create |
| GET | `/api/v1/field-comments` | FieldComment list |
| GET | `/api/v1/field-comments/{comment_id}` | FieldComment detail |
| PATCH | `/api/v1/field-comments/{comment_id}` | Review/analyze FieldComment |
| POST | `/api/v1/field-comments/{comment_id}/attachments` | Attachment create; optional multipart `idempotencyKey` returns the existing attachment on retry |
| GET | `/api/v1/field-comments/{comment_id}/attachments` | Attachment list |
| GET | `/api/v1/documents/{document_id}/field-comments` | FieldComments by document |
| POST | `/api/v1/work-sequence-boards` | Work sequence board create |
| GET | `/api/v1/work-sequence-boards` | Work sequence board list |
| GET | `/api/v1/work-sequence-boards/{board_id}` | Work sequence board detail |
| POST | `/api/v1/work-sequence-boards/{board_id}/items` | Add item |
| PUT | `/api/v1/work-sequence-boards/{board_id}/items/order` | Reorder items |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/items/{item_id}/status` | Change item status |
| GET | `/api/v1/work-sequence-boards/{board_id}/history` | Change history |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | Notification candidates |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | Change notification candidate status |
| POST | `/api/v1/notification-channels` | Create notification channel |
| GET | `/api/v1/notification-channels` | List channels visible to current user |
| GET | `/api/v1/notification-channels/{channel_id}` | Channel detail |
| POST | `/api/v1/notification-channels/{channel_id}/members` | Add or reactivate channel member |
| GET | `/api/v1/notification-channels/{channel_id}/members` | Channel member list |
| PATCH | `/api/v1/notification-channels/{channel_id}/members/{member_id}` | Change member role or status |
| POST | `/api/v1/notification-channels/{channel_id}/messages` | Create channel message |
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
| POST | `/api/v1/ai-search/candidates/rebuild` | Rebuild traceable AI search evidence candidates |
| GET | `/api/v1/ai-search/candidates` | List AI search evidence candidates |
| GET | `/api/v1/ai-search/quality` | Candidate counts, exclusion reasons, and FieldComment review readiness |
| POST | `/api/v1/ai-search/evaluations` | Persist offline ground-truth evidence, exclusion, and ranking regression results |
| POST | `/api/v1/ai/queries` | Create an evidence search/summary request through the disabled-by-default safety boundary |
| GET | `/api/v1/ai/queries/{query_id}` | Read sanitized AI query status and evidence snapshot |

## Auth

The server uses HMAC-signed Bearer access tokens plus the `auth_sessions` table. Login creates a session. Refresh rotates the access token ID and refresh token hash. Logout revokes the session.

Development defaults such as `admin / 1234` and the default token secret are local development values only.

Server account lifecycle APIs require `admin` or `system-admin`. Temporary passwords are request-only sensitive values, force a password change after first login, and are never returned. The `python -m app.ops.server_accounts` command remains an emergency/server-console path.

`GET /api/v1/tags` is currently readable without authentication. Creating tags and all document, FieldComment, access log, work sequence, report, and AI search candidate endpoints use the authentication and role policies described in [docs/api.md](../../docs/api.md).

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
- `FLOWNOTE_SESSION_COOKIE_NAME`: default `flownote_session`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`: default `480`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`: default `14`
- `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED`: default `false`
- `FLOWNOTE_AI_PROVIDER`: default `UNCONFIGURED`
- `FLOWNOTE_AI_MODEL`: default `UNCONFIGURED`
- `FLOWNOTE_AI_CUSTOMER_SCOPE`: default `DEFAULT`
- `FLOWNOTE_AI_SITE_SCOPE`: default `DEFAULT`
- `FLOWNOTE_AI_PROVIDER_EXCERPT_MAX_CHARS`: default `600`, constrained to `100`-`4000`
- `FLOWNOTE_AI_PROVIDER_MAX_SOURCES`: default `12`, constrained to `1`-`100`

## Verification

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

As of 2026-07-15, the collected FastAPI test count is 101. `scripts/verify-preserved-tests.ps1` fixes the same collection baseline and verifies the generated JUnit counts. The complete Windows baseline also runs WPF Core/build/smoke and Android unit/debug build checks under one preserved run ID; a FastAPI-only run is partial evidence.

The ORM also includes `ai_sensitive_data_policies`; the active customer/site policy extends the provider-boundary deny terms and customer identifiers. There is no policy-management API or network provider client in the current router.

Test SQLite DBs, logs, upload files, and generated sample files are preserved unless the user explicitly asks to delete them.
