import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import Settings, settings
from app.db.init_db import initialize_database
from app.db.session import Database
from app.services.ai_operations import run_retention
from app.services.ai_provider_adapters import configured_provider_adapter


async def _retention_loop(app: FastAPI) -> None:
    while True:
        # 시작 직후 스키마 초기화나 첫 업무 요청과 보존 쓰기가 경쟁하지 않게 한다.
        await asyncio.sleep(app.state.settings.ai_retention_scheduler_interval_seconds)
        with app.state.database.session() as session:
            run_retention(session)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    initialize_database(app.state.database)
    retention_task = None
    if app.state.settings.ai_retention_scheduler_enabled:
        retention_task = asyncio.create_task(_retention_loop(app))
    try:
        yield
    finally:
        if retention_task is not None:
            retention_task.cancel()
            try:
                await retention_task
            except asyncio.CancelledError:
                pass
        app.state.database.dispose()


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings
    app = FastAPI(title="FlowNote API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.database = Database(app_settings.database_url, echo=app_settings.database_echo)
    app.state.ai_provider = configured_provider_adapter(app_settings)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "FlowNote API", "environment": settings.environment}
