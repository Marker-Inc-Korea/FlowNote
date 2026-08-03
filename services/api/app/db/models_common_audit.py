from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEventEnvelope(Base):
    __tablename__ = "audit_event_envelopes"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS', 'REJECTED', 'CONFLICT')",
            name="ck_audit_event_envelope_result",
        ),
        CheckConstraint(
            "approval_status IN ('NOT_REQUIRED', 'PENDING', 'APPROVED', 'REJECTED')",
            name="ck_audit_event_envelope_approval_status",
        ),
        Index("ix_audit_event_envelopes_server_time", "server_time", "id"),
        Index(
            "ix_audit_event_envelopes_target_time",
            "target_type",
            "target_id",
            "server_time",
        ),
        Index("ix_audit_event_envelopes_correlation", "correlation_id"),
        Index("ix_audit_event_envelopes_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_sessions.session_id"), nullable=False, index=True
    )
    device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_version_id: Mapped[str | None] = mapped_column(String(64))
    target_revision: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_REQUIRED"
    )
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approval_reference: Mapped[str | None] = mapped_column(String(120))
    before_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    after_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    result_code: Mapped[str] = mapped_column(String(80), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    domain_audit_type: Mapped[str | None] = mapped_column(String(60))
    domain_audit_id: Mapped[str | None] = mapped_column(String(64))
    safe_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    server_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SyncMutationReceipt(Base):
    __tablename__ = "sync_mutation_receipts"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS', 'REJECTED', 'CONFLICT')",
            name="ck_sync_mutation_receipt_result",
        ),
        Index("ix_sync_mutation_receipts_target", "target_type", "target_id"),
        Index("ix_sync_mutation_receipts_created", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("audit_event_envelopes.event_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    result_code: Mapped[str] = mapped_column(String(80), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    domain_receipt_type: Mapped[str | None] = mapped_column(String(60))
    domain_receipt_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
