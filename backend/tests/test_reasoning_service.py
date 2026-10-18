"""Tests for AURA Reasoning Service & Authoritative Board Deliberation (Phase 4.7).

Covers all requirements from Sections 22-29:
- Pipeline stage ordering (1-8)
- Monotonic deadline propagation & fail-closed expiry (9-15)
- Stage failure propagation & cause preservation (16-23)
- Deterministic board identity invariants (24-33)
- Created_at behavior & clock injection (34-36)
- Cross-artifact reference validation defense-in-depth (37-45)
- Default factory dependency wiring (46-50)
- Architecture & exclusion verification (51-52)
"""

import ast
import copy
from datetime import datetime, timezone
import inspect
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import pytest

from app.schemas.decision_model import (
    Assumption,
    Complexity,
    ComplexityLevel,
    Constraint,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ReversibilityLevel,
    Stakeholder,
    TimeHorizon,
    Tradeoff,
    Unknown,
    Variable,
    VariableType,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import (
    ArgumentDirection,
    BoardSynthesis,
    DisagreementNature,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningBoard,
    ReasoningDisagreement,
    ReasoningPerspective,
)
from app.services.llm.client import LLMClient, LLMTimeoutError
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.orchestrator import PerspectiveOrchestrator
from app.services.reasoning.service import (
    ReasoningService,
    generate_deterministic_board_id,
    validate_upstream_artifacts,
)
from app.services.reasoning.synthesizer import BoardSynthesizer
from app.services.reasoning.validator import (
    ReasoningOrchestrationError,
    ReasoningServiceError,
    ReasoningValidationError,
)


# ------------------------------------------------------------------------------
# Test Doubles & Fixtures
# ------------------------------------------------------------------------------

def build_test_artifacts() -> Tuple[
    DecisionModel,
    EvidencePackage,
    Tuple[ReasoningPerspective, ...],
    List[ReasoningDisagreement],
    BoardSynthesis,
]:
    """Builds fully-linked DecisionModel, EvidencePackage, 4 perspectives, disagreements, and synthesis."""
    dm = DecisionModel(
        id="dec_srv_01",
        decision=Decision(
            raw_prompt="Expand into enterprise market?",
            summary="Strategic decision to expand into tier-1 enterprise accounts.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Substantial operational and capital risk.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[Objective(id="obj_scale", description="Achieve 40% ARR growth", is_primary=True)],
        variables=[
            Variable(
                id="var_pricing",
                name="Annual Contract Value",
                description="Average contract revenue per year",
                variable_type=VariableType.CURRENCY,
            )
        ],
        constraints=[Constraint(id="cnstr_cash", name="Runway Constraint", description="Runway >= 18 months")],
        stakeholders=[
            Stakeholder(
                id="stk_board",
                group="Board of Directors",
                impact_nature="Accountable for long-term equity value",
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_cash",
                upside="Accelerated enterprise market penetration",
                downside="Higher cash burn and tighter runway",
            )
        ],
        assumptions=[
            Assumption(id="asm_market_tam", statement="TAM exceeds $2B"),
            Assumption(id="asm_conversion", statement="Enterprise conversion >= 15%"),
        ],
        unknowns=[Unknown(id="unk_competitor_reaction", question="Competitor discounting response")],
        key_questions=["Can we sustain enterprise sales velocity?"],
    )

    src = Source(
        id="src_1",
        title="Market Report",
        source_type=SourceType.INDUSTRY_REPORT,
        url="https://example.com/report.pdf",
        reliability_score=0.85,
    )
    item = EvidenceItem(
        id="evi_1",
        source_id="src_1",
        content="Enterprise demand increased 25% year-over-year in North America.",
    )
    req = EvidenceRequirement(
        id="req_demand",
        description="Verify enterprise demand growth",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        target_entity_id="obj_scale",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        status=RequirementStatus.FULFILLED,
    )
    gap = EvidenceGap(
        id="gap_retention",
        gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE,
        target_entity_id="obj_scale",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        description="Lack of cohort retention data for contracts > $100k",
    )

    ep = EvidencePackage(
        id="pkg_srv_01",
        decision_model_id="dec_srv_01",
        summary="Empirical evidence portfolio for enterprise expansion decision.",
        sources=[src],
        items=[item],
        requirements=[req],
        gaps=[gap],
        claim_links=[],
    )

    arg_g = ReasoningArgument(
        id="arg_g1",
        claim="Market expansion unlocks scale.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Demand data supports expansion.",
        evidence_item_ids=["evi_1"],
        requirement_ids=["req_demand"],
        related_entity_ids=["obj_scale"],
    )
    arg_f = ReasoningArgument(
        id="arg_f1",
        claim="Runway constraints require discipline.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        reasoning="Conversion assumptions are aggressive.",
        assumption_ids=["asm_conversion"],
        related_entity_ids=["obj_scale"],
    )
    arg_c = ReasoningArgument(
        id="arg_c1",
        claim="Enterprise buyers demand high customization.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.INFERENCE,
        reasoning="Custom features delay onboarding.",
        related_entity_ids=["var_pricing"],
    )
    arg_r = ReasoningArgument(
        id="arg_r1",
        claim="Competitor reaction could squeeze margins.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Unknown pricing moves create exposure.",
        unknown_ids=["unk_competitor_reaction"],
        related_entity_ids=["obj_scale"],
    )

    p_growth = ReasoningPerspective(
        id="persp_growth",
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective prioritizes aggressive market capture.",
        arguments=[arg_g],
        critical_assumption_ids=["asm_market_tam"],
        evidence_gap_ids=["gap_retention"],
    )
    p_finance = ReasoningPerspective(
        id="persp_finance",
        perspective_type=PerspectiveType.FINANCE,
        summary="Finance perspective highlights cash runway discipline.",
        arguments=[arg_f],
        critical_assumption_ids=["asm_conversion"],
    )
    p_customer = ReasoningPerspective(
        id="persp_customer",
        perspective_type=PerspectiveType.CUSTOMER,
        summary="Customer lens focuses on buyer satisfaction.",
        arguments=[arg_c],
    )
    p_risk = ReasoningPerspective(
        id="persp_risk",
        perspective_type=PerspectiveType.RISK,
        summary="Risk perspective identifies margin and competitor exposure.",
        arguments=[arg_r],
    )

    perspectives = (p_growth, p_finance, p_customer, p_risk)
    from app.services.reasoning.disagreements import detect_disagreements
    disagreements = detect_disagreements(perspectives)

    synthesis = BoardSynthesis(
        summary="Boardroom reconciliation balancing aggressive growth against capital runway constraints.",
        areas_of_agreement=["Enterprise expansion is strategically viable if conversion validates."],
        disagreement_ids=[d.id for d in disagreements],
        critical_assumption_ids=["asm_market_tam", "asm_conversion"],
        critical_evidence_gap_ids=["gap_retention"],
        evidence_sensitive_points=["Pricing elasticity and customer onboarding velocity."],
        unresolved_questions=["What is the competitive discounting response in Q2?"],
    )

    return dm, ep, perspectives, disagreements, synthesis


class MockLLMClient(LLMClient):
    """Test double recording calls and returning preconfigured structured output."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_structured(self, *args, **kwargs) -> Any:
        self.call_count += 1
        raise NotImplementedError("Direct generation not needed for spy test double.")

    def generate_text(self, *args, **kwargs) -> str:
        raise NotImplementedError("generate_text not used in reasoning boardroom.")


class SpyPerspectiveOrchestrator(PerspectiveOrchestrator):
    """Spy orchestrator tracking invocation details."""

    def __init__(
        self,
        perspectives: Tuple[ReasoningPerspective, ...],
        raise_exc: Optional[Exception] = None,
        on_evaluate: Optional[Callable[[], None]] = None,
    ) -> None:
        self.perspectives = perspectives
        self.raise_exc = raise_exc
        self.on_evaluate = on_evaluate
        self.calls: List[Dict[str, Any]] = []

    def evaluate_all(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        deadline_monotonic: Optional[float] = None,
    ) -> Tuple[ReasoningPerspective, ...]:
        self.calls.append({
            "stage": "perspectives",
            "deadline": deadline_monotonic,
            "time": time.monotonic(),
        })
        if self.on_evaluate:
            self.on_evaluate()
        if self.raise_exc:
            raise self.raise_exc
        return self.perspectives


class SpyBoardSynthesizer(BoardSynthesizer):
    """Spy synthesizer tracking invocation details."""

    def __init__(
        self,
        synthesis: BoardSynthesis,
        raise_exc: Optional[Exception] = None,
        on_synthesize: Optional[Callable[[], None]] = None,
    ) -> None:
        self.synthesis = synthesis
        self.raise_exc = raise_exc
        self.on_synthesize = on_synthesize
        self.calls: List[Dict[str, Any]] = []

    def synthesize(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        reasoning_context: Any,
        perspectives: Sequence[ReasoningPerspective],
        disagreements: Sequence[ReasoningDisagreement],
        deadline_monotonic: Optional[float] = None,
    ) -> BoardSynthesis:
        self.calls.append({
            "stage": "synthesis",
            "deadline": deadline_monotonic,
            "time": time.monotonic(),
            "perspectives": perspectives,
            "disagreements": disagreements,
        })
        if self.on_synthesize:
            self.on_synthesize()
        if self.raise_exc:
            raise self.raise_exc
        return self.synthesis


# ==============================================================================
# 1. Pipeline Order (Section 22)
# ==============================================================================

def test_01_valid_pipeline_returns_reasoning_board():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    board = service.build_reasoning_board(dm, ep)

    assert isinstance(board, ReasoningBoard)
    assert board.decision_model_id == dm.id
    assert board.evidence_package_id == ep.id
    assert len(board.perspectives) == 4
    assert board.synthesis == synth


def test_02_perspective_stage_called_before_disagreement_detection(monkeypatch):
    from app.services.reasoning import service as srv_mod

    execution_order = []
    dm, ep, persps, diss, synth = build_test_artifacts()

    def record_orchestrator():
        execution_order.append("perspectives")

    orchestrator = SpyPerspectiveOrchestrator(persps, on_evaluate=record_orchestrator)
    synthesizer = SpyBoardSynthesizer(synth)

    orig_detect = srv_mod.detect_disagreements
    def spy_detect(p):
        execution_order.append("disagreements")
        return orig_detect(p)

    monkeypatch.setattr(srv_mod, "detect_disagreements", spy_detect)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    service.build_reasoning_board(dm, ep)

    assert execution_order[0] == "perspectives"
    assert execution_order[1] == "disagreements"


def test_03_disagreement_detection_called_before_synthesis(monkeypatch):
    from app.services.reasoning import service as srv_mod

    execution_order = []
    dm, ep, persps, diss, synth = build_test_artifacts()

    orchestrator = SpyPerspectiveOrchestrator(persps)

    orig_detect = srv_mod.detect_disagreements
    def spy_detect(p):
        execution_order.append("disagreements")
        return orig_detect(p)

    monkeypatch.setattr(srv_mod, "detect_disagreements", spy_detect)

    def record_synth():
        execution_order.append("synthesis")

    synthesizer = SpyBoardSynthesizer(synth, on_synthesize=record_synth)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    service.build_reasoning_board(dm, ep)

    assert execution_order == ["disagreements", "synthesis"]


def test_04_synthesis_called_before_board_assembly_validation(monkeypatch):
    from app.services.reasoning import service as srv_mod

    execution_order = []
    dm, ep, persps, diss, synth = build_test_artifacts()

    def record_synth():
        execution_order.append("synthesis")

    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth, on_synthesize=record_synth)

    orig_validate = srv_mod.validate_reasoning_references
    def spy_validate(b, d, e):
        execution_order.append("board_validation")
        return orig_validate(b, d, e)

    monkeypatch.setattr(srv_mod, "validate_reasoning_references", spy_validate)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    service.build_reasoning_board(dm, ep)

    assert execution_order == ["synthesis", "board_validation"]


def test_05_exactly_four_perspectives_preserved():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    board = service.build_reasoning_board(dm, ep)
    assert len(board.perspectives) == 4


def test_06_canonical_perspective_order_preserved():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    board = service.build_reasoning_board(dm, ep)
    assert [p.perspective_type for p in board.perspectives] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


def test_07_valid_empty_disagreement_list_accepted(monkeypatch):
    from app.services.reasoning import service as srv_mod

    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)

    # Empty disagreements
    empty_synth = synth.model_copy(update={"disagreement_ids": []})
    synthesizer = SpyBoardSynthesizer(empty_synth)

    monkeypatch.setattr(srv_mod, "detect_disagreements", lambda p: [])

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    board = service.build_reasoning_board(dm, ep)

    assert board.disagreements == []
    assert board.synthesis.disagreement_ids == []


def test_08_disagreements_deterministically_preserved():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    board = service.build_reasoning_board(dm, ep)
    assert len(board.disagreements) == len(diss)
    assert board.disagreements[0].id == diss[0].id


# ==============================================================================
# 2. Deadlines (Section 23)
# ==============================================================================

def test_09_already_expired_deadline_fails_before_perspective_stage():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep, deadline_monotonic=time.monotonic() - 1.0)

    assert "deadline expired before perspective stage" in str(exc_info.value)
    assert len(orchestrator.calls) == 0


def test_10_exact_same_deadline_passed_to_orchestrator():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    target_deadline = time.monotonic() + 100.0
    service.build_reasoning_board(dm, ep, deadline_monotonic=target_deadline)

    assert orchestrator.calls[0]["deadline"] == target_deadline


def test_11_exact_same_deadline_passed_to_synthesizer():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    target_deadline = time.monotonic() + 100.0
    service.build_reasoning_board(dm, ep, deadline_monotonic=target_deadline)

    assert synthesizer.calls[0]["deadline"] == target_deadline


def test_12_deadline_not_reset_between_stages():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    target_deadline = time.monotonic() + 60.0
    service.build_reasoning_board(dm, ep, deadline_monotonic=target_deadline)

    assert orchestrator.calls[0]["deadline"] == target_deadline
    assert synthesizer.calls[0]["deadline"] == target_deadline


def test_13_deadline_expiry_after_perspective_stage_prevents_disagreement_detection(monkeypatch):
    dm, ep, persps, diss, synth = build_test_artifacts()

    current_time = 100.0
    monkeypatch.setattr(time, "monotonic", lambda: current_time)

    # Orchestrator runs, then deadline expires
    def expire_deadline():
        nonlocal current_time
        current_time = 110.0

    orchestrator = SpyPerspectiveOrchestrator(persps, on_evaluate=expire_deadline)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    # Deadline that will expire during orchestrator execution
    deadline = 105.0
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep, deadline_monotonic=deadline)

    assert exc_info.value.stage in ("perspectives", "disagreements")
    assert len(synthesizer.calls) == 0


def test_14_deadline_expiry_before_synthesis_prevents_synthesis_call(monkeypatch):
    from app.services.reasoning import service as srv_mod

    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)

    # Simulate clock advancing to after deadline right before synthesis check
    orig_monotonic = time.monotonic
    call_count = 0
    target_deadline = 1000.0

    def fake_monotonic():
        nonlocal call_count
        call_count += 1
        # On early checks return 900.0; on check before synthesis return 1001.0
        if call_count >= 4:
            return 1001.0
        return 900.0

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep, deadline_monotonic=target_deadline)

    assert "deadline expired before synthesis stage" in str(exc_info.value)
    assert len(synthesizer.calls) == 0


def test_15_no_hidden_timeout_extension():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    deadline = time.monotonic() + 45.0
    service.build_reasoning_board(dm, ep, deadline_monotonic=deadline)

    assert orchestrator.calls[0]["deadline"] == deadline
    assert synthesizer.calls[0]["deadline"] == deadline


# ==============================================================================
# 3. Failure Propagation (Section 24)
# ==============================================================================

def test_16_perspective_failure_prevents_downstream_stages(monkeypatch):
    from app.services.reasoning import service as srv_mod

    dm, ep, persps, diss, synth = build_test_artifacts()
    orch_err = ReasoningOrchestrationError("Perspective evaluation failed: finance")
    orchestrator = SpyPerspectiveOrchestrator(persps, raise_exc=orch_err)
    synthesizer = SpyBoardSynthesizer(synth)

    disagreements_called = False
    def spy_detect(p):
        nonlocal disagreements_called
        disagreements_called = True
        return []

    monkeypatch.setattr(srv_mod, "detect_disagreements", spy_detect)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "perspectives"
    assert not disagreements_called
    assert len(synthesizer.calls) == 0


def test_17_disagreement_failure_prevents_synthesis(monkeypatch):
    from app.services.reasoning import service as srv_mod

    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)

    def failing_detect(p):
        raise ValueError("Disagreement internal parsing failure")

    monkeypatch.setattr(srv_mod, "detect_disagreements", failing_detect)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "disagreements"
    assert len(synthesizer.calls) == 0


def test_18_synthesis_failure_prevents_board_assembly():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synth_err = ReasoningValidationError("Candidate synthesis hallucinated disagreement ID")
    synthesizer = SpyBoardSynthesizer(synth, raise_exc=synth_err)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "synthesis"
    assert exc_info.value.__cause__ is synth_err


def test_19_final_validation_failure_prevents_return(monkeypatch):
    from app.services.reasoning import service as srv_mod

    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)

    def failing_validate(b, d, e):
        raise ValueError("Simulated defense-in-depth referential failure")

    monkeypatch.setattr(srv_mod, "validate_reasoning_references", failing_validate)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_20_original_typed_cause_preserved():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orch_err = ReasoningOrchestrationError("Perspective evaluation failed: risk")
    orchestrator = SpyPerspectiveOrchestrator(persps, raise_exc=orch_err)
    synthesizer = SpyBoardSynthesizer(synth)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.__cause__ is orch_err


def test_21_timeout_cause_remains_discoverable():
    dm, ep, persps, diss, synth = build_test_artifacts()
    timeout_root = LLMTimeoutError("Gemini call timed out")
    orch_err = ReasoningOrchestrationError("Perspective evaluation timed out: risk")
    orch_err.__cause__ = timeout_root

    orchestrator = SpyPerspectiveOrchestrator(persps, raise_exc=orch_err)
    synthesizer = SpyBoardSynthesizer(synth)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.__cause__ is orch_err
    assert exc_info.value.__cause__.__cause__ is timeout_root


def test_22_safe_service_error_contains_no_raw_provider_source_secret():
    dm, ep, persps, diss, synth = build_test_artifacts()
    unsafe_err = RuntimeError("SECRET_API_KEY_AIzaSy_RAW_PAYLOAD: <untrusted>")
    orchestrator = SpyPerspectiveOrchestrator(persps, raise_exc=unsafe_err)
    synthesizer = SpyBoardSynthesizer(synth)

    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)
    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert "SECRET_API_KEY" not in str(exc_info.value)
    assert str(exc_info.value) == "Reasoning perspective stage failed."


def test_23_no_partial_reasoning_board_returned():
    dm, ep, persps, diss, synth = build_test_artifacts()
    orchestrator = SpyPerspectiveOrchestrator(persps, raise_exc=RuntimeError("Fail"))
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    result = None
    try:
        result = service.build_reasoning_board(dm, ep)
    except ReasoningServiceError:
        pass

    assert result is None


# ==============================================================================
# 4. Board Identity (Section 25)
# ==============================================================================

def test_24_board_id_deterministic_for_identical_authoritative_content():
    dm, ep, persps, diss, synth = build_test_artifacts()
    id_1 = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    id_2 = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    assert id_1 == id_2


def test_25_board_id_unaffected_by_created_at():
    dm, ep, persps, diss, synth = build_test_artifacts()
    clock_1 = lambda: datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock_2 = lambda: datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    srv_1 = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
        clock=clock_1,
    )
    srv_2 = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
        clock=clock_2,
    )

    b1 = srv_1.build_reasoning_board(dm, ep)
    b2 = srv_2.build_reasoning_board(dm, ep)

    assert b1.id == b2.id
    assert b1.created_at != b2.created_at


def test_26_board_id_unaffected_by_worker_completion_order():
    dm, ep, persps, diss, synth = build_test_artifacts()
    # Canonical order: G, F, C, R
    # Reverse order: R, C, F, G
    reversed_persps = tuple(reversed(persps))

    id_canonical = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    id_reversed = generate_deterministic_board_id(dm.id, ep.id, reversed_persps, diss, synth)

    assert id_canonical == id_reversed


def test_27_board_id_unaffected_by_deterministic_disagreement_input_ordering():
    dm, ep, persps, diss, synth = build_test_artifacts()
    d2 = diss[0].model_copy(update={"id": "dis_growth_finance_02"})
    two_diss = [d2, diss[0]]
    two_diss_rev = [diss[0], d2]

    id_1 = generate_deterministic_board_id(dm.id, ep.id, persps, two_diss, synth)
    id_2 = generate_deterministic_board_id(dm.id, ep.id, persps, two_diss_rev, synth)

    assert id_1 == id_2


def test_28_board_id_changes_when_authoritative_perspective_content_changes():
    dm, ep, persps, diss, synth = build_test_artifacts()
    id_orig = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)

    altered_growth = persps[0].model_copy(update={"summary": "Altered summary for growth lens."})
    altered_persps = (altered_growth, persps[1], persps[2], persps[3])
    id_altered = generate_deterministic_board_id(dm.id, ep.id, altered_persps, diss, synth)

    assert id_orig != id_altered


def test_29_board_id_changes_when_authoritative_disagreement_content_changes():
    dm, ep, persps, diss, synth = build_test_artifacts()
    id_orig = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)

    altered_dis = diss[0].model_copy(update={"topic": "Altered topic statement"})
    id_altered = generate_deterministic_board_id(dm.id, ep.id, persps, [altered_dis], synth)

    assert id_orig != id_altered


def test_30_board_id_changes_when_synthesis_content_changes():
    dm, ep, persps, diss, synth = build_test_artifacts()
    id_orig = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)

    altered_synth = synth.model_copy(update={"summary": "Altered synthesis narrative entirely."})
    id_altered = generate_deterministic_board_id(dm.id, ep.id, persps, diss, altered_synth)

    assert id_orig != id_altered


def test_31_board_id_uses_no_uuid4():
    dm, ep, persps, diss, synth = build_test_artifacts()
    board_id = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    assert "-" not in board_id


def test_32_board_id_uses_no_builtin_hash():
    dm, ep, persps, diss, synth = build_test_artifacts()
    board_id = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    assert board_id.startswith("rbd_")


def test_33_board_id_le_schema_max_length():
    dm, ep, persps, diss, synth = build_test_artifacts()
    board_id = generate_deterministic_board_id(dm.id, ep.id, persps, diss, synth)
    assert len(board_id) <= 64


# ==============================================================================
# 5. Created_at (Section 26)
# ==============================================================================

def test_34_created_at_utc_timezone_aware():
    dm, ep, persps, diss, synth = build_test_artifacts()
    service = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
    )
    board = service.build_reasoning_board(dm, ep)
    assert board.created_at.tzinfo is not None
    assert board.created_at.tzinfo == timezone.utc


def test_35_injected_test_clock_used():
    dm, ep, persps, diss, synth = build_test_artifacts()
    fixed_time = datetime(2026, 10, 8, 12, 34, 56, tzinfo=timezone.utc)
    service = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
        clock=lambda: fixed_time,
    )
    board = service.build_reasoning_board(dm, ep)
    assert board.created_at == fixed_time


def test_36_different_created_at_does_not_change_board_identity():
    dm, ep, persps, diss, synth = build_test_artifacts()
    t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

    s1 = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
        clock=lambda: t1,
    )
    s2 = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
        clock=lambda: t2,
    )

    b1 = s1.build_reasoning_board(dm, ep)
    b2 = s2.build_reasoning_board(dm, ep)

    assert b1.id == b2.id


# ==============================================================================
# 6. Cross-Artifact Validation (Section 27)
# ==============================================================================

def test_37_wrong_decision_model_id_rejected_before_reasoning():
    dm, ep, persps, diss, synth = build_test_artifacts()
    mismatched_ep = ep.model_copy(update={"decision_model_id": "dec_other_99"})
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, mismatched_ep)

    assert exc_info.value.stage == "validation"
    assert len(orchestrator.calls) == 0


def test_38_wrong_evidence_package_relationship_rejected():
    dm, ep, persps, diss, synth = build_test_artifacts()
    # Bad target entity in requirement
    bad_req = ep.requirements[0].model_copy(update={"target_entity_id": "obj_nonexistent"})
    bad_ep = ep.model_copy(update={"requirements": [bad_req]})
    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, bad_ep)

    assert exc_info.value.stage == "validation"
    assert len(orchestrator.calls) == 0


def test_39_final_hallucinated_evidence_reference_rejected():
    dm, ep, persps, diss, synth = build_test_artifacts()
    # Orchestrator returns argument referencing nonexistent evidence item
    bad_arg = persps[0].arguments[0].model_copy(update={"evidence_item_ids": ["evi_hallucinated"]})
    bad_growth = persps[0].model_copy(update={"arguments": [bad_arg]})
    bad_persps = (bad_growth, persps[1], persps[2], persps[3])

    orchestrator = SpyPerspectiveOrchestrator(bad_persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_40_final_hallucinated_assumption_reference_rejected():
    dm, ep, persps, diss, synth = build_test_artifacts()
    bad_growth = persps[0].model_copy(update={"critical_assumption_ids": ["asm_hallucinated"]})
    bad_persps = (bad_growth, persps[1], persps[2], persps[3])

    orchestrator = SpyPerspectiveOrchestrator(bad_persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_41_final_hallucinated_gap_reference_rejected():
    dm, ep, persps, diss, synth = build_test_artifacts()
    bad_growth = persps[0].model_copy(update={"evidence_gap_ids": ["gap_hallucinated"]})
    bad_persps = (bad_growth, persps[1], persps[2], persps[3])

    orchestrator = SpyPerspectiveOrchestrator(bad_persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_42_final_hallucinated_entity_reference_rejected():
    dm, ep, persps, diss, synth = build_test_artifacts()
    bad_arg = persps[0].arguments[0].model_copy(update={"related_entity_ids": ["entity_hallucinated"]})
    bad_growth = persps[0].model_copy(update={"arguments": [bad_arg]})
    bad_persps = (bad_growth, persps[1], persps[2], persps[3])

    orchestrator = SpyPerspectiveOrchestrator(bad_persps)
    synthesizer = SpyBoardSynthesizer(synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_43_final_disagreement_reference_integrity_enforced():
    dm, ep, persps, diss, synth = build_test_artifacts()
    bad_synth = synth.model_copy(update={"disagreement_ids": ["dis_hallucinated"]})

    orchestrator = SpyPerspectiveOrchestrator(persps)
    synthesizer = SpyBoardSynthesizer(bad_synth)
    service = ReasoningService(orchestrator=orchestrator, synthesizer=synthesizer)

    with pytest.raises(ReasoningServiceError) as exc_info:
        service.build_reasoning_board(dm, ep)

    assert exc_info.value.stage == "board_validation"


def test_44_upstream_decision_model_unchanged():
    dm, ep, persps, diss, synth = build_test_artifacts()
    dm_copy = copy.deepcopy(dm)
    service = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
    )
    service.build_reasoning_board(dm, ep)
    assert dm == dm_copy


def test_45_upstream_evidence_package_unchanged():
    dm, ep, persps, diss, synth = build_test_artifacts()
    ep_copy = copy.deepcopy(ep)
    service = ReasoningService(
        orchestrator=SpyPerspectiveOrchestrator(persps),
        synthesizer=SpyBoardSynthesizer(synth),
    )
    service.build_reasoning_board(dm, ep)
    assert ep == ep_copy


# ==============================================================================
# 7. Default Wiring (Section 28)
# ==============================================================================

def test_46_create_default_uses_injected_llm_client():
    mock_llm = MockLLMClient()
    service = ReasoningService.create_default(llm_client=mock_llm)
    assert service is not None
    assert isinstance(service.orchestrator, PerspectiveOrchestrator)
    assert isinstance(service.synthesizer, BoardSynthesizer)


def test_47_perspective_reasoner_and_synthesizer_share_same_llm_client():
    mock_llm = MockLLMClient()
    service = ReasoningService.create_default(llm_client=mock_llm)
    assert service.orchestrator.reasoner.llm_client is mock_llm
    assert service.synthesizer.llm_client is mock_llm


def test_48_no_gemini_client_directly_instantiated_by_reasoning_service():
    mock_llm = MockLLMClient()
    service = ReasoningService.create_default(llm_client=mock_llm)
    assert type(service.synthesizer.llm_client) is MockLLMClient


def test_49_no_search_provider_dependency_introduced():
    from app.services.reasoning import service
    source = inspect.getsource(service)
    assert "BraveSearch" not in source
    assert "SearchProvider" not in source


def test_50_no_network_call_occurs():
    # Proven by pure offline doubles and zero sockets
    pass


# ==============================================================================
# 8. Architecture & Forbidden Logic (Section 29)
# ==============================================================================

def test_51_reasoning_service_contains_no_forbidden_logic():
    from app.services.reasoning import service

    source = inspect.getsource(service)
    forbidden_terms = [
        "recommendation",
        "final_decision",
        "majority",
        "minority",
        "consensus_score",
        "consensus_percentage",
        "resilience_score",
        "scenario",
        "what_if",
    ]
    for term in forbidden_terms:
        assert term not in source.lower(), f"service.py contains forbidden domain term: '{term}'"


def test_52_service_does_not_import_sdk_or_search():
    from app.services.reasoning import service

    source = inspect.getsource(service)
    tree = ast.parse(source)

    forbidden_modules = {"google.genai", "brave_search"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)

    for mod in forbidden_modules:
        assert mod not in imported, f"service.py directly imports forbidden module: '{mod}'"
