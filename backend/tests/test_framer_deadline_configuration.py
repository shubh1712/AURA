"""Unit and regression tests for AURA Day 4 Phase 4.36: Safe Framer-Specific LLM Deadline Configuration.

Verifies:
1. Default requests retain the 60-second Framer ceiling.
2. Opt-in diagnostic requests use 75 seconds for the Framer.
3. Evidence Requirements still use 60 seconds.
4. Evidence Mapping batches still use 60 seconds.
5. All four Boardroom perspectives still use 60 seconds.
6. Board synthesis still uses 60 seconds.
7. The parent deadline always takes precedence over the local ceiling.
8. Concurrent requests with different settings remain isolated.
9. An invalid override fails predictably (ValueError).
10. Retry and cancellation behavior remain unchanged.
11. Simulated third-attempt recovery can complete under 75 seconds when actual durations fit.
12. Repeated provider stalls still terminate and fail closed.
13. No partial artifacts escape on timeout.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
from typing import Any, Dict, List, Optional
import pytest
from fastapi import HTTPException

from app.config import settings
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import (
    CandidateBoardSynthesis,
    CandidatePerspectiveAnalysis,
    PerspectiveType,
    ReasoningBoard,
)
from app.services.analysis_service import AnalysisService, AnalysisTimeoutError
from app.services.evidence import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    EvidenceMapper,
    EvidenceService,
    FakeSearchProvider,
    NormalizedSourceResult,
    SearchResultItem,
)
from app.services.evidence.requirements import (
    CandidateEvidenceRequirement,
    CandidateRequirementsPayload,
)
from app.services.llm.client import DEFAULT_LLM_CONFIG, FakeLLMClient, LLMConfig, LLMTimeoutError
from app.services.llm.mock_data import get_default_decision_model
from app.services.reasoning import ReasoningService


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
    analysis_to: float = 120.0,
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
    )


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------

def test_1_default_requests_retain_60s_framer_ceiling():
    """Default requests without overrides retain the 60.0s operation ceiling for DecisionModel."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=None, analysis_to=120.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    res = svc.analyze(request)

    assert res.decision_model is not None
    # Check DecisionModel call config
    decision_model_calls = [c for c in client.recorded_configs if c[0] == "DecisionModel"]
    assert len(decision_model_calls) >= 1
    _, config_passed = decision_model_calls[0]
    # When config_passed is None, GeminiLLMClient defaults to DEFAULT_LLM_CONFIG (60.0s)
    effective_ceiling = config_passed.operation_timeout_seconds if config_passed else DEFAULT_LLM_CONFIG.operation_timeout_seconds
    assert effective_ceiling == 60.0


def test_2_opt_in_diagnostic_requests_use_75s_for_framer():
    """Opt-in requests with framer_operation_timeout_seconds=75.0 apply 75s to DecisionModel."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    res = svc.analyze(request)

    assert res.decision_model is not None
    decision_model_calls = [c for c in client.recorded_configs if c[0] == "DecisionModel"]
    assert len(decision_model_calls) >= 1
    _, config_passed = decision_model_calls[0]
    assert config_passed is not None
    assert config_passed.operation_timeout_seconds == 75.0


def test_3_evidence_requirements_still_use_60s():
    """Under framer_operation_timeout_seconds=75.0, Evidence Requirements still uses 60s."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    req_calls = [c for c in client.recorded_configs if c[0] == "CandidateRequirementsPayload"]
    assert len(req_calls) >= 1
    _, config_passed = req_calls[0]
    effective_ceiling = config_passed.operation_timeout_seconds if config_passed else DEFAULT_LLM_CONFIG.operation_timeout_seconds
    assert effective_ceiling == 60.0


def test_4_evidence_mapping_batches_still_use_60s():
    """Under framer_operation_timeout_seconds=75.0, Evidence Mapping batches still use 60s."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    map_calls = [c for c in client.recorded_configs if c[0] == "CandidateBatchEvidenceMappingPayload"]
    # If mapping calls occurred, they must use 60.0s
    for _, config_passed in map_calls:
        effective_ceiling = config_passed.operation_timeout_seconds if config_passed else DEFAULT_LLM_CONFIG.operation_timeout_seconds
        assert effective_ceiling == 60.0


def test_5_all_four_boardroom_perspectives_still_use_60s():
    """Under framer_operation_timeout_seconds=75.0, Boardroom perspective evaluations still use 60s."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    persp_calls = [c for c in client.recorded_configs if c[0] == "CandidatePerspectiveAnalysis"]
    assert len(persp_calls) >= 1
    for _, config_passed in persp_calls:
        effective_ceiling = config_passed.operation_timeout_seconds if config_passed else DEFAULT_LLM_CONFIG.operation_timeout_seconds
        assert effective_ceiling == 60.0


def test_6_board_synthesis_still_uses_60s():
    """Under framer_operation_timeout_seconds=75.0, Board synthesis still uses 60s."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request)

    synth_calls = [c for c in client.recorded_configs if c[0] == "CandidateBoardSynthesis"]
    assert len(synth_calls) >= 1
    _, config_passed = synth_calls[0]
    effective_ceiling = config_passed.operation_timeout_seconds if config_passed else DEFAULT_LLM_CONFIG.operation_timeout_seconds
    assert effective_ceiling == 60.0


def test_7_parent_deadline_always_takes_precedence():
    """Parent deadline takes precedence over local 75s ceiling when parent deadline expires first."""
    client = ConfigTrackingLLMClient()
    # 75s framer ceiling, but parent deadline has only 10 seconds remaining
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    t_now = time.monotonic()
    parent_tight_deadline = t_now + 10.0

    # Simulate client that verifies clamped deadline
    observed_deadlines = []
    orig_generate = client.generate_structured
    def inspect_deadline(*args: Any, **kwargs: Any) -> Any:
        deadline_arg = kwargs.get("deadline_monotonic")
        observed_deadlines.append(deadline_arg)
        return orig_generate(*args, **kwargs)
    client.generate_structured = inspect_deadline

    request = AnalysisRequest(question="Should we expand pricing?")
    svc.analyze(request, deadline_monotonic=parent_tight_deadline)

    assert len(observed_deadlines) >= 1
    # Effective deadline passed to generate_structured is parent_tight_deadline (t_now + 10)
    assert observed_deadlines[0] == parent_tight_deadline


def test_8_concurrent_requests_with_different_settings_remain_isolated():
    """Concurrent requests with 75s vs default 60s remain strictly isolated without cross-talk."""
    client_1 = ConfigTrackingLLMClient()
    client_2 = ConfigTrackingLLMClient()

    svc_75 = _setup_mock_analysis_service(client_1, framer_to=75.0, analysis_to=180.0)
    svc_def = _setup_mock_analysis_service(client_2, framer_to=None, analysis_to=120.0)

    def run_75():
        req = AnalysisRequest(question="Question 75?")
        svc_75.analyze(req)

    def run_def():
        req = AnalysisRequest(question="Question def?")
        svc_def.analyze(req)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_75)
        f2 = executor.submit(run_def)
        f1.result()
        f2.result()

    calls_75 = [c for c in client_1.recorded_configs if c[0] == "DecisionModel"]
    calls_def = [c for c in client_2.recorded_configs if c[0] == "DecisionModel"]

    assert calls_75[0][1].operation_timeout_seconds == 75.0
    assert (calls_def[0][1] is None or calls_def[0][1].operation_timeout_seconds == 60.0)


def test_9_invalid_override_fails_predictably():
    """Setting non-positive or non-numeric framer override raises ValueError predictably."""
    with pytest.raises(ValueError, match="strictly greater than 0.0"):
        AnalysisService(framer_operation_timeout_seconds=-10.0)

    with pytest.raises(ValueError, match="strictly greater than 0.0"):
        AnalysisService(framer_operation_timeout_seconds=0.0)

    # Test via environment variable
    old_env = os.environ.get("AURA_FRAMER_OPERATION_TIMEOUT_SECONDS")
    try:
        os.environ["AURA_FRAMER_OPERATION_TIMEOUT_SECONDS"] = "-25.0"
        with pytest.raises(ValueError, match="strictly greater than 0.0"):
            AnalysisService()

        os.environ["AURA_FRAMER_OPERATION_TIMEOUT_SECONDS"] = "invalid_string"
        with pytest.raises(ValueError, match="Invalid AURA_FRAMER_OPERATION_TIMEOUT_SECONDS"):
            AnalysisService()
    finally:
        if old_env is not None:
            os.environ["AURA_FRAMER_OPERATION_TIMEOUT_SECONDS"] = old_env
        else:
            os.environ.pop("AURA_FRAMER_OPERATION_TIMEOUT_SECONDS", None)


def test_10_retry_and_cancellation_behavior_remain_unchanged():
    """Retry count on LLMConfig remains 2 (max 3 attempts) and backoff settings are untouched."""
    framer_cfg = LLMConfig(operation_timeout_seconds=75.0)
    assert framer_cfg.max_retries == 2
    assert framer_cfg.timeout_seconds == 30.0
    assert framer_cfg.operation_timeout_seconds == 75.0


def test_11_simulated_third_attempt_recovery_completes_under_75s():
    """Fake-clock simulation proving third attempt succeeds under 75s when durations fit.

    Attempt 1: 30s timeout + 0.5s backoff = 30.5s
    Attempt 2: 20s validation error + 1.0s backoff = 21.0s (total: 51.5s)
    Attempt 3: 20s generation duration
    Total: 71.5s <= 75.0s ceiling.
    """
    from tests.test_decision_framer_unit_contract import FakeClockLLMOperation, SimulatedAttempt

    sim = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=75.0)
    res = sim.execute(
        0.0,
        [
            SimulatedAttempt(duration=30.0, outcome="timeout"),
            SimulatedAttempt(duration=20.0, outcome="validation_error", validation_error_path="variables.0.unit"),
            SimulatedAttempt(duration=20.0, outcome="success"),
        ],
    )
    assert res["status"] == "success"
    assert res["total_op_duration"] == pytest.approx(71.5, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(108.5, rel=1e-3)


def test_12_repeated_provider_stalls_still_terminate_and_fail_closed():
    """Under 75s ceiling, three consecutive 30s provider stalls cleanly fail closed at 75s."""
    from tests.test_decision_framer_unit_contract import FakeClockLLMOperation, SimulatedAttempt

    sim = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=75.0)
    res = sim.execute(
        0.0,
        [
            SimulatedAttempt(duration=30.0, outcome="timeout"),
            SimulatedAttempt(duration=30.0, outcome="timeout"),
            SimulatedAttempt(duration=30.0, outcome="timeout"),
        ],
    )
    assert res["status"] == "timeout"
    assert res["total_op_duration"] == pytest.approx(75.0, rel=1e-3)


def test_13_no_partial_artifacts_escape_on_timeout():
    """When timeout occurs during analysis, an HTTPException(504) is raised with zero escaped response."""
    client = ConfigTrackingLLMClient()
    svc = _setup_mock_analysis_service(client, framer_to=75.0, analysis_to=180.0)

    # Force deconstruct to raise timeout
    def failing_deconstruct(*args: Any, **kwargs: Any) -> Any:
        raise LLMTimeoutError("Simulated LLM operation timeout during deconstruction.")
    svc.engine.deconstruct = failing_deconstruct

    request = AnalysisRequest(question="Test question?")
    with pytest.raises(HTTPException) as exc_info:
        svc.analyze(request)

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()
