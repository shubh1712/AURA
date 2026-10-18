"""Deterministic tests for Phase 4.27: Controlled HTTP Attempt-Timeout Alignment.

Verifies:
1. Default first-attempt HTTP timeout is 30 seconds.
2. Explicit timeout overrides remain effective.
3. After a first-attempt timeout near 30 seconds and a 0.5s backoff, the second attempt
   receives approximately 29.5 seconds (60.0s operation ceiling - 30.0s - 0.5s).
4. Total LLM operation duration remains strictly bounded by 60 seconds.
5. Parent deadline always takes precedence if shorter than HTTP timeout or operation ceiling.
6. Retry exhaustion still raises existing safe typed exceptions (LLMTimeoutError, LLMProviderError).
7. Existing validation-error retries behave unchanged.
8. No additional provider attempts are introduced beyond configured max_retries.
9. No partial EvidencePackage is returned on mapping failure (fail-closed semantics).
10. No partial ReasoningBoard is returned on reasoning failure (fail-closed semantics).
"""

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import httpx
import pytest
from pydantic import BaseModel, Field

from datetime import date
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidenceRequirement,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence.normalizer import NormalizedSourceResult, SearchResultItem
from app.services.llm.mock_data import get_default_decision_model
from app.services.evidence.mapper import EvidenceMapper
from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.gemini import GeminiLLMClient


class SampleStructuredOutput(BaseModel):
    summary: str = Field(..., description="Summary text.")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ControlledClock:
    def __init__(self, start_time: float = 100.0):
        self.time = start_time

    def __call__(self) -> float:
        return self.time

    def advance(self, delta: float) -> None:
        self.time += delta


def _create_canned_json() -> str:
    return '{"summary": "Test response", "confidence": 0.95}'


# ------------------------------------------------------------------------------
# 1. Default First-Attempt HTTP Timeout is 30.0 Seconds
# ------------------------------------------------------------------------------

def test_default_first_attempt_http_timeout_is_30s(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that unconfigured calls default to exactly 30.0s per-request HTTP timeout."""
    assert DEFAULT_LLM_CONFIG.timeout_seconds == 30.0
    assert DEFAULT_LLM_CONFIG.operation_timeout_seconds == 60.0

    observed_timeouts: List[float] = []
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": _create_canned_json()}))
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        observed_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    result = client.generate_structured(
        prompt="Analyze inquiry",
        response_schema=SampleStructuredOutput,
    )

    assert result.summary == "Test response"
    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] == 30.0


# ------------------------------------------------------------------------------
# 2. Explicit Timeout Overrides Remain Effective
# ------------------------------------------------------------------------------

def test_explicit_timeout_overrides_remain_effective(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that custom LLMConfig.timeout_seconds overrides the 30.0s default."""
    observed_timeouts: List[float] = []
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": _create_canned_json()}))
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        observed_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    # Override 1: 15.0s
    client.generate_structured(
        prompt="Analyze inquiry",
        response_schema=SampleStructuredOutput,
        config=LLMConfig(timeout_seconds=15.0),
    )
    assert observed_timeouts[-1] == 15.0

    # Override 2: 45.0s (under 60s operation ceiling)
    client.generate_structured(
        prompt="Analyze inquiry",
        response_schema=SampleStructuredOutput,
        config=LLMConfig(timeout_seconds=45.0),
    )
    assert observed_timeouts[-1] == 45.0

    # Override 3: 10.0s with 20.0s operation ceiling
    client.generate_structured(
        prompt="Analyze inquiry",
        response_schema=SampleStructuredOutput,
        config=LLMConfig(timeout_seconds=10.0, operation_timeout_seconds=20.0),
    )
    assert observed_timeouts[-1] == 10.0


# ------------------------------------------------------------------------------
# 3. Second Attempt Receives Approx 29.5s After 30s Stall and Backoff
# ------------------------------------------------------------------------------

def test_second_attempt_receives_approx_29_5s_after_30s_stall(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that after a 30.0s timeout on attempt 1 and a 0.5s backoff, attempt 2 receives 29.5s."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    observed_timeouts: List[float] = []

    clock = ControlledClock(100.0)
    monkeypatch.setattr(time, "monotonic", clock)

    def mock_sleep(s: float) -> None:
        sleeps.append(s)
        clock.advance(s)

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        sleep_fn=mock_sleep,
    )
    genai_client = client._get_genai_client()

    call_count = 0
    def mock_create(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        observed_timeouts.append(kwargs.get("timeout"))
        if call_count == 1:
            clock.advance(30.0)  # Attempt 1 consumes 30.0s then times out
            raise httpx.ReadTimeout("Socket read timed out")
        clock.advance(3.0)  # Attempt 2 finishes cleanly in 3.0s
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    result = client.generate_structured(
        prompt="Synthesize decision inquiry",
        response_schema=SampleStructuredOutput,
    )

    assert result.summary == "Test response"
    assert call_count == 2
    assert len(observed_timeouts) == 2
    # Attempt 1 received 30.0s
    assert observed_timeouts[0] == pytest.approx(30.0, abs=0.01)
    # Attempt 2 received min(30.0, 60.0 - 30.0 - 0.5) = 29.5s
    assert observed_timeouts[1] == pytest.approx(29.5, abs=0.01)

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "success"
    assert diag["attempt"] == 2
    attempts = diag.get("attempts", [])
    assert len(attempts) == 2
    assert attempts[0]["status"] == "timeout"
    assert attempts[0]["duration_seconds"] == pytest.approx(30.0, abs=0.01)
    assert attempts[0]["backoff_seconds"] == 0.5
    assert attempts[1]["status"] == "success"
    assert attempts[1]["effective_http_timeout_seconds"] == pytest.approx(29.5, abs=0.01)


# ------------------------------------------------------------------------------
# 4. Total LLM Operation Duration Bounded by 60 Seconds
# ------------------------------------------------------------------------------

def test_total_operation_duration_strictly_bounded_by_60s(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that two consecutive timeouts terminate at the 60.0s operation ceiling."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    observed_timeouts: List[float] = []

    clock = ControlledClock(100.0)
    monkeypatch.setattr(time, "monotonic", clock)

    def mock_sleep(s: float) -> None:
        sleeps.append(s)
        clock.advance(s)

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        sleep_fn=mock_sleep,
    )
    genai_client = client._get_genai_client()

    call_count = 0
    def mock_create(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        observed_timeouts.append(kwargs.get("timeout"))
        if call_count == 1:
            clock.advance(30.0)  # Attempt 1 takes 30.0s
            raise httpx.ReadTimeout("Attempt 1 socket timeout")
        # Attempt 2: Remaining is 29.5s. It exhausts the full 29.5s
        clock.advance(29.5)
        raise httpx.ReadTimeout("Attempt 2 socket timeout")

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Synthesize inquiry",
            response_schema=SampleStructuredOutput,
        )

    # Operation ceiling hit: 30.0 + 0.5 + 29.5 = 60.0s
    assert exc_info.value.details.get("timeout_source") == "operation"
    assert exc_info.value.details.get("attempt") == 2

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "timeout"
    assert diag["final_timeout_source"] == "operation"
    assert diag["attempt"] == 2


# ------------------------------------------------------------------------------
# 5. Parent Deadline Always Takes Precedence If Shorter
# ------------------------------------------------------------------------------

def test_parent_deadline_takes_precedence_if_shorter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that parent deadline constrains HTTP timeout when shorter than 30.0s."""
    observed_timeouts: List[float] = []

    # Start: 100.0, Parent deadline: 118.0 (18.0s remaining)
    clock = ControlledClock(100.0)
    monkeypatch.setattr(time, "monotonic", clock)

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        observed_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    # 1. 18.0s parent budget clamps attempt 1 to 18.0s
    client.generate_structured(
        prompt="Inquiry",
        response_schema=SampleStructuredOutput,
        deadline_monotonic=118.0,
    )
    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] == pytest.approx(18.0, abs=0.01)

    # 2. Already expired parent deadline makes 0 provider calls
    call_count_expired = 0
    def mock_create_expired(**kwargs: Any) -> Any:
        nonlocal call_count_expired
        call_count_expired += 1
        return MagicMock()

    monkeypatch.setattr(genai_client.interactions, "create", mock_create_expired)

    clock.advance(25.0)  # Clock is now 125.0, deadline is in past (118.0)
    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Inquiry",
            response_schema=SampleStructuredOutput,
            deadline_monotonic=118.0,
        )

    assert call_count_expired == 0
    assert exc_info.value.details.get("timeout_source") == "parent"


# ------------------------------------------------------------------------------
# 6. Retry Exhaustion Still Raises Existing Safe Exception
# ------------------------------------------------------------------------------

def test_retry_exhaustion_raises_existing_safe_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that exhausting max_retries on transient 503 errors raises typed LLMProviderError."""
    call_count = 0
    sleeps: List[float] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "Service Unavailable"}})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        sleep_fn=sleeps.append,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.generate_structured(
            prompt="Inquiry",
            response_schema=SampleStructuredOutput,
            config=LLMConfig(max_retries=2),
        )

    # 1 initial + 2 retries = 3 attempts
    assert call_count == 3
    assert len(sleeps) == 2
    assert "Gemini upstream server error (503)" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 7. Existing Validation-Error Retries Behave Unchanged
# ------------------------------------------------------------------------------

def test_existing_validation_error_retries_behave_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that structured output parsing failures trigger backoff and retry normally."""
    sleeps: List[float] = []
    call_count = 0

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
        sleep_fn=sleeps.append,
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        if call_count == 1:
            # Invalid JSON on attempt 1
            mock_resp.output_text = "Not valid JSON at all"
        else:
            # Valid JSON on attempt 2
            mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    result = client.generate_structured(
        prompt="Inquiry",
        response_schema=SampleStructuredOutput,
    )

    assert result.summary == "Test response"
    assert call_count == 2
    assert len(sleeps) == 1
    assert sleeps[0] == 0.5


# ------------------------------------------------------------------------------
# 8. No Additional Provider Attempts Are Introduced
# ------------------------------------------------------------------------------

def test_no_additional_provider_attempts_are_introduced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that attempt counts strictly honor 1 + max_retries under all conditions."""
    for retries in [0, 1, 2]:
        call_count = 0
        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(503, json={"error": {"code": 503, "message": "Unavailable"}})

        client = GeminiLLMClient(
            project="aura-test-project",
            location="global",
            http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
            sleep_fn=lambda s: None,
        )

        with pytest.raises(LLMProviderError):
            client.generate_structured(
                prompt="Inquiry",
                response_schema=SampleStructuredOutput,
                config=LLMConfig(max_retries=retries),
            )

        assert call_count == 1 + retries, f"Expected {1 + retries} attempts for max_retries={retries}, got {call_count}"


# ------------------------------------------------------------------------------
# 9. No Partial EvidencePackage Returned on Mapping Failure (Fail-Closed)
# ------------------------------------------------------------------------------

def test_no_partial_evidence_package_returned_on_mapping_failure() -> None:
    """Proves that EvidenceMapper discards partial results and raises LLMTimeoutError on batch failure."""
    mock_llm = MagicMock()
    # Batch 0 raises LLMTimeoutError
    mock_llm.generate_structured.side_effect = LLMTimeoutError("Mapping batch 0 timed out after 30.0s")

    mapper = EvidenceMapper(llm_client=mock_llm)
    mapper.batch_size = 2
    mapper.max_workers = 2
    dm = get_default_decision_model("Test decision")
    req = EvidenceRequirement(
        id="req_test_01",
        target_entity_id=dm.assumptions[0].id,
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Market pricing sensitivity",
        status=RequirementStatus.PENDING,
        suggested_queries=["B2B SaaS pricing"],
    )
    src_obj = Source(
        id="src_test_01",
        url="https://example.com/study",
        title="Pricing Study",
        publisher="OpenView",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 1, 1),
    )
    search_item = SearchResultItem(
        url="https://example.com/study",
        title="Pricing Study",
        snippet="SaaS churn increases when price cuts occur.",
        publisher="OpenView",
        published_date=date(2024, 1, 1),
    )
    normalized = NormalizedSourceResult(
        requirement_id=req.id,
        query="B2B SaaS pricing",
        source=src_obj,
        search_result=search_item,
        extraction_timestamp=None,
    )

    with pytest.raises(LLMTimeoutError):
        mapper.map_evidence(
            decision_model=dm,
            requirements=[req],
            normalized_sources=[normalized],
        )


# ------------------------------------------------------------------------------
# 10. No Partial ReasoningBoard Returned on Reasoning Failure (Fail-Closed)
# ------------------------------------------------------------------------------

def test_no_partial_reasoning_board_returned_on_failure() -> None:
    """Proves that reasoning evaluator raises ReasoningEvaluationError fail-closed wrapping LLMTimeoutError."""
    from tests.test_perspective_reasoner import _create_simple_context
    from app.services.reasoning.evaluator import PerspectiveReasoner
    from app.services.reasoning.validator import ReasoningEvaluationError

    mock_llm = MagicMock()
    mock_llm.generate_structured.side_effect = LLMTimeoutError("Perspective analysis timed out")

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context()

    with pytest.raises(ReasoningEvaluationError) as exc_info:
        reasoner.evaluate(perspective_context=ctx)

    assert isinstance(exc_info.value.__cause__, LLMTimeoutError)
