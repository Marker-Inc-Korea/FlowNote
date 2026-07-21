from fastapi import APIRouter, Request

from app.db.session import get_database
from app.api.v1.sync_reconciliation import manifest_payload

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def database_health_check(request: Request) -> dict[str, str]:
    database = get_database(request)
    database.check_connection()
    return {"status": "ok", "database": "ok"}


@router.get("/health/sync-manifest")
def sync_manifest_health_check(request: Request) -> dict[str, object]:
    database = get_database(request)
    database.check_connection()
    with database.session() as session:
        return {"status": "ok", **manifest_payload(session)}
