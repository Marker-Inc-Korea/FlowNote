from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models_core import TimestampMixin


class WorkSequenceCandidateDelivery(TimestampMixin, Base):
    __tablename__ = "work_sequence_candidate_deliveries"
    __table_args__ = (
        CheckConstraint("delivery_mode IN ('CHANNEL', 'HANDOVER')", name="ck_wseq_delivery_mode"),
        CheckConstraint("status IN ('PARTIAL', 'COMPLETED')", name="ck_wseq_delivery_status"),
        UniqueConstraint("candidate_id", "channel_id", name="uq_wseq_delivery_candidate_channel"),
        Index("ix_wseq_delivery_board_created", "board_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_notification_candidates.candidate_id"), nullable=False, index=True
    )
    board_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_boards.board_id"), nullable=False, index=True
    )
    board_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    change_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_change_history.change_id"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notification_channels.channel_id"), nullable=False, index=True
    )
    delivery_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    related_document_id: Mapped[str | None] = mapped_column(String(64))
    related_document_version_id: Mapped[str | None] = mapped_column(String(64))
    requested_recipient_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("channel_messages.message_id"))
    handover_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("handovers.handover_id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PARTIAL")
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)


class WorkSequenceDeliveryRecipient(Base):
    __tablename__ = "work_sequence_delivery_recipients"
    __table_args__ = (
        CheckConstraint("delivery_status IN ('DELIVERED', 'FAILED')", name="ck_wseq_recipient_status"),
        UniqueConstraint("delivery_id", "recipient_id", name="uq_wseq_delivery_recipient"),
        Index("ix_wseq_delivery_recipient_status", "recipient_id", "delivery_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_recipient_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    delivery_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("work_sequence_candidate_deliveries.delivery_id"), nullable=False, index=True
    )
    recipient_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    handover_receipt_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("handover_receipts.receipt_id"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkSequenceDeliveryTemplate(TimestampMixin, Base):
    __tablename__ = "work_sequence_delivery_templates"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_wseq_template_status"),
        UniqueConstraint("site_scope", "name", name="uq_wseq_template_site_name"),
        Index("ix_wseq_template_site_status", "site_scope", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
