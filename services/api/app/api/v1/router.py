from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.document_access_logs import router as document_access_logs_router
from app.api.v1.documents import router as documents_router
from app.api.v1.field_notes import document_field_notes_router
from app.api.v1.field_notes import router as field_notes_router
from app.api.v1.health import router as health_router
from app.api.v1.tags import router as tags_router
from app.api.v1.work_sequences import router as work_sequences_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(document_access_logs_router)
api_v1_router.include_router(field_notes_router)
api_v1_router.include_router(document_field_notes_router)
api_v1_router.include_router(tags_router)
api_v1_router.include_router(work_sequences_router)
