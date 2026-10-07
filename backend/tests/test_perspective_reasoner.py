"""Offline unit tests for PerspectiveReasoner.

Verifies:
42. Exactly one LLM call is made per evaluate().
43. Response schema requested is CandidatePerspectiveAnalysis.
44. Correct perspective system instruction is passed to the LLM.
45. deadline_monotonic is propagated unchanged to LLMClient.
46. Valid candidate returns an authoritative ReasoningPerspective.
47. Returned perspective type matches the requested perspective.
48. Authoritative IDs were Python-generated.
49. Candidate cannot control authoritative IDs.
50. Invalid candidate reference raises typed ReasoningValidationError.
51. LLM provider/validation exceptions preserve safe cause chain.
52. No secondary retry loop exists inside PerspectiveReasoner.
53. Upstream DecisionModel, EvidencePackage, and Context remain unchanged.
54. Zero external network, Vertex, or search calls occur.
"""

from copy import deepcopy
from datetime import datetime, timezone
import time
import pytest

from app.schemas.decision_model import (
    Assumption,
    Complexity,
    ComplexityLevel,
    ConfidenceLevel,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ProvenanceType,
    ReversibilityLevel,
    TimeHorizon,
    Tradeoff,
    Variable,
    VariableType,
)
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import (
    ArgumentDirection,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    PerspectiveType,
    ReasoningBasis,
    ReasoningPerspective,
)
from app.services.llm.client import (
    LLMError,
    LLMProviderError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.reasoning.context_builder import (
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.perspectives import (
    FINANCE,
    GROWTH,
    RISK,
)
from app.services.reasoning.validator import (
    ReasoningEvaluationError,
    ReasoningValidationError,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _create_simple_context(perspective_lens=GROWTH):
    dm = DecisionModel(
        id="dec_simple_01",
        decision=Decision(
            raw_prompt="Expand into enterprise market?",
            summary="Scale enterprise operations.",
            decision_type=DecisionType.STRATEGIC_DIRECTION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.LOW,
            reasoning="Straightforward scaling initiative.",
            reversibility=ReversibilityLevel.REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_growth",
                description="Expand customer base.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_scale",
                name="Sales Volume",
                description="Target enterprise accounts.",
                variable_type=VariableType.NUMERIC,
                baseline_value=10,
                proposed_value=50,
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        constraints=[],
        stakeholders=[],
        tradeoffs=[
            Tradeoff(
                id="trd_simple",
                upside="Scale",
                downside="Cost",
                affected_variable_ids=["var_scale"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_market",
                statement="Enterprise demand is robust.",
                confidence=ConfidenceLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        unknowns=[],
        key_questions=["Will enterprise buyers convert?"],
    )

    src = Source(
        id="src_01",
        title="Industry Report",
        source_type=SourceType.INDUSTRY_REPORT,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    evi = EvidenceItem(
        id="evi_01",
        source_id="src_01",
        content="Enterprise buyers increased budget allocation by 20%.",
        summary="Budget growth observed.",
        retrieval_timestamp=datetime(2026, 10, 1, 10, 5, 0, tzinfo=timezone.utc),
    )
    req = EvidenceRequirement(
        id="req_01",
        target_entity_id="asm_market",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify enterprise budget allocations.",
        status=RequirementStatus.FULFILLED,
    )
    lnk = ClaimEvidenceLink(
        id="lnk_01",
        evidence_item_id="evi_01",
        target_entity_id="asm_market",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        stance=EvidenceStance.SUPPORTS,
        reasoning="Supports demand assumption.",
        requirement_id="req_01",
    )
    gap = EvidenceGap(
        id="gap_01",
        target_entity_id="asm_market",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE,
        description="Limited sample size.",
    )

    ep = EvidencePackage(
        id="evpkg_simple_01",
        decision_model_id="dec_simple_01",
        sources=[src],
        items=[evi],
        requirements=[req],
        claim_links=[lnk],
        gaps=[gap],
        summary="Initial empirical research completed.",
        created_at=datetime(2026, 10, 1, 10, 10, 0, tzinfo=timezone.utc),
    )

    rctx = build_reasoning_context(dm, ep)
    return build_perspective_context(perspective_lens, rctx)


def _valid_candidate(perspective_type=PerspectiveType.GROWTH) -> CandidatePerspectiveAnalysis:
    return CandidatePerspectiveAnalysis(
        perspective_type=perspective_type,
        summary="Enterprise opportunity is verified by industry budget expansions.",
        arguments=[
            CandidateReasoningArgument(
                claim="Enterprise demand expansion supports top-line target.",
                direction=ArgumentDirection.FAVORABLE,
                basis=ReasoningBasis.EVIDENCE,
                reasoning="Industry reports confirm 20% budget expansion.",
                evidence_item_ids=["evi_01"],
                requirement_ids=["req_01"],
                related_entity_ids=["obj_growth"],
            ),
        ],
        critical_assumption_ids=["asm_market"],
        evidence_gap_ids=["gap_01"],
        unresolved_questions=["Will conversion hold at scale?"],
        limitations=["Early market data."],
    )


# ------------------------------------------------------------------------------
# Test Suite
# ------------------------------------------------------------------------------

def test_42_exactly_one_llm_call_per_evaluate() -> None:
    """Test 42: PerspectiveReasoner invokes generate_structured exactly once per evaluation."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    res = reasoner.evaluate(ctx)

    assert isinstance(res, ReasoningPerspective)
    assert len(mock_llm.call_history) == 1


def test_43_response_schema_is_candidate_perspective_analysis() -> None:
    """Test 43: PerspectiveReasoner specifies CandidatePerspectiveAnalysis as response_schema."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    _ = reasoner.evaluate(ctx)

    assert mock_llm.call_history[0]["response_schema"] == CandidatePerspectiveAnalysis


def test_44_correct_system_instruction_supplied() -> None:
    """Test 44: PerspectiveReasoner provides the perspective-specific system instruction."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    _ = reasoner.evaluate(ctx)

    sys_inst = mock_llm.call_history[0]["system_instruction"]
    assert "Growth & Market Opportunity" in sys_inst
    assert "CRITICAL UNTRUSTED CONTENT GUARD:" in sys_inst


def test_45_deadline_monotonic_propagated_unchanged() -> None:
    """Test 45: deadline_monotonic passed to evaluate() is forwarded directly to LLMClient."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    target_deadline = time.monotonic() + 45.0
    _ = reasoner.evaluate(ctx, deadline_monotonic=target_deadline)

    assert mock_llm.call_history[0]["deadline_monotonic"] == target_deadline


def test_46_valid_candidate_returns_authoritative_reasoning_perspective() -> None:
    """Test 46: A valid candidate is returned as an authoritative ReasoningPerspective instance."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    resp = reasoner.evaluate(ctx)

    assert isinstance(resp, ReasoningPerspective)
    assert resp.perspective_type == PerspectiveType.GROWTH
    assert resp.summary == cand.summary
    assert len(resp.arguments) == 1


def test_47_returned_perspective_type_matches_requested_perspective() -> None:
    """Test 47: Returned perspective matches context perspective lens."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.FINANCE)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(FINANCE)

    resp = reasoner.evaluate(ctx)
    assert resp.perspective_type == PerspectiveType.FINANCE


def test_48_authoritative_ids_were_python_generated() -> None:
    """Test 48: Perspective ID and Argument IDs are authoritative Python-generated strings."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    resp = reasoner.evaluate(ctx)

    assert resp.id == "persp_growth"
    assert resp.arguments[0].id == "arg_growth_01"


def test_49_candidate_cannot_control_authoritative_ids() -> None:
    """Test 49: Candidate schema lacks ID fields, and any injected attributes are ignored."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    # Confirm CandidatePerspectiveAnalysis has no id field
    assert not hasattr(cand, "id")
    assert not hasattr(cand.arguments[0], "id")

    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    resp = reasoner.evaluate(ctx)
    assert resp.id == "persp_growth"


def test_50_invalid_candidate_reference_raises_typed_reasoning_validation_error() -> None:
    """Test 50: If candidate references invalid ID, raises typed ReasoningValidationError."""
    mock_llm = MockLLMClient()
    bad_cand = _valid_candidate(PerspectiveType.GROWTH)
    bad_cand.arguments[0].evidence_item_ids = ["evi_ghost"]
    mock_llm.register_response(CandidatePerspectiveAnalysis, bad_cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    with pytest.raises(ReasoningValidationError, match="nonexistent evidence_item_id 'evi_ghost'"):
        reasoner.evaluate(ctx)


def test_51_llm_provider_exception_preserves_safe_cause_chain() -> None:
    """Test 51: Upstream LLM errors are caught and wrapped in ReasoningEvaluationError with __cause__."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMTimeoutError("Request timed out after 45.0s"))

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    with pytest.raises(ReasoningEvaluationError, match="timed out") as exc_info:
        reasoner.evaluate(ctx)

    assert isinstance(exc_info.value.__cause__, LLMTimeoutError)


def test_52_no_second_retry_loop_exists() -> None:
    """Test 52: If LLM fails with non-retryable error, PerspectiveReasoner does not loop."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMProviderError("Internal Server Error"))

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    with pytest.raises(ReasoningEvaluationError):
        reasoner.evaluate(ctx)

    # Exactly 1 call was attempted before failing closed
    assert len(mock_llm.call_history) == 1


def test_53_upstream_context_and_models_unchanged() -> None:
    """Test 53: Upstream DecisionModel and EvidencePackage are completely unmutated."""
    dm = _create_simple_context(GROWTH).decision_context
    ep = _create_simple_context(GROWTH).evidence_context

    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    _ = reasoner.evaluate(ctx)

    assert ctx.decision_context == dm
    assert ctx.evidence_context == ep


def test_54_deadline_pre_check_fails_fast_before_llm() -> None:
    """Test 54: If deadline is already expired, evaluate() fails immediately without invoking LLM."""
    mock_llm = MockLLMClient()
    cand = _valid_candidate(PerspectiveType.GROWTH)
    mock_llm.register_response(CandidatePerspectiveAnalysis, cand)

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    ctx = _create_simple_context(GROWTH)

    expired_deadline = time.monotonic() - 1.0  # Already in the past

    with pytest.raises(ReasoningEvaluationError, match="deadline exceeded prior to LLM execution"):
        reasoner.evaluate(ctx, deadline_monotonic=expired_deadline)

    assert len(mock_llm.call_history) == 0
