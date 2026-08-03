from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, event, inspect
from sqlalchemy import String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ServerIdentity(Base):
    __tablename__ = "server_identity"
    __table_args__ = (CheckConstraint("singleton_id = 1", name="ck_server_identity_singleton"),)

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    server_instance_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    server_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_contract: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    api_contract_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    api_contract_max: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


@event.listens_for(ServerIdentity, "before_update")
def prevent_server_instance_id_update(
    _mapper: object, _connection: object, target: ServerIdentity
) -> None:
    if inspect(target).attrs.server_instance_id.history.has_changes():
        raise ValueError("server_instance_id is immutable; increment server_epoch instead.")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REVIEW_REQUIRED', 'APPLIED', 'FAILED')",
            name="ck_reconciliation_run_status",
        ),
        Index("ix_reconciliation_runs_client_created", "client_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(100), nullable=False)
    server_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    server_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_server_instance_id: Mapped[str | None] = mapped_column(String(64))
    previous_server_epoch: Mapped[int | None] = mapped_column(Integer)
    trigger_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="REVIEW_REQUIRED")
    client_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    server_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approval_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('CONFIRMED', 'ABSENT', 'DIVERGED')",
            name="ck_reconciliation_item_verdict",
        ),
        CheckConstraint(
            "proposed_action IN ('REBOUND', 'REQUEUE', 'CONFLICT')",
            name="ck_reconciliation_item_action",
        ),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('REBOUND', 'REQUEUE', 'CONFLICT')",
            name="ck_reconciliation_item_resolution",
        ),
        UniqueConstraint("run_id", "client_item_id", name="uq_reconciliation_run_client_item"),
        Index("ix_reconciliation_items_run_verdict", "run_id", "verdict"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reconciliation_runs.run_id"), nullable=False, index=True
    )
    client_item_id: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    local_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    local_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    previous_server_document_id: Mapped[str | None] = mapped_column(String(64))
    previous_server_version_id: Mapped[str | None] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    proposed_action: Mapped[str] = mapped_column(String(20), nullable=False)
    server_document_id: Mapped[str | None] = mapped_column(String(64))
    server_version_id: Mapped[str | None] = mapped_column(String(64))
    server_revision: Mapped[int | None] = mapped_column(Integer)
    server_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text)
    resolution_action: Mapped[str | None] = mapped_column(String(20))
    resolution_status: Mapped[str | None] = mapped_column(String(30))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_accounts"
    __table_args__ = (
        CheckConstraint(
            (
                "role IN ('admin', 'manager', 'viewer', 'system-admin', 'document-admin', "
                "'assistant-manager', 'department-manager', 'line-foreman', 'team-lead', "
                "'team-member')"
            ),
            name="ck_user_role",
        ),
        CheckConstraint("status IN ('ACTIVE', 'LOCKED', 'DISABLED')", name="ck_user_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    login_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("roles.role_id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'REVOKED', 'EXPIRED')", name="ck_auth_session_status"),
        Index("ix_auth_sessions_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    device_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("terminal_devices.device_id"))
    access_token_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(120))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OperatorProfile(TimestampMixin, Base):
    __tablename__ = "operator_profiles"
    __table_args__ = (
        CheckConstraint(
            "operator_type IN ('individual', 'group', 'lead', 'proxy_admin', 'external')",
            name="ck_operator_type",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_operator_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    operator_type: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    line_code: Mapped[str | None] = mapped_column(String(64))
    process_code: Mapped[str | None] = mapped_column(String(64))
    equipment_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class FileObject(Base):
    __tablename__ = "file_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_type: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(30))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_family: Mapped[str | None] = mapped_column(String(50))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    hash_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('WORKING', 'IN_REVIEW', 'PUBLISHED', 'ARCHIVED', 'DELETED')",
            name="ck_document_status",
        ),
        Index("ix_documents_title", "title"),
        Index("ix_documents_type_status", "document_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    category_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="WORKING")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_version_id: Mapped[str | None] = mapped_column(String(64))
    published_version_id: Mapped[str | None] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_versions_document_version"),
        CheckConstraint(
            (
                "version_status IN ('WORKING', 'IN_REVIEW', 'APPROVED', 'PUBLISHED', "
                "'SUPERSEDED', 'ARCHIVED')"
            ),
            name="ck_document_version_status",
        ),
        Index("ix_document_versions_document_latest", "document_id", "is_latest"),
        Index("ix_document_versions_document_published", "document_id", "is_published"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    file_object_id: Mapped[int] = mapped_column(ForeignKey("file_objects.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(80))
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    version_status: Mapped[str] = mapped_column(String(20), nullable=False, default="WORKING")
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentMutationReceipt(Base):
    __tablename__ = "document_mutation_receipts"
    __table_args__ = (
        Index(
            "ix_document_mutation_receipts_document_created",
            "document_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    mutation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    applied_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentTagRevision(Base):
    __tablename__ = "document_tag_revisions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "document_revision",
            name="uq_document_tag_revisions_document_revision",
        ),
        Index(
            "ix_document_tag_revisions_document_revision",
            "document_id",
            "document_revision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    document_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False)
    mutation_key: Mapped[str | None] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TagDefinition(Base):
    __tablename__ = "tag_definitions"
    __table_args__ = (
        CheckConstraint(
            "tag_type IN ('equipment', 'item', 'process', 'error_type', 'line', 'location', 'custom')",
            name="ck_tag_type",
        ),
        UniqueConstraint("tag_type", "code", name="uq_tag_definitions_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tag_type: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_tag_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tag_definitions.tag_id"))
    external_system: Mapped[str | None] = mapped_column(String(50))
    external_ref_id: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"
    __table_args__ = (UniqueConstraint("document_id", "tag_id", name="uq_document_tags_document_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tag_definitions.tag_id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TerminalDevice(TimestampMixin, Base):
    __tablename__ = "terminal_devices"
    __table_args__ = (
        CheckConstraint("device_mode IN ('viewer', 'admin_support')", name="ck_device_mode"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'RETIRED')", name="ck_device_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer")
    location_code: Mapped[str | None] = mapped_column(String(64))
    group_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    updated_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    replaced_device_id: Mapped[str | None] = mapped_column(String(64))


class FieldComment(TimestampMixin, Base):
    __tablename__ = "field_comments"
    __table_args__ = (
        CheckConstraint(
            "comment_type IN ('experience', 'work_evaluation', 'issue')", name="ck_field_comment_type"
        ),
        CheckConstraint(
            (
                "input_mode IN ('signal', 'free_text', 'template', 'template_with_text', "
                "'admin_proxy', 'mes_integration')"
            ),
            name="ck_field_comment_input_mode",
        ),
        CheckConstraint(
            (
                "status IN ('NEW', 'NEEDS_REVIEW', 'ANALYZED', 'REVIEWED', "
                "'SELECTED', 'EXCLUDED', 'ARCHIVED')"
            ),
            name="ck_field_comment_status",
        ),
        CheckConstraint(
            "document_id IS NOT NULL OR structure_item_id IS NOT NULL OR work_record_id IS NOT NULL",
            name="ck_field_comment_has_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.document_id"))
    document_version_id: Mapped[str | None] = mapped_column(String(64))
    structure_item_id: Mapped[str | None] = mapped_column(String(64))
    work_record_id: Mapped[str | None] = mapped_column(String(64))
    comment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    input_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    signal_level: Mapped[str | None] = mapped_column(String(20))
    template_id: Mapped[str | None] = mapped_column(String(64))
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text)
    analysis_content: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    reported_by: Mapped[str | None] = mapped_column(String(64))
    operator_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operator_profiles.operator_id"))
    entry_source: Mapped[str] = mapped_column(String(30), nullable=False, default="field_user")
    device_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("terminal_devices.device_id"))
    location_code: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NEW")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    analyzed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    assigned_to: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transition_reason: Mapped[str | None] = mapped_column(Text)
    conflict_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_basis: Mapped[str | None] = mapped_column(Text)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FieldCommentReviewMutationReceipt(Base):
    __tablename__ = "field_comment_review_mutation_receipts"
    __table_args__ = (
        UniqueConstraint("comment_id", "review_revision", name="uq_field_comment_review_receipt_revision"),
        Index("ix_field_comment_review_receipts_comment_created", "comment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    comment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_comments.comment_id"), nullable=False, index=True
    )
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(FieldComment, "before_update")
def prevent_field_comment_source_update(_mapper: object, _connection: object, target: FieldComment) -> None:
    """Field input is evidence; manager interpretation must use separate columns."""
    state = inspect(target)
    immutable_fields = (
        "comment_id",
        "document_id",
        "document_version_id",
        "structure_item_id",
        "work_record_id",
        "comment_type",
        "input_mode",
        "signal_level",
        "template_id",
        "raw_content",
        "author_id",
        "reported_by",
        "operator_id",
        "entry_source",
        "device_id",
        "location_code",
        "created_at",
    )
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError("FieldComment source fields are immutable.")


@event.listens_for(FieldComment, "before_delete")
def prevent_field_comment_delete(_mapper: object, _connection: object, _target: FieldComment) -> None:
    raise ValueError("FieldComment source records cannot be deleted.")


class FieldCommentAttachment(Base):
    __tablename__ = "field_comment_attachments"
    __table_args__ = (
        CheckConstraint("attachment_type IN ('photo', 'document', 'other')", name="ck_attachment_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    comment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_comments.comment_id"), nullable=False, index=True
    )
    file_object_id: Mapped[int] = mapped_column(ForeignKey("file_objects.id"), nullable=False)
    attachment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommentTemplate(TimestampMixin, Base):
    __tablename__ = "comment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str | None] = mapped_column(String(30))
    document_type: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(80))
    location_code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))


class WorkRecord(TimestampMixin, Base):
    __tablename__ = "work_records"
    __table_args__ = (
        CheckConstraint("source_type IN ('manual', 'external')", name="ck_work_record_source_type"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'COMPLETED', 'ARCHIVED')", name="ck_work_record_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_record_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    work_order_no: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    work_instruction_document_id: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    external_system: Mapped[str | None] = mapped_column(String(50))
    external_ref_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    latest_version_id: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))


class WorkRecordVersion(Base):
    __tablename__ = "work_record_versions"
    __table_args__ = (
        UniqueConstraint("work_record_id", "version_no", name="uq_work_record_versions_record_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    work_record_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_records.work_record_id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    result_note: Mapped[str | None] = mapped_column(Text)
    issue_note: Mapped[str | None] = mapped_column(Text)
    action_note: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
