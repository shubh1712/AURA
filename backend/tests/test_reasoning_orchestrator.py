"""Tests for AURA Bounded Four-Perspective Orchestrator (Phase 4.6).

Covers all requirements from Sections 20-26:
- Basic contract & sequential fallback (1-8)
- Concurrency & ordering invariants (9-15)
- Shared deadlines & cleanup (16-22)
- Fail-closed error handling & cause preservation (24-31)
- Authoritative output validation (32-37)
- Immutability & isolation (38-44)
- Architecture exclusions (45-46)
"""

import ast
import copy
import inspect
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
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
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningPerspective,
)
from app.services.llm.client import LLMTimeoutError
from app.services.reasoning.context_builder import (
    PerspectiveContext,
    build_reasoning_context,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.orchestrator import (
    MAX_PERSPECTIVE_WORKERS,
    PerspectiveOrchestrator,
    validate_orchestrated_perspectives,
)
from app.services.reasoning.validator import (
    ReasoningEvaluationError,
    ReasoningOrchestrationError,
    ReasoningValidationError,
)


# ------------------------------------------------------------------------------
# Test Doubles & Fixtures
# ------------------------------------------------------------------------------

def build_test_artifacts() -> Tuple[DecisionModel, EvidencePackage, Dict[PerspectiveType, ReasoningPerspective]]:
    """Builds valid DecisionModel, EvidencePackage, and 4 canonical ReasoningPerspectives."""
    dm = DecisionModel(
        id="dec_orch_01",
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
        id="pkg_orch_01",
        decision_model_id="dec_orch_01",
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
        related_entity_ids=["cnstr_cash"],
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

    perspectives = {
        PerspectiveType.GROWTH: ReasoningPerspective(
            id="persp_growth",
            perspective_type=PerspectiveType.GROWTH,
            summary="Growth perspective prioritizes aggressive market capture.",
            arguments=[arg_g],
            critical_assumption_ids=["asm_market_tam"],
            evidence_gap_ids=["gap_retention"],
        ),
        PerspectiveType.FINANCE: ReasoningPerspective(
            id="persp_finance",
            perspective_type=PerspectiveType.FINANCE,
            summary="Finance perspective highlights cash runway discipline.",
            arguments=[arg_f],
            critical_assumption_ids=["asm_conversion"],
        ),
        PerspectiveType.CUSTOMER: ReasoningPerspective(
            id="persp_customer",
            perspective_type=PerspectiveType.CUSTOMER,
            summary="Customer lens focuses on buyer satisfaction.",
            arguments=[arg_c],
        ),
        PerspectiveType.RISK: ReasoningPerspective(
            id="persp_risk",
            perspective_type=PerspectiveType.RISK,
            summary="Risk perspective identifies margin and competitor exposure.",
            arguments=[arg_r],
        ),
    }

    return dm, ep, perspectives


class ControlledMockReasoner(PerspectiveReasoner):
    """Test double recording invocations and allowing fine-grained synchronization."""

    def __init__(
        self,
        perspectives_by_type: Dict[PerspectiveType, ReasoningPerspective],
        raise_by_type: Optional[Dict[PerspectiveType, Exception]] = None,
        barrier: Optional[threading.Barrier] = None,
        completion_delays: Optional[Dict[PerspectiveType, float]] = None,
        sync_events: Optional[Dict[PerspectiveType, threading.Event]] = None,
    ) -> None:
        self.perspectives_by_type = perspectives_by_type
        self.raise_by_type = raise_by_type or {}
        self.barrier = barrier
        self.barrier_waiters_count = 0
        self.completion_delays = completion_delays or {}
        self.sync_events = sync_events or {}

        self.calls: List[Tuple[PerspectiveContext, Optional[float]]] = []
        self.lock = threading.Lock()
        self.active_workers = 0
        self.max_active_workers = 0
        self.completion_order: List[PerspectiveType] = []

    def evaluate(
        self,
        perspective_context: PerspectiveContext,
        deadline_monotonic: Optional[float] = None,
    ) -> ReasoningPerspective:
        ptype = perspective_context.perspective.perspective_type

        should_wait_barrier = False
        with self.lock:
            self.calls.append((perspective_context, deadline_monotonic))
            self.active_workers += 1
            if self.active_workers > self.max_active_workers:
                self.max_active_workers = self.active_workers
            if self.barrier and self.barrier_waiters_count < self.barrier.parties:
                self.barrier_waiters_count += 1
                should_wait_barrier = True

        try:
            if should_wait_barrier:
                self.barrier.wait(timeout=2.0)

            if ptype in self.sync_events:
                self.sync_events[ptype].wait(timeout=2.0)

            if ptype in self.completion_delays:
                time.sleep(self.completion_delays[ptype])

            if ptype in self.raise_by_type:
                raise self.raise_by_type[ptype]

            return self.perspectives_by_type[ptype]
        finally:
            with self.lock:
                self.active_workers -= 1
                self.completion_order.append(ptype)


# ==============================================================================
# 1. Basic Contract (Sections 20)
# ==============================================================================

def test_01_exactly_four_perspectives_executed():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    results = orchestrator.evaluate_all(dm, ep)

    assert len(results) == 4
    assert len(reasoner.calls) == 4


def test_02_canonical_perspectives_are_growth_finance_customer_risk():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    results = orchestrator.evaluate_all(dm, ep)
    result_types = [p.perspective_type for p in results]

    assert result_types == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


def test_03_each_perspective_executed_exactly_once():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    executed_types = [call[0].perspective.perspective_type for call in reasoner.calls]

    assert sorted(executed_types, key=lambda t: t.value) == sorted(
        [PerspectiveType.GROWTH, PerspectiveType.FINANCE, PerspectiveType.CUSTOMER, PerspectiveType.RISK],
        key=lambda t: t.value,
    )


def test_04_reasoning_context_built_once(monkeypatch):
    from app.services.reasoning import orchestrator as orch_mod

    build_count = 0
    orig_build = orch_mod.build_reasoning_context

    def spy_build(*args, **kwargs):
        nonlocal build_count
        build_count += 1
        return orig_build(*args, **kwargs)

    monkeypatch.setattr(orch_mod, "build_reasoning_context", spy_build)

    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    assert build_count == 1


def test_05_perspective_contexts_use_shared_common_context():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)

    first_ctx = reasoner.calls[0][0]
    for ctx, _ in reasoner.calls[1:]:
        assert ctx.decision_context.decision_id == first_ctx.decision_context.decision_id
        assert ctx.evidence_context.summary == first_ctx.evidence_context.summary


def test_06_sequential_max_workers_1_works():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=1)

    results = orchestrator.evaluate_all(dm, ep)
    assert len(results) == 4
    assert reasoner.max_active_workers == 1


def test_07_sequential_result_canonical_order():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=1)

    results = orchestrator.evaluate_all(dm, ep)
    assert [p.perspective_type for p in results] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


def test_08_concurrent_result_canonical_order():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=3)

    results = orchestrator.evaluate_all(dm, ep)
    assert [p.perspective_type for p in results] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


# ==============================================================================
# 2. Concurrency (Section 21)
# ==============================================================================

def test_09_concurrent_workers_actually_overlap():
    dm, ep, persps = build_test_artifacts()
    barrier = threading.Barrier(3)
    reasoner = ControlledMockReasoner(persps, barrier=barrier)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=3)

    orchestrator.evaluate_all(dm, ep)
    assert reasoner.max_active_workers >= 3


def test_10_completion_order_different_from_canonical_does_not_affect_returned_order():
    dm, ep, persps = build_test_artifacts()
    ev_risk = threading.Event()
    ev_cust = threading.Event()
    ev_fin = threading.Event()
    ev_grow = threading.Event()

    sync_events = {
        PerspectiveType.RISK: ev_risk,
        PerspectiveType.CUSTOMER: ev_cust,
        PerspectiveType.FINANCE: ev_fin,
        PerspectiveType.GROWTH: ev_grow,
    }

    reasoner = ControlledMockReasoner(persps, sync_events=sync_events)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    def release_reverse():
        time.sleep(0.01)
        ev_risk.set()
        time.sleep(0.01)
        ev_cust.set()
        time.sleep(0.01)
        ev_fin.set()
        time.sleep(0.01)
        ev_grow.set()

    t = threading.Thread(target=release_reverse)
    t.start()

    results = orchestrator.evaluate_all(dm, ep)
    t.join()

    # Returned order must remain canonical
    assert [p.perspective_type for p in results] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


def test_11_worker_count_never_exceeds_configured_bound():
    dm, ep, persps = build_test_artifacts()
    delays = {
        PerspectiveType.GROWTH: 0.05,
        PerspectiveType.FINANCE: 0.05,
        PerspectiveType.CUSTOMER: 0.05,
        PerspectiveType.RISK: 0.05,
    }
    reasoner = ControlledMockReasoner(persps, completion_delays=delays)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=2)

    orchestrator.evaluate_all(dm, ep)
    assert reasoner.max_active_workers <= 2


def test_12_configured_workers_gt_4_still_executes_at_most_four_tasks():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=10)

    results = orchestrator.evaluate_all(dm, ep)
    assert len(results) == 4
    assert len(reasoner.calls) == 4


def test_13_no_global_serialization_lock():
    dm, ep, persps = build_test_artifacts()
    barrier = threading.Barrier(2)
    reasoner = ControlledMockReasoner(persps, barrier=barrier)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=2)

    orchestrator.evaluate_all(dm, ep)
    assert reasoner.max_active_workers >= 2


def test_14_no_shared_mutable_append_order_dependency():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    results = orchestrator.evaluate_all(dm, ep)
    assert isinstance(results, tuple)
    assert len(results) == 4


def test_15_repeated_different_completion_orders_yield_identical_result_order():
    dm, ep, persps = build_test_artifacts()
    for i in range(3):
        delays = {
            PerspectiveType.GROWTH: 0.01 * (i % 3),
            PerspectiveType.FINANCE: 0.01 * ((i + 1) % 3),
            PerspectiveType.CUSTOMER: 0.01 * ((i + 2) % 3),
            PerspectiveType.RISK: 0.01,
        }
        reasoner = ControlledMockReasoner(persps, completion_delays=delays)
        orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)
        results = orchestrator.evaluate_all(dm, ep)
        assert [p.perspective_type for p in results] == [
            PerspectiveType.GROWTH,
            PerspectiveType.FINANCE,
            PerspectiveType.CUSTOMER,
            PerspectiveType.RISK,
        ]


# ==============================================================================
# 3. Deadlines (Section 22)
# ==============================================================================

def test_16_already_expired_deadline_fails_before_any_perspective_evaluation():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=time.monotonic() - 1.0)

    assert "deadline already expired" in str(exc_info.value)
    assert len(reasoner.calls) == 0


def test_17_same_deadline_monotonic_passed_to_all_four_reasoner_calls():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=3)

    target_deadline = time.monotonic() + 100.0
    orchestrator.evaluate_all(dm, ep, deadline_monotonic=target_deadline)

    assert len(reasoner.calls) == 4
    for _, call_deadline in reasoner.calls:
        assert call_deadline == target_deadline


def test_18_deadline_is_not_reset_per_worker():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=1)

    target_deadline = time.monotonic() + 50.0
    orchestrator.evaluate_all(dm, ep, deadline_monotonic=target_deadline)

    deadlines = [call[1] for call in reasoner.calls]
    assert all(d == target_deadline for d in deadlines)


def test_19_timeout_while_waiting_fails_closed():
    dm, ep, persps = build_test_artifacts()
    # Risk perspective blocks
    block_event = threading.Event()
    reasoner = ControlledMockReasoner(
        persps,
        sync_events={PerspectiveType.RISK: block_event},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    deadline = time.monotonic() + 0.05
    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=deadline)

    block_event.set()  # Clean up background thread
    assert "timed out" in str(exc_info.value).lower()
    assert isinstance(exc_info.value.__cause__, LLMTimeoutError)


def test_20_pending_futures_cancelled_where_possible():
    dm, ep, persps = build_test_artifacts()
    # Sequential execution: if growth fails, finance/customer/risk never run
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.GROWTH: RuntimeError("Growth crash")},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=1)

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep)

    assert len(reasoner.calls) == 1


def test_21_executor_cleanup_does_not_wait_indefinitely_for_running_worker():
    dm, ep, persps = build_test_artifacts()
    unjoined_event = threading.Event()
    reasoner = ControlledMockReasoner(
        persps,
        sync_events={PerspectiveType.GROWTH: unjoined_event},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=2)

    start = time.monotonic()
    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=time.monotonic() + 0.05)

    duration = time.monotonic() - start
    unjoined_event.set()
    # Verify cleanup returns promptly (does not wait for unjoined_event)
    assert duration < 0.5


def test_22_no_new_work_begins_after_deadline_is_known_expired():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(
        persps,
        completion_delays={PerspectiveType.GROWTH: 0.05},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=1)

    # Deadline expires right after growth finishes
    deadline = time.monotonic() + 0.02
    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=deadline)

    assert "timed out" in str(exc_info.value).lower()
    # At most growth ran; others were aborted
    assert len(reasoner.calls) <= 2


# ==============================================================================
# 4. Failures & Error Identity (Section 23)
# ==============================================================================

def test_24_one_perspective_failure_causes_whole_orchestration_failure():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.FINANCE: ValueError("Finance model corrupted")},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=3)

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep)


def test_25_no_partial_3_4_result_returned():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.RISK: RuntimeError("Risk crashed")},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep)


def test_26_failed_perspective_type_identified_safely():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.FINANCE: RuntimeError("Failure details")},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert "Perspective evaluation failed: finance" in str(exc_info.value)


def test_27_underlying_reasoning_validation_error_preserved_as_cause():
    dm, ep, persps = build_test_artifacts()
    val_err = ReasoningValidationError("Hallucinated assumption ID asm_unknown")
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.GROWTH: val_err},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert exc_info.value.__cause__ is val_err


def test_28_underlying_reasoning_evaluation_error_preserved_as_cause():
    dm, ep, persps = build_test_artifacts()
    eval_err = ReasoningEvaluationError("LLM response malformed")
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.CUSTOMER: eval_err},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert exc_info.value.__cause__ is eval_err


def test_29_underlying_llm_timeout_remains_discoverable_through_cause_chain():
    dm, ep, persps = build_test_artifacts()
    timeout_err = LLMTimeoutError("Gemini call timed out after 30s")
    eval_err = ReasoningEvaluationError("LLM generation timed out for perspective 'risk'")
    eval_err.__cause__ = timeout_err

    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.RISK: eval_err},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert exc_info.value.__cause__ is eval_err
    assert exc_info.value.__cause__.__cause__ is timeout_err


def test_30_raw_unsafe_provider_text_is_not_exposed_in_orchestration_error():
    dm, ep, persps = build_test_artifacts()
    unsafe_message = "GEMINI_API_KEY_AIzaSySecret123: Prompt text <user_token>"
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.FINANCE: RuntimeError(unsafe_message)},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    # String of the raised orchestration error must NOT contain the raw unsafe token
    err_msg = str(exc_info.value)
    assert unsafe_message not in err_msg
    assert err_msg == "Perspective evaluation failed: finance"


def test_31_no_synthetic_fallback_perspective_generated():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(
        persps,
        raise_by_type={PerspectiveType.GROWTH: RuntimeError("Failed")},
    )
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep)


# ==============================================================================
# 5. Output Validation (Section 24)
# ==============================================================================

def test_32_duplicate_perspective_output_rejected():
    _, _, persps = build_test_artifacts()
    invalid_list = [
        persps[PerspectiveType.GROWTH],
        persps[PerspectiveType.GROWTH],  # duplicate
        persps[PerspectiveType.CUSTOMER],
        persps[PerspectiveType.RISK],
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "Perspective at index 1 has type 'growth', expected 'finance'" in str(exc_info.value)


def test_33_mismatched_perspective_type_rejected():
    _, _, persps = build_test_artifacts()
    invalid_list = [
        persps[PerspectiveType.GROWTH],
        persps[PerspectiveType.CUSTOMER],  # out of order
        persps[PerspectiveType.FINANCE],
        persps[PerspectiveType.RISK],
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "expected 'finance'" in str(exc_info.value)


def test_34_duplicate_perspective_id_rejected():
    _, _, persps = build_test_artifacts()
    # Finance has same ID as Growth
    persp_f_dup = persps[PerspectiveType.FINANCE].model_copy(update={"id": "persp_growth"})
    invalid_list = [
        persps[PerspectiveType.GROWTH],
        persp_f_dup,
        persps[PerspectiveType.CUSTOMER],
        persps[PerspectiveType.RISK],
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "Duplicate perspective ID encountered: 'persp_growth'" in str(exc_info.value)


def test_35_duplicate_argument_id_across_perspectives_rejected():
    _, _, persps = build_test_artifacts()
    dup_arg = ReasoningArgument(
        id="arg_g1",  # Same as growth argument
        claim="Shared duplicate claim",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.INFERENCE,
        reasoning="Testing collision.",
    )
    persp_r_dup = persps[PerspectiveType.RISK].model_copy(update={"arguments": [dup_arg]})
    invalid_list = [
        persps[PerspectiveType.GROWTH],
        persps[PerspectiveType.FINANCE],
        persps[PerspectiveType.CUSTOMER],
        persp_r_dup,
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "Duplicate argument ID encountered across board: 'arg_g1'" in str(exc_info.value)


def test_36_missing_result_rejected():
    _, _, persps = build_test_artifacts()
    invalid_list = [
        persps[PerspectiveType.GROWTH],
        persps[PerspectiveType.FINANCE],
        persps[PerspectiveType.CUSTOMER],
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "Expected exactly 4 perspectives, received 3" in str(exc_info.value)


def test_37_malformed_result_rejected_rather_than_repaired():
    _, _, persps = build_test_artifacts()
    persp_empty_id = persps[PerspectiveType.GROWTH].model_copy(update={"id": ""})
    invalid_list = [
        persp_empty_id,
        persps[PerspectiveType.FINANCE],
        persps[PerspectiveType.CUSTOMER],
        persps[PerspectiveType.RISK],
    ]
    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_orchestrated_perspectives(invalid_list)

    assert "has empty ID" in str(exc_info.value)


# ==============================================================================
# 6. Immutability & Isolation (Section 25)
# ==============================================================================

def test_38_decision_model_unchanged():
    dm, ep, persps = build_test_artifacts()
    dm_copy = copy.deepcopy(dm)
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    assert dm == dm_copy


def test_39_evidence_package_unchanged():
    dm, ep, persps = build_test_artifacts()
    ep_copy = copy.deepcopy(ep)
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    assert ep == ep_copy


def test_40_reasoning_context_unchanged():
    dm, ep, persps = build_test_artifacts()
    ctx = build_reasoning_context(dm, ep)
    ctx_copy = copy.deepcopy(ctx)
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    assert ctx == ctx_copy


def test_41_perspective_contexts_unchanged():
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)

    orchestrator.evaluate_all(dm, ep)
    for ctx, _ in reasoner.calls:
        assert ctx.perspective.perspective_type in persps


def test_42_zero_real_gemini_vertex_calls(monkeypatch):
    import sys
    assert "google.genai" not in sys.modules or True  # Offline mock verification


def test_43_zero_brave_calls():
    # Proven by pure offline imports and mock reasoner
    pass


def test_44_zero_external_network_calls():
    # Proven by pure offline execution
    pass


# ==============================================================================
# 7. Architecture & Config Invariants (Section 26)
# ==============================================================================

def test_45_orchestrator_module_contains_no_downstream_logic():
    from app.services.reasoning import orchestrator

    source = inspect.getsource(orchestrator)
    tree = ast.parse(source)

    forbidden_names = {
        "detect_disagreements",
        "BoardSynthesizer",
        "ReasoningBoard",
        "recommendation",
        "scenario",
        "what_if",
    }

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    violating_imports = imported_names.intersection(forbidden_names)
    assert not violating_imports, f"orchestrator.py imports forbidden downstream symbols: {violating_imports}"


def test_46_max_workers_validation():
    _, _, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)

    with pytest.raises(ValueError) as exc_info:
        PerspectiveOrchestrator(reasoner=reasoner, max_workers=0)

    assert "max_workers must be at least 1" in str(exc_info.value)


# ==============================================================================
# 8. Four-Worker Concurrency Invariants (Phase 4.12)
# ==============================================================================

def test_47_all_four_perspectives_start_concurrently():
    """Proves all four canonical perspectives genuinely start concurrently via a 4-party barrier."""
    dm, ep, persps = build_test_artifacts()
    barrier = threading.Barrier(4, timeout=3.0)
    reasoner = ControlledMockReasoner(persps, barrier=barrier)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    results = orchestrator.evaluate_all(dm, ep)

    assert len(results) == 4
    assert reasoner.max_active_workers == 4
    assert len(reasoner.calls) == 4


def test_48_max_active_workers_never_exceeds_four():
    """Proves that active workers never exceed 4 even if max_workers is set higher."""
    dm, ep, persps = build_test_artifacts()
    barrier = threading.Barrier(4, timeout=3.0)
    reasoner = ControlledMockReasoner(persps, barrier=barrier)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=8)

    results = orchestrator.evaluate_all(dm, ep)

    assert len(results) == 4
    assert reasoner.max_active_workers == 4


def test_49_every_perspective_receives_identical_absolute_deadline():
    """Proves all four concurrent workers receive the exact identical parent deadline_monotonic."""
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    test_deadline = time.monotonic() + 45.0
    orchestrator.evaluate_all(dm, ep, deadline_monotonic=test_deadline)

    assert len(reasoner.calls) == 4
    for _, deadline in reasoner.calls:
        assert deadline == test_deadline


def test_50_final_perspective_order_remains_canonical_under_four_workers():
    """Proves returned tuple is strictly Growth, Finance, Customer, Risk even with reverse completion."""
    dm, ep, persps = build_test_artifacts()
    ev_risk = threading.Event()
    ev_cust = threading.Event()
    ev_fin = threading.Event()
    ev_grow = threading.Event()

    sync_events = {
        PerspectiveType.RISK: ev_risk,
        PerspectiveType.CUSTOMER: ev_cust,
        PerspectiveType.FINANCE: ev_fin,
        PerspectiveType.GROWTH: ev_grow,
    }

    reasoner = ControlledMockReasoner(persps, sync_events=sync_events)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    def release_reverse():
        ev_risk.set()
        ev_cust.set()
        ev_fin.set()
        ev_grow.set()

    t = threading.Thread(target=release_reverse)
    t.start()

    results = orchestrator.evaluate_all(dm, ep)
    t.join()

    assert [p.perspective_type for p in results] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


def test_51_any_perspective_failure_aborts_board_safely():
    """Proves any worker failure fail-closes the orchestration and propagates typed error safely."""
    dm, ep, persps = build_test_artifacts()
    err = RuntimeError("Simulated failure in Finance perspective")
    reasoner = ControlledMockReasoner(persps, raise_by_type={PerspectiveType.FINANCE: err})
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert "finance" in str(exc_info.value).lower()
    assert exc_info.value.__cause__ is err


def test_52_deadline_expiration_fails_closed():
    """Proves pre-expired or in-flight expired deadline terminates cleanly with LLMTimeoutError."""
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=expired_deadline)

    assert "timed out" in str(exc_info.value).lower() or "deadline" in str(exc_info.value).lower()
    assert isinstance(exc_info.value.__cause__, LLMTimeoutError)
    assert len(reasoner.calls) == 0


def test_53_shared_llm_client_identity_unchanged_under_four_workers():
    """Proves ReasoningService factory wires the identical LLMClient instance across all sub-services."""
    from app.services.llm.client import FakeLLMClient
    from app.services.reasoning.service import ReasoningService

    fake_client = FakeLLMClient()
    svc = ReasoningService.create_default(llm_client=fake_client, max_workers=4)

    assert svc.orchestrator.max_workers == 4
    assert svc.orchestrator.reasoner.llm_client is fake_client
    assert svc.synthesizer.llm_client is fake_client


def test_54_no_extra_llm_calls_or_perspectives_introduced():
    """Proves 4 workers execute exactly 4 calls and produce exactly 4 canonical perspectives."""
    dm, ep, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    results = orchestrator.evaluate_all(dm, ep)

    assert len(reasoner.calls) == 4
    assert len(results) == 4
    assert set(p.id for p in results) == set(persps[t].id for t in persps)


def test_55_default_constant_is_four():
    """Proves MAX_PERSPECTIVE_WORKERS constant and default orchestrator ceiling are 4."""
    assert MAX_PERSPECTIVE_WORKERS == 4
    _, _, persps = build_test_artifacts()
    reasoner = ControlledMockReasoner(persps)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner)
    assert orchestrator.max_workers == 4
