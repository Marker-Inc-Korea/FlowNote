# API Service

FlowNote FastAPI 서버는 SQLite 기반 현재 REST API를 제공한다. 운영 기본 경로는 `/api/v1`이며, 파일은 서버 로컬 `storage/`에 저장한다. 보호 API는 Bearer access token과 `auth_sessions` 상태를 함께 검증한다.

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
| POST | `/api/v1/documents` | Register document and first version |
| GET | `/api/v1/documents` | Document list |
| GET | `/api/v1/documents/published` | Published document list |
| GET | `/api/v1/documents/{document_id}` | Document detail |
| GET | `/api/v1/documents/{document_id}/published` | Published version |
| PUT | `/api/v1/documents/{document_id}/tags` | Replace document tags |
| PATCH | `/api/v1/documents/{document_id}/status` | Change document status |
| GET | `/api/v1/documents/{document_id}/versions` | Version list |
| POST | `/api/v1/documents/{document_id}/versions` | Register new version |
| PATCH | `/api/v1/documents/{document_id}/versions/{version_id}/status` | Change version status |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/publish` | Publish selected version |
| POST | `/api/v1/documents/{document_id}/access-logs` | Register access log |
| GET | `/api/v1/documents/{document_id}/access-logs` | Access log list |
| GET | `/api/v1/tags` | Tag list |
| POST | `/api/v1/tags` | Tag create |
| POST | `/api/v1/field-comments` | FieldComment create |
| GET | `/api/v1/field-comments` | FieldComment list |
| GET | `/api/v1/field-comments/{comment_id}` | FieldComment detail |
| PATCH | `/api/v1/field-comments/{comment_id}` | Review/analyze FieldComment |
| POST | `/api/v1/field-comments/{comment_id}/attachments` | Attachment create |
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
| POST | `/api/v1/reports/drafts` | Create report draft |
| POST | `/api/v1/reports` | Save report |
| GET | `/api/v1/reports` | Report list |
| GET | `/api/v1/reports/{report_id}` | Report detail |
| POST | `/api/v1/ai-search/candidates/rebuild` | Rebuild traceable AI search evidence candidates |
| GET | `/api/v1/ai-search/candidates` | List AI search evidence candidates |
| GET | `/api/v1/ai-search/quality` | Candidate counts, exclusion reasons, and FieldComment review readiness |

## Auth

The server uses HMAC-signed Bearer access tokens plus the `auth_sessions` table. Login creates a session. Refresh rotates the access token ID and refresh token hash. Logout revokes the session.

Development defaults such as `admin / 1234` and the default token secret are local development values only.

Server account operations are handled by `python -m app.ops.server_accounts` for the current implementation. It supports `create`, `reset-password`, `set-status`, and `set-role`; WPF user management is local SQLite only and does not create or modify server accounts. Password entry is interactive and the current script rejects passwords shorter than 8 characters.

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
- `FLOWNOTE_SESSION_COOKIE_NAME`: default `flownote_session`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`: default `480`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`: default `14`

## Verification

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

The current collected FastAPI test count is 50.

Test SQLite DBs, logs, upload files, and generated sample files are preserved unless the user explicitly asks to delete them.
