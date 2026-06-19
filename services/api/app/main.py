from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="FlowNote API", version="0.1.0")
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "FlowNote API", "environment": settings.environment}
