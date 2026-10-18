"""Deterministic regression tests for Day 5 Phase 4C:
AI Boardroom Unknown-ID Reference Failure Fix.

Verifies:
1. Exact req_3 failure: Candidate referencing req_3 (which targets an Unknown) is reconciled to canonical unknown_id.
2. Correctly grounded unknown IDs: Direct references to valid unk_* IDs succeed unchanged.
3. Invalid unknown IDs remain rejected: Nonexistent unk_* and nonexistent req_* IDs raise ReasoningValidationError.
4. Ambiguous mappings remain rejected: Requirements targeting assumptions, tradeoffs, variables, or missing unknowns raise ReasoningValidationError.
5. Successful perspective validation: All 4 perspectives validate and reconcile accurately.
6. Boardroom synthesis compatibility: Reconciled perspectives integrate seamlessly with ReasoningBoard validation, disagreement detection, and synthesis input validation.
7. Prompt builder ID namespace clarity: Prompt distinguishes req_*, unk_*, asm_*, evi_*, and gap_* namespaces.
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
    BoardSynthesis,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    DisagreementNature,
    PerspectiveType,
    ReasoningBasis,
    ReasoningBoard,
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
from app.services.reasoning.prompt_builder import build_perspective_prompt
from app.services.reasoning.synthesizer import validate_synthesis_inputs
from app.services.reasoning.validator import (
    ReasoningValidationError,
    validate_and_reconcile_candidate_perspective,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _create_test_decision_model() -> DecisionModel:
    """Creates a deterministic DecisionModel for SaaS pricing decision."""
    return DecisionModel(
        id="dec_saas_pricing_01",
        decision=Decision(
            raw_prompt="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?",
            summary="Evaluate 20% price reduction to boost acquisition.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="High uncertainty regarding price elasticity and churn.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_growth",
                description="Increase new customer acquisition by 25%.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
            Objective(
                id="obj_margin",
                description="Maintain gross margin above 70%.",
                is_primary=False,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_price_discount",
                name="Price Discount",
                description="Percentage discount applied to standard plans.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=0.0,
                proposed_value=20.0,
                unit="%",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
            Variable(
                id="var_cac",
                name="Blended CAC",
                description="Customer acquisition cost across tiers.",
                variable_type=VariableType.CURRENCY,
                baseline_value=1200.0,
                proposed_value=950.0,
                unit="USD",
                is_controllable=False,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        constraints=[
            Constraint(
                id="con_runway",
                name="Minimum Runway",
                description="Maintain minimum 18 months cash runway.",
                is_hard_constraint=True,
                threshold_expression="runway_months >= 18",
                source="finance_policy",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        stakeholders=[
            Stakeholder(
                id="stk_customers",
                group="Target Customers",
                impact_nature="Higher adoption due to lower barrier to entry.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_volume_vs_arpu",
                upside="Accelerated customer growth.",
                downside="Lower revenue per user requiring higher volume.",
                affected_variable_ids=["var_price_discount"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_elasticity",
                statement="B2B SaaS demand is elastic under a 20% price cut.",
                confidence=ConfidenceLevel.MEDIUM,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_competitor_pricing",
                question="Will competitors respond with matched price discounts?",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            ),
            Unknown(
                id="unk_churn_sensitivity",
                question="What is the net revenue churn rate of discount-acquired cohorts?",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        key_questions=["Will competitor repricing negate the acquisition advantage?"],
    )


def _create_test_evidence_package(model_id: str = "dec_saas_pricing_01") -> EvidencePackage:
    """Creates a deterministic EvidencePackage with req_1, req_2, and req_3."""
    src = Source(
        id="src_benchmark_01",
        title="SaaS Pricing Elasticity Report 2026",
        publisher="OpenView Partners",
        source_type=SourceType.INDUSTRY_REPORT,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    evi_item = EvidenceItem(
        id="evi_elasticity_data",
        source_id="src_benchmark_01",
        content="20% price discount drove 14% median increase in new logo velocity.",
        summary="Empirical elasticity findings show sub-linear volume response.",
        numeric_data=[NumericEvidence(metric_name="volume_increase", value=14.0, unit="%")],
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 5, 0, tzinfo=timezone.utc),
    )
    # req_1: Targets asm_elasticity (ASSUMPTION) -> FULFILLED
    req_1 = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical elasticity study for B2B SaaS under price discount.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.FULFILLED,
    )
    # req_2: Targets trd_volume_vs_arpu (TRADEOFF) -> PENDING (calculation)
    req_2 = EvidenceRequirement(
        id="req_2",
        target_entity_id="trd_volume_vs_arpu",
        target_entity_type=DecisionEntityType.TRADEOFF,
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        description="Calculate break-even volume increase for 20% ARPU reduction.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    # req_3: Targets unk_competitor_pricing (UNKNOWN) -> PENDING (internal/external data)
    req_3 = EvidenceRequirement(
        id="req_3",
        target_entity_id="unk_competitor_pricing",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Assess competitive pricing response telemetry and history.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    # req_4: Targets unk_churn_sensitivity (UNKNOWN) -> PENDING
    req_4 = EvidenceRequirement(
        id="req_4",
        target_entity_id="unk_churn_sensitivity",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Cohort retention telemetry for discounted SaaS subscriptions.",
        priority=CriticalityLevel.MEDIUM,
        status=RequirementStatus.PENDING,
    )
    claim_link = ClaimEvidenceLink(
        id="lnk_elasticity_01",
        evidence_item_id="evi_elasticity_data",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        requirement_id="req_1",
        stance=EvidenceStance.SUPPORTS,
        relationship_confidence=ConfidenceLevel.HIGH,
        reasoning="Confirms directional volume elasticity.",
    )
    gap = EvidenceGap(
        id="gap_competitor_pricing",
        gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
        target_entity_id="unk_competitor_pricing",
        target_entity_type=DecisionEntityType.UNKNOWN,
        requirement_id="req_3",
        description="Competitor reaction to pricing cuts is unverified.",
        impact=CriticalityLevel.HIGH,
    )
    return EvidencePackage(
        id="pkg_saas_pricing_01",
        decision_model_id=model_id,
        summary="Summary of empirical evidence for SaaS pricing decision.",
        requirements=[req_1, req_2, req_3, req_4],
        sources=[src],
        items=[evi_item],
        claim_links=[claim_link],
        gaps=[gap],
    )


# ------------------------------------------------------------------------------
# 1. Exact req_3 Failure & Reconciliation
# ------------------------------------------------------------------------------

def test_01_exact_req_3_failure_reconciles_to_canonical_unknown_id() -> None:
    """Test 1: The exact failure from live run — candidate referencing req_3 in unknown_ids.

    In the live analysis, the candidate placed 'req_3' in unknown_ids.
    Since req_3 targets unk_competitor_pricing (an UNKNOWN in DecisionModel),
    the validator must deterministically reconcile req_3 -> unk_competitor_pricing.
    """
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    # Candidate argument mimicking the exact live failure:
    # basis='unresolved', unknown_ids=['req_3']
    cand_arg = CandidateReasoningArgument(
        claim="Growth upside depends on competitor reaction remaining benign.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="We cannot project sustainable market share gains without knowing if competitors match the cut.",
        unknown_ids=["req_3"],  # The exact problematic reference!
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=["obj_growth"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective indicates upside hinges on unverified competitor reactions.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=["Will competitors match?"],
        limitations=[],
    )

    # Must succeed without raising ReasoningValidationError:
    persp = validate_and_reconcile_candidate_perspective(cand, pctx)

    assert len(persp.arguments) == 1
    # Authoritative argument must contain the CANONICAL unknown_id, NOT 'req_3'
    assert persp.arguments[0].unknown_ids == ["unk_competitor_pricing"]
    assert "req_3" not in persp.arguments[0].unknown_ids
    assert persp.arguments[0].basis == ReasoningBasis.UNRESOLVED


# ------------------------------------------------------------------------------
# 2. Correctly Grounded Unknown IDs
# ------------------------------------------------------------------------------

def test_02_correctly_grounded_unknown_ids_succeed_unchanged() -> None:
    """Test 2: Direct references to valid canonical unknown IDs succeed unchanged."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(RISK, rctx)

    cand_arg = CandidateReasoningArgument(
        claim="Downside risk is unquantified due to unknown competitor reactions and churn.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Direct canonical references unk_competitor_pricing and unk_churn_sensitivity.",
        unknown_ids=["unk_competitor_pricing", "unk_churn_sensitivity"],
        evidence_gap_ids=["gap_competitor_pricing"],
        related_entity_ids=["con_runway"],
    )
    cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk analysis flags open unknowns.",
        arguments=[cand_arg],
        critical_assumption_ids=[],
        evidence_gap_ids=["gap_competitor_pricing"],
        unresolved_questions=[],
        limitations=[],
    )

    persp = validate_and_reconcile_candidate_perspective(cand, pctx)
    assert len(persp.arguments) == 1
    assert persp.arguments[0].unknown_ids == ["unk_competitor_pricing", "unk_churn_sensitivity"]


# ------------------------------------------------------------------------------
# 3. Invalid Unknown IDs Remaining Rejected
# ------------------------------------------------------------------------------

def test_03_invalid_unknown_id_rejected() -> None:
    """Test 3a: Nonexistent unknown ID starting with unk_ is strictly rejected."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Fake unknown.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["unk_completely_fabricated_id"],
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
    assert exc_info.value.details.get("invalid_id") == "unk_completely_fabricated_id"


def test_03b_nonexistent_requirement_id_in_unknown_ids_rejected() -> None:
    """Test 3b: Requirement ID not present in EvidencePackage is strictly rejected in unknown_ids."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(FINANCE, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Referencing phantom requirement.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["req_phantom_99"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.FINANCE,
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
    assert exc_info.value.details.get("invalid_id") == "req_phantom_99"


# ------------------------------------------------------------------------------
# 4. Ambiguous & Non-Unknown Mappings Remaining Rejected
# ------------------------------------------------------------------------------

def test_04a_requirement_targeting_assumption_rejected_in_unknown_ids() -> None:
    """Test 4a: A requirement ID that targets an ASSUMPTION is rejected in unknown_ids."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    # req_1 targets asm_elasticity (ASSUMPTION), not an UNKNOWN
    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Invalid placement of assumption requirement into unknown_ids.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["req_1"],
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
    assert exc_info.value.details.get("invalid_id") == "req_1"


def test_04b_requirement_targeting_tradeoff_rejected_in_unknown_ids() -> None:
    """Test 4b: A requirement ID that targets a TRADEOFF is rejected in unknown_ids."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(FINANCE, rctx)

    # req_2 targets trd_volume_vs_arpu (TRADEOFF), not an UNKNOWN
    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Invalid placement of calculation requirement into unknown_ids.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["req_2"],
        requirement_ids=[],
        assumption_ids=[],
        evidence_item_ids=[],
        evidence_gap_ids=[],
        related_entity_ids=[],
    )
    cand = CandidatePerspectiveAnalysis.model_construct(
        perspective_type=PerspectiveType.FINANCE,
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
    assert exc_info.value.details.get("invalid_id") == "req_2"


def test_04c_requirement_targeting_missing_unknown_rejected() -> None:
    """Test 4c: A requirement whose target_entity_id does not exist in DecisionModel.unknowns is rejected."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)

    # Invalidate req_3's target entity ID so it points to a nonexistent unknown
    broken_reqs = list(pkg.requirements)
    broken_reqs[2] = req_broken = EvidenceRequirement(
        id="req_3",
        target_entity_id="unk_ghost_entity",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Requirement targeting ghost unknown.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.PENDING,
    )
    pkg_broken = pkg.model_copy(update={"requirements": broken_reqs})

    rctx = build_reasoning_context(model, pkg_broken)
    pctx = build_perspective_context(GROWTH, rctx)

    cand_arg = CandidateReasoningArgument.model_construct(
        claim="Citing requirement with ghost target unknown.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Reasoning.",
        unknown_ids=["req_3"],
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
    assert exc_info.value.details.get("invalid_id") == "req_3"


# ------------------------------------------------------------------------------
# 5. Successful Perspective Validation Across All Perspectives
# ------------------------------------------------------------------------------

def test_05_perspective_validation_succeeds_with_reconciliation_and_deduplication() -> None:
    """Test 5: Reconciled unknown IDs pass across perspectives and handle deduplication."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)

    for pdef in [GROWTH, FINANCE, CUSTOMER, RISK]:
        pctx = build_perspective_context(pdef, rctx)

        # Citing both 'req_3' AND 'unk_competitor_pricing' directly
        # Should deduplicate cleanly to ['unk_competitor_pricing']
        cand_arg = CandidateReasoningArgument(
            claim=f"Perspective {pdef.title} analysis of competitive response.",
            direction=ArgumentDirection.NEUTRAL,
            basis=ReasoningBasis.UNRESOLVED,
            reasoning=f"Perspective {pdef.title} evaluates competitive reaction unknown.",
            unknown_ids=["req_3", "unk_competitor_pricing"],
            requirement_ids=[],
            assumption_ids=[],
            evidence_item_ids=[],
            evidence_gap_ids=[],
            related_entity_ids=["obj_growth"],
        )
        cand = CandidatePerspectiveAnalysis(
            perspective_type=pdef.perspective_type,
            summary=f"Summary for {pdef.title}.",
            arguments=[cand_arg],
            critical_assumption_ids=[],
            evidence_gap_ids=[],
            unresolved_questions=[],
            limitations=[],
        )

        persp = validate_and_reconcile_candidate_perspective(cand, pctx)
        assert len(persp.arguments) == 1
        # Deduplicated to single canonical entry
        assert persp.arguments[0].unknown_ids == ["unk_competitor_pricing"]
        assert persp.arguments[0].id == f"arg_{pdef.perspective_type.value}_01"


# ------------------------------------------------------------------------------
# 6. Boardroom Synthesis & Full Artifact Compatibility
# ------------------------------------------------------------------------------

def test_06_boardroom_synthesis_and_reasoning_board_compatibility() -> None:
    """Test 6: Perspectives produced via req_3 reconciliation integrate cleanly into ReasoningBoard.

    Verifies:
    - validate_reasoning_references passes without foreign key errors.
    - DisagreementEngine computes shared unknowns across perspectives.
    - ReasoningSynthesizer validates synthesis inputs cleanly.
    """
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)

    perspectives: List[ReasoningPerspective] = []

    # Growth cites req_3 (which reconciles to unk_competitor_pricing)
    growth_pctx = build_perspective_context(GROWTH, rctx)
    growth_cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective summary.",
        arguments=[
            CandidateReasoningArgument(
                claim="Growth upside depends on competitor reaction remaining benign.",
                direction=ArgumentDirection.FAVORABLE,
                basis=ReasoningBasis.UNRESOLVED,
                reasoning="Upside is substantial if competitors do not retaliate.",
                unknown_ids=["req_3"],  # Reconciles to unk_competitor_pricing
                related_entity_ids=["obj_growth"],
            )
        ],
    )
    perspectives.append(validate_and_reconcile_candidate_perspective(growth_cand, growth_pctx))

    # Finance cites req_4 (which reconciles to unk_churn_sensitivity)
    finance_pctx = build_perspective_context(FINANCE, rctx)
    finance_cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.FINANCE,
        summary="Finance perspective summary.",
        arguments=[
            CandidateReasoningArgument(
                claim="Discount volume sensitivity is undetermined.",
                direction=ArgumentDirection.NEUTRAL,
                basis=ReasoningBasis.UNRESOLVED,
                reasoning="Need churn telemetry.",
                unknown_ids=["req_4"],  # Reconciles to unk_churn_sensitivity
                related_entity_ids=["var_cac"],
            )
        ],
    )
    perspectives.append(validate_and_reconcile_candidate_perspective(finance_cand, finance_pctx))

    # Customer cites unk_competitor_pricing directly
    customer_pctx = build_perspective_context(CUSTOMER, rctx)
    customer_cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.CUSTOMER,
        summary="Customer perspective summary.",
        arguments=[
            CandidateReasoningArgument(
                claim="Customers benefit from price competition.",
                direction=ArgumentDirection.FAVORABLE,
                basis=ReasoningBasis.UNRESOLVED,
                reasoning="Willingness to pay depends on alternatives.",
                unknown_ids=["unk_competitor_pricing"],
                related_entity_ids=["stk_customers"],
            )
        ],
    )
    perspectives.append(validate_and_reconcile_candidate_perspective(customer_cand, customer_pctx))

    # Risk cites both unk_competitor_pricing and unk_churn_sensitivity
    risk_pctx = build_perspective_context(RISK, rctx)
    risk_cand = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.RISK,
        summary="Risk perspective summary.",
        arguments=[
            CandidateReasoningArgument(
                claim="Price war creates severe churn exposure.",
                direction=ArgumentDirection.UNFAVORABLE,
                basis=ReasoningBasis.UNRESOLVED,
                reasoning="Retaliation will crush margins and spike churn.",
                unknown_ids=["unk_competitor_pricing", "unk_churn_sensitivity"],
                related_entity_ids=["con_runway", "obj_growth"],
            )
        ],
    )
    perspectives.append(validate_and_reconcile_candidate_perspective(risk_cand, risk_pctx))

    # 1. Detect disagreements between perspectives
    disagreements = list(detect_disagreements(perspectives))

    # Growth (FAVORABLE on unk_competitor_pricing, obj_growth) vs Risk (UNFAVORABLE on unk_competitor_pricing, obj_growth)
    # produces an UNRESOLVED disagreement on shared scope unk_competitor_pricing anchored on obj_growth
    assert len(disagreements) >= 1
    dis_growth_risk = next(
        (d for d in disagreements if "persp_growth" in d.perspective_ids and "persp_risk" in d.perspective_ids),
        None,
    )
    assert dis_growth_risk is not None
    assert dis_growth_risk.nature == DisagreementNature.UNRESOLVED

    # 2. Build full ReasoningBoard
    synthesis = BoardSynthesis(
        summary="Synthesis of 4 perspectives.",
        areas_of_agreement=["Pricing impact is uncertain."],
        disagreement_ids=[d.id for d in disagreements],
        critical_assumption_ids=["asm_elasticity"],
        critical_evidence_gap_ids=["gap_competitor_pricing"],
        evidence_sensitive_points=["Retaliation elasticity"],
        unresolved_questions=["Will competitor match discount?"],
    )
    board = ReasoningBoard(
        id="board_test_reconciled",
        decision_model_id=model.id,
        evidence_package_id=pkg.id,
        perspectives=perspectives,
        disagreements=disagreements,
        synthesis=synthesis,
    )

    # 3. Pure cross-artifact reference validation must pass cleanly!
    validate_reasoning_references(board, model, pkg)

    # 4. Synthesizer input validation must pass cleanly!
    validate_synthesis_inputs(
        decision_model=model,
        evidence_package=pkg,
        reasoning_context=rctx,
        perspectives=perspectives,
        disagreements=disagreements,
    )


# ------------------------------------------------------------------------------
# 7. Prompt Serialization Namespace Verification
# ------------------------------------------------------------------------------

def test_07_prompt_builder_clearly_distinguishes_id_namespaces() -> None:
    """Test 7: Perspective prompt clearly separates and explains ID namespaces."""
    model = _create_test_decision_model()
    pkg = _create_test_evidence_package(model.id)
    rctx = build_reasoning_context(model, pkg)
    pctx = build_perspective_context(GROWTH, rctx)

    prompt = build_perspective_prompt(pctx)
    user_prompt = prompt.user_prompt

    # 1. Section headings are distinct and present
    assert "=== ASSUMPTIONS ===" in user_prompt
    assert "=== UNKNOWNS ===" in user_prompt
    assert "=== EVIDENCE REQUIREMENTS ===" in user_prompt
    assert "=== EVIDENCE ITEMS ===" in user_prompt
    assert "=== EVIDENCE GAPS & CONTRADICTIONS ===" in user_prompt

    # 2. Section notes indicate exact prefixes
    assert "Note: IDs start with 'asm_'." in user_prompt
    assert "Note: IDs start with 'unk_'." in user_prompt
    assert "Note: IDs start with 'req_'." in user_prompt

    # 3. Instruction rules explicitly forbid cross-namespace mixing
    assert "evidence_item_ids: Reference ONLY Evidence Item IDs from === EVIDENCE ITEMS === (must start with 'evi_')." in user_prompt
    assert "requirement_ids: Reference ONLY Requirement IDs from === EVIDENCE REQUIREMENTS === (must start with 'req_')." in user_prompt
    assert "NEVER place 'req_...' in unknown_ids." in user_prompt
    assert "unknown_ids: Reference ONLY Unknown IDs from === UNKNOWNS === (must start with 'unk_')." in user_prompt
    assert "NEVER place Requirement IDs ('req_...') or Gap IDs ('gap_...') in unknown_ids." in user_prompt
