from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

COMMENT_TYPES = {"experience", "work_evaluation", "issue"}
INPUT_MODES = {"signal", "free_text", "template", "template_with_text", "admin_proxy", "mes_integration"}
STATUSES = {"NEW", "ASSIGNED", "NEEDS_REVIEW", "ANALYZED", "REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"}
PRIMARY_WORKFLOW_STATUSES = {"NEW", "ASSIGNED", "ANALYZED", "REVIEWED", "SELECTED"}
ALLOWED_TRANSITIONS = {
    "NEW": {"ASSIGNED", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED"},
    "ASSIGNED": {"NEW", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED"},
    "NEEDS_REVIEW": {"NEW", "ASSIGNED", "ANALYZED", "EXCLUDED"},
    "ANALYZED": {"NEW", "NEEDS_REVIEW", "REVIEWED", "EXCLUDED"},
    "REVIEWED": {"ANALYZED", "SELECTED", "EXCLUDED"},
    "SELECTED": {"REVIEWED", "EXCLUDED", "ARCHIVED"},
    "EXCLUDED": {"NEW", "ARCHIVED"},
    "ARCHIVED": {"EXCLUDED"},
}
ATTACHMENT_TYPES = {"photo", "document", "other"}
ATTACHMENT_ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".pdf",
    ".txt",
    ".md",
}


class FieldCommentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    document_id: str | None = Field(default=None, alias="documentId")
    document_version_id: str | None = Field(default=None, alias="documentVersionId")
    structure_item_id: str | None = Field(default=None, alias="structureItemId")
    work_record_id: str | None = Field(default=None, alias="workRecordId")
    source_type: str | None = Field(default=None, alias="sourceType")
    source_id: str | None = Field(default=None, alias="sourceId")
    source_revision: int | None = Field(default=None, alias="sourceRevision", ge=1)
    server_scope: str | None = Field(default=None, alias="serverScope", max_length=500)
    intent_hash_sha256: str | None = Field(
        default=None,
        alias="intentHashSha256",
        min_length=64,
        max_length=64,
    )
    comment_type: str = Field(default="issue", alias="commentType")
    input_mode: str = Field(default="free_text", alias="inputMode")
    signal_level: str | None = Field(default=None, alias="signalLevel")
    template_id: str | None = Field(default=None, alias="templateId")
    raw_content: str = Field(alias="rawContent", min_length=1)
    author_id: str | None = Field(default=None, alias="authorId")
    reported_by: str | None = Field(default=None, alias="reportedBy")
    operator_id: str | None = Field(default=None, alias="operatorId")
    entry_source: str = Field(default="field_user", alias="entrySource")
    device_id: str | None = Field(default=None, alias="deviceId")
    location_code: str | None = Field(default=None, alias="locationCode")
    category: str | None = None
    priority: int | None = None
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class FieldCommentReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    status: str | None = None
    normalized_content: str | None = Field(default=None, alias="normalizedContent")
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    reviewed_by: str | None = Field(default=None, alias="reviewedBy")
    analyzed_by: str | None = Field(default=None, alias="analyzedBy")
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")
    conflict_flag: bool | None = Field(default=None, alias="conflictFlag")
    conflict_basis: str | None = Field(default=None, alias="conflictBasis")
    base_review_revision: int | None = Field(default=None, alias="baseReviewRevision", ge=1)
    mutation_key: str | None = Field(default=None, alias="mutationKey", max_length=160)


class FieldCommentBulkReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    comment_ids: list[str] = Field(alias="commentIds", min_length=1, max_length=200)
    status: str | None = None
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")


class FieldCommentBulkReviewItemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    comment_id: str = Field(alias="commentId", min_length=1)
    base_review_revision: int = Field(alias="baseReviewRevision", ge=1)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)


class FieldCommentBulkReviewV2Request(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    items: list[FieldCommentBulkReviewItemRequest] = Field(min_length=1, max_length=200)
    status: str | None = None
    normalized_content: str | None = Field(default=None, alias="normalizedContent")
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")
    conflict_flag: bool | None = Field(default=None, alias="conflictFlag")
    conflict_basis: str | None = Field(default=None, alias="conflictBasis")


class FieldCommentBulkReviewItemResponse(BaseModel):
    comment_id: str
    allowed: bool
    success: bool | None = None
    from_status: str | None = None
    target_status: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    review_revision: int | None = None
    receipt: str | None = None
    field_comment: "FieldCommentResponse | None" = None


class FieldCommentBulkReviewResponse(BaseModel):
    requested_count: int
    success_count: int
    failure_count: int
    items: list[FieldCommentBulkReviewItemResponse]


class FieldCommentAuditResponse(BaseModel):
    history_id: str
    event_type: str
    actor_id: str | None
    before_snapshot: dict | None
    after_snapshot: dict | None
    change_reason: str | None
    created_at: datetime


class FieldCommentQualityItemResponse(BaseModel):
    issue_type: str
    comment_id: str | None
    report_id: str | None = None
    age_days: int | None = None
    detail: str


class FieldCommentResponse(BaseModel):
    comment_id: str
    document_id: str | None
    document_version_id: str | None
    structure_item_id: str | None
    work_record_id: str | None
    source_type: str | None
    source_id: str | None
    source_revision: int | None
    server_scope: str | None
    intent_hash_sha256: str | None
    comment_type: str
    input_mode: str
    signal_level: str | None
    template_id: str | None
    raw_content: str
    normalized_content: str | None
    analysis_content: str | None
    author_id: str | None
    reported_by: str | None
    operator_id: str | None
    entry_source: str
    device_id: str | None
    location_code: str | None
    category: str | None
    priority: int | None
    status: str
    reviewed_by: str | None
    analyzed_by: str | None
    assigned_to: str | None
    assigned_role: str | None = None
    review_due_at: datetime | None
    last_transition_reason: str | None
    conflict_flag: bool
    conflict_basis: str | None
    selected_at: datetime | None
    source_hash_sha256: str
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    analyzed_at: datetime | None
    review_revision: int
    workbench_flags: list[str] = Field(default_factory=list)
    workbench_priority: int = 0
    attachment_count: int = 0
    channel_access: str = "NOT_LINKED"
    channel_labels: list[str] = Field(default_factory=list)


class FieldCommentTraceDocumentResponse(BaseModel):
    document_id: str
    title: str
    status: str
    latest_version_id: str | None
    published_version_id: str | None
    generated_version_ids: list[str]
    observed_version_id: str | None = None


class FieldCommentTraceReportResponse(BaseModel):
    report_id: str
    report_type: str
    title: str
    status: str
    relation_type: str | None
    source_version_id: str | None
    source_revision: int | None
    source_hash_sha256: str
    trace_id: str
    generated_document: FieldCommentTraceDocumentResponse | None


class FieldCommentTraceWorkSequenceResponse(BaseModel):
    board_id: str
    board_title: str
    item_id: str
    item_title: str
    status: str
    assigned_to: str | None
    document_id: str | None


class FieldCommentTraceResponse(BaseModel):
    field_comment: FieldCommentResponse
    source_document: FieldCommentTraceDocumentResponse | None
    attachments: list[FieldCommentAttachmentResponse]
    audit: list[FieldCommentAuditResponse]
    work_sequences: list[FieldCommentTraceWorkSequenceResponse]
    reports: list[FieldCommentTraceReportResponse]


class FieldCommentAttachmentFileResponse(BaseModel):
    storage_type: str
    storage_key: str
    original_filename: str
    extension: str | None
    mime_type: str | None
    file_family: str | None
    size_bytes: int | None
    hash_sha256: str | None


class FieldCommentAttachmentResponse(BaseModel):
    attachment_id: str
    comment_id: str
    attachment_type: str
    caption: str | None
    captured_at: datetime | None
    created_by: str | None
    created_at: datetime
    file: FieldCommentAttachmentFileResponse
