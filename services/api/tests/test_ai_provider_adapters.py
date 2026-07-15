from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.ai_provider_adapters import (
    FakeProviderAdapter,
    JsonHttpProviderAdapter,
    ProviderAdapterError,
    RecordingProviderAdapter,
    configured_provider_adapter,
)
from app.services.ai_response_validation import (
    ResponseValidationError,
    parse_provider_response,
    semantic_grounding,
)


PAYLOAD = {
    "purpose": "EVIDENCE_SUMMARY",
    "query": "압력 기준을 요약해 주세요",
    "queryHash": "a" * 64,
    "promptVersionId": "prompt-1",
    "promptVersion": "evidence/1",
    "traceId": "aiq-1",
    "outputFormat": {"type": "json"},
    "sources": [{
        "candidateId": "candidate-1",
        "sourceType": "PUBLISHED_DOCUMENT_VERSION",
        "sourceId": "document-1",
        "sourceVersionId": "version-1",
        "traceId": "document-1",
        "traceVersionId": "version-1",
        "contentHash": "b" * 64,
        "rank": 1,
        "excerpt": "정상 압력 기준은 12 bar이며 초과 시 작업을 중지한다.",
    }],
}


def test_fake_and_recording_adapters_are_deterministic() -> None:
    recording = RecordingProviderAdapter(FakeProviderAdapter(["RATE_LIMIT", "SUCCESS"]))
    with pytest.raises(ProviderAdapterError) as raised:
        recording.invoke(PAYLOAD)
    assert raised.value.code == "AI_PROVIDER_RATE_LIMIT"
    assert raised.value.retryable is True
    result = recording.invoke(PAYLOAD)
    assert isinstance(result, dict)
    assert result["claims"][0]["candidateIds"] == ["candidate-1"]
    assert recording.requests == [PAYLOAD, PAYLOAD]
    assert recording.requests[0] is not PAYLOAD


@pytest.mark.parametrize(
    ("scenario", "code"),
    [
        ("INCOMPLETE_JSON", "AI_PROVIDER_INVALID_JSON"),
        ("OVERSIZED", "AI_PROVIDER_RESPONSE_TOO_LARGE"),
        ("PROMPT_INJECTION", "AI_PROVIDER_PROMPT_INJECTION"),
        ("DUPLICATE_CITATION", "CITATION_VALIDATION_FAILED"),
    ],
)
def test_malformed_oversized_injection_and_duplicate_outputs_are_blocked(
    scenario: str, code: str
) -> None:
    result = FakeProviderAdapter([scenario]).invoke(PAYLOAD)
    with pytest.raises(ResponseValidationError) as raised:
        parse_provider_response(result, max_bytes=2_000)
    assert raised.value.code == code


def test_semantic_rules_reject_mutated_numbers_and_hold_low_confidence() -> None:
    conflict = semantic_grounding(
        "정상 압력 기준은 99 bar이며 초과 시 작업을 중지한다.",
        ["정상 압력 기준은 12 bar이며 초과 시 작업을 중지한다."],
    )
    assert conflict.accepted is False
    assert conflict.reason_code == "CLAIM_EVIDENCE_CONFLICT"
    low_confidence = semantic_grounding(
        "냉각수 밸브를 교체하고 생산량을 늘린다.",
        ["정상 압력 기준은 12 bar이며 초과 시 작업을 중지한다."],
    )
    assert low_confidence.accepted is False
    assert low_confidence.human_review_required is True


def test_network_adapter_requires_explicit_test_scope_and_environment_secret(monkeypatch) -> None:
    common = {
        "_env_file": None,
        "ai_provider_adapter_mode": "NETWORK_TEST",
        "ai_network_test_scope_enabled": True,
        "ai_provider": "TEST_PROVIDER",
        "ai_provider_endpoint": "https://provider.invalid/v1/summary",
    }
    with pytest.raises(ValueError, match="test-scope"):
        configured_provider_adapter(Settings(environment="local", **common))
    monkeypatch.setenv("FLOWNOTE_AI_TEST_PROVIDER_API_KEY", "test-only-canary")
    adapter = configured_provider_adapter(Settings(environment="test", **common))
    assert isinstance(adapter, JsonHttpProviderAdapter)
    assert configured_provider_adapter(Settings(_env_file=None)) is None
