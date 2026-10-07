"""Comprehensive offline unit and architecture tests for Authoritative Reasoning Schemas.

Verifies:
1. Valid ReasoningBoard succeeds with all four canonical perspectives.
2. Exactly four canonical perspectives required.
3. Missing Growth perspective rejected.
4. Duplicate Finance perspective rejected.
5. Unknown/ad-hoc perspective enum rejected.
6. Duplicate perspective ID rejected.
7. Duplicate argument ID across perspectives rejected.
8. Duplicate disagreement ID rejected.
9. Disagreement referencing nonexistent perspective rejected.
10. Disagreement referencing nonexistent argument rejected.
11. Synthesis referencing nonexistent disagreement rejected.
12. EVIDENCE basis without evidence_item_id rejected.
13. ASSUMPTION basis without assumption_id rejected.
14. UNRESOLVED basis without unresolved dependency rejected.
15. Valid MIXED basis succeeds.
16. Invalid MIXED basis with insufficient dependency categories rejected.
17. Wrong decision_model_id rejected by cross-artifact validator.
18. Wrong evidence_package_id rejected by cross-artifact validator.
19. Nonexistent evidence_item_id rejected by cross-artifact validator.
20. Nonexistent requirement_id rejected by cross-artifact validator.
21. Nonexistent assumption_id rejected by cross-artifact validator.
22. Nonexistent unknown_id rejected by cross-artifact validator.
23. Nonexistent evidence_gap_id rejected by cross-artifact validator.
24. Nonexistent related_entity_id rejected by cross-artifact validator.
25. Valid related entity references succeed across all DecisionModel entity types.
26. Upstream DecisionModel is unchanged after validation.
27. Upstream EvidencePackage is unchanged after validation.
28. ReasoningBoard is unchanged after validation.
29. Candidate schemas contain no authoritative Day 4 IDs.
30. created_at handles timezone awareness matching repository conventions.
31. Architecture test: ReasoningBoard and components contain no vote/recommendation/scoring/scenario fields.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import copy
import pytest
from pydantic import ValidationError

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
    CandidateBoardSynthesis,
    CandidateDisagreement,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    DisagreementNature,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningBoard,
    ReasoningDisagreement,
    ReasoningPerspective,
    validate_reasoning_references,
)


# ------------------------------------------------------------------------------
# Test Fixtures & Factories
# ------------------------------------------------------------------------------

def _build_valid_decision_model() -> DecisionModel:
    """Builds a minimal valid DecisionModel fixture."""
    return DecisionModel(
        id="dec_test_01",
        decision=Decision(
            raw_prompt="Should our B2B SaaS startup establish a dedicated enterprise sales team?",
            summary="Evaluate establishing an enterprise sales motion.",
            decision_type=DecisionType.STRATEGIC_DIRECTION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Significant sales cycle friction and capital commitment.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
            score=45.0,
        ),
        objectives=[
            Objective(
                id="obj_arr_growth",
                description="Accelerate ARR expansion from enterprise accounts",
                is_primary=True,
                target_metric="+$5M ARR",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_sales_headcount",
                name="Enterprise Sales Headcount",
                description="Number of dedicated enterprise account executives",
                variable_type=VariableType.NUMERIC,
                baseline_value=0,
                proposed_value=8,
                unit="headcount",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        constraints=[
            Constraint(
                id="cnstr_burn_budget",
                name="Sales Budget Cap",
                description="Sales expansion budget capped at $2M in year 1",
                is_hard_constraint=True,
                threshold_expression="sales_expense <= 2000000",
                source="user_specified",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        stakeholders=[
            Stakeholder(
                id="stk_founders",
                group="Executive Leadership",
                impact_nature="Accountable for burn and runway",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_vs_burn",
                upside="Capture high-ACV enterprise logos",
                downside="Higher cash burn and extended payback period",
                affected_variable_ids=["var_sales_headcount"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_acv_threshold",
                statement="Average enterprise contract value will exceed $80k annually",
                confidence=ConfidenceLevel.MEDIUM,
                falsification_condition="Average deal size drops below $40k across initial cohort",
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_cycle_length",
                question="What is the expected enterprise sales cycle length in months?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Gartner benchmark", "Competitor disclosures"],
                provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        key_questions=["Can the company sustain sales cycle latency without compromising runway?"],
    )


def _build_valid_evidence_package(decision_model_id: str = "dec_test_01") -> EvidencePackage:
    """Builds a minimal valid EvidencePackage fixture."""
    source = Source(
        id="src_gartner_01",
        title="2024 B2B SaaS Enterprise Sales Benchmark",
        publisher="Gartner Research",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 2, 1),
    )
    item = EvidenceItem(
        id="evi_sales_cycle_stat",
        source_id="src_gartner_01",
        content="Average enterprise SaaS sales cycle was 6.4 months across 180 B2B providers.",
        summary="Empirical enterprise sales cycle benchmark averages 6.4 months.",
        numeric_data=[
            NumericEvidence(
                metric_name="median_sales_cycle",
                value=6.4,
                unit="months",
                sample_size=180,
            )
        ],
        extraction_confidence=ConfidenceLevel.HIGH,
    )
    req = EvidenceRequirement(
        id="req_cycle_benchmark",
        target_entity_id="unk_cycle_length",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical benchmark for enterprise SaaS sales cycles.",
        priority=CriticalityLevel.HIGH,
        status=RequirementStatus.FULFILLED,
        suggested_queries=["enterprise SaaS sales cycle length benchmarks"],
    )
    link = ClaimEvidenceLink(
        id="lnk_cycle_to_unknown",
        evidence_item_id="evi_sales_cycle_stat",
        target_entity_id="unk_cycle_length",
        target_entity_type=DecisionEntityType.UNKNOWN,
        stance=EvidenceStance.SUPPORTS,
        reasoning="Gartner benchmark directly informs the sales cycle length unknown.",
        requirement_id="req_cycle_benchmark",
    )
    gap = EvidenceGap(
        id="gap_acv_evidence",
        gap_type=EvidenceGapType.UNSUPPORTED_CLAIM,
        target_entity_id="asm_acv_threshold",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        description="No empirical evidence confirms the $80k ACV assumption for this product tier.",
        impact=CriticalityLevel.HIGH,
        resolution_guidance="Conduct exploratory enterprise discovery interviews to validate pricing acceptance.",
    )
    return EvidencePackage(
        id="evpkg_test_01",
        decision_model_id=decision_model_id,
        requirements=[req],
        sources=[source],
        items=[item],
        claim_links=[link],
        gaps=[gap],
        summary="1 requirement fulfilled; 1 critical evidence gap identified on ACV assumption.",
    )


def _build_valid_arguments() -> Dict[str, ReasoningArgument]:
    """Builds standard valid arguments across the four perspectives."""
    return {
        "growth": ReasoningArgument(
            id="arg_growth_01",
            claim="Enterprise expansion opens access to 7-figure logo ARR tiers.",
            direction=ArgumentDirection.FAVORABLE,
            basis=ReasoningBasis.EVIDENCE,
            reasoning="Industry evidence shows enterprise buyers deliver sustainable LTV once onboarded.",
            evidence_item_ids=["evi_sales_cycle_stat"],
            related_entity_ids=["obj_arr_growth", "var_sales_headcount"],
        ),
        "finance": ReasoningArgument(
            id="arg_finance_01",
            claim="Sales team ramp requires substantial upfront capital with deferred payback.",
            direction=ArgumentDirection.UNFAVORABLE,
            basis=ReasoningBasis.ASSUMPTION,
            reasoning="Payback models hinge on the $80k ACV assumption holding true.",
            assumption_ids=["asm_acv_threshold"],
            related_entity_ids=["cnstr_burn_budget"],
        ),
        "customer": ReasoningArgument(
            id="arg_customer_01",
            claim="Enterprise buyers demand high-touch support and security audit compliance.",
            direction=ArgumentDirection.NEUTRAL,
            basis=ReasoningBasis.UNRESOLVED,
            reasoning="Customer success demands remain unresolved pending sales cycle discovery.",
            unknown_ids=["unk_cycle_length"],
            requirement_ids=["req_cycle_benchmark"],
            related_entity_ids=["stk_founders"],
        ),
        "risk": ReasoningArgument(
            id="arg_risk_01",
            claim="Extended sales cycles compound cash burn exposure if ACV underperforms.",
            direction=ArgumentDirection.UNFAVORABLE,
            basis=ReasoningBasis.MIXED,
            reasoning="Evidence confirms 6+ month sales cycles while ACV remains an unverified assumption with a high-impact gap.",
            evidence_item_ids=["evi_sales_cycle_stat"],
            assumption_ids=["asm_acv_threshold"],
            evidence_gap_ids=["gap_acv_evidence"],
            related_entity_ids=["trd_growth_vs_burn"],
        ),
    }


def _build_valid_perspectives() -> List[ReasoningPerspective]:
    """Builds the canonical set of 4 valid ReasoningPerspective instances."""
    args = _build_valid_arguments()
    return [
        ReasoningPerspective(
            id="persp_growth",
            perspective_type=PerspectiveType.GROWTH,
            summary="Enterprise expansion is the highest-leverage path to market scale.",
            arguments=[args["growth"]],
            critical_assumption_ids=["asm_acv_threshold"],
            evidence_gap_ids=["gap_acv_evidence"],
            unresolved_questions=["How fast will initial enterprise AEs ramp to quota?"],
            limitations=["Does not account for product readiness gaps in enterprise security."],
            opportunities=["Multi-year contracts with predictable cash flow."],
            concerns=["Channel distraction from high-velocity self-serve."],
        ),
        ReasoningPerspective(
            id="persp_finance",
            perspective_type=PerspectiveType.FINANCE,
            summary="Enterprise sales headcount commits fixed cash outlays against variable future revenue.",
            arguments=[args["finance"]],
            critical_assumption_ids=["asm_acv_threshold"],
            evidence_gap_ids=["gap_acv_evidence"],
            unresolved_questions=["What is the break-even ACV given a 6-month ramp?"],
            limitations=["Static budget model assumes linear rep onboarding costs."],
            opportunities=["Negative working capital from annual upfront billing."],
            concerns=["Runway compression if deal closing delays exceed 9 months."],
        ),
        ReasoningPerspective(
            id="persp_customer",
            perspective_type=PerspectiveType.CUSTOMER,
            summary="Enterprise procurement cycles require customized SLA and security commitments.",
            arguments=[args["customer"]],
            critical_assumption_ids=[],
            evidence_gap_ids=[],
            unresolved_questions=["Are existing SMB customers vulnerable to support neglect?"],
            limitations=["Customer feedback sampled primarily from mid-market segment."],
            opportunities=["High net-revenue retention through enterprise expansion."],
            concerns=["Customer churn if onboarding takes longer than sales cycle."],
        ),
        ReasoningPerspective(
            id="persp_risk",
            perspective_type=PerspectiveType.RISK,
            summary="One-way door exposure created by irreversible headcount expenditure under deal-size uncertainty.",
            arguments=[args["risk"]],
            critical_assumption_ids=["asm_acv_threshold"],
            evidence_gap_ids=["gap_acv_evidence"],
            unresolved_questions=["What is the unwinding cost if the initiative is aborted after 9 months?"],
            limitations=["Risk analysis assumes no external macro shocks."],
            opportunities=["Downside protection through phased, milestone-gated hiring."],
            concerns=["Overhiring ahead of confirmed product-market fit in enterprise."],
        ),
    ]


def _build_valid_disagreement() -> ReasoningDisagreement:
    """Builds a valid ReasoningDisagreement between Growth and Finance."""
    return ReasoningDisagreement(
        id="dis_growth_vs_finance_01",
        topic="Timing and pace of sales team headcount expansion",
        perspective_ids=["persp_growth", "persp_finance"],
        argument_ids=["arg_growth_01", "arg_finance_01"],
        positions={
            "persp_growth": "Hire all 8 AEs immediately to capture market window.",
            "persp_finance": "Phase hiring in cohorts of 2 pending ACV validation.",
        },
        evidence_item_ids=["evi_sales_cycle_stat"],
        assumption_ids=["asm_acv_threshold"],
        evidence_gap_ids=["gap_acv_evidence"],
        nature=DisagreementNature.ASSUMPTION_DEPENDENT,
    )


def _build_valid_synthesis() -> BoardSynthesis:
    """Builds a valid BoardSynthesis fixture."""
    return BoardSynthesis(
        summary="The board converges on enterprise market viability but diverges sharply on hiring velocity.",
        areas_of_agreement=[
            "Enterprise contracts represent substantial long-term value.",
            "Sales cycle length is approximately 6.4 months based on empirical benchmarks.",
        ],
        disagreement_ids=["dis_growth_vs_finance_01"],
        critical_assumption_ids=["asm_acv_threshold"],
        critical_evidence_gap_ids=["gap_acv_evidence"],
        evidence_sensitive_points=[
            "Empirical customer deal sizes from pilot discovery would resolve the growth-finance pacing dispute."
        ],
        unresolved_questions=[
            "Can we pilot 2 enterprise reps before committing to the full 8 headcount budget?"
        ],
    )


def _build_valid_reasoning_board(
    decision_model_id: str = "dec_test_01",
    evidence_package_id: str = "evpkg_test_01",
) -> ReasoningBoard:
    """Assembles a complete, valid canonical ReasoningBoard fixture."""
    return ReasoningBoard(
        id="board_test_01",
        decision_model_id=decision_model_id,
        evidence_package_id=evidence_package_id,
        perspectives=_build_valid_perspectives(),
        disagreements=[_build_valid_disagreement()],
        synthesis=_build_valid_synthesis(),
    )


# ------------------------------------------------------------------------------
# 1. Valid ReasoningBoard Construction
# ------------------------------------------------------------------------------

def test_1_valid_reasoning_board_succeeds() -> None:
    """Test 1: A fully populated, referentially valid ReasoningBoard succeeds instantiation."""
    board = _build_valid_reasoning_board()
    assert board.id == "board_test_01"
    assert board.decision_model_id == "dec_test_01"
    assert board.evidence_package_id == "evpkg_test_01"
    assert len(board.perspectives) == 4
    assert len(board.disagreements) == 1
    assert board.synthesis is not None
    assert board.created_at.tzinfo is not None

    # Test perspective lookup helpers
    growth = board.get_perspective(PerspectiveType.GROWTH)
    assert growth.perspective_type == PerspectiveType.GROWTH
    ordered = board.get_ordered_perspectives()
    assert [p.perspective_type for p in ordered] == [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]


# ------------------------------------------------------------------------------
# 2-5. Canonical Perspectives Constraints
# ------------------------------------------------------------------------------

def test_2_exactly_four_canonical_perspectives_required() -> None:
    """Test 2: Board with fewer or more than four perspectives is rejected."""
    perspectives = _build_valid_perspectives()

    # Case A: 3 perspectives (missing Risk)
    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_invalid_count",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=perspectives[:3],
            synthesis=_build_valid_synthesis(),
        )
    assert "perspectives" in str(exc_info.value)

    # Case B: 5 perspectives (duplicate Growth appended)
    extra_growth = copy.deepcopy(perspectives[0])
    extra_growth.id = "persp_growth_dup"
    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_invalid_count_5",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=perspectives + [extra_growth],
            synthesis=_build_valid_synthesis(),
        )
    assert "perspectives" in str(exc_info.value)


def test_3_missing_growth_rejected() -> None:
    """Test 3: Board lacking the canonical Growth perspective is rejected."""
    perspectives = _build_valid_perspectives()
    # Replace Growth with a duplicate Risk
    dup_risk = copy.deepcopy(perspectives[3])
    dup_risk.id = "persp_risk_dup"
    four_without_growth = [dup_risk, perspectives[1], perspectives[2], perspectives[3]]

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_missing_growth",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=four_without_growth,
            synthesis=_build_valid_synthesis(),
        )
    assert "missing canonical perspectives: growth" in str(exc_info.value).lower()


def test_4_duplicate_finance_rejected() -> None:
    """Test 4: Board containing duplicate Finance perspectives is rejected."""
    perspectives = _build_valid_perspectives()
    # Replace Customer with a second Finance
    dup_finance = copy.deepcopy(perspectives[1])
    dup_finance.id = "persp_finance_second"
    four_with_dup_finance = [perspectives[0], perspectives[1], dup_finance, perspectives[3]]

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_dup_finance",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=four_with_dup_finance,
            synthesis=_build_valid_synthesis(),
        )
    assert "missing canonical perspectives: customer" in str(exc_info.value).lower()


def test_5_unknown_adhoc_perspective_enum_rejected() -> None:
    """Test 5: An arbitrary or unknown perspective type string is rejected by PerspectiveType enum."""
    with pytest.raises(ValidationError) as exc_info:
        ReasoningPerspective(
            id="persp_legal",
            perspective_type="legal",  # type: ignore[arg-type]
            summary="Legal perspective evaluation.",
        )
    assert "perspective_type" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 6-11. Intra-Board ID Uniqueness and Cross-References
# ------------------------------------------------------------------------------

def test_6_duplicate_perspective_id_rejected() -> None:
    """Test 6: Duplicate perspective IDs across different perspectives are rejected."""
    perspectives = _build_valid_perspectives()
    perspectives[1].id = perspectives[0].id  # Both have persp_growth

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_dup_pid",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=perspectives,
            synthesis=_build_valid_synthesis(),
        )
    assert "duplicate perspective ids" in str(exc_info.value).lower()


def test_7_duplicate_argument_id_across_perspectives_rejected() -> None:
    """Test 7: Duplicate argument IDs across different perspectives are rejected."""
    perspectives = _build_valid_perspectives()
    # Give Risk argument the same ID as Growth argument
    perspectives[3].arguments[0].id = perspectives[0].arguments[0].id

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_dup_aid",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=perspectives,
            synthesis=_build_valid_synthesis(),
        )
    assert "duplicate argument ids" in str(exc_info.value).lower()


def test_8_duplicate_disagreement_id_rejected() -> None:
    """Test 8: Duplicate disagreement IDs inside the board are rejected."""
    d1 = _build_valid_disagreement()
    d2 = copy.deepcopy(d1)  # Same ID dis_growth_vs_finance_01

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_dup_did",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=_build_valid_perspectives(),
            disagreements=[d1, d2],
            synthesis=_build_valid_synthesis(),
        )
    assert "duplicate disagreement ids" in str(exc_info.value).lower()


def test_9_disagreement_referencing_nonexistent_perspective_rejected() -> None:
    """Test 9: Disagreement citing a perspective ID not present on the board is rejected."""
    disagreement = _build_valid_disagreement()
    disagreement.perspective_ids = ["persp_growth", "persp_nonexistent_alien"]

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_bad_dis_persp",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=_build_valid_perspectives(),
            disagreements=[disagreement],
            synthesis=_build_valid_synthesis(),
        )
    assert "nonexistent perspective id 'persp_nonexistent_alien'" in str(exc_info.value).lower()


def test_10_disagreement_referencing_nonexistent_argument_rejected() -> None:
    """Test 10: Disagreement citing an argument ID not present on the board is rejected."""
    disagreement = _build_valid_disagreement()
    disagreement.argument_ids = ["arg_growth_01", "arg_nonexistent_ghost"]

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_bad_dis_arg",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=_build_valid_perspectives(),
            disagreements=[disagreement],
            synthesis=_build_valid_synthesis(),
        )
    assert "nonexistent argument id 'arg_nonexistent_ghost'" in str(exc_info.value).lower()


def test_11_synthesis_referencing_nonexistent_disagreement_rejected() -> None:
    """Test 11: BoardSynthesis citing a disagreement ID not present on the board is rejected."""
    synthesis = _build_valid_synthesis()
    synthesis.disagreement_ids = ["dis_fabricated_999"]

    with pytest.raises(ValidationError) as exc_info:
        ReasoningBoard(
            id="board_bad_synth_dis",
            decision_model_id="dec_test_01",
            evidence_package_id="evpkg_test_01",
            perspectives=_build_valid_perspectives(),
            disagreements=[_build_valid_disagreement()],
            synthesis=synthesis,
        )
    assert "nonexistent disagreement id 'dis_fabricated_999'" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 12-16. Epistemic Basis Validation in ReasoningArgument
# ------------------------------------------------------------------------------

def test_12_evidence_basis_without_evidence_item_id_rejected() -> None:
    """Test 12: An argument with basis=EVIDENCE must reference at least one evidence_item_id."""
    with pytest.raises(ValidationError) as exc_info:
        ReasoningArgument(
            id="arg_ev_empty",
            claim="Claims empirical backing with zero evidence IDs.",
            direction=ArgumentDirection.FAVORABLE,
            basis=ReasoningBasis.EVIDENCE,
            reasoning="Asserts strong factual foundation but provides no citations.",
            evidence_item_ids=[],  # Empty
        )
    assert "must reference at least one evidence_item_id" in str(exc_info.value)


def test_13_assumption_basis_without_assumption_id_rejected() -> None:
    """Test 13: An argument with basis=ASSUMPTION must reference at least one assumption_id."""
    with pytest.raises(ValidationError) as exc_info:
        ReasoningArgument(
            id="arg_asm_empty",
            claim="Claims assumption backing with zero assumption IDs.",
            direction=ArgumentDirection.UNFAVORABLE,
            basis=ReasoningBasis.ASSUMPTION,
            reasoning="Asserts reliance on assumption but links no IDs.",
            assumption_ids=[],  # Empty
        )
    assert "must reference at least one assumption_id" in str(exc_info.value)


def test_14_unresolved_basis_without_unresolved_dependency_rejected() -> None:
    """Test 14: An argument with basis=UNRESOLVED must reference an unknown, gap, or requirement."""
    with pytest.raises(ValidationError) as exc_info:
        ReasoningArgument(
            id="arg_unres_empty",
            claim="Claims uncertainty without citing any unknowns or gaps.",
            direction=ArgumentDirection.NEUTRAL,
            basis=ReasoningBasis.UNRESOLVED,
            reasoning="Uncertainty asserted in the abstract.",
            unknown_ids=[],
            evidence_gap_ids=[],
            requirement_ids=[],
        )
    assert "must reference at least one unresolved dependency" in str(exc_info.value)


def test_15_valid_mixed_basis_succeeds() -> None:
    """Test 15: An argument with basis=MIXED referencing at least two distinct epistemic categories succeeds."""
    arg = ReasoningArgument(
        id="arg_mixed_valid",
        claim="Blends empirical benchmarks with unverified margin assumptions.",
        direction=ArgumentDirection.MIXED,
        basis=ReasoningBasis.MIXED,
        reasoning="Draws upon sales cycle benchmark while hinging on ACV assumption.",
        evidence_item_ids=["evi_sales_cycle_stat"],
        assumption_ids=["asm_acv_threshold"],
    )
    assert arg.basis == ReasoningBasis.MIXED
    assert len(arg.evidence_item_ids) == 1
    assert len(arg.assumption_ids) == 1


def test_16_invalid_mixed_basis_with_insufficient_dependency_categories_rejected() -> None:
    """Test 16: An argument with basis=MIXED containing fewer than two distinct epistemic categories is rejected."""
    # Case A: Only evidence provided
    with pytest.raises(ValidationError) as exc_info:
        ReasoningArgument(
            id="arg_mixed_only_evidence",
            claim="Claims mixed basis but only has evidence.",
            direction=ArgumentDirection.MIXED,
            basis=ReasoningBasis.MIXED,
            reasoning="Only evidence provided.",
            evidence_item_ids=["evi_01"],
            assumption_ids=[],
            unknown_ids=[],
        )
    assert "must contain references across at least two distinct epistemic categories" in str(exc_info.value)

    # Case B: Only unresolved dependencies provided (unknown and gap both belong to unresolved category)
    with pytest.raises(ValidationError) as exc_info:
        ReasoningArgument(
            id="arg_mixed_only_unresolved",
            claim="Claims mixed basis but only has unresolved items.",
            direction=ArgumentDirection.MIXED,
            basis=ReasoningBasis.MIXED,
            reasoning="Only unknowns and gaps provided.",
            evidence_item_ids=[],
            assumption_ids=[],
            unknown_ids=["unk_01"],
            evidence_gap_ids=["gap_01"],
        )
    assert "must contain references across at least two distinct epistemic categories" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 17-25. Cross-Artifact Referential Integrity Validator
# ------------------------------------------------------------------------------

def test_17_wrong_decision_model_id_rejected_by_cross_artifact_validator() -> None:
    """Test 17: Board with mismatched decision_model_id is rejected by validate_reasoning_references."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id="dec_mismatched_999", evidence_package_id=pkg.id)

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "decision_model_id 'dec_mismatched_999' does not match DecisionModel id 'dec_test_01'" in str(exc_info.value)


def test_18_wrong_evidence_package_id_rejected() -> None:
    """Test 18: Board with mismatched evidence_package_id is rejected by validate_reasoning_references."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id="evpkg_mismatched_888")

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "evidence_package_id 'evpkg_mismatched_888' does not match EvidencePackage id 'evpkg_test_01'" in str(exc_info.value)


def test_19_nonexistent_evidence_item_id_rejected() -> None:
    """Test 19: An argument referencing an evidence_item_id absent from the EvidencePackage is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Growth argument to a nonexistent evidence item ID
    board.perspectives[0].arguments[0].evidence_item_ids = ["evi_ghost_finding"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent evidence_item_id 'evi_ghost_finding'" in str(exc_info.value)


def test_20_nonexistent_requirement_id_rejected() -> None:
    """Test 20: An argument referencing a requirement_id absent from the EvidencePackage is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Customer argument to a nonexistent requirement ID
    board.perspectives[2].arguments[0].requirement_ids = ["req_unregistered_99"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent requirement_id 'req_unregistered_99'" in str(exc_info.value)


def test_21_nonexistent_assumption_id_rejected() -> None:
    """Test 21: An argument or perspective referencing an assumption_id absent from DecisionModel is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Finance argument to a nonexistent assumption ID
    board.perspectives[1].arguments[0].assumption_ids = ["asm_hallucinated_assumption"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent assumption_id 'asm_hallucinated_assumption'" in str(exc_info.value)


def test_22_nonexistent_unknown_id_rejected() -> None:
    """Test 22: An argument referencing an unknown_id absent from DecisionModel is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Customer argument to a nonexistent unknown ID
    board.perspectives[2].arguments[0].unknown_ids = ["unk_nonexistent_mystery"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent unknown_id 'unk_nonexistent_mystery'" in str(exc_info.value)


def test_23_nonexistent_evidence_gap_id_rejected() -> None:
    """Test 23: An argument or perspective referencing an evidence_gap_id absent from EvidencePackage is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Risk perspective critical gap to a nonexistent gap ID
    board.perspectives[3].evidence_gap_ids = ["gap_nonexistent_chasm"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent evidence gap id 'gap_nonexistent_chasm'" in str(exc_info.value).lower()


def test_24_nonexistent_related_entity_id_rejected() -> None:
    """Test 24: An argument referencing an entity ID absent from DecisionModel is rejected."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Point Growth argument to a nonexistent related entity ID
    board.perspectives[0].arguments[0].related_entity_ids = ["var_nonexistent_variable_99"]

    with pytest.raises(ValueError) as exc_info:
        validate_reasoning_references(board, model, pkg)
    assert "nonexistent related_entity_id 'var_nonexistent_variable_99'" in str(exc_info.value)


def test_25_valid_related_entity_references_succeed() -> None:
    """Test 25: Valid related entity references across all canonical DecisionModel types resolve cleanly."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    # Attach all legitimate DecisionModel entity IDs to Growth argument
    board.perspectives[0].arguments[0].related_entity_ids = [
        model.id,                           # Decision model itself
        model.objectives[0].id,             # Objective
        model.variables[0].id,              # Variable
        model.constraints[0].id,            # Constraint
        model.stakeholders[0].id,           # Stakeholder
        model.tradeoffs[0].id,              # Tradeoff
        model.assumptions[0].id,            # Assumption
        model.unknowns[0].id,               # Unknown
    ]

    # Must pass without raising any exception
    validate_reasoning_references(board, model, pkg)


# ------------------------------------------------------------------------------
# 26-28. Immutability Invariant Verification
# ------------------------------------------------------------------------------

def test_26_upstream_decision_model_is_unchanged_after_validation() -> None:
    """Test 26: validate_reasoning_references does not mutate the upstream DecisionModel."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    snapshot_before = model.model_dump()
    validate_reasoning_references(board, model, pkg)
    snapshot_after = model.model_dump()

    assert snapshot_before == snapshot_after


def test_27_upstream_evidence_package_is_unchanged_after_validation() -> None:
    """Test 27: validate_reasoning_references does not mutate the upstream EvidencePackage."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    snapshot_before = pkg.model_dump()
    validate_reasoning_references(board, model, pkg)
    snapshot_after = pkg.model_dump()

    assert snapshot_before == snapshot_after


def test_28_reasoning_board_is_unchanged_after_validation() -> None:
    """Test 28: validate_reasoning_references does not mutate the ReasoningBoard."""
    model = _build_valid_decision_model()
    pkg = _build_valid_evidence_package(decision_model_id=model.id)
    board = _build_valid_reasoning_board(decision_model_id=model.id, evidence_package_id=pkg.id)

    snapshot_before = board.model_dump()
    validate_reasoning_references(board, model, pkg)
    snapshot_after = board.model_dump()

    assert snapshot_before == snapshot_after


# ------------------------------------------------------------------------------
# 29-30. Candidate Schemas and Timezone Conventions
# ------------------------------------------------------------------------------

def test_29_candidate_schemas_contain_no_authoritative_day_4_ids() -> None:
    """Test 29: Candidate LLM output schemas do not contain authoritative Day 4 ID fields."""
    candidate_classes = [
        CandidateReasoningArgument,
        CandidatePerspectiveAnalysis,
        CandidateDisagreement,
        CandidateBoardSynthesis,
    ]

    for cls in candidate_classes:
        assert "id" not in cls.model_fields, f"Candidate schema {cls.__name__} must not contain authoritative 'id' field."

    # Verify instantiation of CandidateReasoningArgument without ID
    cand_arg = CandidateReasoningArgument(
        claim="Market timing is optimal for enterprise entry.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Market research supports timing.",
        evidence_item_ids=["evi_01"],
    )
    assert not hasattr(cand_arg, "id")
    assert cand_arg.claim == "Market timing is optimal for enterprise entry."

    # Verify CandidatePerspectiveAnalysis without ID
    cand_persp = CandidatePerspectiveAnalysis(
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth potential is significant.",
        arguments=[cand_arg],
    )
    assert not hasattr(cand_persp, "id")

    # Verify CandidateDisagreement without ID
    cand_dis = CandidateDisagreement(
        topic="Timing of launch",
        perspective_types=[PerspectiveType.GROWTH, PerspectiveType.FINANCE],
        positions={"growth": "Go fast", "finance": "Go slow"},
        nature=DisagreementNature.INTERPRETATION,
    )
    assert not hasattr(cand_dis, "id")

    # Verify CandidateBoardSynthesis without ID
    cand_synth = CandidateBoardSynthesis(
        summary="Board broadly aligned with tactical disagreements.",
        areas_of_agreement=["Enter enterprise"],
        disagreement_ids=["dis_growth_finance_01"],
    )
    assert not hasattr(cand_synth, "id")


def test_30_created_at_timezone_handling() -> None:
    """Test 30: created_at enforces timezone-aware UTC datetime matching repository conventions."""
    # 1. Default generation is timezone-aware UTC
    board = _build_valid_reasoning_board()
    assert board.created_at.tzinfo is not None
    assert board.created_at.tzinfo == timezone.utc

    # 2. Explicit UTC timestamp is preserved
    explicit_utc = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    board_utc = ReasoningBoard(
        id="board_explicit_utc",
        decision_model_id="dec_test_01",
        evidence_package_id="evpkg_test_01",
        perspectives=_build_valid_perspectives(),
        disagreements=[_build_valid_disagreement()],
        synthesis=_build_valid_synthesis(),
        created_at=explicit_utc,
    )
    assert board_utc.created_at == explicit_utc

    # 3. Naive datetime is coerced to UTC matching evidence.py convention
    naive_dt = datetime(2026, 10, 8, 12, 0, 0)
    board_coerced = ReasoningBoard(
        id="board_naive_coerced",
        decision_model_id="dec_test_01",
        evidence_package_id="evpkg_test_01",
        perspectives=_build_valid_perspectives(),
        disagreements=[_build_valid_disagreement()],
        synthesis=_build_valid_synthesis(),
        created_at=naive_dt,
    )
    assert board_coerced.created_at.tzinfo == timezone.utc


# ------------------------------------------------------------------------------
# 31. Strict Architectural Invariant Verification
# ------------------------------------------------------------------------------

def test_31_architecture_reasoning_board_contains_no_forbidden_fields() -> None:
    """Test 31: Architectural verification that ReasoningBoard contains no recommendation/voting/scenario fields.

    Explicitly forbidden fields per canonical Day 4 architecture:
    - recommendation / recommended_action
    - final_decision / winning_option
    - vote / votes / board_vote
    - consensus_score / consensus_percentage / approval_percentage
    - scenario / scenarios
    - resilience / resilience_score
    - what_if
    """
    forbidden_substrings = [
        "recommend",
        "final_decision",
        "winning",
        "vote",
        "consensus_score",
        "consensus_pct",
        "approval_pct",
        "scenario",
        "resilience",
        "what_if",
    ]

    models_to_inspect = [
        ReasoningBoard,
        ReasoningPerspective,
        ReasoningArgument,
        ReasoningDisagreement,
        BoardSynthesis,
        CandidateReasoningArgument,
        CandidatePerspectiveAnalysis,
        CandidateDisagreement,
        CandidateBoardSynthesis,
    ]

    for model_cls in models_to_inspect:
        for field_name in model_cls.model_fields.keys():
            lower_name = field_name.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lower_name, (
                    f"Forbidden pattern '{forbidden}' found in field '{field_name}' "
                    f"of model '{model_cls.__name__}'. Day 4 must not introduce recommendation, "
                    f"voting, scenario, resilience, or what-if semantics."
                )
