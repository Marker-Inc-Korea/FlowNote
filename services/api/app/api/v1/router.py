from fastapi import APIRouter

from app.api.v1.ai_field_readiness_reviews import router as ai_field_readiness_reviews_router
from app.api.v1.ai_search import router as ai_search_router
from app.api.v1.ai_queries import router as ai_queries_router
from app.api.v1.ai_operations import router as ai_operations_router
from app.api.v1.ai_sensitive_data_policies import router as ai_sensitive_data_policies_router
from app.api.v1.auth import router as auth_router
from app.api.v1.audit_events import router as audit_events_router
from app.api.v1.android_document_views import router as android_document_views_router
from app.api.v1.channels import router as channels_router
from app.api.v1.change_history import router as change_history_router
from app.api.v1.controlled_copies import router as controlled_copies_router
from app.api.v1.document_access_logs import router as document_access_logs_router
from app.api.v1.document_approvals import router as document_approvals_router
from app.api.v1.documents import router as documents_router
from app.api.v1.field_comments import document_field_comments_router
from app.api.v1.field_comments import router as field_comments_router
from app.api.v1.field_comment_review_dashboard import router as field_comment_review_dashboard_router
from app.api.v1.health import router as health_router
from app.api.v1.reports import router as reports_router
from app.api.v1.server_accounts import router as server_accounts_router
from app.api.v1.sync_reconciliation import router as sync_reconciliation_router
from app.api.v1.tags import router as tags_router
from app.api.v1.terminal_devices import router as terminal_devices_router
from app.api.v1.work_sequences import router as work_sequences_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(audit_events_router)
api_v1_router.include_router(change_history_router)
api_v1_router.include_router(server_accounts_router)
api_v1_router.include_router(sync_reconciliation_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(document_approvals_router)
api_v1_router.include_router(android_document_views_router)
api_v1_router.include_router(controlled_copies_router)
api_v1_router.include_router(document_access_logs_router)
api_v1_router.include_router(field_comment_review_dashboard_router)
api_v1_router.include_router(field_comments_router)
api_v1_router.include_router(document_field_comments_router)
api_v1_router.include_router(tags_router)
api_v1_router.include_router(terminal_devices_router)
api_v1_router.include_router(work_sequences_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(ai_search_router)
api_v1_router.include_router(ai_field_readiness_reviews_router)
api_v1_router.include_router(ai_queries_router)
api_v1_router.include_router(ai_operations_router)
api_v1_router.include_router(ai_sensitive_data_policies_router)
api_v1_router.include_router(channels_router)
