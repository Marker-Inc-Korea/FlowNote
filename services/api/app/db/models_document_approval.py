from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentApproval(Base):
    __tablename__ = "document_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'STALE', 'PUBLISHED')",
            name="ck_document_approval_status",
        ),
        Index("ix_document_approvals_document_created", "document_id", "created_at"),
        Index("ix_document_approvals_reviewer_status", "reviewer_user_id", "status"),
        Index("ix_document_approvals_role_status", "reviewer_role", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("document_versions.version_id"), nullable=False, index=True
    )
    base_document_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTED")
    requester_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), index=True
    )
    reviewer_role: Mapped[str | None] = mapped_column(String(50), index=True)
    request_reason: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentApprovalEvent(Base):
    __tablename__ = "document_approval_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED', "
            "'MARKED_STALE', 'PUBLISHED', 'PUBLICATION_WITHDRAWN')",
            name="ck_document_approval_event_type",
        ),
        Index("ix_document_approval_events_approval_created", "approval_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    approval_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("document_approvals.approval_id"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), nullable=False, index=True
    )
    version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    document_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentApprovalMutationReceipt(Base):
    __tablename__ = "document_approval_mutation_receipts"
    __table_args__ = (
        Index("ix_document_approval_receipts_approval_created", "approval_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    intent_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(DocumentApprovalEvent, "before_update")
def prevent_document_approval_event_update(
    _mapper: object,
    _connection: object,
    _target: DocumentApprovalEvent,
) -> None:
    raise ValueError("Document approval events are append-only.")


@event.listens_for(DocumentApprovalEvent, "before_delete")
def prevent_document_approval_event_delete(
    _mapper: object,
    _connection: object,
    _target: DocumentApprovalEvent,
) -> None:
    raise ValueError("Document approval events are append-only.")
