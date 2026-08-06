from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.db.models import (
    AISearchCandidate,
    AISensitiveDataPolicy,
    AITransferApproval,
    Document,
    DocumentVersion,
    FieldComment,
    NotificationChannel,
    NotificationChannelMember,
    Report,
    ReportSource,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.services.ai_response_validation import contains_prompt_injection

ALLOWED_FIELD_COMMENT_STATUSES = frozenset({"ANALYZED", "REVIEWED", "SELECTED"})
ALLOWED_SOURCE_TYPES = frozenset(
    {"PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"}
)
GLOBAL_SOURCE_ROLES = frozenset({"admin", "system-admin", "document-admin"})

MASK_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("RESIDENT_REGISTRATION_NUMBER", re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)"), "[주민번호 마스킹]"),
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[이메일 마스킹]"),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?82[- ]?)?0(?:1[016789]|2|[3-6][1-5])[- ]?\d{3,4}[- ]?\d{4}(?!\d)"), "[전화번호 마스킹]"),
)
BLOCK_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ACCOUNT_OR_TOKEN", re.compile(
        r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
        r"client[_ -]?secret|authorization|bearer)\b\s*[:=]?\s*\S+"
    )),
    ("LOCAL_PATH", re.compile(r"(?i)(?:\b[A-Z]:\\(?:[^\s\\]+\\)*[^\s\\]+|/(?:Users|home|var|etc|opt)/[^\s]+)")),
    ("CUSTOMER_IDENTIFIER", re.compile(r"(?i)\b(?:customer|cust|고객)[_ -]?(?:id|code|번호|식별자)\b\s*[:=]?\s*\S+")),
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _clean_text(*values: str | None) -> str:
    return "\n".join(value.strip() for value in values if value and value.strip())


def _json_string_set(value: str) -> set[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item).strip() for item in parsed if str(item).strip()}


@dataclass(frozen=True)
class ContentFilterResult:
    allowed: bool
    text: str | None
    reason_code: str | None
    detections: tuple[str, ...]


@dataclass(frozen=True)
class SensitivePolicySnapshot:
    policy_id: str
    content_hash: str
    state_revision: int


@dataclass(frozen=True)
class SourcePolicyResult:
    allowed: bool
    reason_code: str | None
    source_text: str | None
    content_hash: str


@dataclass(frozen=True)
class ProviderEvidence:
    candidate_id: str
    source_type: str
    source_id: str
    source_version_id: str | None
    trace_id: str
    trace_version_id: str | None
    content_hash: str
    rank: int
    excerpt: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "sourceType": self.source_type,
            "sourceId": self.source_id,
            "sourceVersionId": self.source_version_id,
            "traceId": self.trace_id,
            "traceVersionId": self.trace_version_id,
            "contentHash": self.content_hash,
            "rank": self.rank,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True)
class ProviderBoundaryPayload:
    purpose: str
    query: str
    query_hash: str
    prompt_version_id: str
    prompt_version: str
    trace_id: str
    sources: tuple[ProviderEvidence, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "query": self.query,
            "queryHash": self.query_hash,
            "promptVersionId": self.prompt_version_id,
            "promptVersion": self.prompt_version,
            "traceId": self.trace_id,
            "outputFormat": {
                "type": "json",
                "additionalProperties": False,
                "required": ["response", "claims"],
                "claimRequired": ["claimKey", "text", "candidateIds"],
                "rule": "모든 사실 주장은 하나 이상의 제공된 candidateId를 인용한다.",
            },
            "sources": [source.as_dict() for source in self.sources],
        }


class SensitiveContentFilter:
    def __init__(self, forbidden_terms: set[str], customer_identifiers: set[str]) -> None:
        self._forbidden_terms = forbidden_terms
        self._customer_identifiers = customer_identifiers

    def filter(self, text: str) -> ContentFilterResult:
        detections: list[str] = []
        if contains_prompt_injection(text):
            detections.append("PROMPT_INJECTION")
        for name, pattern in BLOCK_RULES:
            if pattern.search(text):
                detections.append(name)
        folded = text.casefold()
        if any(term.casefold() in folded for term in self._forbidden_terms):
            detections.append("SITE_FORBIDDEN_TERM")
        if any(identifier.casefold() in folded for identifier in self._customer_identifiers):
            detections.append("SITE_CUSTOMER_IDENTIFIER")
        if detections:
            return ContentFilterResult(False, None, "CONTENT_RESTRICTED", tuple(sorted(set(detections))))

        masked = text
        for name, pattern, replacement in MASK_RULES:
            masked, count = pattern.subn(replacement, masked)
            if count:
                detections.append(name)
        return ContentFilterResult(True, masked, None, tuple(sorted(set(detections))))


class AISourceAccessPolicy:
    """Re-fetches every source and evaluates access at query snapshot time."""

    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def evaluate(self, candidate: AISearchCandidate) -> SourcePolicyResult:
        source_text, author_id, state_allowed = self._source(candidate)
        if not state_allowed or source_text is None:
            return SourcePolicyResult(False, "SOURCE_FORBIDDEN", None, candidate.content_hash)
        if not self._author_role_allowed(author_id):
            return SourcePolicyResult(False, "SOURCE_FORBIDDEN", None, candidate.content_hash)
        if not self._channel_allowed(candidate):
            return SourcePolicyResult(False, "SOURCE_FORBIDDEN", None, candidate.content_hash)
        current_hash = sha256_text(source_text)
        if current_hash != candidate.content_hash:
            return SourcePolicyResult(False, "SOURCE_FORBIDDEN", None, current_hash)
        return SourcePolicyResult(True, None, source_text, current_hash)

    def _source(self, candidate: AISearchCandidate) -> tuple[str | None, str | None, bool]:
        if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
            document = self.session.scalar(select(Document).where(Document.document_id == candidate.source_id))
            version = self.session.scalar(
                select(DocumentVersion).where(DocumentVersion.version_id == candidate.source_version_id)
            )
            valid = bool(
                document
                and version
                and document.status == "PUBLISHED"
                and document.deleted_at is None
                and document.published_version_id == version.version_id
                and version.document_id == document.document_id
                and version.version_status == "PUBLISHED"
                and version.is_published
            )
            text = _clean_text(
                document.title if document else None,
                document.description if document else None,
                version.version_label if version else None,
                version.change_reason if version else None,
            )
            return text or None, version.created_by if version else None, valid

        if candidate.source_type == "FIELD_COMMENT":
            comment = self.session.scalar(
                select(FieldComment).where(FieldComment.comment_id == candidate.source_id)
            )
            valid = bool(comment and comment.status in ALLOWED_FIELD_COMMENT_STATUSES)
            text = _clean_text(
                comment.normalized_content if comment else None,
                comment.raw_content if comment else None,
                comment.analysis_content if comment else None,
                comment.category if comment else None,
                comment.signal_level if comment else None,
            )
            return text or None, comment.author_id if comment else None, valid

        if candidate.source_type == "WORK_SEQUENCE_HISTORY":
            history = self.session.scalar(
                select(WorkSequenceChangeHistory).where(
                    WorkSequenceChangeHistory.change_id == candidate.source_id
                )
            )
            text = _clean_text(
                history.change_type if history else None,
                history.before_value if history else None,
                history.after_value if history else None,
                history.change_reason if history else None,
            )
            board_exists = bool(
                history
                and self.session.scalar(
                    select(WorkSequenceBoard.id).where(WorkSequenceBoard.board_id == history.board_id)
                )
            )
            return text or None, history.actor_id if history else None, board_exists

        if candidate.source_type == "REPORT_SOURCE":
            source = self.session.scalar(
                select(ReportSource).where(ReportSource.id == int(candidate.source_id))
            ) if candidate.source_id.isdigit() else None
            report = self.session.scalar(
                select(Report).where(Report.report_id == source.report_id)
            ) if source else None
            valid = bool(
                source
                and report
                and report.status != "ARCHIVED"
                and report.superseded_by_report_id is None
                and self._report_origin_allowed(source)
            )
            text = _clean_text(
                report.title if report else None,
                report.summary if report else None,
                report.analysis_content if report else None,
                report.conclusion if report else None,
                report.action_plan if report else None,
                f"{source.source_type}: {source.source_id}" if source else None,
                source.source_version_id if source else None,
                source.relation_type if source else None,
            )
            return text or None, report.created_by if report else None, valid

        return None, None, False

    def _report_origin_allowed(self, source: ReportSource) -> bool:
        source_type = source.source_type.strip().upper()
        if source_type == "FIELD_COMMENT":
            comment = self.session.scalar(
                select(FieldComment).where(FieldComment.comment_id == source.source_id)
            )
            return bool(comment and comment.status in ALLOWED_FIELD_COMMENT_STATUSES)
        if source_type == "DOCUMENT":
            document = self.session.scalar(
                select(Document).where(Document.document_id == source.source_id)
            )
            if not document or document.status != "PUBLISHED" or document.deleted_at is not None:
                return False
            if source.source_version_id:
                version = self.session.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.version_id == source.source_version_id,
                        DocumentVersion.document_id == document.document_id,
                    )
                )
                return bool(version and version.version_status == "PUBLISHED" and version.is_published)
            return True
        if source_type == "WORK_SEQUENCE_HISTORY":
            return self.session.scalar(
                select(WorkSequenceChangeHistory.id).where(
                    WorkSequenceChangeHistory.change_id == source.source_id
                )
            ) is not None
        if source_type == "WORK_SEQUENCE_ITEM":
            return self.session.scalar(
                select(WorkSequenceItem.id).where(WorkSequenceItem.item_id == source.source_id)
            ) is not None
        return True

    def _author_role_allowed(self, author_id: str | None) -> bool:
        if author_id is None:
            return True
        author = self.session.scalar(select(UserAccount).where(UserAccount.user_id == author_id))
        if author is None:
            return False
        if author.role == "system-admin" and self.user.role != "system-admin":
            return False
        return author.is_active and author.status == "ACTIVE"

    def _channel_allowed(self, candidate: AISearchCandidate) -> bool:
        if self.user.role in GLOBAL_SOURCE_ROLES:
            return True
        pairs = [(candidate.source_type, candidate.source_id)]
        if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
            pairs.append(("DOCUMENT", candidate.source_id))
        elif candidate.source_type == "REPORT_SOURCE" and candidate.parent_id:
            pairs.append(("REPORT", candidate.parent_id))
            source = self.session.scalar(
                select(ReportSource).where(ReportSource.id == int(candidate.source_id))
            ) if candidate.source_id.isdigit() else None
            if source:
                pairs.append((source.source_type.strip().upper(), source.source_id))
        elif candidate.source_type == "WORK_SEQUENCE_HISTORY" and candidate.parent_id:
            pairs.append((candidate.parent_type or "WORK_SEQUENCE_ITEM", candidate.parent_id))
        conditions = [
            (NotificationChannel.source_type == source_type)
            & (NotificationChannel.source_id == source_id)
            for source_type, source_id in pairs
        ]
        channel_ids = list(
            self.session.scalars(
                select(NotificationChannel.channel_id).where(
                    NotificationChannel.status == "ACTIVE", or_(*conditions)
                )
            ).all()
        )
        if not channel_ids:
            return True
        membership = self.session.scalar(
            select(NotificationChannelMember.id).where(
                NotificationChannelMember.channel_id.in_(channel_ids),
                NotificationChannelMember.user_id == self.user.user_id,
                NotificationChannelMember.status == "ACTIVE",
            )
        )
        return membership is not None


def active_sensitive_policy(
    session: Session, settings: Settings
) -> AISensitiveDataPolicy | None:
    return session.scalar(
        select(AISensitiveDataPolicy)
        .where(
            AISensitiveDataPolicy.customer_scope == settings.ai_customer_scope,
            AISensitiveDataPolicy.site_scope == settings.ai_site_scope,
            AISensitiveDataPolicy.status == "ACTIVE",
            AISensitiveDataPolicy.is_active.is_(True),
        )
        .order_by(AISensitiveDataPolicy.created_at.desc(), AISensitiveDataPolicy.id.desc())
    )


def sensitive_policy_filter(
    policy: AISensitiveDataPolicy | None,
) -> SensitiveContentFilter:
    return SensitiveContentFilter(
        _json_string_set(policy.forbidden_terms_json) if policy else set(),
        _json_string_set(policy.customer_identifiers_json) if policy else set(),
    )


def load_sensitive_filter(session: Session, settings: Settings) -> SensitiveContentFilter:
    return sensitive_policy_filter(active_sensitive_policy(session, settings))


def sensitive_policy_snapshot(
    policy: AISensitiveDataPolicy | None,
) -> SensitivePolicySnapshot | None:
    if policy is None:
        return None
    return SensitivePolicySnapshot(
        policy_id=policy.policy_id,
        content_hash=policy.content_hash,
        state_revision=policy.state_revision,
    )


def sensitive_policy_block_code(session: Session, settings: Settings) -> str | None:
    if active_sensitive_policy(session, settings) is not None:
        return None
    inactive_terminal = session.scalar(
        select(AISensitiveDataPolicy)
        .where(
            AISensitiveDataPolicy.customer_scope == settings.ai_customer_scope,
            AISensitiveDataPolicy.site_scope == settings.ai_site_scope,
            AISensitiveDataPolicy.status.in_({"APPROVAL_WITHDRAWN", "RETIRED"}),
        )
        .order_by(AISensitiveDataPolicy.created_at.desc(), AISensitiveDataPolicy.id.desc())
    )
    if inactive_terminal is not None:
        return "AI_SENSITIVE_POLICY_NOT_ACTIVE"
    return None


def sensitive_policy_snapshot_is_current(
    session: Session,
    settings: Settings,
    expected: SensitivePolicySnapshot | None,
) -> bool:
    current = sensitive_policy_snapshot(active_sensitive_policy(session, settings))
    return current == expected and sensitive_policy_block_code(session, settings) is None


def approval_block_code(
    approval: AITransferApproval | None,
    settings: Settings,
    now: datetime,
) -> str | None:
    if approval is None:
        return "APPROVAL_REVOKED"
    if (
        approval.customer_scope != settings.ai_customer_scope
        or approval.site_scope != settings.ai_site_scope
        or approval.provider != settings.ai_provider
        or approval.model_scope not in {"*", settings.ai_model}
        or approval.revoked_at is not None
        or _utc(approval.expires_at) <= now
    ):
        return "APPROVAL_REVOKED"
    return None


def minimal_excerpt(text: str, query: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    tokens = [token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣_-]{2,}", query)]
    folded = normalized.casefold()
    positions = [folded.find(token) for token in tokens if folded.find(token) >= 0]
    center = min(positions) if positions else 0
    start = max(center - max_chars // 4, 0)
    end = min(start + max_chars, len(normalized))
    start = max(end - max_chars, 0)
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end]}{suffix}"
