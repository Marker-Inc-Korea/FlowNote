from fastapi import APIRouter, Request

from app.db.session import get_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def database_health_check(request: Request) -> dict[str, str]:
    database = get_database(request)
    database.check_connection()
    return {"status": "ok", "database": "ok"}
