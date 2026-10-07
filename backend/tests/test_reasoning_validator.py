"""Offline unit tests for authoritative grounding and epistemic validator.

Verifies:
20. Valid candidate converts successfully into authoritative ReasoningPerspective.
21. Hallucinated evidence ID rejected.
22. Hallucinated requirement ID rejected.
23. Hallucinated assumption ID rejected.
24. Hallucinated unknown ID rejected.
25. Hallucinated gap ID rejected.
26. Hallucinated related entity ID rejected.
27. EVIDENCE basis without evidence rejected.
28. ASSUMPTION basis without assumption rejected.
29. UNRESOLVED basis without unresolved dependency rejected.
30. Invalid MIXED basis rejected (fewer than 2 distinct categories).
31. Valid MIXED basis succeeds.
32. False requirement/evidence lineage rejected.
33. Valid shared evidence lineage succeeds.
34. PENDING internal_data requirement cannot become factual evidence.
35. PENDING deterministic calculation requirement cannot become factual evidence.
36. PENDING user clarification requirement cannot become factual evidence.
37. Challenging evidence remains structurally challenging (cannot assert favorable without supporting evidence).
38. Contested requirement cannot be structurally converted to settled.
39. Invalid candidate causes zero authoritative output (raises typed ReasoningValidationError).
40. Deterministic IDs stable across repeated conversion.
41. Deterministic IDs independent of Python hash randomization assumptions.
"""

from datetime import date, datetime, timezone
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
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    PerspectiveType,
    ReasoningBasis,
    ReasoningPerspective,
)
from app.services.reasoning.context_builder import (
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.perspectives import (
    FINANCE,
    GROWTH,
    RISK,
)
from app.services.reasoning.validator import (
    ReasoningValidationError,
    validate_and_reconcile_candidate_perspective,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _create_fixture_context(perspective_lens=GROWTH):
    dm = DecisionModel(
        id="dec_test_01",
        decision=Decision(
            raw_prompt="Expand sales team into enterprise?",
            summary="Hire enterprise AE team.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Capital commitment with sales cycle latency.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_arr",
                description="Double ARR to $10M.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_headcount",
                name="Sales Headcount",
                description="Number of AEs.",
                variable_type=VariableType.NUMERIC,
                baseline_value=2,
                proposed_value=8,
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        constraints=[
            Constraint(
                id="con_budget",
                name="Budget Cap",
                description="Hiring budget capped at $1.5M.",
                is_hard_constraint=True,
                threshold_expression="spend <= 1500000",
                source="user_specified",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        stakeholders=[
            Stakeholder(
                id="stk_board",
                group="Board of Directors",
                impact_nature="Monitors capital allocation.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_burn",
                upside="High logo acquisition.",
                downside="Increased cash burn.",
                affected_variable_ids=["var_headcount"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_acv",
                statement="Average contract value is $80k.",
                confidence=ConfidenceLevel.MEDIUM,
                provenance=ProvenanceType.INFERRED,
            ),
            Assumption(
                id="asm_ramp",
                statement="Rep ramp time is 3 months.",
                confidence=ConfidenceLevel.LOW,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_cycle",
                question="What is the average sales cycle in months?",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        key_questions=["Can we sustain the burn during sales ramp?"],
    )

    src = Source(
        id="src_gartner",
        title="B2B Sales Benchmark",
        publisher="Gartner",
        source_type=SourceType.INDUSTRY_REPORT,
        retrieval_timestamp=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    evi_valid = EvidenceItem(
        id="evi_sales_cycle",
        source_id="src_gartner",
        content="Enterprise sales cycle averaged 6 months.",
        summary="6-month cycle verified.",
        numeric_data=[NumericEvidence(metric_name="cycle_months", value=6.0, unit="months")],
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime(2026, 10, 1, 12, 5, 0, tzinfo=timezone.utc),
    )
    evi_challenge = EvidenceItem(
        id="evi_high_churn",
        source_id="src_gartner",
        content="Competitor analysis shows 35% annual churn under premature enterprise expansion.",
        summary="Premature expansion drives high churn.",
        numeric_data=[NumericEvidence(metric_name="churn_rate", value=0.35, unit="ratio")],
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime(2026, 10, 1, 12, 6, 0, tzinfo=timezone.utc),
    )
    req_cycle = EvidenceRequirement(
        id="req_cycle_proof",
        target_entity_id="unk_cycle",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify sales cycle length.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.FULFILLED,
    )
    req_internal = EvidenceRequirement(
        id="req_billing_internal",
        target_entity_id="var_headcount",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Extract actual payroll expenses from internal HRIS.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    req_deterministic = EvidenceRequirement(
        id="req_math_breakeven",
        target_entity_id="trd_growth_burn",
        target_entity_type=DecisionEntityType.TRADEOFF,
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        description="Calculate break-even rep quota threshold.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    req_user = EvidenceRequirement(
        id="req_clarify_budget",
        target_entity_id="con_budget",
        target_entity_type=DecisionEntityType.CONSTRAINT,
        kind=EvidenceKind.USER_CLARIFICATION,
        description="Clarify if budget cap includes bonus incentives.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    req_contested = EvidenceRequirement(
        id="req_churn_stat",
        target_entity_id="asm_ramp",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify churn impact of ramp velocity.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.CONTESTED,
    )
    lnk_cycle = ClaimEvidenceLink(
        id="lnk_cycle_01",
        evidence_item_id="evi_sales_cycle",
        target_entity_id="unk_cycle",
        target_entity_type=DecisionEntityType.UNKNOWN,
        stance=EvidenceStance.SUPPORTS,
        reasoning="Confirms 6-month cycle benchmark.",
        requirement_id="req_cycle_proof",
    )
    lnk_challenge = ClaimEvidenceLink(
        id="lnk_churn_01",
        evidence_item_id="evi_high_churn",
        target_entity_id="asm_ramp",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        stance=EvidenceStance.CHALLENGES,
        reasoning="Challenges ramp premise due to high churn.",
        requirement_id="req_churn_stat",
    )
    gap = EvidenceGap(
        id="gap_acv_proof",
        target_entity_id="asm_acv",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        gap_type=EvidenceGapType.UNSUPPORTED_CLAIM,
        description="No empirical evidence for $80k ACV assumption.",
        impact=CriticalityLevel.HIGH,
    )

    ep = EvidencePackage(
        id="evpkg_test_01",
        decision_model_id="dec_test_01",
        sources=[src],
        items=[evi_valid, evi_challenge],
        requirements=[req_cycle, req_internal, req_deterministic, req_user, req_contested],
        claim_links=[lnk_cycle, lnk_challenge],
        gaps=[gap],
        summary="Benchmark evidence available; internal data pending.",
        created_at=datetime(2026, 10, 1, 12, 10, 0, tzinfo=timezone.utc),
    )

    rctx = build_reasoning_context(dm, ep)
    return build_perspective_context(perspective_lens, rctx)


def _valid_candidate(perspective_type=PerspectiveType.GROWTH) -> CandidatePerspectiveAnalysis:
    return CandidatePerspectiveAnalysis(
        perspective_type=perspective_type,
        summary="Enterprise expansion offers strong top-line scale subject to ramp constraints.",
        arguments=[
            CandidateReasoningArgument(
                claim="Enterprise sales cycle of 6 months supports annual revenue goals.",
                direction=ArgumentDirection.FAVORABLE,
                basis=ReasoningBasis.EVIDENCE,
                reasoning="Empirical findings show a 6-month cycle allows closed ARR within fiscal year.",
                evidence_item_ids=["evi_sales_cycle"],
                requirement_ids=["req_cycle_proof"],
                related_entity_ids=["obj_arr"],
            ),
            CandidateReasoningArgument(
                claim="Average contract value of $80k is crucial to justify headcount.",
                direction=ArgumentDirection.NEUTRAL,
                basis=ReasoningBasis.ASSUMPTION,
                reasoning="The economic model requires this unit size to break even.",
                assumption_ids=["asm_acv"],
                related_entity_ids=["var_headcount"],
            ),
        ],
        critical_assumption_ids=["asm_acv"],
        evidence_gap_ids=["gap_acv_proof"],
        unresolved_questions=["What is the ramp timeline for new reps?"],
        limitations=["Analysis assumes current market pricing holds."],
    )


# ------------------------------------------------------------------------------
# Test Suite
# ------------------------------------------------------------------------------

def test_20_valid_candidate_converts_successfully() -> None:
    """Test 20: Valid candidate converts into authoritative ReasoningPerspective."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    resp = validate_and_reconcile_candidate_perspective(cand, ctx)

    assert isinstance(resp, ReasoningPerspective)
    assert resp.id == "persp_growth"
    assert resp.perspective_type == PerspectiveType.GROWTH
    assert len(resp.arguments) == 2
    assert resp.arguments[0].id == "arg_growth_01"
    assert resp.arguments[1].id == "arg_growth_02"


def test_21_hallucinated_evidence_id_rejected() -> None:
    """Test 21: Hallucinated evidence ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[0].evidence_item_ids = ["evi_ghost_id"]

    with pytest.raises(ReasoningValidationError, match="nonexistent evidence_item_id 'evi_ghost_id'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_22_hallucinated_requirement_id_rejected() -> None:
    """Test 22: Hallucinated requirement ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[0].requirement_ids = ["req_ghost_id"]

    with pytest.raises(ReasoningValidationError, match="nonexistent requirement_id 'req_ghost_id'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_23_hallucinated_assumption_id_rejected() -> None:
    """Test 23: Hallucinated assumption ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[1].assumption_ids = ["asm_ghost_id"]

    with pytest.raises(ReasoningValidationError, match="nonexistent assumption_id 'asm_ghost_id'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_24_hallucinated_unknown_id_rejected() -> None:
    """Test 24: Hallucinated unknown ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[0].unknown_ids = ["unk_ghost_id"]

    with pytest.raises(ReasoningValidationError, match="nonexistent unknown_id 'unk_ghost_id'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_25_hallucinated_gap_id_rejected() -> None:
    """Test 25: Hallucinated gap ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.evidence_gap_ids = ["gap_ghost_id"]

    with pytest.raises(ReasoningValidationError, match="nonexistent evidence_gap_id 'gap_ghost_id'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_26_hallucinated_related_entity_id_rejected() -> None:
    """Test 26: Hallucinated related entity ID raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[0].related_entity_ids = ["ent_hallucinated"]

    with pytest.raises(ReasoningValidationError, match="nonexistent related_entity_id 'ent_hallucinated'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_27_evidence_basis_without_evidence_rejected() -> None:
    """Test 27: Argument with basis EVIDENCE but no evidence IDs raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    # Using model_construct to bypass Pydantic model_validator to test validator.py defense-in-depth
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Claim without evidence.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Just trust me.",
        evidence_item_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'evidence' but references no evidence_item_ids"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_28_assumption_basis_without_assumption_rejected() -> None:
    """Test 28: Argument with basis ASSUMPTION but no assumption IDs raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Claim without assumption.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.ASSUMPTION,
        reasoning="No premise cited.",
        assumption_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'assumption' but references no assumption_ids"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_29_unresolved_basis_without_dependency_rejected() -> None:
    """Test 29: Argument with basis UNRESOLVED but no unknown/gap/req raises ReasoningValidationError."""
    ctx = _create_fixture_context(GROWTH)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Unresolved claim.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Unclear.",
        unknown_ids=[],
        evidence_gap_ids=[],
        requirement_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'unresolved' but references no unresolved dependency"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_30_invalid_mixed_basis_rejected() -> None:
    """Test 30: Argument with basis MIXED referencing <2 distinct epistemic categories is rejected."""
    ctx = _create_fixture_context(GROWTH)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Mixed claim with only evidence.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.MIXED,
        reasoning="Only evidence.",
        evidence_item_ids=["evi_sales_cycle"],
        assumption_ids=[],
        unknown_ids=[],
        evidence_gap_ids=[],
        requirement_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="does not reference at least two distinct epistemic categories"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_31_valid_mixed_basis_succeeds() -> None:
    """Test 31: Argument with basis MIXED referencing evidence AND assumption succeeds."""
    ctx = _create_fixture_context(GROWTH)
    mixed_arg = CandidateReasoningArgument(
        claim="Sales cycle evidence combined with ACV assumption demonstrates path to $10M ARR.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.MIXED,
        reasoning="Evidence confirms 6-month cycle and model assumes $80k deal size.",
        evidence_item_ids=["evi_sales_cycle"],
        requirement_ids=["req_cycle_proof"],
        assumption_ids=["asm_acv"],
        related_entity_ids=["obj_arr"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[mixed_arg],
        critical_assumption_ids=["asm_acv"],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    resp = validate_and_reconcile_candidate_perspective(cand, ctx)
    assert len(resp.arguments) == 1
    assert resp.arguments[0].basis == ReasoningBasis.MIXED


def test_32_false_requirement_evidence_lineage_rejected() -> None:
    """Test 32: Candidate claiming evi_sales_cycle satisfies req_billing_internal fails lineage check."""
    ctx = _create_fixture_context(GROWTH)
    # evi_sales_cycle was retrieved for req_cycle_proof, NOT req_billing_internal
    bad_lineage_arg = CandidateReasoningArgument(
        claim="Internal payroll is verified by external sales cycle data.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Mismatched lineage.",
        evidence_item_ids=["evi_sales_cycle"],
        requirement_ids=["req_billing_internal"],
        related_entity_ids=["var_headcount"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_lineage_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="asserts false requirement lineage"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_33_valid_shared_evidence_lineage_succeeds() -> None:
    """Test 33: Citing matching requirement and evidence lineages succeeds."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    resp = validate_and_reconcile_candidate_perspective(cand, ctx)
    assert resp.arguments[0].evidence_item_ids == ["evi_sales_cycle"]
    assert resp.arguments[0].requirement_ids == ["req_cycle_proof"]


def test_34_pending_internal_data_cannot_become_factual_evidence() -> None:
    """Test 34: Pending internal_data requirement cannot be claimed as factual basis EVIDENCE."""
    ctx = _create_fixture_context(FINANCE)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Internal payroll expenses are fully verified.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Relying on pending HRIS request as settled facts.",
        requirement_ids=["req_billing_internal"],
        evidence_item_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.FINANCE,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'evidence'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_35_pending_deterministic_calculation_cannot_become_factual_evidence() -> None:
    """Test 35: Pending deterministic_calculation requirement cannot be claimed as basis EVIDENCE."""
    ctx = _create_fixture_context(FINANCE)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Break-even calculation proves profitability.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Math is assumed done.",
        requirement_ids=["req_math_breakeven"],
        evidence_item_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.FINANCE,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'evidence'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_36_pending_user_clarification_cannot_become_factual_evidence() -> None:
    """Test 36: Pending user_clarification requirement cannot be claimed as basis EVIDENCE."""
    ctx = _create_fixture_context(GROWTH)
    bad_arg = CandidateReasoningArgument.model_construct(
        claim="Budget clarification is confirmed.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="User clarification assumed settled without response.",
        requirement_ids=["req_clarify_budget"],
        evidence_item_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.GROWTH,
        summary="Summary",
        arguments=[bad_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="basis 'evidence'"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_37_challenging_evidence_remains_structurally_challenging() -> None:
    """Test 37: Argument citing only CHALLENGES evidence cannot claim direction FAVORABLE."""
    ctx = _create_fixture_context(RISK)
    # evi_high_churn carries stance CHALLENGES
    distorted_arg = CandidateReasoningArgument(
        claim="High churn rate is favorable for our expansion strategy.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Attempting to rebrand challenge as favorable.",
        evidence_item_ids=["evi_high_churn"],
        requirement_ids=["req_churn_stat"],
        related_entity_ids=["asm_ramp"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk summary.",
        arguments=[distorted_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    with pytest.raises(ReasoningValidationError, match="asserts direction 'favorable' but only cites challenging evidence"):
        validate_and_reconcile_candidate_perspective(cand, ctx)


def test_38_contested_requirement_not_structurally_settled() -> None:
    """Test 38: When requirement is CONTESTED, citing its challenging findings as UNFAVORABLE succeeds."""
    ctx = _create_fixture_context(RISK)
    risk_arg = CandidateReasoningArgument(
        claim="35% competitor churn challenges the 3-month rep ramp assumption.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Empirical churn benchmark demonstrates severe downside risk.",
        evidence_item_ids=["evi_high_churn"],
        requirement_ids=["req_churn_stat"],
        related_entity_ids=["asm_ramp"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Downside analysis surfaces friction.",
        arguments=[risk_arg],
        critical_assumption_ids=["asm_ramp"],
        evidence_gap_ids=[],
        unresolved_questions=[],
        limitations=[],
    )
    resp = validate_and_reconcile_candidate_perspective(cand, ctx)
    assert resp.arguments[0].direction == ArgumentDirection.UNFAVORABLE


def test_39_invalid_candidate_causes_zero_authoritative_output() -> None:
    """Test 39: If candidate is invalid, no partial authoritative object is constructed or leaked."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)
    cand.arguments[0].evidence_item_ids = ["evi_nonexistent_99"]

    output = None
    with pytest.raises(ReasoningValidationError):
        output = validate_and_reconcile_candidate_perspective(cand, ctx)

    assert output is None


def test_40_deterministic_ids_stable_across_repeated_conversion() -> None:
    """Test 40: Calling validator multiple times yields identical authoritative IDs."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)

    resp_1 = validate_and_reconcile_candidate_perspective(cand, ctx)
    resp_2 = validate_and_reconcile_candidate_perspective(cand, ctx)

    assert resp_1.id == resp_2.id == "persp_growth"
    assert [a.id for a in resp_1.arguments] == [a.id for a in resp_2.arguments] == ["arg_growth_01", "arg_growth_02"]


def test_41_deterministic_ids_independent_of_python_hash_randomization() -> None:
    """Test 41: ID generation does not depend on hash() or dictionary ordering accidents."""
    ctx = _create_fixture_context(GROWTH)
    cand = _valid_candidate(PerspectiveType.GROWTH)

    # Re-ordering arguments in candidate changes index strictly by position
    cand_swapped = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary=cand.summary,
        arguments=[cand.arguments[1], cand.arguments[0]],
        critical_assumption_ids=cand.critical_assumption_ids,
        evidence_gap_ids=cand.evidence_gap_ids,
        unresolved_questions=cand.unresolved_questions,
        limitations=cand.limitations,
    )
    resp_swapped = validate_and_reconcile_candidate_perspective(cand_swapped, ctx)
    assert resp_swapped.arguments[0].id == "arg_growth_01"
    assert resp_swapped.arguments[1].id == "arg_growth_02"
    assert resp_swapped.arguments[0].claim == cand.arguments[1].claim
