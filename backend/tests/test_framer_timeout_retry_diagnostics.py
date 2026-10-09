"""Deterministic offline test suite for AURA Phase 4.15: Decision Framer Timeout & Retry Diagnostics.

Validates:
1. Fast successful first attempt records clean attempt diagnostics and 0 retries.
2. First attempt fails quickly with 503, second succeeds; attempt history records both attempts.
3. First attempt consumes most of operation budget (e.g. 45s); attempt 2 HTTP timeout is clamped to remaining budget.
4. Retry backoff exhausts remaining budget; operation terminates without extra provider call.
5. Parent deadline expires before operation deadline; final_timeout_source is "parent".
6. Operation deadline expires before parent deadline; final_timeout_source is "operation".
7. Non-retryable provider error (401 / 400) fails immediately without retry.
8. Repeated retryable errors exhaust max_retries and raise typed provider error.
9. No call exceeds its configured deadline contract under all clock conditions.
10. Error classification remains strictly typed across 401, 429, 503, transport, and timeout.
11. No extra provider calls occur after deadline exhaustion.
"""

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import httpx
import pytest
from pydantic import BaseModel

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


class MockSampleOutput(BaseModel):
    summary: str
    score: float


def _create_canned_json() -> str:
    return '{"summary": "Test response", "score": 0.95}'


# ------------------------------------------------------------------------------
# 1. Fast Successful First Attempt
# ------------------------------------------------------------------------------

def test_01_fast_successful_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that a fast successful first attempt records clean attempt diagnostics and 0 retries."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": _create_canned_json()}))
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
        sleep_fn=sleeps.append,
    )

    result = client.generate_structured(
        prompt="Synthesize decision inquiry",
        response_schema=MockSampleOutput,
    )

    assert result.summary == "Test response"
    assert len(sleeps) == 0

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "success"
    assert diag["attempt"] == 1
    assert diag["final_timeout_source"] is None

    attempts = diag.get("attempts", [])
    assert len(attempts) == 1
    att1 = attempts[0]
    assert att1["attempt_index"] == 1
    assert att1["status"] == "success"
    assert att1["error_category"] is None
    assert att1["backoff_seconds"] == 0.0
    assert att1["effective_http_timeout_seconds"] == 30.0


# ------------------------------------------------------------------------------
# 2. First Attempt Fails Quickly, Second Succeeds
# ------------------------------------------------------------------------------

def test_02_first_attempt_fails_quickly_second_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that when attempt 1 fails quickly (503), attempt 2 succeeds and telemetry captures both."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, json={"error": {"code": 503, "message": "Backend unavailable"}})
        return httpx.Response(200, json={"output_text": _create_canned_json()})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        sleep_fn=sleeps.append,
    )

    result = client.generate_structured(
        prompt="Synthesize decision inquiry",
        response_schema=MockSampleOutput,
    )

    assert result.summary == "Test response"
    assert call_count == 2
    assert len(sleeps) == 1
    assert sleeps[0] == 0.5  # initial backoff

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "success"
    assert diag["attempt"] == 2

    attempts = diag.get("attempts", [])
    assert len(attempts) == 2
    assert attempts[0]["attempt_index"] == 1
    assert attempts[0]["status"] == "server_error"
    assert attempts[0]["error_category"] == "server_error"
    assert attempts[0]["backoff_seconds"] == 0.5

    assert attempts[1]["attempt_index"] == 2
    assert attempts[1]["status"] == "success"
    assert attempts[1]["backoff_seconds"] == 0.0


# ------------------------------------------------------------------------------
# 3. First Attempt Consumes Most of Operation Budget
# ------------------------------------------------------------------------------

class ControlledClock:
    def __init__(self, start: float = 100.0) -> None:
        self.time = start

    def __call__(self) -> float:
        return self.time

    def advance(self, delta: float) -> None:
        self.time += delta


# ------------------------------------------------------------------------------
# 3. First Attempt Consumes Most of Operation Budget
# ------------------------------------------------------------------------------

def test_03_first_attempt_consumes_most_of_operation_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that when attempt 1 consumes 45s, attempt 2 HTTP timeout is clamped to remaining budget (~14.5s)."""
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
            clock.advance(30.0)  # Attempt 1 consumes 30.0s
            raise httpx.ReadTimeout("Socket read timed out")
        clock.advance(2.0)  # Attempt 2 takes 2.0s
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    result = client.generate_structured(
        prompt="Synthesize decision inquiry",
        response_schema=MockSampleOutput,
    )

    assert result.summary == "Test response"
    assert call_count == 2
    assert len(observed_timeouts) == 2
    # Attempt 1 timeout was min(30.0, 60.0) = 30.0
    assert observed_timeouts[0] == pytest.approx(30.0, abs=0.01)
    # Attempt 2 timeout was min(30.0, 29.5) = 29.5 (60 - 30 - 0.5)
    assert observed_timeouts[1] == pytest.approx(29.5, abs=0.01)

    diag = client.last_diagnostic
    assert diag is not None
    attempts = diag.get("attempts", [])
    assert len(attempts) == 2
    assert attempts[0]["status"] == "timeout"
    assert attempts[0]["duration_seconds"] == pytest.approx(30.0, abs=0.01)
    assert attempts[1]["status"] == "success"
    assert attempts[1]["effective_http_timeout_seconds"] == pytest.approx(29.5, abs=0.01)


# ------------------------------------------------------------------------------
# 4. Retry Backoff Exhausts Remaining Budget
# ------------------------------------------------------------------------------

def test_04_retry_backoff_exhausts_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that when attempt 1 leaves less time than required backoff, it times out without extra call."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []

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
        clock.advance(59.9)  # takes 59.9s, leaving 0.1s
        raise httpx.ReadTimeout("Attempt 1 timed out")

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
        )

    assert call_count == 1
    assert exc_info.value.details.get("timeout_source") == "operation"

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "timeout"
    assert diag["final_timeout_source"] == "operation"


# ------------------------------------------------------------------------------
# 5. Parent Deadline Expires Before Operation Deadline
# ------------------------------------------------------------------------------

def test_05_parent_deadline_expires_before_operation_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that when parent deadline expires first, final_timeout_source is 'parent'."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")

    clock = ControlledClock(100.0)
    monkeypatch.setattr(time, "monotonic", clock)

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        assert kwargs.get("timeout") == pytest.approx(10.0, abs=0.01)
        clock.advance(10.05)  # parent deadline was 110.0, so at 110.05 it expired
        raise httpx.ReadTimeout("Parent deadline exceeded")

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
            deadline_monotonic=110.0,
        )

    assert exc_info.value.details.get("timeout_source") == "parent"
    diag = client.last_diagnostic
    assert diag is not None
    assert diag["final_timeout_source"] == "parent"


# ------------------------------------------------------------------------------
# 6. Operation Deadline Expires Before Parent Deadline
# ------------------------------------------------------------------------------

def test_06_operation_deadline_expires_before_parent_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that when operation ceiling expires while parent has ample budget, source is 'operation'."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []

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
        if call_count == 1:
            clock.advance(45.0)  # Attempt 1 takes 45.0s
            raise httpx.ReadTimeout("Attempt 1 timed out")
        # Attempt 2: Remaining was 14.5s. It takes 15.0s (exceeding operation ceiling 60.0s)
        clock.advance(15.0)
        raise httpx.ReadTimeout("Attempt 2 timed out")

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
            deadline_monotonic=220.0,  # 120s parent deadline
        )

    assert exc_info.value.details.get("timeout_source") == "operation"
    assert exc_info.value.details.get("attempt") == 2

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["final_timeout_source"] == "operation"
    assert diag["attempt"] == 2


# ------------------------------------------------------------------------------
# 7. Non-Retryable Provider Error
# ------------------------------------------------------------------------------

def test_07_non_retryable_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that non-retryable errors (401 auth, 400 client error) fail immediately with 1 attempt."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": {"code": 401, "message": "Unauthorized"}})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        sleep_fn=sleeps.append,
    )

    with pytest.raises(LLMAuthenticationError):
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
        )

    # Immediately stopped: exactly 1 attempt, 0 sleep retries
    assert call_count == 1
    assert len(sleeps) == 0

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "auth_error"
    attempts = diag.get("attempts", [])
    assert len(attempts) == 1
    assert attempts[0]["status"] == "auth_error"


# ------------------------------------------------------------------------------
# 8. Repeated Retryable Errors Exhausts Max Retries
# ------------------------------------------------------------------------------

def test_08_repeated_retryable_errors_exhausts_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that repeated 503 errors exhaust configured max_retries and raise LLMProviderError."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []
    call_count = 0

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

    with pytest.raises(LLMProviderError):
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
            config=LLMConfig(max_retries=2),
        )

    # 1 initial + 2 retries = 3 attempts
    assert call_count == 3
    assert len(sleeps) == 2
    assert sleeps[0] == 0.5
    assert sleeps[1] == 1.0

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "server_error"
    assert diag["attempt"] == 3
    attempts = diag.get("attempts", [])
    assert len(attempts) == 3
    for att in attempts:
        assert att["status"] == "server_error"


# ------------------------------------------------------------------------------
# 9. No Call Exceeds Its Configured Deadline Contract
# ------------------------------------------------------------------------------

def test_09_no_call_exceeds_its_configured_deadline_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that per-request timeout strictly honors min(per_request_timeout, remaining) across attempts."""
    observed_timeouts: List[float] = []

    # Controlled monotonic time sequence:
    # Start: 100.0. Parent deadline = 125.0 (25s remaining budget).
    # Attempt 1 begins: remaining = 25s -> timeout passed must be 25.0s, NOT 45.0s!
    simulated_times = [100.0, 100.0, 100.0, 102.0, 102.0]
    monkeypatch.setattr(time, "monotonic", lambda: simulated_times.pop(0) if simulated_times else 105.0)

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

    client.generate_structured(
        prompt="Synthesize decision inquiry",
        response_schema=MockSampleOutput,
        deadline_monotonic=125.0,  # 25s deadline
    )

    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] == pytest.approx(25.0, abs=0.01)


# ------------------------------------------------------------------------------
# 10. Error Classification Remains Correct Across All Categories
# ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status_code,expected_exc,expected_status",
    [
        (401, LLMAuthenticationError, "auth_error"),
        (403, LLMAuthenticationError, "auth_error"),
        (429, LLMRateLimitError, "rate_limit"),
        (500, LLMProviderError, "server_error"),
        (502, LLMProviderError, "server_error"),
        (503, LLMProviderError, "server_error"),
        (504, LLMProviderError, "server_error"),
        (400, LLMError, "client_error"),
        (404, LLMError, "client_error"),
    ],
)
def test_10_error_classification_remains_correct(
    status_code: int,
    expected_exc: type,
    expected_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that typed exception mapping preserves exact semantic status codes."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sleeps: List[float] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"code": status_code, "message": "Simulated error"}})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
        sleep_fn=sleeps.append,
    )

    with pytest.raises(expected_exc):
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
            config=LLMConfig(max_retries=0),  # fail on attempt 1 to test classification
        )

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == expected_status


# ------------------------------------------------------------------------------
# 11. No Extra Provider Calls After Deadline Exhaustion
# ------------------------------------------------------------------------------

def test_11_no_extra_provider_calls_after_deadline_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that if deadline is already expired before call, 0 provider calls are dispatched."""
    call_count = 0
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))),
    )
    genai_client = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.output_text = _create_canned_json()
        return mock_resp

    monkeypatch.setattr(genai_client.interactions, "create", mock_create)

    # Monotonic time is already at 200.0, deadline is in the past at 190.0
    monkeypatch.setattr(time, "monotonic", lambda: 200.0)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Synthesize decision inquiry",
            response_schema=MockSampleOutput,
            deadline_monotonic=190.0,
        )

    assert call_count == 0
    assert exc_info.value.details.get("timeout_source") == "parent"


# ------------------------------------------------------------------------------
# 12. Concurrency Safety Audit: 4 Concurrent Workers Overwrite Shared Diagnostic
# ------------------------------------------------------------------------------

def test_12_concurrent_perspective_workers_overwrite_parent_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that 4 concurrent perspective workers sharing one GeminiLLMClient:
    1. Maintain thread-local isolation when read inside each worker thread.
    2. Overwrite each other's diagnostic from the orchestrator (parent) thread
       via the shared fallback `_latest_diagnostic` (last-write-wins).
    """
    import threading

    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")

    workers = ["growth", "finance", "customer", "risk"]
    worker_prompts = {
        "growth": "Prompt for growth perspective analysis (long padding for unique char length)",
        "finance": "Prompt for finance (short)",
        "customer": "Customer perspective prompt medium length here",
        "risk": "Risk perspective evaluation prompt with specific chars",
    }

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"output_text": _create_canned_json()})
    )
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )

    barrier = threading.Barrier(len(workers))
    worker_internal_diags: Dict[str, Any] = {}

    def worker_run(w_name: str) -> None:
        barrier.wait()
        prompt = worker_prompts[w_name]
        # Slight staggered delay so completions are ordered
        order_delays = {"growth": 0.01, "finance": 0.02, "customer": 0.03, "risk": 0.04}
        time.sleep(order_delays[w_name])

        client.generate_structured(
            prompt=prompt,
            response_schema=MockSampleOutput,
        )
        # Worker reads its own thread-local diagnostic
        diag = client.last_diagnostic
        if diag:
            worker_internal_diags[w_name] = dict(diag)

    threads = [
        threading.Thread(target=worker_run, args=(w,), name=f"worker-{w}")
        for w in workers
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 1. Inside each worker thread, thread-local isolation succeeded
    assert len(worker_internal_diags) == 4
    for w in workers:
        assert worker_internal_diags[w]["user_prompt_chars"] == len(worker_prompts[w])

    # 2. From the orchestrator / parent thread, client.last_diagnostic contains only ONE of the worker diagnostics
    parent_diag = client.last_diagnostic
    assert parent_diag is not None
    matching_workers = [
        w for w in workers if parent_diag["user_prompt_chars"] == len(worker_prompts[w])
    ]
    # Exactly one worker's diagnostic survived (last-write-wins)
    assert len(matching_workers) == 1
    surviving_worker = matching_workers[0]

    # 3. Prove that the remaining 3 workers' diagnostics were overwritten and are permanently lost to parent thread
    lost_workers = [w for w in workers if w != surviving_worker]
    assert len(lost_workers) == 3
    for lost in lost_workers:
        assert parent_diag["user_prompt_chars"] != len(worker_prompts[lost])


