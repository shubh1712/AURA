"""Tests for AURA Day 4 — AI Boardroom Phase 4.8: Analysis Service + API/DI Integration.

Verifies:
- Request-scoped LLMClient identity invariant across all three stages (Section 17)
- AnalysisResponse schema contract and backward compatibility (Section 18, Tests 1–7)
- AnalysisService Stage 1 -> Stage 2 -> Stage 3 pipeline orchestration (Section 19, Tests 8–16)
- Shared absolute monotonic deadline propagation & expiry (Section 20, Tests 17–22)
- Boardroom error cause-chain translation and HTTP mappings (Section 21, Tests 23–32)
- Security and sensitive data sanitization (Section 22)
- Architecture exclusions: no recommendation, scenario, resilience, or voting (Section 26)
"""

import copy
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import pytest
from fastapi import Depends, HTTPException, status
from fastapi.testclient import TestClient

from app.config import settings
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningBoard,
)
from app.services.analysis_service import (
    AnalysisService,
    AnalysisTimeoutError,
    get_analysis_service,
    get_evidence_service,
    get_llm_client,
    get_reasoning_service,
)
from app.services.evidence.mapper import EvidenceMapper
from app.services.evidence.requirements import EvidenceRequirementEngine
from app.services.evidence.search_provider import FakeSearchProvider
from app.services.evidence.service import EvidenceService, EvidenceServiceError
from app.services.llm.client import (
    FakeLLMClient,
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.service import ReasoningService
from app.services.reasoning.synthesizer import BoardSynthesizer
from app.services.reasoning.validator import (
    ReasoningEvaluationError,
    ReasoningOrchestrationError,
    ReasoningPromptError,
    ReasoningServiceError,
    ReasoningValidationError,
)
from tests.test_reasoning_service import build_test_artifacts


# ------------------------------------------------------------------------------
# Helpers & Spies
# ------------------------------------------------------------------------------

def _create_canonical_board(
    dm: DecisionModel,
    ep: EvidencePackage,
) -> ReasoningBoard:
    """Creates a valid, referentially-sound ReasoningBoard for testing."""
    _, _, perspectives, disagreements, synthesis = build_test_artifacts()
    return ReasoningBoard(
        id="rbd_integration_test_01",
        decision_model_id=dm.id,
        evidence_package_id=ep.id,
        perspectives=list(perspectives),
        disagreements=disagreements,
        synthesis=synthesis,
    )


class SpyQuestionUnderstandingEngine(QuestionUnderstandingEngine):
    """Spy engine recording deconstruct invocation order and parameters."""

    def __init__(self, dm: DecisionModel, llm_client: Optional[LLMClient] = None) -> None:
        client = llm_client or FakeLLMClient()
        super().__init__(llm_client=client)
        self.dm = dm
        self.calls: List[Dict[str, Any]] = []

    def deconstruct(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> DecisionModel:
        self.calls.append({
            "stage": "stage_1",
            "time": time.monotonic(),
            "deadline": deadline_monotonic,
        })
        return self.dm


class SpyEvidenceService(EvidenceService):
    """Spy service recording build_evidence_package invocation order and parameters."""

    def __init__(self, ep: EvidencePackage, llm_client: Optional[LLMClient] = None) -> None:
        client = llm_client or FakeLLMClient()
        super().__init__(
            requirement_engine=EvidenceRequirementEngine(llm_client=client),
            retriever=None,  # type: ignore
            normalizer=None,  # type: ignore
            mapper=EvidenceMapper(llm_client=client),
            gap_detector=None,  # type: ignore
        )
        self.ep = ep
        self.calls: List[Dict[str, Any]] = []

    def build_evidence_package(
        self,
        decision_model: DecisionModel,
        deadline_monotonic: Optional[float] = None,
    ) -> EvidencePackage:
        self.calls.append({
            "stage": "stage_2",
            "time": time.monotonic(),
            "decision_model": decision_model,
            "deadline": deadline_monotonic,
        })
        return self.ep


class SpyReasoningService(ReasoningService):
    """Spy service recording build_reasoning_board invocation order and parameters."""

    def __init__(self, board: ReasoningBoard, llm_client: Optional[LLMClient] = None) -> None:
        client = llm_client or FakeLLMClient()
        reasoner = PerspectiveReasoner(llm_client=client)
        synthesizer = BoardSynthesizer(llm_client=client)
        super().__init__(
            orchestrator=None,  # type: ignore
            synthesizer=synthesizer,
        )
        self.reasoner = reasoner
        self.board = board
        self.calls: List[Dict[str, Any]] = []

    def build_reasoning_board(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        deadline_monotonic: Optional[float] = None,
    ) -> ReasoningBoard:
        self.calls.append({
            "stage": "stage_3",
            "time": time.monotonic(),
            "decision_model": decision_model,
            "evidence_package": evidence_package,
            "deadline": deadline_monotonic,
        })
        return self.board


# ------------------------------------------------------------------------------
# 1. Section 17: Request-Scoped LLM Identity Invariant Test
# ------------------------------------------------------------------------------

def test_request_scoped_llm_client_identity_reused_across_all_stages() -> None:
    """Verifies that within ONE request, the exact same LLMClient object is reused across all stages.

    Identity invariant:
    Decision Framer LLM client
    IS
    Evidence requirement/mapping LLM client
    IS
    Reasoning PerspectiveReasoner LLM client
    IS
    Reasoning BoardSynthesizer LLM client
    """
    class IdentityCapturingClient(FakeLLMClient):
        pass

    captured_instances: List[LLMClient] = []

    def capturing_llm_client() -> LLMClient:
        inst = IdentityCapturingClient()
        captured_instances.append(inst)
        return inst

    captured_service: List[AnalysisService] = []

    from app.services.analysis_service import (
        get_question_understanding_engine,
        get_search_provider,
    )

    def capturing_analysis_service(
        engine: QuestionUnderstandingEngine = Depends(get_question_understanding_engine),
        evidence_service: EvidenceService = Depends(get_evidence_service),
        reasoning_service: ReasoningService = Depends(get_reasoning_service),
    ) -> AnalysisService:
        svc = AnalysisService(
            engine=engine,
            evidence_service=evidence_service,
            reasoning_service=reasoning_service,
        )
        captured_service.append(svc)
        return svc

    saved_overrides = dict(app.dependency_overrides)
    try:
        # Clear out conftest overrides so FastAPI resolves the real graph
        app.dependency_overrides.pop(get_analysis_service, None)
        app.dependency_overrides.pop(get_evidence_service, None)
        app.dependency_overrides.pop(get_reasoning_service, None)

        # Wire capturing LLM client and fake search
        app.dependency_overrides[get_llm_client] = capturing_llm_client
        app.dependency_overrides[get_search_provider] = lambda: FakeSearchProvider()
        app.dependency_overrides[get_analysis_service] = capturing_analysis_service

        with TestClient(app) as test_client:
            resp = test_client.post("/api/analyze", json={"question": "Should we migrate to distributed caching?"})
            assert resp.status_code == 200, resp.text

        # 1. Exactly ONE client instance created for the request
        assert len(captured_instances) == 1
        shared_client = captured_instances[0]

        # 2. Inspect the captured AnalysisService from the request
        assert len(captured_service) == 1
        service = captured_service[0]

        # Invariant 1: Decision Framer LLM client IS the shared client
        framer_client = service.engine.llm_client
        assert framer_client is shared_client

        # Invariant 2: Evidence requirement engine LLM client IS the shared client
        evidence_req_client = service.evidence_service.requirement_engine.llm_client
        assert evidence_req_client is shared_client

        # Invariant 3: Evidence mapper LLM client IS the shared client
        evidence_map_client = service.evidence_service.mapper.llm_client
        assert evidence_map_client is shared_client

        # Invariant 4: Reasoning PerspectiveReasoner LLM client IS the shared client
        reasoner_client = service.reasoning_service.orchestrator.reasoner.llm_client
        assert reasoner_client is shared_client

        # Invariant 5: Reasoning BoardSynthesizer LLM client IS the shared client
        synthesizer_client = service.reasoning_service.synthesizer.llm_client
        assert synthesizer_client is shared_client

        # Full transitive identity assertion using `is`
        assert framer_client is evidence_req_client
        assert evidence_req_client is evidence_map_client
        assert evidence_map_client is reasoner_client
        assert reasoner_client is synthesizer_client

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)


# ------------------------------------------------------------------------------
# 2. Section 18: AnalysisResponse Contract Tests (1–7)
# ------------------------------------------------------------------------------

def test_1_reasoning_board_defaults_to_none() -> None:
    """Test 1: AnalysisResponse.reasoning_board defaults to None."""
    resp = AnalysisResponse(
        analysis_id="test_id_01",
        status="completed",
        question="Should we scale?",
    )
    assert resp.reasoning_board is None


def test_2_existing_response_construction_remains_valid() -> None:
    """Test 2: Callers constructing AnalysisResponse without reasoning_board remain valid."""
    dm, ep, _, _, _ = build_test_artifacts()
    resp = AnalysisResponse(
        analysis_id="test_id_02",
        status="completed",
        decision_model=dm,
        evidence_package=ep,
        question="Should we hire?",
        message="Deconstruction complete.",
    )
    assert resp.reasoning_board is None
    assert resp.decision_model == dm
    assert resp.evidence_package == ep


def test_3_response_accepts_valid_reasoning_board() -> None:
    """Test 3: AnalysisResponse accepts an instantiated, valid ReasoningBoard."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)
    resp = AnalysisResponse(
        analysis_id="test_id_03",
        status="completed",
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=board,
        question="Should we expand?",
    )
    assert resp.reasoning_board is not None
    assert resp.reasoning_board.id == board.id


def test_4_serialized_api_response_includes_reasoning_board(client: TestClient) -> None:
    """Test 4: Serialized POST /api/analyze JSON response includes reasoning_board."""
    http_res = client.post("/api/analyze", json={"question": "Should we build an internal platform?"})
    assert http_res.status_code == 200
    data = http_res.json()
    assert "reasoning_board" in data
    assert data["reasoning_board"] is not None
    assert "perspectives" in data["reasoning_board"]
    assert "synthesis" in data["reasoning_board"]


def test_5_reasoning_board_contains_exactly_four_canonical_perspectives(client: TestClient) -> None:
    """Test 5: reasoning_board in API response contains exactly four canonical perspectives."""
    http_res = client.post("/api/analyze", json={"question": "Should we migrate to Postgres?"})
    assert http_res.status_code == 200
    data = http_res.json()
    board_data = data["reasoning_board"]
    perspectives = board_data["perspectives"]
    assert len(perspectives) == 4
    types = {p["perspective_type"] for p in perspectives}
    assert types == {"growth", "finance", "customer", "risk"}


def test_6_reasoning_board_decision_model_id_matches_decision_model(client: TestClient) -> None:
    """Test 6: reasoning_board.decision_model_id matches decision_model.id."""
    http_res = client.post("/api/analyze", json={"question": "Should we open a European office?"})
    assert http_res.status_code == 200
    data = http_res.json()
    assert data["reasoning_board"]["decision_model_id"] == data["decision_model"]["id"]


def test_7_reasoning_board_evidence_package_id_matches_evidence_package(client: TestClient) -> None:
    """Test 7: reasoning_board.evidence_package_id matches evidence_package.id."""
    http_res = client.post("/api/analyze", json={"question": "Should we change pricing models?"})
    assert http_res.status_code == 200
    data = http_res.json()
    assert data["reasoning_board"]["evidence_package_id"] == data["evidence_package"]["id"]


# ------------------------------------------------------------------------------
# 3. Section 19: AnalysisService Pipeline Execution Tests (8–16)
# ------------------------------------------------------------------------------

def test_8_stage_1_executes_before_stage_2() -> None:
    """Test 8: Stage 1 (Decision Framer) executes strictly before Stage 2 (Evidence Engine)."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    service.analyze(AnalysisRequest(question="Test sequence?"))

    assert len(engine.calls) == 1
    assert len(evidence_svc.calls) == 1
    assert engine.calls[0]["time"] <= evidence_svc.calls[0]["time"]


def test_9_stage_2_executes_before_stage_3() -> None:
    """Test 9: Stage 2 (Evidence Engine) executes strictly before Stage 3 (AI Boardroom)."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    service.analyze(AnalysisRequest(question="Test sequence?"))

    assert len(evidence_svc.calls) == 1
    assert len(reasoning_svc.calls) == 1
    assert evidence_svc.calls[0]["time"] <= reasoning_svc.calls[0]["time"]


def test_10_stage_3_receives_exact_decision_model_from_stage_1() -> None:
    """Test 10: Stage 3 receives the exact DecisionModel object produced by Stage 1."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    service.analyze(AnalysisRequest(question="Test exact model passing?"))

    assert reasoning_svc.calls[0]["decision_model"] is dm


def test_11_stage_3_receives_exact_evidence_package_from_stage_2() -> None:
    """Test 11: Stage 3 receives the exact EvidencePackage object produced by Stage 2."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    service.analyze(AnalysisRequest(question="Test exact package passing?"))

    assert reasoning_svc.calls[0]["evidence_package"] is ep


def test_12_same_effective_deadline_passed_to_all_three_stages() -> None:
    """Test 12: The exact same effective_deadline is passed to all three stages."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    explicit_deadline = time.monotonic() + 99.0
    service.analyze(AnalysisRequest(question="Test deadline propagation?"), deadline_monotonic=explicit_deadline)

    assert engine.calls[0]["deadline"] == explicit_deadline
    assert evidence_svc.calls[0]["deadline"] == explicit_deadline
    assert reasoning_svc.calls[0]["deadline"] == explicit_deadline


def test_13_completed_response_includes_all_three_artifacts() -> None:
    """Test 13: Completed AnalysisResponse includes DecisionModel, EvidencePackage, and ReasoningBoard."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )
    resp = service.analyze(AnalysisRequest(question="Test all three artifacts?"))

    assert resp.decision_model is dm
    assert resp.evidence_package is ep
    assert resp.reasoning_board is board
    assert resp.status == "completed"


def test_14_stage_3_not_called_if_stage_1_fails() -> None:
    """Test 14: Stage 3 is not called if Stage 1 (Decision Framer) fails."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    class FailingEngine(QuestionUnderstandingEngine):
        def deconstruct(self, *args, **kwargs) -> DecisionModel:
            raise LLMError("Stage 1 LLM failure")

    reasoning_svc = SpyReasoningService(board=board)
    service = AnalysisService(
        engine=FailingEngine(llm_client=FakeLLMClient()),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=reasoning_svc,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test stage 1 failure?"))

    assert exc_info.value.status_code == 502
    assert len(reasoning_svc.calls) == 0


def test_15_stage_3_not_called_if_stage_2_fails() -> None:
    """Test 15: Stage 3 is not called if Stage 2 (Evidence Engine) fails."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    class FailingEvidenceService(EvidenceService):
        def build_evidence_package(self, *args, **kwargs) -> EvidencePackage:
            raise EvidenceServiceError("Stage 2 evidence retrieval failure")

    reasoning_svc = SpyReasoningService(board=board)
    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=FailingEvidenceService(None, None, None, None, None),  # type: ignore
        reasoning_service=reasoning_svc,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test stage 2 failure?"))

    assert exc_info.value.status_code == 502
    assert len(reasoning_svc.calls) == 0


def test_16_response_not_returned_if_stage_3_fails() -> None:
    """Test 16: Response is NOT returned if Stage 3 fails (fail-closed, no partial success)."""
    dm, ep, _, _, _ = build_test_artifacts()

    class FailingReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            raise ReasoningServiceError("Stage 3 boardroom deliberation failed", stage="perspectives")

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=FailingReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test fail-closed stage 3?"))

    assert exc_info.value.status_code == 502


# ------------------------------------------------------------------------------
# 4. Section 20: Deadline & Budget Tests (17–22)
# ------------------------------------------------------------------------------

def test_17_expired_deadline_before_stage_1_raises_504(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 17: Expired monotonic deadline before Stage 1 maps to HTTP 504 and Stage 1 is not called."""
    dm, ep, _, _, _ = build_test_artifacts()
    engine = SpyQuestionUnderstandingEngine(dm=dm)
    service = AnalysisService(
        engine=engine,
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=SpyReasoningService(board=_create_canonical_board(dm, ep)),
    )

    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test expired deadline?"), deadline_monotonic=expired_deadline)

    assert exc_info.value.status_code == 504
    assert len(engine.calls) == 0


def test_18_deadline_expires_between_stage_1_and_2_aborts_stage_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 18: Monotonic deadline expiring between Stage 1 and Stage 2 aborts Stage 2."""
    dm, ep, _, _, _ = build_test_artifacts()
    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=_create_canonical_board(dm, ep))

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )

    base_time = 1000.0
    current_time = base_time

    def fake_monotonic() -> float:
        return current_time

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    effective_deadline = base_time + 120.0

    # Advance clock past deadline inside stage 1 execution
    def stage_1_deconstruct(*args, **kwargs) -> DecisionModel:
        nonlocal current_time
        current_time = base_time + 125.0  # Expired
        return dm

    engine.deconstruct = stage_1_deconstruct  # type: ignore

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test deadline expire stage 1/2?"), deadline_monotonic=effective_deadline)

    assert exc_info.value.status_code == 504
    assert len(evidence_svc.calls) == 0
    assert len(reasoning_svc.calls) == 0


def test_19_deadline_expires_between_stage_2_and_3_aborts_stage_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 19: Monotonic deadline expiring between Stage 2 and Stage 3 aborts Stage 3."""
    dm, ep, _, _, _ = build_test_artifacts()
    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=_create_canonical_board(dm, ep))

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
    )

    base_time = 2000.0
    current_time = base_time

    def fake_monotonic() -> float:
        return current_time

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    effective_deadline = base_time + 120.0

    # Advance clock past deadline inside stage 2 execution
    def stage_2_build(*args, **kwargs) -> EvidencePackage:
        nonlocal current_time
        current_time = base_time + 121.0  # Expired
        return ep

    evidence_svc.build_evidence_package = stage_2_build  # type: ignore

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test deadline expire stage 2/3?"), deadline_monotonic=effective_deadline)

    assert exc_info.value.status_code == 504
    assert len(reasoning_svc.calls) == 0


def test_20_stage_3_receives_remaining_parent_budget_not_fresh_budget() -> None:
    """Test 20: Stage 3 receives the shared parent absolute deadline, not a fresh 120-second budget."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)

    engine = SpyQuestionUnderstandingEngine(dm=dm)
    evidence_svc = SpyEvidenceService(ep=ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=engine,
        evidence_service=evidence_svc,
        reasoning_service=reasoning_svc,
        analysis_timeout_seconds=120.0,
    )

    t0 = time.monotonic()
    parent_deadline = t0 + 120.0
    service.analyze(AnalysisRequest(question="Budget sharing test?"), deadline_monotonic=parent_deadline)

    # Stage 3 must receive parent_deadline, not a fresh t_stage3 + 120.0
    assert reasoning_svc.calls[0]["deadline"] == parent_deadline


def test_21_analysis_service_canonical_120_seconds_timeout_unchanged() -> None:
    """Test 21: AnalysisService canonical timeout defaults to 120.0 seconds."""
    service = AnalysisService()
    assert service.analysis_timeout_seconds == 120.0
    assert getattr(settings, "ANALYSIS_TIMEOUT_SECONDS", 120.0) == 120.0


def test_22_no_boardroom_specific_timeout_extension_exists() -> None:
    """Test 22: AnalysisService does not grant Boardroom its own independent or extended budget."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)
    reasoning_svc = SpyReasoningService(board=board)

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=reasoning_svc,
    )

    t_start = time.monotonic()
    service.analyze(AnalysisRequest(question="Check no extension?"))

    passed_deadline = reasoning_svc.calls[0]["deadline"]
    # The deadline passed to Stage 3 cannot exceed t_start + 120.0 + epsilon
    assert passed_deadline <= t_start + 120.5


# ------------------------------------------------------------------------------
# 5. Section 21: Error Mapping & Precedence Tests (23–32)
# ------------------------------------------------------------------------------

def test_23_boardroom_llm_timeout_cause_maps_to_504() -> None:
    """Test 23: LLMTimeoutError in nested cause chain maps to HTTP 504."""
    dm, ep, _, _, _ = build_test_artifacts()

    class TimeoutReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            timeout_err = LLMTimeoutError("Vertex call timed out after 60s")
            eval_err = ReasoningEvaluationError("Perspective evaluation failed")
            eval_err.__cause__ = timeout_err
            orch_err = ReasoningOrchestrationError("Orchestrator failed")
            orch_err.__cause__ = eval_err
            svc_err = ReasoningServiceError("Boardroom service failed", stage="perspectives")
            svc_err.__cause__ = orch_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=TimeoutReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test nested timeout?"))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail


def test_24_boardroom_reasoning_deadline_timeout_maps_to_504() -> None:
    """Test 24: Reasoning service deadline timeout maps to HTTP 504."""
    dm, ep, _, _, _ = build_test_artifacts()

    class DeadlineReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            raise ReasoningServiceError(
                "Reasoning service timed out: deadline expired before perspective stage.",
                stage="perspectives",
            )

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=DeadlineReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test direct reasoning timeout?"))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail


def test_25_boardroom_llm_auth_error_cause_maps_to_503() -> None:
    """Test 25: LLMAuthenticationError in cause chain maps to HTTP 503."""
    dm, ep, _, _, _ = build_test_artifacts()

    class AuthReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            auth_err = LLMAuthenticationError("Google ADC credentials invalid")
            svc_err = ReasoningServiceError("Boardroom deliberation failed")
            svc_err.__cause__ = auth_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=AuthReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test auth error?"))

    assert exc_info.value.status_code == 503
    assert "authentication failed" in exc_info.value.detail


def test_26_boardroom_llm_rate_limit_cause_maps_to_429() -> None:
    """Test 26: LLMRateLimitError in cause chain maps to HTTP 429."""
    dm, ep, _, _, _ = build_test_artifacts()

    class RateLimitReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            rate_err = LLMRateLimitError("ResourceExhausted: 429 quota exceeded")
            eval_err = ReasoningEvaluationError("Perspective evaluation failed")
            eval_err.__cause__ = rate_err
            svc_err = ReasoningServiceError("Boardroom deliberation failed")
            svc_err.__cause__ = eval_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=RateLimitReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test rate limit?"))

    assert exc_info.value.status_code == 429
    assert "rate limit or quota exceeded" in exc_info.value.detail


def test_27_boardroom_llm_response_validation_cause_maps_to_502() -> None:
    """Test 27: LLMResponseValidationError in cause chain maps to HTTP 502."""
    dm, ep, _, _, _ = build_test_artifacts()

    class ValidationReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            val_err = LLMResponseValidationError("Missing required candidate fields")
            svc_err = ReasoningServiceError("Perspective generation failed")
            svc_err.__cause__ = val_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=ValidationReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test response validation error?"))

    assert exc_info.value.status_code == 502
    assert "unparseable response structure" in exc_info.value.detail


def test_28_boardroom_llm_provider_error_cause_maps_to_502() -> None:
    """Test 28: LLMProviderError in cause chain maps to HTTP 502."""
    dm, ep, _, _, _ = build_test_artifacts()

    class ProviderErrorReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            prov_err = LLMProviderError("500 Internal error from Gemini model backend")
            svc_err = ReasoningServiceError("Perspective generation failed")
            svc_err.__cause__ = prov_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=ProviderErrorReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test provider error?"))

    assert exc_info.value.status_code == 502
    assert "Upstream decision intelligence provider error" in exc_info.value.detail


def test_29_boardroom_reasoning_validation_error_maps_to_502() -> None:
    """Test 29: ReasoningValidationError maps to HTTP 502."""
    dm, ep, _, _, _ = build_test_artifacts()

    class GroundingFailReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            val_err = ReasoningValidationError("Candidate cited non-existent assumption ID asm_hallucinated")
            svc_err = ReasoningServiceError("Boardroom grounding validation failed", stage="validation")
            svc_err.__cause__ = val_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=GroundingFailReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test reasoning validation error?"))

    assert exc_info.value.status_code == 502
    assert "Reasoning validation failed" in exc_info.value.detail


def test_30_boardroom_reasoning_prompt_error_maps_to_502() -> None:
    """Test 30: ReasoningPromptError maps to HTTP 502."""
    dm, ep, _, _, _ = build_test_artifacts()

    class PromptFailReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            prompt_err = ReasoningPromptError("Synthesis prompt length exceeded maximum 20000 characters")
            svc_err = ReasoningServiceError("Boardroom synthesis prompt failed", stage="synthesis")
            svc_err.__cause__ = prompt_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=PromptFailReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test reasoning prompt error?"))

    assert exc_info.value.status_code == 502
    assert "Reasoning prompt construction failed" in exc_info.value.detail


def test_31_boardroom_generic_reasoning_service_error_maps_to_502() -> None:
    """Test 31: Generic ReasoningServiceError without recognized root cause maps to HTTP 502."""
    dm, ep, _, _, _ = build_test_artifacts()

    class GenericFailReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            raise ReasoningServiceError("Internal boardroom orchestration pipeline breakdown")

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=GenericFailReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test generic reasoning error?"))

    assert exc_info.value.status_code == 502
    assert "pipeline failure" in exc_info.value.detail


def test_32_boardroom_unexpected_exception_maps_to_500() -> None:
    """Test 32: Unexpected exception in boardroom stage maps to safe HTTP 500."""
    dm, ep, _, _, _ = build_test_artifacts()

    class CrashReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            raise MemoryError("Fatal memory corruption in thread pool")

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=CrashReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test unexpected error?"))

    assert exc_info.value.status_code == 500
    assert "unexpected internal error" in exc_info.value.detail


# ------------------------------------------------------------------------------
# 6. Section 22: Security & Sanitization Tests
# ------------------------------------------------------------------------------

SECRET_MARKER = "AURA_REASONING_SECRET_SHOULD_NOT_LEAK_9F31"


def test_security_secret_marker_not_leaked_in_boardroom_provider_error(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies SECRET_MARKER inside provider error is redacted from HTTP response and logs."""
    dm, ep, _, _, _ = build_test_artifacts()

    class LeakyProviderReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            prov_err = LLMProviderError(f"500 Internal error: payload {SECRET_MARKER} rejected")
            svc_err = ReasoningServiceError("Deliberation failed")
            svc_err.__cause__ = prov_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=LeakyProviderReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test secret leakage in provider error?"))

    assert exc_info.value.status_code == 502
    assert SECRET_MARKER not in exc_info.value.detail
    assert SECRET_MARKER not in caplog.text


def test_security_secret_marker_not_leaked_in_boardroom_validation_error(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies SECRET_MARKER inside reasoning validation error is redacted from HTTP response and logs."""
    dm, ep, _, _, _ = build_test_artifacts()

    class LeakyValidationReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            val_err = ReasoningValidationError(f"Invalid reference containing {SECRET_MARKER}")
            svc_err = ReasoningServiceError("Grounding failed")
            svc_err.__cause__ = val_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=LeakyValidationReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test secret leakage in validation error?"))

    assert exc_info.value.status_code == 502
    assert SECRET_MARKER not in exc_info.value.detail
    assert SECRET_MARKER not in caplog.text


def test_security_secret_marker_not_leaked_in_boardroom_unexpected_error(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies SECRET_MARKER inside unexpected exception is redacted from HTTP response and logs."""
    dm, ep, _, _, _ = build_test_artifacts()

    class LeakyCrashReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            raise RuntimeError(f"Low-level dump contains {SECRET_MARKER}")

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=LeakyCrashReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test secret leakage in crash?"))

    assert exc_info.value.status_code == 500
    assert SECRET_MARKER not in exc_info.value.detail
    assert SECRET_MARKER not in caplog.text


def test_security_boardroom_validation_error_diagnostic_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies structured diagnostic log for ReasoningValidationError contains type, stage, location, field, rule."""
    dm, ep, _, _, _ = build_test_artifacts()

    class DiagnosticValidationReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            val_err = ReasoningValidationError(
                "Candidate cited non-existent disagreement ID 'dis_fake_999'",
                details={
                    "location": "synthesizer.validate_candidate_synthesis",
                    "field": "candidate.disagreement_ids",
                    "rule": "nonexistent_disagreement_id",
                    "invalid_id": "dis_fake_999",
                },
            )
            svc_err = ReasoningServiceError("Synthesis validation failed", stage="synthesis")
            svc_err.__cause__ = val_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=DiagnosticValidationReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test structured diagnostic log?"))

    assert exc_info.value.status_code == 502
    assert "Reasoning validation failed during boardroom deliberation." in exc_info.value.detail
    # Verify structured fields in logger output
    assert "reasoning validation failed: type=ReasoningValidationError" in caplog.text
    assert "stage=synthesis" in caplog.text
    assert "location=synthesizer.validate_candidate_synthesis" in caplog.text
    assert "field=candidate.disagreement_ids" in caplog.text
    assert "rule=nonexistent_disagreement_id" in caplog.text
    assert "'invalid_id': 'dis_fake_999'" in caplog.text


def test_security_boardroom_validation_error_diagnostic_redacts_credentials(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies credentials and secret markers in details are redacted in logger output."""
    dm, ep, _, _, _ = build_test_artifacts()

    class SecretDetailValidationReasoningService(ReasoningService):
        def build_reasoning_board(self, *args, **kwargs) -> ReasoningBoard:
            val_err = ReasoningValidationError(
                f"Candidate leaked secret: {SECRET_MARKER}",
                details={
                    "api_key": "AIzaSyFakeKey1234567890",
                    "token": "Bearer secret_token_value",
                    "secret_data": SECRET_MARKER,
                },
            )
            svc_err = ReasoningServiceError("Validation failed", stage="validation")
            svc_err.__cause__ = val_err
            raise svc_err

    service = AnalysisService(
        engine=SpyQuestionUnderstandingEngine(dm=dm),
        evidence_service=SpyEvidenceService(ep=ep),
        reasoning_service=SecretDetailValidationReasoningService(None, None),  # type: ignore
    )

    with pytest.raises(HTTPException):
        service.analyze(AnalysisRequest(question="Test secret redaction in details?"))

    assert SECRET_MARKER not in caplog.text
    assert "AIzaSy" not in caplog.text
    assert "secret_token_value" not in caplog.text
    assert "[REDACTED]" in caplog.text


# ------------------------------------------------------------------------------
# 7. Section 26: Architecture Exclusions Tests
# ------------------------------------------------------------------------------

def test_architecture_exclusions_no_future_engines_or_voting() -> None:
    """Proves Phase 4.8 integration introduced no future engines, recommendations, or voting mechanisms."""
    dm, ep, _, _, _ = build_test_artifacts()
    board = _create_canonical_board(dm, ep)
    response = AnalysisResponse(
        analysis_id="test_id_arch",
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=board,
    )

    # 1. AnalysisResponse has NO future engine fields beyond Day 5 recommendation
    assert not hasattr(response, "scenario_analysis")
    assert not hasattr(response, "resilience")
    assert not hasattr(response, "what_if")

    # 2. ReasoningBoard has NO voting, majority, or scoring fields
    assert not hasattr(board, "votes")
    assert not hasattr(board, "vote_tally")
    assert not hasattr(board, "majority_opinion")
    assert not hasattr(board, "minority_opinion")
    assert not hasattr(board, "consensus_score")
    assert not hasattr(board, "alignment_score")
    assert not hasattr(board, "confidence_percentage")

    # 3. BoardSynthesis has NO recommendation or verdict
    assert not hasattr(board.synthesis, "recommendation")
    assert not hasattr(board.synthesis, "verdict")
    assert not hasattr(board.synthesis, "confidence_score")


# ------------------------------------------------------------------------------
# 8. Phase 4.9 Architectural Audit Verification Tests
# ------------------------------------------------------------------------------

def test_audit_exception_cause_cycle_safety() -> None:
    """Audit 4.1: Proves cyclic __cause__ and __context__ chains terminate safely without infinite recursion."""
    err1 = ReasoningServiceError("First error")
    err2 = ReasoningOrchestrationError("Second error")
    # Form cycle: err1 -> err2 -> err1
    err1.__cause__ = err2
    err2.__cause__ = err1

    from app.services.analysis_service import _find_cause_instance, _is_timeout_error
    # Traversal must terminate safely and return None without hanging
    result = _find_cause_instance(err1, LLMTimeoutError)
    assert result is None

    is_timeout = _is_timeout_error(err1)
    assert is_timeout is False


def test_audit_constructor_fallback_reuses_injected_llm_client() -> None:
    """Audit 1.1: Proves direct AnalysisService construction reuses injected engine.llm_client without creating a second Gemini client."""
    fake_client = FakeLLMClient()
    engine = QuestionUnderstandingEngine(llm_client=fake_client)

    # Instantiate AnalysisService with only engine; reasoning_service and evidence_service are None
    service = AnalysisService(engine=engine)

    # Verify fallback construction wired reasoning_service using the SAME client
    assert service.reasoning_service is not None
    assert service.reasoning_service.orchestrator.reasoner.llm_client is fake_client
    assert service.reasoning_service.synthesizer.llm_client is fake_client
    assert service.evidence_service.requirement_engine.llm_client is fake_client


def test_audit_fake_llm_client_grounding_and_thread_safety() -> None:
    """Audit 2.1: Proves FakeLLMClient output contains no fabricated references and is thread-safe under concurrency."""
    import concurrent.futures
    from app.schemas.reasoning import CandidateBoardSynthesis, CandidatePerspectiveAnalysis

    fake = FakeLLMClient()

    # Verify CandidatePerspectiveAnalysis has no hallucinated IDs
    cand_persp = fake.generate_structured(
        prompt="Analyze growth",
        response_schema=CandidatePerspectiveAnalysis,
        system_instruction="You are analyzing growth perspective.",
    )
    assert cand_persp.perspective_type == PerspectiveType.GROWTH
    assert cand_persp.arguments == []
    assert cand_persp.critical_assumption_ids == []
    assert cand_persp.evidence_gap_ids == []

    # Verify CandidateBoardSynthesis has no hallucinated IDs
    cand_synth = fake.generate_structured(
        prompt="Synthesize board",
        response_schema=CandidateBoardSynthesis,
        system_instruction="Synthesize board.",
    )
    assert cand_synth.disagreement_ids == []
    assert cand_synth.critical_assumption_ids == []
    assert cand_synth.critical_evidence_gap_ids == []

    # Test thread safety under concurrent calls
    def call_fake(i: int) -> Any:
        return fake.generate_structured(
            prompt=f"Prompt {i}",
            response_schema=CandidateBoardSynthesis,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call_fake, range(30)))

    assert len(results) == 30
    assert len(fake.call_history) == 32  # 2 + 30 calls


def test_audit_upstream_artifacts_remain_unmodified_during_deliberation() -> None:
    """Audit 5.1: Proves DecisionModel and EvidencePackage remain completely immutable throughout deliberation."""
    dm, ep, _, _, _ = build_test_artifacts()
    dm_before = dm.model_dump()
    ep_before = ep.model_dump()

    fake = FakeLLMClient()
    svc = ReasoningService.create_default(llm_client=fake)
    board = svc.build_reasoning_board(decision_model=dm, evidence_package=ep)

    assert board.decision_model_id == dm.id
    assert board.evidence_package_id == ep.id

    # Verify upstream models were not mutated in place
    assert dm.model_dump() == dm_before
    assert ep.model_dump() == ep_before
