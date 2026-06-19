# FlowNote Development Access

This document records shared development and test access points for FlowNote.

## Test Environment

- Legacy web test endpoint: https://edge-nano-docs.it-sent.com/

This endpoint belongs to the older web-based direction. New development should not treat it as the target frontend. The new target is a Python FastAPI server accessed by a WPF or Avalonia native client.

## Data Retention

- Development and field testing are running in parallel in this environment.
- Database records in this test environment may be reset or removed during development, migration, troubleshooting, or field-test preparation.
- Do not treat test-environment data as permanent production records.

## Security Note

- This repository is private, but real user accounts, passwords, tokens, API keys, and database connection details should not be committed.
- Keep secrets in local `.env` files, deployment settings, or the approved secret manager for the environment.
- Commit only non-secret access information that helps collaborators find the correct development or test endpoint.
