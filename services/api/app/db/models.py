from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, event, inspect
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
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class WorkSequenceBoard(TimestampMixin, Base):
    __tablename__ = "work_sequence_boards"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_work_sequence_board_status"),
        Index("ix_work_sequence_boards_date_status", "board_date", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    line_code: Mapped[str | None] = mapped_column(String(64), index=True)
    board_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))


class WorkSequenceItem(TimestampMixin, Base):
    __tablename__ = "work_sequence_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('WAITING', 'IN_PROGRESS', 'HOLD', 'COMPLETED')",
            name="ck_work_sequence_item_status",
        ),
        UniqueConstraint("board_id", "sort_order", name="uq_work_sequence_items_board_sort"),
        Index("ix_work_sequence_items_board_order", "board_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_boards.board_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    work_order_no: Mapped[str | None] = mapped_column(String(120), index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.document_id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="WAITING")
    hold_reason: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))


class WorkSequenceChangeHistory(Base):
    __tablename__ = "work_sequence_change_history"
    __table_args__ = (
        Index("ix_work_sequence_history_board_created", "board_id", "created_at"),
        Index("ix_work_sequence_history_item_created", "item_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_boards.board_id"), nullable=False, index=True
    )
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("work_sequence_items.item_id"))
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkSequenceNotificationCandidate(Base):
    __tablename__ = "work_sequence_notification_candidates"
    __table_args__ = (
        CheckConstraint("status IN ('CANDIDATE', 'SENT', 'DISMISSED')", name="ck_work_sequence_notify_status"),
        Index("ix_work_sequence_notify_board_created", "board_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_boards.board_id"), nullable=False, index=True
    )
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("work_sequence_items.item_id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    recipient_hint: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CANDIDATE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationChannel(TimestampMixin, Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        CheckConstraint(
            (
                "channel_type IN ('LINE', 'EQUIPMENT', 'PROCESS', 'WORK_GROUP', "
                "'HANDOVER', 'WORK_RECORD', 'CUSTOM')"
            ),
            name="ck_notification_channel_type",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_notification_channel_status"),
        Index("ix_notification_channels_type_status", "channel_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    channel_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50), index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))


class NotificationChannelMember(Base):
    __tablename__ = "notification_channel_members"
    __table_args__ = (
        CheckConstraint("member_role IN ('OWNER', 'MANAGER', 'MEMBER')", name="ck_channel_member_role"),
        CheckConstraint("status IN ('ACTIVE', 'REMOVED')", name="ck_channel_member_status"),
        UniqueConstraint("channel_id", "user_id", name="uq_channel_members_channel_user"),
        Index("ix_channel_members_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notification_channels.channel_id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    member_role: Mapped[str] = mapped_column(String(20), nullable=False, default="MEMBER")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_read_message_id: Mapped[str | None] = mapped_column(String(64))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    __table_args__ = (
        CheckConstraint(
            (
                "message_type IN ('NOTICE', 'DOCUMENT_EVENT', 'FIELD_COMMENT_EVENT', "
                "'WORK_SEQUENCE_EVENT', 'HANDOVER', 'SYSTEM')"
            ),
            name="ck_channel_message_type",
        ),
        CheckConstraint(
            (
                "source_type IN ('DOCUMENT', 'FIELD_COMMENT', 'WORK_SEQUENCE_ITEM', "
                "'WORK_SEQUENCE_HISTORY', 'WORK_RECORD', 'REPORT', 'HANDOVER', 'SYSTEM')"
            ),
            name="ck_channel_message_source_type",
        ),
        Index("ix_channel_messages_channel_created", "channel_id", "created_at"),
        Index("ix_channel_messages_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notification_channels.channel_id"), nullable=False, index=True
    )
    message_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Handover(TimestampMixin, Base):
    __tablename__ = "handovers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'SENT', 'ACKNOWLEDGED', 'FOLLOW_UP_REQUIRED', 'ARCHIVED')",
            name="ck_handover_status",
        ),
        CheckConstraint(
            (
                "source_type IN ('DOCUMENT', 'FIELD_COMMENT', 'WORK_SEQUENCE_ITEM', "
                "'WORK_SEQUENCE_HISTORY', 'WORK_RECORD', 'REPORT', 'CHANNEL_MESSAGE')"
            ),
            name="ck_handover_source_type",
        ),
        Index("ix_handovers_channel_status", "channel_id", "status"),
        Index("ix_handovers_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handover_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notification_channels.channel_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[str | None] = mapped_column(String(64))
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SENT")
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandoverReceipt(Base):
    __tablename__ = "handover_receipts"
    __table_args__ = (
        CheckConstraint(
            "receipt_status IN ('UNREAD', 'READ', 'ACKNOWLEDGED', 'FOLLOW_UP_REQUIRED')",
            name="ck_handover_receipt_status",
        ),
        UniqueConstraint("handover_id", "recipient_id", name="uq_handover_receipts_handover_recipient"),
        Index("ix_handover_receipts_recipient_status", "recipient_id", "receipt_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    handover_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("handovers.handover_id"), nullable=False, index=True
    )
    recipient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    receipt_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNREAD")
    note: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'AI_DRAFTED', 'REVIEWED', 'APPROVED', 'ARCHIVED')",
            name="ck_report_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    report_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    analysis_content: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    action_plan: Mapped[str | None] = mapped_column(Text)
    work_record_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("work_records.work_record_id"))
    structure_item_id: Mapped[str | None] = mapped_column(String(64))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    ai_draft_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.document_id"))
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportSource(Base):
    __tablename__ = "report_sources"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "source_type",
            "source_id",
            "source_version_id",
            name="uq_report_sources_report_source_version",
        ),
        Index("ix_report_sources_report", "report_id", "source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reports.report_id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relation_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AISearchCandidate(Base):
    __tablename__ = "ai_search_candidates"
    __table_args__ = (
        CheckConstraint(
            (
                "source_type IN ('PUBLISHED_DOCUMENT_VERSION', 'FIELD_COMMENT', "
                "'WORK_SEQUENCE_HISTORY', 'REPORT_SOURCE')"
            ),
            name="ck_ai_search_candidate_source_type",
        ),
        UniqueConstraint(
            "source_type",
            "source_id",
            "source_version_id",
            name="uq_ai_search_candidates_source",
        ),
        Index("ix_ai_search_candidates_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    parent_type: Mapped[str | None] = mapped_column(String(50))
    parent_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_status: Mapped[str | None] = mapped_column(String(30))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AISearchEvaluationRun(Base):
    __tablename__ = "ai_search_evaluation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('PASSED', 'FAILED')", name="ck_ai_search_evaluation_run_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_label: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    evaluated_as_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_identity_stable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ranking_stable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchEvaluationCase(Base):
    __tablename__ = "ai_search_evaluation_cases"
    __table_args__ = (
        UniqueConstraint("run_id", "case_key", name="uq_ai_search_evaluation_case"),
        Index("ix_ai_search_evaluation_cases_case_key_id", "case_key", "id"),
        CheckConstraint(
            "expected_outcome IN ('SUFFICIENT', 'INSUFFICIENT_EVIDENCE')",
            name="ck_ai_search_evaluation_expected_outcome",
        ),
        CheckConstraint(
            "actual_outcome IN ('SUFFICIENT', 'INSUFFICIENT_EVIDENCE')",
            name="ck_ai_search_evaluation_actual_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_evaluation_runs.run_id"), nullable=False, index=True
    )
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    actual_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    ranking_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchGroundTruthCase(Base):
    __tablename__ = "ai_search_ground_truth_cases"
    __table_args__ = (
        UniqueConstraint("customer_scope", "site_scope", "case_key", name="uq_ai_ground_truth_scope_case"),
        CheckConstraint(
            (
                "category IN ('SAFETY', 'QUALITY', 'EQUIPMENT_ANOMALY', 'WORK_HOLD', "
                "'REWORK', 'HANDOVER', 'LATEST_PUBLISHED_DOCUMENT', 'CONFLICTING_RECORDS')"
            ),
            name="ck_ai_ground_truth_category",
        ),
        CheckConstraint(
            "scenario_type IN ('NORMAL', 'EXCLUSION', 'CONFLICT')",
            name="ck_ai_ground_truth_scenario_type",
        ),
        Index(
            "ix_ai_ground_truth_scope_approved",
            "customer_scope",
            "site_scope",
            "line_scope",
            "approved_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ground_truth_case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    line_scope: Mapped[str | None] = mapped_column(String(64))
    database_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_rank_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_rank_max: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchGroundTruthProvenance(Base):
    __tablename__ = "ai_search_ground_truth_provenance"
    __table_args__ = (
        CheckConstraint(
            "data_classification IN ('SYNTHETIC', 'TEST', 'ANONYMOUS_FIELD', 'PILOT')",
            name="ck_ai_ground_truth_provenance_classification",
        ),
        CheckConstraint(
            "readiness_track IN ('SMOKE_REGRESSION', 'FIELD_READINESS')",
            name="ck_ai_ground_truth_provenance_track",
        ),
        CheckConstraint(
            "approval_status IN ('PENDING_SECOND_APPROVAL', 'APPROVED', 'REJECTED')",
            name="ck_ai_ground_truth_provenance_approval",
        ),
        CheckConstraint(
            "second_approved_by IS NULL OR second_approved_by <> first_approved_by",
            name="ck_ai_ground_truth_distinct_approvers",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provenance_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ground_truth_case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_ground_truth_cases.ground_truth_case_id"),
        unique=True, nullable=False, index=True
    )
    data_classification: Mapped[str] = mapped_column(String(30), nullable=False)
    readiness_track: Mapped[str] = mapped_column(String(30), nullable=False)
    provenance_note: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contains_sensitive_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False)
    first_approved_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    first_approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    second_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    second_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIGroundTruthDatasetVersion(Base):
    __tablename__ = "ai_ground_truth_dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "customer_scope", "site_scope", "dataset_key", "version",
            name="uq_ai_ground_truth_dataset_version",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'IN_REVIEW', 'PENDING_FIRST_APPROVAL', "
            "'PENDING_SECOND_APPROVAL', 'APPROVED', 'SUPERSEDED', 'RETIRED')",
            name="ck_ai_ground_truth_dataset_status",
        ),
        CheckConstraint(
            "readiness_track IN ('SMOKE_REGRESSION', 'FIELD_READINESS')",
            name="ck_ai_ground_truth_dataset_track",
        ),
        Index(
            "ix_ai_ground_truth_dataset_scope_status",
            "customer_scope", "site_scope", "line_scope", "status", "version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    dataset_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    line_scope: Mapped[str | None] = mapped_column(String(64))
    database_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    readiness_track: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    author_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    first_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    second_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    replaces_dataset_version_id: Mapped[str | None] = mapped_column(String(64))
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    second_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIGroundTruthDatasetCase(Base):
    __tablename__ = "ai_ground_truth_dataset_cases"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "ground_truth_case_id", name="uq_ai_dataset_case"),
        UniqueConstraint("dataset_version_id", "case_key", name="uq_ai_dataset_case_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_ground_truth_dataset_versions.dataset_version_id"),
        nullable=False, index=True,
    )
    ground_truth_case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_ground_truth_cases.ground_truth_case_id"),
        nullable=False, index=True,
    )
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    added_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEvaluationDatasetBinding(Base):
    __tablename__ = "ai_evaluation_dataset_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_evaluation_runs.run_id"), unique=True, nullable=False, index=True
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_ground_truth_dataset_versions.dataset_version_id"),
        nullable=False, index=True,
    )
    dataset_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ai_prompt_versions_name_version"),
        CheckConstraint(
            "allowed_purpose IN ('EVIDENCE_SEARCH', 'EVIDENCE_SUMMARY')",
            name="ck_ai_prompt_version_purpose",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIQuery(Base):
    __tablename__ = "ai_queries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RECEIVED', 'BLOCKED', 'CALLING', 'SUCCEEDED', "
            "'INSUFFICIENT_EVIDENCE', 'CITATION_VALIDATION_FAILED', 'FAILED')",
            name="ck_ai_query_status",
        ),
        CheckConstraint(
            "response_storage_mode IN ('DO_NOT_STORE', 'STORE_90_DAYS')",
            name="ck_ai_query_response_storage_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False, default="DEFAULT")
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False, default="DEFAULT")
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RECEIVED")
    prompt_version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("ai_prompt_versions.prompt_version_id"))
    prompt_snapshot_json: Mapped[str | None] = mapped_column(Text)
    approval_snapshot_json: Mapped[str | None] = mapped_column(Text)
    response_storage_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="DO_NOT_STORE")
    response_text: Mapped[str | None] = mapped_column(Text)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    regeneration_of_query_id: Mapped[str | None] = mapped_column(String(64))
    regenerable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    block_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIQueryEvidenceCandidate(Base):
    __tablename__ = "ai_query_evidence_candidates"
    __table_args__ = (UniqueConstraint("query_id", "candidate_id", name="uq_ai_query_evidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_for_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_externally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    eligibility_result: Mapped[str] = mapped_column(String(30), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIQueryCitation(Base):
    __tablename__ = "ai_query_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    citation_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    claim_key: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    internal_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AICallAttempt(Base):
    __tablename__ = "ai_call_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    sanitized_error_message: Mapped[str | None] = mapped_column(String(255))
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    cost_micros: Mapped[int | None] = mapped_column(Integer)


class AITransferApproval(Base):
    __tablename__ = "ai_transfer_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    allowed_purposes: Mapped[str] = mapped_column(
        Text, nullable=False, default='["EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"]'
    )
    allowed_source_types: Mapped[str] = mapped_column(Text, nullable=False)
    data_handling_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class AIOperationalPolicy(Base):
    """Fail-safe operational limits. Secrets are intentionally absent."""

    __tablename__ = "ai_operational_policies"
    __table_args__ = (
        UniqueConstraint("customer_scope", "site_scope", name="uq_ai_operational_policy_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    daily_cost_budget_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    query_payload_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    response_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    audit_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    allow_audit_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIProviderOnboardingReview(Base):
    """Versioned provider due-diligence and four-party start decision."""

    __tablename__ = "ai_provider_onboarding_reviews"
    __table_args__ = (
        UniqueConstraint(
            "customer_scope", "site_scope", "provider", "model_scope", "review_version",
            name="uq_ai_provider_onboarding_review_version",
        ),
        CheckConstraint(
            "technical_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_technical_status",
        ),
        CheckConstraint(
            "security_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_security_status",
        ),
        CheckConstraint(
            "legal_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_legal_status",
        ),
        CheckConstraint(
            "customer_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_customer_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    review_version: Mapped[str] = mapped_column(String(80), nullable=False)
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_purposes_json: Mapped[str] = mapped_column(Text, nullable=False)
    technical_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    security_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    legal_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    technical_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    security_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    legal_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    customer_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    technical_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    security_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIOperationAuditEvent(Base):
    __tablename__ = "ai_operation_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), index=True)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AIRetentionAudit(Base):
    __tablename__ = "ai_retention_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retention_audit_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    query_text_action: Mapped[str] = mapped_column(String(30), nullable=False)
    response_text_action: Mapped[str] = mapped_column(String(30), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AISensitiveDataPolicy(Base):
    """Site-scoped deny terms and customer identifiers for the provider boundary."""

    __tablename__ = "ai_sensitive_data_policies"
    __table_args__ = (
        UniqueConstraint(
            "customer_scope",
            "site_scope",
            "version",
            name="uq_ai_sensitive_data_policy_scope_version",
        ),
        Index(
            "ix_ai_sensitive_data_policy_scope_active",
            "customer_scope",
            "site_scope",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    forbidden_terms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    customer_identifiers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(AIPromptVersion, "before_update")
def prevent_approved_prompt_content_update(_mapper: object, _connection: object, target: AIPromptVersion) -> None:
    """Approved prompt content is immutable; retirement metadata may still be updated."""
    if target.approved_at is None:
        return
    state = inspect(target)
    immutable_fields = ("name", "version", "template_hash", "template_text", "allowed_purpose")
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError("Approved AI prompt versions are immutable; create a new version.")


class DocumentAccessLog(Base):
    __tablename__ = "document_access_logs"
    __table_args__ = (Index("ix_document_access_logs_document_created", "document_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    document_version_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    device_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("terminal_devices.device_id"))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ControlledCopyGrant(Base):
    __tablename__ = "controlled_copy_grants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ISSUED', 'CONSUMED', 'EXPIRED', 'FAILED')",
            name="ck_controlled_copy_grant_status",
        ),
        Index("ix_controlled_copy_grants_expiry_status", "expires_at", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("document_versions.version_id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_sessions.session_id"), nullable=False, index=True
    )
    device_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("terminal_devices.device_id"))
    expected_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ISSUED")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AndroidDocumentViewGrant(Base):
    __tablename__ = "android_document_view_grants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ISSUED', 'CONSUMED', 'EXPIRED', 'FAILED')",
            name="ck_android_document_view_grant_status",
        ),
        Index("ix_android_document_view_grants_expiry_status", "expires_at", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("document_versions.version_id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_sessions.session_id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("terminal_devices.device_id"), nullable=False, index=True
    )
    media_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ISSUED")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActivityHistory(Base):
    __tablename__ = "activity_history"
    __table_args__ = (
        Index("ix_activity_history_created", "created_at", "id"),
        Index("ix_activity_history_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    history_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    target_title: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
