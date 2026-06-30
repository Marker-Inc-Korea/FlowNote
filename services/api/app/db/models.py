from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer
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
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_device_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer")
    location_code: Mapped[str | None] = mapped_column(String(64))
    group_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FieldNote(TimestampMixin, Base):
    __tablename__ = "field_notes"
    __table_args__ = (
        CheckConstraint(
            "note_type IN ('experience', 'work_evaluation', 'issue')", name="ck_field_note_type"
        ),
        CheckConstraint(
            (
                "input_mode IN ('signal', 'free_text', 'template', 'template_with_text', "
                "'admin_proxy', 'mes_integration')"
            ),
            name="ck_field_note_input_mode",
        ),
        CheckConstraint(
            (
                "status IN ('NEW', 'NEEDS_REVIEW', 'ANALYZED', 'REVIEWED', "
                "'SELECTED', 'EXCLUDED', 'ARCHIVED')"
            ),
            name="ck_field_note_status",
        ),
        CheckConstraint(
            "document_id IS NOT NULL OR structure_item_id IS NOT NULL OR work_record_id IS NOT NULL",
            name="ck_field_note_has_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.document_id"))
    document_version_id: Mapped[str | None] = mapped_column(String(64))
    structure_item_id: Mapped[str | None] = mapped_column(String(64))
    work_record_id: Mapped[str | None] = mapped_column(String(64))
    note_type: Mapped[str] = mapped_column(String(30), nullable=False)
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
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FieldNoteAttachment(Base):
    __tablename__ = "field_note_attachments"
    __table_args__ = (
        CheckConstraint("attachment_type IN ('photo', 'document', 'other')", name="ck_attachment_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    note_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_notes.note_id"), nullable=False, index=True
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
    note_type: Mapped[str | None] = mapped_column(String(30))
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


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'AI_DRAFTED', 'REVIEWED', 'APPROVED', 'ARCHIVED')",
            name="ck_report_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    __table_args__ = (Index("ix_report_sources_report", "report_id", "source_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reports.report_id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    relation_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
