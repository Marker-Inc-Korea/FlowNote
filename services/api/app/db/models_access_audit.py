from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer
from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
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
