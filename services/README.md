# Services

FlowNote server-side components live under this directory.

## Scope

- `api/`: Python FastAPI REST API server

## Current Implementation

`services/api/` implements the SQLite MVP API:

- Health check and DB connectivity check
- Development default admin account seed
- Username/password login
- HMAC Bearer access token issue
- Refresh token rotation
- Logout session revocation through `auth_sessions`
- `/auth/me` current user lookup
- Document registration, list, detail, version list, and new version registration
- Document status changes, version status changes, explicit published version selection, published document lookup
- Document tag create/list/replace
- FieldNote create, list, detail, manager review, and analysis update
- FieldNote photo/file attachment create/list
- Document access log create/list
- Work sequence board create, item add, reorder, status change, and history lookup

Reports, AI search/advice, MES/ERP integration, administrator-forced session revocation UI, and administrator file-watch APIs remain follow-up scope.

## Development Baseline

- Server framework: FastAPI
- Metadata DB: SQLite first
- File storage: server-local `storage/`
- API base path: `/api/v1`

Test DBs, test upload files, logs, and generated sample files are preserved unless the user explicitly asks to delete them.
