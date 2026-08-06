from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer
from sqlalchemy import String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models_core import TimestampMixin

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
    board_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    board_revision: Mapped[int] = mapped_column(Integer, nullable=False)
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
class WorkSequenceMutationReceipt(Base):
    __tablename__ = "work_sequence_mutation_receipts"
    __table_args__ = (
        UniqueConstraint("board_id", "board_revision", name="uq_work_sequence_receipt_board_revision"),
        Index("ix_work_sequence_receipts_board_created", "board_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    mutation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    board_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_boards.board_id"), nullable=False, index=True
    )
    board_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    change_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_change_history.change_id"), unique=True, nullable=False
    )
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
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
    board_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    change_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("work_sequence_change_history.change_id"), index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    related_document_id: Mapped[str | None] = mapped_column(String(64))
    related_document_version_id: Mapped[str | None] = mapped_column(String(64))
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
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notification_channels.channel_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[str | None] = mapped_column(String(64))
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    source_revision: Mapped[int | None] = mapped_column(Integer)
    server_scope: Mapped[str | None] = mapped_column(String(500))
    intent_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    related_document_id: Mapped[str | None] = mapped_column(String(64))
    related_document_version_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SENT")
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    entry_source: Mapped[str] = mapped_column(String(30), nullable=False, default="field_user")
    device_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("terminal_devices.device_id")
    )
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
    report_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    source_set_hash_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    report_family_id: Mapped[str | None] = mapped_column(String(64), index=True)
    replaces_report_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("reports.report_id"), unique=True, index=True
    )
    replaces_report_revision: Mapped[int | None] = mapped_column(Integer)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    superseded_by_report_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("reports.report_id"), unique=True, index=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportMutationReceipt(Base):
    __tablename__ = "report_mutation_receipts"
    __table_args__ = (
        UniqueConstraint("report_id", "report_revision", name="uq_report_receipt_revision"),
        Index("ix_report_receipts_report_created", "report_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reports.report_id"), nullable=False, index=True
    )
    report_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_set_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_document_id: Mapped[str | None] = mapped_column(String(64))
    generated_version_id: Mapped[str | None] = mapped_column(String(64))
    report_family_id: Mapped[str | None] = mapped_column(String(64), index=True)
    replaces_report_id: Mapped[str | None] = mapped_column(String(64), index=True)
    replaces_report_revision: Mapped[int | None] = mapped_column(Integer)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    source_revision: Mapped[int | None] = mapped_column(Integer)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relation_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
