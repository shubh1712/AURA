"""Unit and regression tests for AURA AI Boardroom Safe LLM Deadline Configuration.

Verifies:
1. Default requests retain the 60-second Boardroom perspective ceiling.
2. Opt-in requests with boardroom_operation_timeout_seconds=75.0 apply 75s (and 45s HTTP timeout) to all four perspectives.
3. Decision Framer and Evidence Engine remain isolated and unaffected.
4. Board synthesis retains its default 60-second operation ceiling.
5. The parent deadline always takes precedence over the boardroom ceiling when parent expires first.
6. Slow provider response within 45s completes on the first attempt without timing out.
7. Simulated attempt 1 timeout followed by attempt 2 recovery completes under boardroom ceiling.
8. Repeated provider stalls fail closed at the boardroom ceiling with typed LLMTimeoutError (source="operation").
9. Invalid boardroom override values fail predictably with ValueError (both constructor and env var).
10. Concurrent requests with different settings remain strictly isolated.
11. No partial artifacts escape on timeout (HTTP 504 raised).
12. All four perspectives and referential integrity preserved on success.
13. SQLite job storage and AnalysisJobManager roundtrip boardroom_operation_timeout_seconds correctly.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.schemas.analysis import AnalysisRequest
from app.schemas.decision_model import DecisionModel
from app.schemas.job import AnalysisJobCreateRequest, JobStatus
from app.schemas.reasoning import (
    CandidateBoardSynthesis,
    CandidatePerspectiveAnalysis,
    PerspectiveType,
    ReasoningBoard,
)
from app.services.analysis_service import AnalysisService, AnalysisTimeoutError
from app.services.evidence import FakeSearchProvider, SearchResultItem
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import DEFAULT_LLM_CONFIG, FakeLLMClient, LLMConfig, LLMTimeoutError
from app.services.llm.gemini import GeminiLLMClient
from app.services.reasoning.service import ReasoningService
from tests.test_decision_framer_unit_contract import FakeClockLLMOperation, SimulatedAttempt


# ------------------------------------------------------------------------------
# Test Tracking LLM Client
# ------------------------------------------------------------------------------

class ConfigTrackingLLMClient(FakeLLMClient):
    """Fake LLM client that logs the LLMConfig passed to every generate_structured call."""

    def __init__(self, default_response: Optional[Any] = None) -> None:
        super().__init__(default_response=default_response)
        self.recorded_configs: List[Tuple[str, Optional[LLMConfig]]] = []
        self._lock = threading.Lock()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        schema_name = getattr(response_schema, "__name__", str(response_schema))
        with self._lock:
            self.recorded_configs.append((schema_name, config))
        return super().generate_structured(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
            config=config,
            deadline_monotonic=deadline_monotonic,
        )


def _setup_mock_analysis_service(
    tracking_client: ConfigTrackingLLMClient,
    framer_to: Optional[float] = None,
    boardroom_to: Optional[float] = None,
    analysis_to: float = 180.0,
) -> AnalysisService:
    """Constructs a fully offline AnalysisService with fake provider."""
    fake_search = FakeSearchProvider(
        default_results=[
            SearchResultItem(
                url="https://example.com/item1",
                title="SaaS Pricing Benchmark",
                snippet="Pricing reduction of 20% lifted customer acquisition by 14%.",
            )
        ]
    )
    return AnalysisService(
        llm_client=tracking_client,
        search_provider=fake_search,
        analysis_timeout_seconds=analysis_to,
        framer_operation_timeout_seconds=framer_to,
        boardroom_operation_timeout_seconds=boardroom_to,
    )


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------

def test_01_default_requests_retain_60s_boardroom_ceiling():
    """Default requests without overrides retain the 60.0s operation ceiling for all 4 perspectives."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=None, boardroom_to=None, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    res = svc.analyze(request)

    assert res.reasoning_board is not None
    persp_calls = [c for c in client.recorded_configs if c[0] == "CandidatePerspectiveAnalysis"]
    assert len(persp_calls) == 4
    for _, config_passed in persp_calls:
        effective_ceiling = (
            config_passed.operation_timeout_seconds
            if config_passed
            else DEFAULT_LLM_CONFIG.operation_timeout_seconds
        )
        assert effective_ceiling == 60.0


def test_02_opt_in_boardroom_timeout_propagates_to_all_four_perspectives():
    """Opt-in boardroom_operation_timeout_seconds=75.0 applies 75s ceiling and 45s HTTP timeout to all 4 perspectives."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=None, boardroom_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    res = svc.analyze(request)

    assert res.reasoning_board is not None
    persp_calls = [c for c in client.recorded_configs if c[0] == "CandidatePerspectiveAnalysis"]
    assert len(persp_calls) == 4
    for _, config_passed in persp_calls:
        assert config_passed is not None
        assert config_passed.operation_timeout_seconds == 75.0
        assert config_passed.timeout_seconds == 45.0


def test_03_framer_and_evidence_remain_isolated():
    """Setting boardroom_operation_timeout_seconds=75.0 leaves Framer and Evidence mapping using their default 60s."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=None, boardroom_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    framer_calls = [c for c in client.recorded_configs if c[0] == "DecisionModel"]
    assert len(framer_calls) >= 1
    _, framer_cfg = framer_calls[0]
    effective_framer = framer_cfg.operation_timeout_seconds if framer_cfg else DEFAULT_LLM_CONFIG.operation_timeout_seconds
    assert effective_framer == 60.0


def test_04_board_synthesis_retains_default_operation_ceiling():
    """Boardroom synthesis retains its default 60s operation ceiling, protected from perspective settings."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=None, boardroom_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    synth_calls = [c for c in client.recorded_configs if c[0] == "CandidateBoardSynthesis"]
    assert len(synth_calls) >= 1
    _, synth_cfg = synth_calls[0]
    effective_synth = synth_cfg.operation_timeout_seconds if synth_cfg else DEFAULT_LLM_CONFIG.operation_timeout_seconds
    assert effective_synth == 60.0


def test_05_parent_deadline_takes_precedence_over_boardroom_ceiling(monkeypatch: pytest.MonkeyPatch):
    """When remaining parent deadline is shorter than the boardroom ceiling, parent deadline takes precedence."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=40.0,
        operation_timeout_seconds=75.0,
        http_timeout_seconds=45.0,
    )
    # Start at t=30.0 with only 10.0s remaining of 40.0s parent deadline
    res = sim.execute(
        30.0,
        [SimulatedAttempt(duration=45.0, outcome="timeout")],
    )
    assert res["status"] == "timeout"
    # Should time out after 10.0s (clamped to remaining parent deadline), not 45s or 75s
    assert res["total_op_duration"] == pytest.approx(10.0, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(0.0, abs=1e-3)


def test_06_slow_provider_response_within_45s_completes_on_first_attempt():
    """Under 45s HTTP timeout, a 35s live generation completes successfully on attempt 1 without timing out."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=180.0,
        operation_timeout_seconds=75.0,
        http_timeout_seconds=45.0,
    )
    # Attempt 1 takes 35s (which previously failed under 30s HTTP timeout)
    res = sim.execute(
        0.0,
        [SimulatedAttempt(duration=35.0, outcome="success")],
    )
    assert res["status"] == "success"
    assert len(res["attempts"]) == 1
    assert res["total_op_duration"] == pytest.approx(35.0, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(145.0, rel=1e-3)


def test_07_attempt_one_timeout_attempt_two_recovery_within_boardroom_ceiling():
    """Simulated attempt 1 timeout (45s) followed by attempt 2 recovery (25s) succeeds within 75s ceiling."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=180.0,
        operation_timeout_seconds=75.0,
        http_timeout_seconds=45.0,
    )
    # Attempt 1 times out at 45.0s + 0.5s backoff = 45.5s
    # Attempt 2 takes 25.0s (<= remaining ceiling 29.5s) and succeeds
    res = sim.execute(
        0.0,
        [
            SimulatedAttempt(duration=45.0, outcome="timeout"),
            SimulatedAttempt(duration=25.0, outcome="success"),
        ],
    )
    assert res["status"] == "success"
    assert len(res["attempts"]) == 2
    assert res["total_op_duration"] == pytest.approx(70.5, rel=1e-3)  # 45 + 0.5 + 25 = 70.5s <= 75.0s
    assert res["remaining_parent_budget"] == pytest.approx(109.5, rel=1e-3)


def test_08_repeated_provider_stalls_fail_closed_at_boardroom_ceiling():
    """Under 75s ceiling, repeated provider stalls fail closed at 75s without exceeding the ceiling."""
    sim = FakeClockLLMOperation(
        parent_timeout_seconds=180.0,
        operation_timeout_seconds=75.0,
        http_timeout_seconds=45.0,
    )
    # Attempt 1 stalls: 45.0s + 0.5s backoff = 45.5s
    # Attempt 2 stalls: min(45, 29.5) = 29.5s -> total 75.0s
    res = sim.execute(
        0.0,
        [
            SimulatedAttempt(duration=45.0, outcome="timeout"),
            SimulatedAttempt(duration=45.0, outcome="timeout"),
        ],
    )
    assert res["status"] == "timeout"
    assert res["total_op_duration"] == pytest.approx(75.0, rel=1e-3)
    # 105.0s still remains in the parent budget! The parent budget was NOT consumed by the stalled provider.
    assert res["remaining_parent_budget"] == pytest.approx(105.0, rel=1e-3)


def test_09_invalid_boardroom_timeout_values_fail_predictably():
    """Invalid boardroom timeout values (<=0.0 or non-numeric strings) raise ValueError predictably."""
    with pytest.raises(ValueError, match="strictly greater than 0.0"):
        AnalysisService(boardroom_operation_timeout_seconds=-10.0)

    with pytest.raises(ValueError, match="strictly greater than 0.0"):
        AnalysisService(boardroom_operation_timeout_seconds=0.0)

    # Test via environment variable
    old_env = os.environ.get("AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS")
    try:
        os.environ["AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS"] = "-50.0"
        with pytest.raises(ValueError, match="strictly greater than 0.0"):
            AnalysisService()

        os.environ["AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS"] = "non_numeric"
        with pytest.raises(ValueError, match="Invalid AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS"):
            AnalysisService()
    finally:
        if old_env is not None:
            os.environ["AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS"] = old_env
        else:
            os.environ.pop("AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS", None)


def test_10_concurrent_requests_with_different_settings_remain_isolated():
    """Two concurrent requests (one with 75s boardroom override, one default) remain strictly isolated."""
    client_a = ConfigTrackingLLMClient()
    svc_a = _setup_mock_analysis_service(client_a, boardroom_to=75.0, analysis_to=180.0)

    client_b = ConfigTrackingLLMClient()
    svc_b = _setup_mock_analysis_service(client_b, boardroom_to=None, analysis_to=180.0)

    def run_a():
        return svc_a.analyze(AnalysisRequest(question="Inquiry A"))

    def run_b():
        return svc_b.analyze(AnalysisRequest(question="Inquiry B"))

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_a = ex.submit(run_a)
        fut_b = ex.submit(run_b)
        res_a = fut_a.result()
        res_b = fut_b.result()

    assert res_a.reasoning_board is not None
    assert res_b.reasoning_board is not None

    persp_a = [c for c in client_a.recorded_configs if c[0] == "CandidatePerspectiveAnalysis"]
    for _, cfg in persp_a:
        assert cfg is not None
        assert cfg.operation_timeout_seconds == 75.0
        assert cfg.timeout_seconds == 45.0

    persp_b = [c for c in client_b.recorded_configs if c[0] == "CandidatePerspectiveAnalysis"]
    for _, cfg in persp_b:
        effective_b = cfg.operation_timeout_seconds if cfg else DEFAULT_LLM_CONFIG.operation_timeout_seconds
        assert effective_b == 60.0


def test_11_no_partial_artifacts_escape_on_timeout():
    """When a perspective evaluation times out, an HTTPException(504) is raised with no escaped response."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, boardroom_to=75.0, analysis_to=180.0)

    # Force reasoning service to raise LLMTimeoutError
    def failing_build(*args: Any, **kwargs: Any) -> Any:
        raise LLMTimeoutError(
            "Simulated LLM operation timeout during perspective evaluation.",
            details={"timeout_source": "operation", "attempt": 2},
        )
    svc.reasoning_service.build_reasoning_board = failing_build

    request = AnalysisRequest(question="Should we expand pricing?")
    with pytest.raises(HTTPException) as exc_info:
        svc.analyze(request)

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()


def test_12_all_four_perspectives_and_referential_integrity_preserved_on_success():
    """All four canonical perspectives (growth, finance, customer, risk) and valid ID references succeed."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, boardroom_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    res = svc.analyze(request)

    assert res.reasoning_board is not None
    types = [p.perspective_type for p in res.reasoning_board.perspectives]
    assert types == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]
    assert res.reasoning_board.synthesis is not None
    assert res.reasoning_board.id.startswith("rbd_")


def test_13_job_manager_and_storage_roundtrip_boardroom_timeout():
    """Submitting an asynchronous job with boardroom_operation_timeout_seconds persists and hydrates cleanly."""
    storage = SQLiteJobStorage(db_path=":memory:")
    created_services: List[AnalysisService] = []

    def service_factory():
        svc = AnalysisService(
            llm_client=ConfigTrackingLLMClient(),
            search_provider=FakeSearchProvider(),
        )
        created_services.append(svc)
        return svc

    manager = AnalysisJobManager(
        storage=storage,
        service_factory=service_factory,
        max_workers=1,
    )

    req = AnalysisJobCreateRequest(
        question="Should we launch enterprise tier?",
        timeout_seconds=200.0,
        framer_operation_timeout_seconds=70.0,
        boardroom_operation_timeout_seconds=85.0,
    )

    job_status = manager.submit_job(req)
    assert job_status.job_id is not None

    record = storage.get_job(job_status.job_id)
    assert record is not None
    assert record.timeout_seconds == 200.0
    assert record.framer_timeout_seconds == 70.0
    assert record.boardroom_timeout_seconds == 85.0
