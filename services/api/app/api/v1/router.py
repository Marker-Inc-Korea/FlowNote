from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.document_access_logs import router as document_access_logs_router
from app.api.v1.documents import router as documents_router
from app.api.v1.field_comments import document_field_comments_router
from app.api.v1.field_comments import router as field_comments_router
from app.api.v1.health import router as health_router
from app.api.v1.reports import router as reports_router
from app.api.v1.tags import router as tags_router
from app.api.v1.work_sequences import router as work_sequences_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(document_access_logs_router)
api_v1_router.include_router(field_comments_router)
api_v1_router.include_router(document_field_comments_router)
api_v1_router.include_router(tags_router)
api_v1_router.include_router(work_sequences_router)
api_v1_router.include_router(reports_router)
