# FlowNote Native Client

Active client development starts here.

## Direction

- UI: WPF or Avalonia
- Server communication: REST API to the Python FastAPI server
- Deployment: client installer distributed to field/admin PCs
- Document files: requested from the server; do not keep a silent local document sync

## Initial Responsibilities

- Login
- Document explorer
- Published document viewer
- Field comment input
- Admin document/version upload flow
- Optional local file watcher for admin PCs

## Directories

- `src/FlowNote.Client.App/`: native client app entry point
- `src/FlowNote.Client.Core/`: API client, auth/session, local file handling, viewer policy
- `docs/`: client screen flow and install notes
