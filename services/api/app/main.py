from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import Settings, settings
from app.db.init_db import initialize_database
from app.db.session import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    initialize_database(app.state.database)
    try:
        yield
    finally:
        app.state.database.dispose()


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings
    app = FastAPI(title="FlowNote API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.database = Database(app_settings.database_url, echo=app_settings.database_echo)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "FlowNote API", "environment": settings.environment}
