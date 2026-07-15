from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore (?:all |the )?(?:previous|prior) instructions?"),
    re.compile(r"(?i)(?:reveal|print|return).{0,30}(?:system|developer) prompt"),
    re.compile(r"(?i)you are now (?:a|an)"),
    re.compile(r"(?:이전|위의) (?:지시|명령).{0,12}(?:무시|잊어)"),
    re.compile(r"(?:시스템|개발자) (?:프롬프트|지시).{0,12}(?:공개|출력|반환)"),
)
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z가-힣])\d+(?:[.,]\d+)?(?:%|mm|cm|kg|분|초|시간|건|회)?")
NEGATIVE_TERMS = frozenset({"없음", "없다", "아님", "아니다", "금지", "중지", "not", "no", "never"})
STOPWORDS = frozenset({
    "그리고", "또한", "대한", "관련", "근거", "요약", "내용", "것으로", "합니다", "입니다",
    "the", "and", "for", "with", "from", "that", "this", "claim",
})
NON_FACTUAL_LABEL_TERMS = frozenset({
    "검증된", "응답", "원문", "주장", "허용", "승인", "승인됨", "상태", "원천", "결과",
})


class ResponseValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedClaim:
    claim_key: str
    text: str
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedResponse:
    response: str
    claims: tuple[ValidatedClaim, ...]
    provider_request_id: str | None
    cost_micros: int


@dataclass(frozen=True)
class SemanticDecision:
    accepted: bool
    reason_code: str | None
    human_review_required: bool


def contains_prompt_injection(value: str) -> bool:
    return any(pattern.search(value) for pattern in INJECTION_PATTERNS)


def parse_provider_response(raw: Any, *, max_bytes: int) -> ValidatedResponse:
    if isinstance(raw, bytes):
        encoded = raw
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ResponseValidationError("AI_PROVIDER_INVALID_JSON") from None
    elif isinstance(raw, str):
        encoded = raw.encode("utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ResponseValidationError("AI_PROVIDER_INVALID_JSON") from None
    elif isinstance(raw, dict):
        try:
            encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError):
            raise ResponseValidationError("AI_PROVIDER_INVALID_JSON") from None
        parsed = raw
    else:
        raise ResponseValidationError("AI_PROVIDER_INVALID_JSON")
    if len(encoded) > max_bytes:
        raise ResponseValidationError("AI_PROVIDER_RESPONSE_TOO_LARGE")
    if not isinstance(parsed, dict):
        raise ResponseValidationError("AI_PROVIDER_INVALID_SCHEMA")
    allowed_top_level = {
        "response", "claims", "providerRequestId", "costMicros", "inputUnits", "outputUnits"
    }
    if set(parsed) - allowed_top_level:
        raise ResponseValidationError("AI_PROVIDER_INVALID_SCHEMA")
    response = parsed.get("response")
    claims = parsed.get("claims")
    if not isinstance(response, str) or not response.strip() or not isinstance(claims, list) or not claims:
        raise ResponseValidationError("CITATION_VALIDATION_FAILED")
    if contains_prompt_injection(response):
        raise ResponseValidationError("AI_PROVIDER_PROMPT_INJECTION")
    validated: list[ValidatedClaim] = []
    seen_keys: set[str] = set()
    seen_claims: set[tuple[str, tuple[str, ...]]] = set()
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            raise ResponseValidationError("CITATION_VALIDATION_FAILED")
        if set(claim) - {"claimKey", "text", "candidateIds"}:
            raise ResponseValidationError("AI_PROVIDER_INVALID_SCHEMA")
        text = claim.get("text")
        candidate_ids = claim.get("candidateIds")
        key = str(claim.get("claimKey", "")).strip()[:80] or f"claim-{index}"
        if key in seen_keys or not isinstance(text, str) or not text.strip():
            raise ResponseValidationError("CITATION_VALIDATION_FAILED")
        if contains_prompt_injection(text):
            raise ResponseValidationError("AI_PROVIDER_PROMPT_INJECTION")
        if (
            not isinstance(candidate_ids, list)
            or not candidate_ids
            or any(not isinstance(item, str) or not item for item in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)
        ):
            raise ResponseValidationError("CITATION_VALIDATION_FAILED")
        signature = (text.strip().casefold(), tuple(candidate_ids))
        if signature in seen_claims:
            raise ResponseValidationError("CITATION_VALIDATION_FAILED")
        seen_keys.add(key)
        seen_claims.add(signature)
        validated.append(ValidatedClaim(key, text.strip(), tuple(candidate_ids)))
    try:
        cost_micros = max(0, int(parsed.get("costMicros", 0) or 0))
    except (TypeError, ValueError):
        cost_micros = 0
    request_id = parsed.get("providerRequestId")
    return ValidatedResponse(
        response=response.strip(),
        claims=tuple(validated),
        provider_request_id=str(request_id)[:120] if request_id else None,
        cost_micros=cost_micros,
    )


def _tokens(value: str) -> set[str]:
    return {
        token.casefold() for token in TOKEN_PATTERN.findall(value)
        if len(token) >= 2 and token.casefold() not in STOPWORDS
    }


def semantic_grounding(claim_text: str, evidence_texts: list[str]) -> SemanticDecision:
    """Conservative deterministic check; uncertainty is a normal hold, never a guessed answer."""
    joined = "\n".join(evidence_texts)
    claim_numbers = set(NUMBER_PATTERN.findall(claim_text))
    evidence_numbers = set(NUMBER_PATTERN.findall(joined))
    if not claim_numbers.issubset(evidence_numbers):
        return SemanticDecision(False, "CLAIM_EVIDENCE_CONFLICT", False)
    claim_tokens = _tokens(claim_text)
    # Only known response labels may bypass semantic overlap as non-factual structure.
    if not claim_tokens or (
        len(claim_tokens) <= 3
        and not claim_numbers
        and claim_tokens.issubset(NON_FACTUAL_LABEL_TERMS)
    ):
        return SemanticDecision(True, None, False)
    evidence_tokens = _tokens(joined)
    overlap = len(claim_tokens & evidence_tokens) / max(len(claim_tokens), 1)
    claim_negative = bool(claim_tokens & NEGATIVE_TERMS)
    evidence_negative = bool(evidence_tokens & NEGATIVE_TERMS)
    if claim_negative != evidence_negative and overlap < 0.8:
        return SemanticDecision(False, "CLAIM_EVIDENCE_CONFLICT", False)
    if overlap < 0.6:
        return SemanticDecision(False, "CLAIM_GROUNDING_LOW_CONFIDENCE", True)
    return SemanticDecision(True, None, False)
