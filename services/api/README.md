# API Service

FlowNote Python FastAPI server for the SQLite MVP API.

## Current Scope

The server currently implements:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service and environment check |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/health/db` | Database health check |
| POST | `/api/v1/auth/login` | Username/password login, user payload, Bearer access token, refresh token |
| POST | `/api/v1/auth/refresh` | Refresh token rotation and new access/refresh token issue |
| POST | `/api/v1/auth/logout` | Revoke the current auth session |
| GET | `/api/v1/auth/me` | Current user lookup with Bearer access token |
| POST | `/api/v1/documents` | Document and initial version registration |
| GET | `/api/v1/documents` | Document list |
| GET | `/api/v1/documents/{documentId}` | Document detail |
| PATCH | `/api/v1/documents/{documentId}/status` | Document status transition |
| GET | `/api/v1/documents/published` | Published document list |
| GET | `/api/v1/documents/{documentId}/published` | Published document version |
| GET | `/api/v1/documents/{documentId}/versions` | Document version list |
| POST | `/api/v1/documents/{documentId}/versions` | New document version registration |
| PATCH | `/api/v1/documents/{documentId}/versions/{versionId}/status` | Document version status transition |
| POST | `/api/v1/documents/{documentId}/versions/{versionId}/publish` | Publish a specific document version |
| PUT | `/api/v1/documents/{documentId}/tags` | Replace document tags |
| POST | `/api/v1/documents/{documentId}/access-logs` | Document access log registration |
| GET | `/api/v1/documents/{documentId}/access-logs` | Document access log list |
| GET | `/api/v1/tags` | Tag list |
| POST | `/api/v1/tags` | Tag creation |
| POST | `/api/v1/field-notes` | FieldNote source history registration |
| GET | `/api/v1/field-notes` | FieldNote list |
| GET | `/api/v1/field-notes/{noteId}` | FieldNote detail |
| PATCH | `/api/v1/field-notes/{noteId}` | Manager review and analysis update |
| POST | `/api/v1/field-notes/{noteId}/attachments` | FieldNote photo/file attachment registration |
| GET | `/api/v1/field-notes/{noteId}/attachments` | FieldNote attachment list |
| GET | `/api/v1/documents/{documentId}/field-notes` | FieldNotes for a document |
| POST | `/api/v1/work-sequence-boards` | Work sequence board creation |
| GET | `/api/v1/work-sequence-boards` | Work sequence board list |
| GET | `/api/v1/work-sequence-boards/{boardId}` | Work sequence board detail |
| POST | `/api/v1/work-sequence-boards/{boardId}/items` | Add work sequence item |
| PUT | `/api/v1/work-sequence-boards/{boardId}/items/order` | Reorder all board items |
| PATCH | `/api/v1/work-sequence-boards/{boardId}/items/{itemId}/status` | Change item status |
| GET | `/api/v1/work-sequence-boards/{boardId}/history` | Work sequence change history |

Document, FieldNote, and document access log APIs require `Authorization: Bearer {access_token}`. Missing, invalid, or expired credentials return `401`.
Document registration, document version registration, document tag changes, and tag creation
require a document-write role such as `admin`, `document-admin`, `line-foreman`, or
`team-lead`. `team-member` and `viewer` accounts can create FieldNotes but receive `403` for
document write flows. Document access log reads are limited to `admin` and `system-admin`.

Server auth uses HMAC-signed access tokens plus the `auth_sessions` table. Login creates a
server session and returns an access token and refresh token. Refresh rotates both tokens for
the same session, so the previous access token and previous refresh token are rejected. Logout
marks the session as revoked.

Configure the signing secret and lifetimes with:

- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`, default `480`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`, default `14`

The default admin account `admin / 1234`, fixed smoke-test passwords, and default token secret
are for local development and smoke tests only. Before operational deployment, issue a site
admin account separately, require first-login password replacement, and replace the token
secret with a site-specific value outside Git.

## Local Development

```powershell
cd services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5184 --reload
```

Useful settings:

- `FLOWNOTE_DATABASE_URL`: default `sqlite:///./data/flownote.sqlite3`
- `FLOWNOTE_TEST_DATABASE_URL`: default `sqlite:///./data/flownote.test.sqlite3`
- `FLOWNOTE_STORAGE_ROOT`: default `./storage`
- `FLOWNOTE_FIELD_NOTE_ATTACHMENT_MAX_BYTES`: default `20971520`

Do not commit real accounts, passwords, tokens, API keys, production DB connection strings, customer documents, or operational data.

## Verification

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

## Preserved Test Artifacts

Test SQLite databases, logs, test upload files, sample files, and generated test artifacts are preserved unless the user explicitly asks to delete them.
