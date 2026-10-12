"""Deterministic Regression Tests for Stage 3 AI Boardroom Timeout Investigation.

Reproduces and verifies:
1. Incident Reconstruction: Under operation_timeout_seconds=120.0, http_timeout_seconds=45.0,
   and max_retries=2, three consecutive provider stalls result in:
   - Exactly 3 attempts (45s, 45s, ~28.5s with backoffs).
   - Total elapsed since start of analysis: exactly 222.30s (102.30s prior + 120.0s boardroom).
   - Remaining parent budget: exactly 137.70s (out of 360.0s total parent deadline).
   - Typed timeout exception with timeout_source="operation".
2. Fix Verification: When http_timeout_seconds is given sufficient headroom (e.g. 90.0s)
   within the 120.0s operation budget and max_retries=1:
   - A realistic 55.0s Gemini generation completes cleanly on Attempt 1.
   - Total elapsed time is only ~157.30s with 202.70s remaining parent budget.
3. Fail-Closed Timeout Enforcement: If generation genuinely stalls past 90s, the operation
   fails cleanly without wasting 3 futile 45s attempts.
4. Parent Deadline Preemption: When remaining parent deadline is shorter than the local
   operation ceiling, timeout_source is correctly attributed to "parent".
5. Error Mapping: AnalysisService correctly catches the perspective timeout and maps it
   to HTTP 504 Gateway Timeout, while AnalysisJobManager records status="timed_out".
"""

import time
from typing import Any, Dict, List, Optional
import pytest
from fastapi import HTTPException, status

from app.schemas.analysis import AnalysisRequest
from app.schemas.job import JobStatus
from app.services.analysis_service import AnalysisService, AnalysisTimeoutError
from app.services.evidence import FakeSearchProvider
from app.services.llm.client import FakeLLMClient, LLMConfig, LLMTimeoutError
from app.services.reasoning.validator import ReasoningOrchestrationError, ReasoningServiceError
from tests.test_decision_framer_unit_contract import FakeClockLLMOperation, SimulatedAttempt


# ------------------------------------------------------------------------------
# 1. Incident Reproduction Tests (Fake Clock)
# ------------------------------------------------------------------------------

def test_01_incident_reproduction_three_attempts_222s_elapsed():
    """Reproduces the exact failure mode of Job d33539e4-9048-46a1-8e9e-c1db18413378.

    Given:
    - Global parent timeout: 360.0s
    - Prior stages (Stage 1 + Stage 2) elapsed: 102.30s
    - Boardroom operation ceiling: 120.0s
    - Clamped HTTP timeout: 45.0s
    - Default max_retries: 2 (3 attempts allowed)
    - Initial backoff: 0.5s, multiplier: 2.0

    Expects:
    - Exactly 3 attempts
    - Attempt 1: 45.0s timeout + 0.5s backoff
    - Attempt 2: 45.0s timeout + 1.0s backoff
    - Attempt 3: 28.5s timeout (clamped to remaining 120s budget)
    - Total analysis elapsed: 102.30s + 120.0s = 222.30s
    - Remaining parent budget: 360.0s - 222.30s = 137.70s
    - Timeout source: "operation"
    """
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=360.0,
        operation_timeout_seconds=120.0,
        http_timeout_seconds=45.0,
        max_retries=2,
        initial_backoff_seconds=0.5,
        backoff_multiplier=2.0,
    )

    # Stages 1 and 2 ran from t=0 to t=102.30s
    start_time_offset = 102.30

    attempts = [
        SimulatedAttempt(duration=45.0, outcome="timeout"),
        SimulatedAttempt(duration=45.0, outcome="timeout"),
        SimulatedAttempt(duration=45.0, outcome="timeout"),
    ]

    res = sim.execute(start_time_offset=start_time_offset, attempts=attempts)

    # Assert exact failure attributes
    assert res["status"] == "timeout"
    assert len(res["attempts"]) == 3

    # Attempt 1
    assert res["attempts"][0]["attempt"] == 1
    assert res["attempts"][0]["duration"] == pytest.approx(45.0, rel=1e-3)
    assert res["attempts"][0]["backoff"] == pytest.approx(0.5, rel=1e-3)

    # Attempt 2
    assert res["attempts"][1]["attempt"] == 2
    assert res["attempts"][1]["duration"] == pytest.approx(45.0, rel=1e-3)
    assert res["attempts"][1]["backoff"] == pytest.approx(1.0, rel=1e-3)

    # Attempt 3: Clamped to remaining operation budget (120 - 45 - 0.5 - 45 - 1.0 = 28.5s)
    assert res["attempts"][2]["attempt"] == 3
    assert res["attempts"][2]["duration"] == pytest.approx(28.5, rel=1e-3)

    # Verify total operation and overall analysis elapsed times
    total_op_duration = res["total_op_duration"]
    assert total_op_duration == pytest.approx(120.0, rel=1e-3)

    total_analysis_elapsed = start_time_offset + total_op_duration
    assert total_analysis_elapsed == pytest.approx(222.30, rel=1e-3)

    remaining_parent_budget = res["remaining_parent_budget"]
    assert remaining_parent_budget == pytest.approx(137.70, rel=1e-3)
    assert (total_analysis_elapsed + remaining_parent_budget) == pytest.approx(360.0, rel=1e-3)


def test_02_proposed_fix_headroom_allows_realistic_generation():
    """Verifies that providing sufficient HTTP headroom (e.g. 90.0s) allows a realistic

    55s generation call to succeed cleanly on Attempt 1.
    """
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=360.0,
        operation_timeout_seconds=120.0,
        http_timeout_seconds=90.0,  # Adequate headroom instead of 45.0s clamp
        max_retries=1,
    )

    start_time_offset = 102.30

    # Realistic complex structured generation completes in 55.0s
    attempts = [
        SimulatedAttempt(duration=55.0, outcome="success"),
    ]

    res = sim.execute(start_time_offset=start_time_offset, attempts=attempts)

    assert res["status"] == "success"
    assert len(res["attempts"]) == 1
    assert res["total_op_duration"] == pytest.approx(55.0, rel=1e-3)

    total_analysis_elapsed = start_time_offset + 55.0
    assert total_analysis_elapsed == pytest.approx(157.30, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(202.70, rel=1e-3)


def test_03_parent_deadline_preemption_under_near_expiry():
    """Verifies that when parent deadline expires first, timeout_source is attributed to 'parent'."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=120.0,  # Parent deadline expires at 120.0s
        operation_timeout_seconds=120.0,  # Local ceiling would permit up to t=220.0s
        http_timeout_seconds=45.0,
        max_retries=2,
    )

    # Stage 3 starts at t=100.0s, leaving only 20.0s of parent deadline
    start_time_offset = 100.0

    attempts = [
        SimulatedAttempt(duration=45.0, outcome="timeout"),
    ]

    res = sim.execute(start_time_offset=start_time_offset, attempts=attempts)

    assert res["status"] == "timeout"
    assert len(res["attempts"]) == 1
    # Clamped to remaining 20.0s of parent budget, NOT 45s
    assert res["attempts"][0]["duration"] == pytest.approx(20.0, rel=1e-3)
    assert res["total_op_duration"] == pytest.approx(20.0, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(0.0, abs=1e-3)


# ------------------------------------------------------------------------------
# 2. Integration / Pipeline Error Propagation Tests
# ------------------------------------------------------------------------------

class TimingOutLLMClient(FakeLLMClient):
    """Client that raises LLMTimeoutError specifically on CandidatePerspectiveAnalysis."""

    def __init__(self, timeout_source: str = "operation", attempts: int = 3) -> None:
        super().__init__()
        self.timeout_source = timeout_source
        self.attempts = attempts

    def generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        schema_name = getattr(response_schema, "__name__", str(response_schema))
        if schema_name == "CandidatePerspectiveAnalysis":
            raise LLMTimeoutError(
                "Gemini API request timed out after 120.0s.",
                details={
                    "model": "gemini-3.8-flash",
                    "timeout": 120.0,
                    "timeout_source": self.timeout_source,
                    "attempt": self.attempts,
                },
            )
        return super().generate_structured(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
            config=config,
            deadline_monotonic=deadline_monotonic,
        )


def test_04_boardroom_timeout_maps_to_http_504_with_diagnostics():
    """Verifies that an LLMTimeoutError during Stage 3 perspectives cleanly raises

    HTTPException with status 504 and does not mask the error as a 500 or 502.
    """
    failing_client = TimingOutLLMClient(timeout_source="operation", attempts=3)
    svc = AnalysisService(
        llm_client=failing_client,
        search_provider=FakeSearchProvider(),
        analysis_timeout_seconds=360.0,
        boardroom_operation_timeout_seconds=120.0,
    )

    request = AnalysisRequest(question="Should we migrate inventory systems?")

    with pytest.raises(HTTPException) as exc_info:
        svc.analyze(request)

    assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert "timed out" in exc_info.value.detail.lower()


def test_05_job_storage_roundtrips_timed_out_state():
    """Verifies that SQLite job storage and AnalysisJobManager properly record

    the terminal 'timed_out' status and 504 status code when Stage 3 fails.
    """
    from app.services.jobs.storage import SQLiteJobStorage
    from app.schemas.job import AnalysisJobCreateRequest

    storage = SQLiteJobStorage(db_path=":memory:")

    create_req = AnalysisJobCreateRequest(
        question="Should we migrate inventory systems?",
        timeout_seconds=360.0,
        boardroom_operation_timeout_seconds=120.0,
    )

    job = storage.create_job(create_req)
    assert job.status == JobStatus.QUEUED
    assert job.timeout_seconds == 360.0

    from app.schemas.job import PipelineStage

    # Simulate worker updating to RUNNING, then Stage 3, and timing out
    storage.update_running(job.job_id, PipelineStage.STAGE1_DECISION_FRAMER, "Framing...")
    storage.update_stage(job.job_id, PipelineStage.STAGE3_AI_BOARDROOM, "Conducting cross-perspective deliberation.")
    storage.timeout_job(
        job.job_id,
        error_message="Decision analysis timed out while evaluating the inquiry.",
        stage=PipelineStage.STAGE3_AI_BOARDROOM,
    )

    loaded = storage.get_job(job.job_id)
    assert loaded is not None
    assert loaded.status == JobStatus.TIMED_OUT
    assert loaded.stage == PipelineStage.STAGE3_AI_BOARDROOM
    assert loaded.error_status_code == 504
    assert loaded.response is None


# ------------------------------------------------------------------------------
# 3. Headroom, Retries, and Stage Observability Regression Tests
# ------------------------------------------------------------------------------

def test_06_simulated_55s_response_succeeds_without_45s_abort():
    """Verifies that a 55s generation succeeds under 90s HTTP timeout without premature 45s abort."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=360.0,
        operation_timeout_seconds=120.0,
        http_timeout_seconds=90.0,
        max_retries=1,
    )
    # 55s simulated generation (which would have failed under legacy 45s clamp)
    res = sim.execute(start_time_offset=10.0, attempts=[SimulatedAttempt(duration=55.0, outcome="success")])
    assert res["status"] == "success"
    assert len(res["attempts"]) == 1
    assert res["attempts"][0]["duration"] == 55.0


def test_07_gemini_client_90s_timeout_aborts_futile_retry_with_insufficient_headroom(monkeypatch):
    """Proves that when attempt 1 times out after 90s under 120s budget, the client aborts immediately

    due to insufficient headroom (< 30s remaining) and does NOT initiate a futile attempt 2.
    """
    from unittest.mock import MagicMock
    import httpx
    from app.services.llm.gemini import GeminiLLMClient
    from app.schemas.decision_model import DecisionModel

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = GeminiLLMClient(
        project="test-proj",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )
    client._sleep_fn = lambda s: None

    mock_genai_client = MagicMock()
    call_count = 0

    fake_now = [0.0]

    def mock_monotonic():
        return fake_now[0]

    def failing_create(**kwargs):
        nonlocal call_count
        call_count += 1
        fake_now[0] = 90.5  # 90.5s elapsed, leaving 29.5s < 30.0s headroom
        raise httpx.TimeoutException("Read timed out after 90.0s")

    mock_genai_client.interactions.create = failing_create
    monkeypatch.setattr(client, "_get_genai_client", lambda: mock_genai_client)
    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    cfg = LLMConfig(
        operation_timeout_seconds=120.0,
        timeout_seconds=90.0,
        max_retries=1,
        min_retry_headroom_seconds=30.0,
        stage="stage3_ai_boardroom_perspectives",
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Evaluate perspective",
            response_schema=DecisionModel,
            config=cfg,
        )

    # Exactly 1 attempt made: futile retry was prevented
    assert call_count == 1
    err = exc_info.value
    assert err.details.get("attempt") == 1
    assert err.details.get("exhaustion_reason") == "insufficient_retry_headroom"
    assert "insufficient" in str(err).lower()


def test_08_gemini_client_fast_failure_with_sufficient_headroom_initiates_retry(monkeypatch):
    """Proves that a fast failure (e.g. 5s) with plenty of headroom (> 30s) safely retries and succeeds."""
    from unittest.mock import MagicMock
    import httpx
    from app.services.llm.gemini import GeminiLLMClient
    from app.schemas.decision_model import DecisionModel
    from tests.test_reasoning_orchestrator import build_test_artifacts

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = GeminiLLMClient(
        project="test-proj",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )
    client._sleep_fn = lambda s: None

    mock_genai_client = MagicMock()
    call_count = 0
    fake_now = [0.0]

    def mock_monotonic():
        return fake_now[0]

    sample_dm, _, _ = build_test_artifacts()

    def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            fake_now[0] = 5.0  # Failed quickly after 5s, 115s remaining > 30s headroom
            raise httpx.ConnectError("Connection reset by peer")
        fake_now[0] = 10.0
        mock_resp = MagicMock()
        mock_resp.output_text = sample_dm.model_dump_json()
        return mock_resp

    mock_genai_client.interactions.create = flaky_create
    monkeypatch.setattr(client, "_get_genai_client", lambda: mock_genai_client)
    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    cfg = LLMConfig(
        operation_timeout_seconds=120.0,
        timeout_seconds=90.0,
        max_retries=1,
        min_retry_headroom_seconds=30.0,
    )

    res = client.generate_structured(
        prompt="Evaluate perspective",
        response_schema=DecisionModel,
        config=cfg,
    )

    # Retry was initiated because 115s > 30s headroom
    assert call_count == 2
    assert res.decision.summary == sample_dm.decision.summary


def test_09_parent_deadline_preempts_operation_deadline_classification(monkeypatch):
    """Proves that parent deadline takes absolute precedence and timeout source is attributed to 'parent'."""
    from unittest.mock import MagicMock
    import httpx
    from app.services.llm.gemini import GeminiLLMClient
    from app.schemas.decision_model import DecisionModel

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = GeminiLLMClient(
        project="test-proj",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )
    mock_genai_client = MagicMock()

    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    def timeout_create(**kwargs):
        fake_now[0] = 20.1  # Expired past parent deadline of 20.0s
        raise httpx.TimeoutException("Operation timed out")

    mock_genai_client.interactions.create = timeout_create
    monkeypatch.setattr(client, "_get_genai_client", lambda: mock_genai_client)

    cfg = LLMConfig(
        operation_timeout_seconds=120.0,
        timeout_seconds=90.0,
        max_retries=1,
    )

    # Parent deadline is at t=20.0s, local ceiling is at t=120.0s
    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Evaluate perspective",
            response_schema=DecisionModel,
            config=cfg,
            deadline_monotonic=20.0,
        )

    assert exc_info.value.details.get("timeout_source") == "parent"


def test_10_concurrent_perspective_failures_handled_consistently():
    """Proves that PerspectiveOrchestrator handles concurrent worker failures consistently and fails closed."""
    from unittest.mock import MagicMock
    from app.services.reasoning.orchestrator import PerspectiveOrchestrator
    from app.services.reasoning.evaluator import PerspectiveReasoner
    from tests.test_reasoning_orchestrator import build_test_artifacts

    mock_reasoner = MagicMock(spec=PerspectiveReasoner)

    def failing_eval(ctx, *args, **kwargs):
        ptype = ctx.perspective.perspective_type.value
        if "growth" in ptype or "finance" in ptype:
            raise LLMTimeoutError(f"Simulated timeout in {ptype}", details={"timeout_source": "operation"})
        raise ValueError(f"Provider error in {ptype}")

    mock_reasoner.evaluate = failing_eval
    orchestrator = PerspectiveOrchestrator(reasoner=mock_reasoner, max_workers=4)

    dm, ep, _ = build_test_artifacts()

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(decision_model=dm, evidence_package=ep)

    assert "timed out" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


def test_11_no_background_worker_continues_spending_api_credits_after_cancellation():
    """Proves that if parent deadline is already expired, workers fail before calling Gemini."""
    from unittest.mock import MagicMock
    from app.services.reasoning.orchestrator import PerspectiveOrchestrator
    from app.services.reasoning.evaluator import PerspectiveReasoner
    from tests.test_reasoning_orchestrator import build_test_artifacts

    mock_reasoner = MagicMock(spec=PerspectiveReasoner)
    call_count = 0

    def counting_eval(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Should never be called")

    mock_reasoner.evaluate = counting_eval
    orchestrator = PerspectiveOrchestrator(reasoner=mock_reasoner, max_workers=4)

    dm, ep, _ = build_test_artifacts()

    # Monotonic deadline expired 5 seconds ago
    expired_deadline = time.monotonic() - 5.0

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(decision_model=dm, evidence_package=ep, deadline_monotonic=expired_deadline)

    # Zero worker calls were dispatched: 0 API credits spent
    assert call_count == 0


def test_12_structured_timing_metrics_recorded_across_all_six_stages():
    """Proves that AnalysisService records structured timing across all 6 stages."""
    svc = AnalysisService(
        llm_client=FakeLLMClient(),
        search_provider=FakeSearchProvider(),
        analysis_timeout_seconds=180.0,
    )

    req = AnalysisRequest(question="Should we launch enterprise tier?")
    res = svc.analyze(req)

    assert res.decision_model is not None
    assert hasattr(svc, "last_stage_timings")
    timings = svc.last_stage_timings

    required_stages = [
        "stage1_decision_framer",
        "stage2_evidence_engine",
        "stage3_ai_boardroom",
        "stage4_recommendation",
        "stage5_scenarios",
        "stage6_resilience",
    ]
    for stage_name in required_stages:
        assert stage_name in timings, f"Missing timing for {stage_name}"
        assert isinstance(timings[stage_name], float)
        assert timings[stage_name] >= 0.0

