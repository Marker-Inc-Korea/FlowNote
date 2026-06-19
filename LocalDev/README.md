# Local Development Helpers

`start-local-service.sh` now treats the Python FastAPI server as the active backend.

```bash
./start-local-service.sh api
```

Legacy helpers are kept only for reference:

```bash
./start-local-service.sh legacy-node-api
./start-local-service.sh legacy-web
```

The legacy commands use the preserved code under `services/api/legacy-node` and `apps/web/legacy-react-vite`.
