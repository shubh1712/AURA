"""Tests for Phase 14A: Bounded Gemini Execution.

Validates deterministic, bounded retry, operation-level deadlines, client reuse,
and sanitized error semantics in GeminiLLMClient.
"""

import time
from typing import Any, Dict, List
import httpx
import pytest
from pydantic import BaseModel, Field

from app.schemas.decision_model import DecisionModel
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.gemini import GeminiLLMClient


class SampleOutput(BaseModel):
    summary: str = Field(description="Summary text")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


VALID_JSON_RESPONSE = '{"summary": "Decision reached successfully", "confidence": 0.95}'


# ------------------------------------------------------------------------------
# 1. Client Lifecycle & Reuse
# ------------------------------------------------------------------------------

def test_genai_client_reused_by_gemini_client() -> None:
    """Proves that a single GeminiLLMClient reuses its underlying genai.Client."""
    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})
    )
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(api_key="test-api-key", http_client=http_client)

    assert client._genai_client is None

    # First call initializes client
    genai_client_1 = client._get_genai_client()
    assert genai_client_1 is not None

    # Second call returns the exact same object reference
    genai_client_2 = client._get_genai_client()
    assert genai_client_1 is genai_client_2

    # Invoking generate_structured reuses the same underlying client
    res = client.generate_structured(
        prompt="Test prompt",
        response_schema=SampleOutput,
    )
    assert res.summary == "Decision reached successfully"
    assert client._genai_client is genai_client_1


# ------------------------------------------------------------------------------
# 2. SDK-Level Transport Invocations (Proving 1:1 Mapping)
# ------------------------------------------------------------------------------

def test_one_sdk_transport_invocation_per_aura_provider_attempt() -> None:
    """Proves that SDK-level retries are disabled and exactly 1 HTTP transport call occurs per AURA attempt."""
    call_counts = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_counts[0] += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "High demand"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    sleep_calls: List[float] = []

    # Case A: max_retries = 0 -> exactly 1 AURA attempt -> exactly 1 transport call
    client_0 = GeminiLLMClient(
        api_key="test-key",
        http_client=http_client,
        sleep_fn=sleep_calls.append,
    )
    with pytest.raises(LLMProviderError):
        client_0.generate_structured(
            prompt="Prompt",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=0),
        )
    assert call_counts[0] == 1
    assert len(sleep_calls) == 0

    # Case B: max_retries = 1 -> exactly 2 AURA attempts -> exactly 2 transport calls
    call_counts[0] = 0
    sleep_calls.clear()
    client_1 = GeminiLLMClient(
        api_key="test-key",
        http_client=http_client,
        sleep_fn=sleep_calls.append,
    )
    with pytest.raises(LLMProviderError):
        client_1.generate_structured(
            prompt="Prompt",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=1),
        )
    assert call_counts[0] == 2
    assert len(sleep_calls) == 1


# ------------------------------------------------------------------------------
# 3. Maximum AURA Attempts Configuration
# ------------------------------------------------------------------------------

def test_max_retries_zero_exactly_one_aura_attempt() -> None:
    """Verifies that max_retries=0 results in exactly 1 attempt."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "High demand"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    with pytest.raises(LLMProviderError):
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=0),
        )
    assert invocations[0] == 1
    assert len(sleeps) == 0


def test_max_retries_two_at_most_three_aura_attempts() -> None:
    """Verifies that max_retries=2 results in 1 initial + 2 retries = 3 attempts total."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "High demand"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(
        api_key="key",
        http_client=http_client,
        sleep_fn=sleeps.append,
        initial_backoff_seconds=0.5,
        backoff_multiplier=2.0,
    )

    with pytest.raises(LLMProviderError):
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=2),
        )
    assert invocations[0] == 3
    assert len(sleeps) == 2
    assert sleeps[0] == 0.5
    assert sleeps[1] == 1.0


# ------------------------------------------------------------------------------
# 4. Failure Categorization: Non-Retryable vs Retryable
# ------------------------------------------------------------------------------

def test_auth_failure_no_retry() -> None:
    """Verifies that 401/403 authentication failures immediately fail without retrying."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(401, json={"error": {"code": 401, "message": "API key invalid"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    with pytest.raises(LLMAuthenticationError) as exc_info:
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=2),
        )
    assert invocations[0] == 1
    assert len(sleeps) == 0
    assert "Gemini authentication failed" in str(exc_info.value)


def test_deterministic_client_error_no_retry() -> None:
    """Verifies that 400 Bad Request client errors fail immediately without retrying."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(400, json={"error": {"code": 400, "message": "Bad model input"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    with pytest.raises(LLMError) as exc_info:
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=2),
        )
    assert invocations[0] == 1
    assert len(sleeps) == 0
    assert "Gemini API client error" in str(exc_info.value)


def test_transient_503_bounded_retry_and_recovery() -> None:
    """Verifies that 503 is retried according to policy and recovers if subsequent attempt succeeds."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        if invocations[0] < 3:
            return httpx.Response(503, json={"error": {"code": 503, "message": "Overloaded"}})
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    result = client.generate_structured(
        prompt="Test",
        response_schema=SampleOutput,
        config=LLMConfig(max_retries=2),
    )
    assert invocations[0] == 3
    assert len(sleeps) == 2
    assert result.summary == "Decision reached successfully"


def test_rate_limit_bounded_retry_and_recovery() -> None:
    """Verifies that 429 rate limit is retried according to policy and recovers."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        if invocations[0] == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "1.5"},
                json={"error": {"code": 429, "message": "Rate limit exceeded"}},
            )
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    result = client.generate_structured(
        prompt="Test",
        response_schema=SampleOutput,
        config=LLMConfig(max_retries=2),
    )
    assert invocations[0] == 2
    assert len(sleeps) == 1
    assert sleeps[0] == 1.5  # Honored Retry-After
    assert result.summary == "Decision reached successfully"


def test_empty_successful_output_bounded_retry() -> None:
    """Verifies that HTTP 200 with empty candidate text triggers bounded retry."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        if invocations[0] == 1:
            return httpx.Response(200, json={"output_text": "   "})
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    result = client.generate_structured(
        prompt="Test",
        response_schema=SampleOutput,
        config=LLMConfig(max_retries=2),
    )
    assert invocations[0] == 2
    assert len(sleeps) == 1
    assert result.summary == "Decision reached successfully"


def test_invalid_structured_output_bounded_retry() -> None:
    """Verifies that HTTP 200 with malformed Pydantic payload triggers bounded retry."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        if invocations[0] == 1:
            return httpx.Response(200, json={"output_text": '{"wrong_field": 123}'})
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=sleeps.append)

    result = client.generate_structured(
        prompt="Test",
        response_schema=SampleOutput,
        config=LLMConfig(max_retries=2),
    )
    assert invocations[0] == 2
    assert len(sleeps) == 1
    assert result.summary == "Decision reached successfully"


# ------------------------------------------------------------------------------
# 5. Operation Deadline & Wall-Clock Budget Enforcement
# ------------------------------------------------------------------------------

def test_operation_deadline_exceeded_before_attempt(monkeypatch) -> None:
    """Verifies that when monotonic clock advances beyond deadline, LLMTimeoutError is raised immediately."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GeminiLLMClient(api_key="key", http_client=http_client)

    # Simulate elapsed time beyond operation timeout (60s)
    simulated_times = [100.0, 165.0]  # Elapsed 65s > 60s
    monkeypatch.setattr(time, "monotonic", lambda: simulated_times.pop(0) if simulated_times else 200.0)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(operation_timeout_seconds=60.0),
        )
    assert invocations[0] == 0  # Aborted before sending HTTP request
    assert "Gemini API request timed out" in str(exc_info.value)


def test_remaining_deadline_reduces_per_request_timeout(monkeypatch) -> None:
    """Verifies that effective HTTP request timeout cannot exceed remaining operation budget."""
    observed_timeouts: List[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        # httpx Request extensions or timeout on client
        return httpx.Response(200, json={"output_text": VALID_JSON_RESPONSE})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GeminiLLMClient(api_key="key", http_client=http_client)

    # Intercept interactions.create to inspect create_kwargs['timeout']
    orig_genai_client = client._get_genai_client()
    orig_create = orig_genai_client.interactions.create

    def capturing_create(**kwargs):
        observed_timeouts.append(kwargs.get("timeout"))
        return orig_create(**kwargs)

    monkeypatch.setattr(orig_genai_client.interactions, "create", capturing_create)

    # Start time = 100.0. When remaining is checked, time = 125.0 -> remaining = 130 - 125 = 5.0s
    # Even though timeout_seconds = 30.0, effective timeout must be reduced to 5.0s!
    times = [100.0, 125.0, 126.0]
    monkeypatch.setattr(time, "monotonic", lambda: times.pop(0) if times else 130.0)

    client.generate_structured(
        prompt="Test",
        response_schema=SampleOutput,
        config=LLMConfig(timeout_seconds=30.0, operation_timeout_seconds=30.0),
    )
    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] == pytest.approx(5.0, abs=0.01)


def test_backoff_cannot_exceed_remaining_deadline(monkeypatch) -> None:
    """Verifies that backoff sleep duration is capped by the remaining operation deadline."""
    invocations = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        invocations[0] += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "High demand"}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: List[float] = []
    client = GeminiLLMClient(
        api_key="key",
        http_client=http_client,
        sleep_fn=sleeps.append,
        initial_backoff_seconds=2.0,  # Would normally sleep 2.0s
    )

    # Start = 100.0, deadline = 100 + 1.0 = 101.0. At failure, time = 100.3 -> remaining = 0.7s
    times = [100.0, 100.1, 100.3, 100.3, 101.5]
    monkeypatch.setattr(time, "monotonic", lambda: times.pop(0) if times else 102.0)

    with pytest.raises(LLMTimeoutError):
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(operation_timeout_seconds=1.0, max_retries=2),
        )

    # Sleep must be capped to remaining 0.7s (not 2.0s!)
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.7, abs=0.01)


# ------------------------------------------------------------------------------
# 6. Security Hardening & Zero-Leakage Invariants
# ------------------------------------------------------------------------------

def test_provider_secret_marker_cannot_enter_logs_or_errors() -> None:
    """Verifies that upstream provider response body or secret markers are never reflected in error messages."""
    SECRET_MARKER = "SUPER_SECRET_PAYLOAD_TOKEN_XYZ_999"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            text=f"Service Unavailable with internal dump: {SECRET_MARKER}",
            json={"error": {"code": 503, "message": f"Dump: {SECRET_MARKER}"}},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GeminiLLMClient(api_key="key", http_client=http_client, sleep_fn=lambda d: None)

    with pytest.raises(LLMProviderError) as exc_info:
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=0),
        )

    err = exc_info.value
    assert SECRET_MARKER not in str(err)
    assert SECRET_MARKER not in repr(err)
    if hasattr(err, "details") and err.details:
        assert SECRET_MARKER not in str(err.details)


def test_api_keys_cannot_enter_logs_or_errors() -> None:
    """Verifies that user API keys are never reflected in error messages or details."""
    SECRET_KEY = "AIzaSyD_SECRET_KEY_NEVER_LEAK_12345"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": 401, "message": f"Bad API key: {SECRET_KEY}"}},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GeminiLLMClient(api_key=SECRET_KEY, http_client=http_client, sleep_fn=lambda d: None)

    with pytest.raises(LLMAuthenticationError) as exc_info:
        client.generate_structured(
            prompt="Test",
            response_schema=SampleOutput,
            config=LLMConfig(max_retries=0),
        )

    err = exc_info.value
    assert SECRET_KEY not in str(err)
    assert SECRET_KEY not in repr(err)
    if hasattr(err, "details") and err.details:
        assert SECRET_KEY not in str(err.details)
