# API Tests

This directory contains FlowNote FastAPI server tests.

## Current Test Scope

- SQLite MVP schema creation and `schema_migrations` record
- DB health check API
- Login API, Bearer access token issue, refresh token issue, `/auth/me`
- Expired access token rejection
- Logout session revocation
- Refresh token rotation and invalid/reused refresh token rejection
- Missing auth, wrong password, inactive account rejection
- Document registration, file storage, SHA-256, size, MIME/extension metadata
- New document version registration and previous latest version `SUPERSEDED` handling
- Document status changes, version status changes, explicit published version selection, published document lookup
- Document tag create/replace and tag dictionary lookup
- Role-based permissions for document write, FieldComment create, and access-log read
- FieldComment create, list, document-scoped lookup, manager review, and analysis update
- FieldComment attachment create/list with allowed extension, size, and hash records
- Document access log create/list
- Work sequence board create, item add, full reorder, status change, history, and notification candidate records

## Run

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

Test SQLite DBs, logs, test upload files, and generated sample files are preserved unless the user explicitly asks to delete them.
