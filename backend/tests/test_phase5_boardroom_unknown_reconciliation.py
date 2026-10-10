"""Deterministic regression tests for Day 5 Phase 4E:
Fix Malformed Boardroom Unknown References & Trailing Prose Reconciliation.

Verifies:
1. Exact live failure: Candidate referencing 'unk_hallucination_severity them' in unknown_ids
   reconciles deterministically to 'unk_hallucination_severity'.
2. Correct canonical Unknown IDs: Valid canonical references succeed unchanged.
3. Unknown IDs with stray trailing prose: Punctuation, notes, quotes, and prose delimiters
   are safely stripped to exact canonical IDs.
4. Nonexistent Unknown IDs: Phantom/fabricated IDs with or without prose are strictly rejected.
5. Ambiguous matches: Strings containing multiple IDs or conflicting namespace tokens fail closed.
6. Invalid namespace references: Cross-namespace references remain strictly rejected.
7. Multiple reference lists: Multi-list arguments with trailing prose across evidence, assumptions,
   unknowns, gaps, and entities reconcile cleanly.
8. Compatibility with requirement-to-unknown reconciliation: Phase 4C req -> unk mapping works
   even when trailing prose is present (e.g. 'req_3 them' -> 'unk_competitor_pricing').
9. Compatibility with Boardroom synthesis: Reconciled perspectives integrate seamlessly with
   Boardroom synthesis and Defense-in-Depth validate_reasoning_references.
10. Prompt builder conventions: Perspective and synthesis prompts explicitly forbid appending prose.
"""

from datetime import datetime, timezone
from typing import List
import pytest

from app.schemas.decision_model import (
    Assumption,
    Complexity,
    ComplexityLevel,
    ConfidenceLevel,
    Constraint,
    CriticalityLevel,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ProvenanceType,
    ReversibilityLevel,
    Stakeholder,
    TimeHorizon,
    Tradeoff,
    Unknown,
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
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import (
    ArgumentDirection,
    CandidateBoardSynthesis,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    PerspectiveType,
    ReasoningBasis,
    ReasoningBoard,
    ReasoningDisagreement,
    ReasoningPerspective,
    validate_reasoning_references,
)
from app.services.reasoning.context_builder import (
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.disagreements import detect_disagreements
from app.services.reasoning.perspectives import (
    CUSTOMER,
    FINANCE,
    GROWTH,
    RISK,
)
from app.services.reasoning.prompt_builder import (
    build_perspective_prompt,
    build_perspective_system_instruction,
)
from app.services.reasoning.synthesizer import (
    build_synthesis_system_instruction,
    validate_candidate_synthesis,
    validate_synthesis_inputs,
)
from app.services.reasoning.validator import (
    ReasoningValidationError,
    resolve_canonical_id,
    validate_and_reconcile_candidate_perspective,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _create_ai_assistant_decision_model() -> DecisionModel:
    """Creates deterministic DecisionModel matching the exact live test inquiry."""
    return DecisionModel(
        id="dec_ai_assistant_90d",
        decision=Decision(
            raw_prompt="Should a mid-sized B2B SaaS company launch a new AI-powered customer support assistant within the next 90 days, or first run a limited pilot?",
            summary="Evaluate 90-day launch vs. pilot for AI support assistant.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.SHORT_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Customer risk regarding hallucination severity and cost trade-offs.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_cost_reduction",
                description="Reduce customer support costs by 20%.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
            Objective(
                id="obj_csat",
                description="Maintain CSAT above 90%.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_pilot_duration",
                name="Pilot Duration",
                description="Length of pilot evaluation phase.",
                variable_type=VariableType.NUMERIC,
                baseline_value=0.0,
                proposed_value=90.0,
                unit="days",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        constraints=[
            Constraint(
                id="con_budget",
                name="Engineering Budget Limit",
                description="Engineering implementation budget capped at $50k.",
                is_hard_constraint=True,
                threshold_expression="budget_usd <= 50000",
                source="finance_policy",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        stakeholders=[
            Stakeholder(
                id="stk_support_agents",
                group="Support Agents",
                impact_nature="Shift from repetitive queries to complex escalations.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_speed_vs_safety",
                upside="Immediate cost reduction within 90 days.",
                downside="Higher risk of customer churn if AI hallucinates.",
                affected_variable_ids=["var_pilot_duration"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_agent_adoption",
                statement="Support agents will adopt AI assistant workflow within 14 days.",
                confidence=ConfidenceLevel.MEDIUM,
                provenance=ProvenanceType.INFERRED,
            ),
            Assumption(
                id="asm_cost_savings",
                statement="Deflecting 30% of tier-1 tickets yields 20% total cost savings.",
                confidence=ConfidenceLevel.HIGH,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_hallucination_severity",
                question="What is the empirical rate and business impact of AI hallucinations on complex SaaS tickets?",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            ),
            Unknown(
                id="unk_pilot_conversion",
                question="Will customers in pilot accept automated responses vs live agents?",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        key_questions=["Can guardrails prevent critical hallucination fallout?"],
    )


def _create_ai_assistant_evidence_package(model_id: str = "dec_ai_assistant_90d") -> EvidencePackage:
    """Creates deterministic EvidencePackage matching the AI assistant decision."""
    src = Source(
        id="src_benchmark_ai",
        title="B2B AI Support Automation Study 2026",
        publisher="Gartner",
        source_type=SourceType.INDUSTRY_REPORT,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    evi_item = EvidenceItem(
        id="evi_hallucination_rate",
        source_id="src_benchmark_ai",
        content="Domain-tuned support LLMs exhibit a 1.8% hallucination rate on tier-1 inquiries.",
        summary="Empirical hallucination telemetry indicates sub-2% rate for structured workflows.",
        numeric_data=[NumericEvidence(metric_name="hallucination_rate", value=1.8, unit="%")],
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 5, 0, tzinfo=timezone.utc),
    )
    req_1 = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_cost_savings",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical deflection cost benchmark.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.FULFILLED,
    )
    req_unk = EvidenceRequirement(
        id="req_hallucination_study",
        target_entity_id="unk_hallucination_severity",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Internal telemetry on ticket hallucination severity.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    claim_link = ClaimEvidenceLink(
        id="lnk_hallucination_01",
        evidence_item_id="evi_hallucination_rate",
        target_entity_id="asm_cost_savings",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        requirement_id="req_1",
        stance=EvidenceStance.SUPPORTS,
        relationship_confidence=ConfidenceLevel.HIGH,
        reasoning="Supports cost deflection thesis.",
    )
    gap = EvidenceGap(
        id="gap_hallucination_severity",
        gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
        target_entity_id="unk_hallucination_severity",
        target_entity_type=DecisionEntityType.UNKNOWN,
        requirement_id="req_hallucination_study",
        description="Exact customer churn consequence of hallucinated advice remains unverified.",
        impact=CriticalityLevel.HIGH,
    )
    return EvidencePackage(
        id="pkg_ai_assistant_90d",
        decision_model_id=model_id,
        summary="Summary of evidence regarding AI customer support assistant.",
        requirements=[req_1, req_unk],
        sources=[src],
        items=[evi_item],
        claim_links=[claim_link],
        gaps=[gap],
    )


# ------------------------------------------------------------------------------
# 1. Exact Live Failure Test
# ------------------------------------------------------------------------------

def test_01_exact_live_failure_unk_hallucination_severity_them_reconciles() -> None:
    """Test 1: Reproduce exact live failure with 'unk_hallucination_severity them'.

    In Job 353c3f2e-611f-4c17-92cd-11afb58b359e (Analysis 2a07765a-5ff3-453b-8a11-3d9ac06ae9e6),
    Gemini output candidate.arguments[0].unknown_ids = ['unk_hallucination_severity them'].
    Validation must reconcile this to canonical 'unk_hallucination_severity'.
    """
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Launching without pilot exposes company to unquantified hallucination liability.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Risk perspective requires assessing hallucination fallout before broad release.",
        unknown_ids=["unk_hallucination_severity them"],  # Exact malformed string from live run!
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=["con_budget"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk analysis flags unknown hallucination severity.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=["How damaging are hallucinations?"],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)

    assert len(persp.arguments) == 1
    # Authoritative argument must contain the exact canonical ID without prose:
    assert persp.arguments[0].unknown_ids == ["unk_hallucination_severity"]
    assert "unk_hallucination_severity them" not in persp.arguments[0].unknown_ids
    assert persp.arguments[0].basis == ReasoningBasis.UNRESOLVED


# ------------------------------------------------------------------------------
# 2. Correct Canonical Unknown IDs
# ------------------------------------------------------------------------------

def test_02_correct_canonical_unknown_ids_pass_unchanged() -> None:
    """Test 2: Exact canonical unknown IDs pass through cleanly without alteration."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Open unknowns require pilot evaluation.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Both hallucination severity and pilot conversion remain unresolved.",
        unknown_ids=["unk_hallucination_severity", "unk_pilot_conversion"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk analysis.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)
    assert persp.arguments[0].unknown_ids == ["unk_hallucination_severity", "unk_pilot_conversion"]


# ------------------------------------------------------------------------------
# 3. Unknown IDs with Stray Trailing Prose
# ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "malformed_id",
    [
        "unk_hallucination_severity (critical severity)",
        "unk_hallucination_severity: high risk",
        "unk_hallucination_severity - unresolved dependency",
        "unk_hallucination_severity, pending evaluation",
        "unk_hallucination_severity; note",
        "'unk_hallucination_severity' trailing prose",
        '"unk_hallucination_severity" note',
        "unk_hallucination_severity   lots of trailing spaces and text  ",
    ],
)
def test_03_unknown_ids_with_various_stray_prose_reconcile_cleanly(malformed_id: str) -> None:
    """Test 3: Punctuation, notes, quotes, and prose delimiters are stripped to canonical ID."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Open unknown dependency.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning with stray prose.",
        unknown_ids=[malformed_id],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk analysis.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)
    assert persp.arguments[0].unknown_ids == ["unk_hallucination_severity"]


# ------------------------------------------------------------------------------
# 4. Nonexistent Unknown IDs Strictly Rejected
# ------------------------------------------------------------------------------

def test_04a_nonexistent_unknown_id_without_prose_rejected() -> None:
    """Test 4a: Nonexistent unknown ID is strictly rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Phantom unknown.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["unk_phantom_id"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"
    assert exc_info.value.details.get("invalid_id") == "unk_phantom_id"


def test_04b_nonexistent_unknown_id_with_prose_rejected() -> None:
    """Test 4b: Nonexistent unknown ID with trailing prose is strictly rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Phantom unknown with prose.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["unk_fabricated_id them"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"
    assert "unk_fabricated_id" in exc_info.value.details.get("invalid_id", "")


def test_04c_arbitrary_prefix_match_is_strictly_rejected() -> None:
    """Test 4c: A non-matching token that starts with a canonical prefix must NOT match."""
    # Canonical is 'unk_hallucination_severity'
    # Candidate provides 'unk_hallucination_severity_extra notes'
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Partial match test.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["unk_hallucination_severity_extra notes"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"


# ------------------------------------------------------------------------------
# 5. Ambiguous Matches Rejected
# ------------------------------------------------------------------------------

def test_05a_multiple_canonical_unknown_ids_in_one_string_rejected() -> None:
    """Test 5a: A candidate string combining two valid canonical IDs fails closed."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Ambiguous unknown combining two valid IDs.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Combining unk_hallucination_severity and unk_pilot_conversion in single string.",
        unknown_ids=["unk_hallucination_severity unk_pilot_conversion"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.RISK,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"


def test_05b_canonical_unknown_id_combined_with_conflicting_requirement_rejected() -> None:
    """Test 5b: A string combining a canonical unknown and a requirement ID is rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Ambiguous unknown combining unknown and requirement.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Combining unk_hallucination_severity and req_1 in single string.",
        unknown_ids=["unk_hallucination_severity req_1"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.RISK,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"


# ------------------------------------------------------------------------------
# 6. Invalid Namespace References
# ------------------------------------------------------------------------------

def test_06a_evidence_item_id_in_unknown_ids_rejected() -> None:
    """Test 6a: Evidence item ID placed in unknown_ids is strictly rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Misplaced namespace.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["evi_hallucination_rate them"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"


def test_06b_unknown_id_in_evidence_item_ids_rejected() -> None:
    """Test 6b: Unknown ID placed in evidence_item_ids is strictly rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Misplaced namespace in evidence items.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Reasoning.",
        evidence_item_ids=["unk_hallucination_severity them"],
        requirement_ids=[],
        assumption_ids=[],
        unknown_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_evidence_item_id"


# ------------------------------------------------------------------------------
# 7. Multiple Reference Lists with Trailing Prose
# ------------------------------------------------------------------------------

def test_07_multiple_reference_lists_with_trailing_prose_reconcile_cleanly() -> None:
    """Test 7: Multi-list argument with trailing prose across all reference lists reconciles."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(FINANCE, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Financial outcome depends on evidence, assumptions, unknowns, and gaps.",
        direction=ArgumentDirection.MIXED,
        basis=ReasoningBasis.MIXED,
        reasoning="Comprehensive multi-reference evaluation.",
        evidence_item_ids=["evi_hallucination_rate (benchmark)"],
        requirement_ids=["req_1 fulfilled"],
        assumption_ids=["asm_cost_savings critical assumption"],
        unknown_ids=["unk_hallucination_severity them"],
        evidence_gap_ids=["gap_hallucination_severity open gap"],
        related_entity_ids=["obj_cost_reduction primary target"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.FINANCE,
        summary="Financial perspective summary.",
        arguments=[cand_arg],
        critical_assumption_ids=["asm_cost_savings foundational"],
        evidence_gap_ids=["gap_hallucination_severity high impact"],
        unresolved_questions=[],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)

    assert len(persp.arguments) == 1
    arg = persp.arguments[0]
    assert arg.evidence_item_ids == ["evi_hallucination_rate"]
    assert arg.requirement_ids == ["req_1"]
    assert arg.assumption_ids == ["asm_cost_savings"]
    assert arg.unknown_ids == ["unk_hallucination_severity"]
    assert arg.evidence_gap_ids == ["gap_hallucination_severity"]
    assert arg.related_entity_ids == ["obj_cost_reduction"]
    assert arg.basis == ReasoningBasis.MIXED

    # Top-level lists also reconciled:
    assert persp.critical_assumption_ids == ["asm_cost_savings"]
    assert persp.evidence_gap_ids == ["gap_hallucination_severity"]


# ------------------------------------------------------------------------------
# 8. Compatibility with Requirement-to-Unknown Reconciliation
# ------------------------------------------------------------------------------

def test_08a_requirement_targeting_unknown_with_prose_reconciles() -> None:
    """Test 8a: Phase 4C req -> unk mapping works with trailing prose on requirement ID.

    req_hallucination_study targets unk_hallucination_severity (UNKNOWN).
    Candidate specifies 'req_hallucination_study them' in unknown_ids.
    Reconciles to 'unk_hallucination_severity'.
    """
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Growth depends on resolving empirical study.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Empirical study pending.",
        unknown_ids=["req_hallucination_study them"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)
    assert persp.arguments[0].unknown_ids == ["unk_hallucination_severity"]


def test_08b_requirement_targeting_assumption_with_prose_strictly_rejected() -> None:
    """Test 8b: req_1 targets an ASSUMPTION; 'req_1 them' in unknown_ids is strictly rejected."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Invalid requirement type.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["req_1 them"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )

    with pytest.raises(ReasoningValidationError) as exc_info:
        validate_and_reconcile_candidate_perspective(cand, pctx)
    assert exc_info.value.details.get("rule") == "nonexistent_unknown_id"


# ------------------------------------------------------------------------------
# 9. Boardroom Synthesis & validate_reasoning_references Compatibility
# ------------------------------------------------------------------------------

def test_09_boardroom_synthesis_and_reasoning_board_compatibility() -> None:
    """Test 9: Reconciled perspectives integrate seamlessly with Boardroom synthesis and defense-in-depth."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)

    # 1. Build 4 perspectives, including one with trailing prose
    perspectives: List[ReasoningPerspective] = []
    configs = [
        (GROWTH, "Growth summary", ArgumentDirection.FAVORABLE, ReasoningBasis.INFERENCE, [], []),
        (FINANCE, "Finance summary", ArgumentDirection.FAVORABLE, ReasoningBasis.ASSUMPTION, ["asm_cost_savings note"], []),
        (CUSTOMER, "Customer summary", ArgumentDirection.NEUTRAL, ReasoningBasis.EVIDENCE, [], ["evi_hallucination_rate"]),
        (RISK, "Risk summary", ArgumentDirection.UNFAVORABLE, ReasoningBasis.UNRESOLVED, [], []),
    ]

    for p_lens, summary, direction, basis, asms, evis in configs:
        pctx = build_perspective_context(p_lens, rctx)
        uids = ["unk_hallucination_severity them"] if p_lens == RISK else []
        c_arg = CandidateReasoningArgument(
            claim=f"Claim from {p_lens.title}",
            direction=direction,
            basis=basis,
            reasoning="Grounded argument.",
            unknown_ids=uids,
            requirement_ids=["req_1"] if evis else [],
            assumption_ids=asms,
            evidence_item_ids=evis,
            evidence_gap_ids=[],
            related_entity_ids=["obj_cost_reduction"],
        )
        cand = CandidatePerspectiveAnalysis(
            perspective_type=p_lens.perspective_type,
            summary=summary,
            arguments=[c_arg],
            critical_assumption_ids=[],
            evidence_gap_ids=[],
            unresolved_questions=[],
            limitations=[],
        )
        persp = validate_and_reconcile_candidate_perspective(cand, pctx)
        perspectives.append(persp)

    # Detect disagreements
    disagreements = detect_disagreements(perspectives)

    # Validate synthesis inputs (must pass with zero errors)
    validate_synthesis_inputs(
        decision_model=model,
        evidence_package=pkg,
        reasoning_context=rctx,
        perspectives=perspectives,
        disagreements=disagreements,
    )

    # Test candidate synthesis validation with trailing prose
    cand_synthesis = CandidateBoardSynthesis(
        summary="Boardroom deliberation converges on launching limited pilot first.",
        areas_of_agreement=["Cost deflection potential is validated."],
        disagreement_ids=[d.id for d in disagreements],
        critical_assumption_ids=["asm_cost_savings foundational"],
        critical_evidence_gap_ids=["gap_hallucination_severity high impact"],
        evidence_sensitive_points=["Empirical hallucination telemetry under customer load."],
        unresolved_questions=["How quickly can agents recover from erroneous assistant responses?"],
    )
    synth = validate_candidate_synthesis(cand_synthesis, model, pkg, disagreements)
    assert synth.critical_assumption_ids == ["asm_cost_savings"]
    assert synth.critical_evidence_gap_ids == ["gap_hallucination_severity"]

    # Assemble complete ReasoningBoard
    board = ReasoningBoard(
        id="board_ai_assistant_90d",
        decision_model_id=model.id,
        evidence_package_id=pkg.id,
        perspectives=perspectives,
        disagreements=disagreements,
        synthesis=synth,
    )

    # Defense-in-depth referential integrity check must pass with ZERO errors
    validate_reasoning_references(board, model, pkg)


# ------------------------------------------------------------------------------
# 10. Prompt Builder Exact Copy Conventions
# ------------------------------------------------------------------------------

def test_10_prompt_builder_contains_exact_copying_conventions() -> None:
    """Test 10: Perspective and synthesis prompts explicitly instruct copying exact IDs without prose."""
    model = _create_ai_assistant_decision_model()
    pkg = _create_ai_assistant_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    # Perspective system instruction
    sys_instruction = build_perspective_system_instruction(pctx)
    assert "Copy canonical IDs exactly; never append explanatory words, notes, or prose to ID strings." in sys_instruction

    # Perspective prompt
    prompt = build_perspective_prompt(pctx)
    assert "Copy exact canonical IDs only. NEVER append explanatory text, prose, notes, commentary, or punctuation" in prompt.user_prompt
    assert "Each array element must contain exactly one raw canonical ID string." in prompt.user_prompt

    # Synthesis system instruction
    synth_sys = build_synthesis_system_instruction()
    assert "Copy exact canonical IDs only. NEVER append explanatory text, prose, notes, or punctuation to ID strings." in synth_sys
