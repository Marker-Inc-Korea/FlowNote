# FlowNote Development Access

This document records shared development and test access points for FlowNote.

## Test Environment

- 새 개발 대상은 Python FastAPI 서버와 Windows WPF 네이티브 클라이언트이다.

## Data Retention

- Development and field testing are running in parallel in this environment.
- Database records in this test environment may be reset or removed during development, migration, troubleshooting, or field-test preparation.
- Do not treat test-environment data as permanent production records.

## Security Note

- This repository may be public. Real user accounts, passwords, tokens, API keys, and database connection details must not be committed.
- Keep secrets in local `.env` files, deployment settings, or the approved secret manager for the environment.
- Commit only non-secret access information that helps collaborators find the correct development or test endpoint.
