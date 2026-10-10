"""Tests for AURA Decision Recommendation & Action Planning Engine (Day 5 Phase 1).

Deterministic test suite covering:
1. Valid structured recommendation (proceed status, verified evidence/assumptions/gaps/disagreements).
2. Conditional recommendation with decision gates and milestones.
3. Insufficient-evidence outcome (honest status, non-ready readiness, validation actions).
4. Invalid evidence reference fails closed (RecommendationValidationError).
5. Invalid assumption reference fails closed (RecommendationValidationError).
6. Invalid evidence gap reference fails closed (RecommendationValidationError).
7. Invalid disagreement reference fails closed (RecommendationValidationError).
8. Harmless placeholder reference normalization ('none', 'N/A', 'null', etc.).
9. Missing required fields or malformed candidate schema fails closed.
10. Action-plan validation:
    - Empty action plan rejected.
    - Nonexistent dependency rejected.
    - Self-referential dependency rejected.
    - Cyclic dependency graph (DFS cycle detection) rejected.
11. Deadline propagation and timeout behavior:
    - Expired monotonic deadline before LLM call raises RecommendationEvaluationError / RecommendationServiceError.
    - Upstream LLMTimeoutError wrapped cleanly.
12. Semantic decision consistency:
    - 'insufficient_evidence' cannot have readiness 'ready'.
    - 'reject' cannot have readiness 'ready'.
    - 'proceed' cannot have readiness 'blocked'.
    - 'insufficient_evidence' with unconditional proceed text rejected.
13. Content-derived deterministic recommendation ID (rec_<sha256[:32]>).
14. Upstream artifact binding validation (ID mismatch fails closed).
15. Preservation of upstream Day 4 contracts (immutable DecisionModel, EvidencePackage, ReasoningBoard).
16. Prompt builder bounded length enforcement and prompt injection isolation.
17. RecommendationService facade orchestration with injected MockLLMClient.
"""

from datetime import datetime, timezone
import copy
import time
from typing import Any, List, Optional
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
    EvidenceStance,
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
from app.schemas.recommendation import (
    ActionPriority,
    ActionTimeHorizon,
    CandidateActionItem,
    CandidateActionPlan,
    CandidateAlternativeOption,
    CandidateDecisionGate,
    CandidateDecisionRecommendation,
    CandidateUncertaintyAssessment,
    DecisionReadiness,
    DecisionRecommendation,
    DecisionStatus,
    EvidenceStrength,
    RecommendationStability,
    generate_deterministic_recommendation_id,
)
from app.services.llm.client import LLMClient, LLMConfig, LLMTimeoutError
from app.services.recommendation.generator import RecommendationGenerator
from app.services.recommendation.prompt_builder import (
    MAX_RECOMMENDATION_PROMPT_CHARS,
    build_recommendation_prompt,
    build_recommendation_system_instruction,
    truncate_narrative,
)
from app.services.recommendation.service import RecommendationService
from app.services.recommendation.validator import (
    RecommendationError,
    RecommendationEvaluationError,
    RecommendationPromptError,
    RecommendationServiceError,
    RecommendationValidationError,
    clean_id_list,
    validate_action_dependencies,
    validate_candidate_recommendation,
    validate_decision_consistency,
    validate_recommendation_inputs,
    validate_recommendation_references,
)


# ------------------------------------------------------------------------------
# Test Doubles & Fixtures
# ------------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Deterministic in-memory test double for structured recommendation generation."""

    def __init__(self, response_candidate: Optional[CandidateDecisionRecommendation] = None) -> None:
        self.response_candidate = response_candidate
        self.call_count = 0
        self.last_prompt: Optional[str] = None
        self.last_system_instruction: Optional[str] = None
        self.last_response_schema: Optional[Any] = None
        self.last_deadline_monotonic: Optional[float] = None
        self.raise_exc: Optional[Exception] = None

    def generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        self.last_response_schema = response_schema
        self.last_deadline_monotonic = deadline_monotonic

        if self.raise_exc:
            raise self.raise_exc

        if self.response_candidate:
            return self.response_candidate

        # Default valid candidate
        return build_valid_candidate()

    def generate_text(self, *args, **kwargs):
        raise NotImplementedError("generate_text not used in recommendation engine.")


def build_test_upstream_artifacts():
    """Builds valid, consistent Day 4 DecisionModel, EvidencePackage, and ReasoningBoard."""
    dm = DecisionModel(
        id="dec_enterprise_01",
        decision=Decision(
            raw_prompt="Expand into enterprise tier-1 market?",
            summary="Strategic decision to expand sales team and product for enterprise tier.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="High execution risk and long enterprise sales cycles.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(id="obj_arr", description="Attain $20M ARR within 24 months", is_primary=True),
        ],
        variables=[
            Variable(
                id="var_acv",
                name="Average Contract Value",
                description="Annual spend per enterprise account",
                variable_type=VariableType.CURRENCY,
            ),
        ],
        constraints=[
            Constraint(id="cnstr_cash", name="Runway Constraint", description="Maintain >= 18 months runway"),
        ],
        stakeholders=[
            Stakeholder(id="stk_board", group="Board", impact_nature="Shareholder returns"),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_cash",
                upside="High market dominance",
                downside="Higher upfront cash burn",
            ),
        ],
        assumptions=[
            Assumption(id="asm_market_tam", statement="Enterprise TAM exceeds $3B"),
            Assumption(id="asm_win_rate", statement="Enterprise competitive win rate >= 20%"),
        ],
        unknowns=[
            Unknown(id="unk_competitor_pricing", question="Competitor discounting response"),
        ],
        key_questions=["Can product fulfill SOC-2 and enterprise compliance requirements?"],
    )

    src = Source(
        id="src_gartner",
        title="Gartner Magic Quadrant Report",
        source_type=SourceType.INDUSTRY_REPORT,
        url="https://example.com/gartner-report.pdf",
        reliability_score=0.9,
    )
    item = EvidenceItem(
        id="evi_demand_growth",
        source_id="src_gartner",
        content="Enterprise category spend grew 28% year-over-year in 2025.",
    )
    req = EvidenceRequirement(
        id="req_demand",
        description="Verify tier-1 market category expansion",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        target_entity_id="obj_arr",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        status=RequirementStatus.FULFILLED,
    )
    gap = EvidenceGap(
        id="gap_retention_cohort",
        gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE,
        target_entity_id="obj_arr",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        description="No empirical data on multi-year enterprise logo retention.",
    )

    ep = EvidencePackage(
        id="pkg_enterprise_01",
        decision_model_id="dec_enterprise_01",
        summary="Empirical evidence portfolio for enterprise expansion.",
        sources=[src],
        items=[item],
        requirements=[req],
        gaps=[gap],
        claim_links=[],
    )

    arg_g = ReasoningArgument(
        id="arg_g1",
        claim="Market tailwinds strongly favor enterprise expansion.",
        direction=ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        reasoning="Gartner market spend growth validates demand.",
        evidence_item_ids=["evi_demand_growth"],
        requirement_ids=["req_demand"],
        related_entity_ids=["obj_arr"],
    )
    arg_f = ReasoningArgument(
        id="arg_f1",
        claim="Runway discipline requires keeping burn under strict ceilings.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        reasoning="Win rate assumptions remain unproven.",
        assumption_ids=["asm_win_rate"],
        related_entity_ids=["cnstr_cash"],
    )
    arg_c = ReasoningArgument(
        id="arg_c1",
        claim="Enterprise customers require custom integrations.",
        direction=ArgumentDirection.NEUTRAL,
        basis=ReasoningBasis.INFERENCE,
        reasoning="Complex requirements will lengthen sales cycles.",
        related_entity_ids=["var_acv"],
    )
    arg_r = ReasoningArgument(
        id="arg_r1",
        claim="Incumbent aggressive discounting could erode margins.",
        direction=ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        reasoning="Competitor reaction is unknown.",
        unknown_ids=["unk_competitor_pricing"],
        related_entity_ids=["obj_arr"],
    )

    p_growth = ReasoningPerspective(
        id="persp_growth",
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective advocates aggressive enterprise sales hiring.",
        arguments=[arg_g],
        critical_assumption_ids=["asm_market_tam"],
        evidence_gap_ids=["gap_retention_cohort"],
    )
    p_finance = ReasoningPerspective(
        id="persp_finance",
        perspective_type=PerspectiveType.FINANCE,
        summary="Finance perspective urges capital preservation and phased milestones.",
        arguments=[arg_f],
        critical_assumption_ids=["asm_win_rate"],
    )
    p_customer = ReasoningPerspective(
        id="persp_customer",
        perspective_type=PerspectiveType.CUSTOMER,
        summary="Customer perspective focuses on implementation and security standards.",
        arguments=[arg_c],
    )
    p_risk = ReasoningPerspective(
        id="persp_risk",
        perspective_type=PerspectiveType.RISK,
        summary="Risk perspective highlights pricing pressure and incumbent reaction.",
        arguments=[arg_r],
        evidence_gap_ids=["gap_retention_cohort"],
    )

    dis = ReasoningDisagreement(
        id="dis_growth_finance_01",
        topic="Sales expansion speed vs capital runway preservation",
        perspective_ids=["persp_growth", "persp_finance"],
        argument_ids=["arg_g1", "arg_f1"],
        positions={"persp_growth": "Scale headcount", "persp_finance": "Phase headcount"},
        evidence_item_ids=["evi_demand_growth"],
        assumption_ids=["asm_win_rate"],
        evidence_gap_ids=["gap_retention_cohort"],
        nature=DisagreementNature.EVIDENCE_DEPENDENT,
    )

    synth = BoardSynthesis(
        summary="The Board agrees enterprise market demand is real, but split on speed versus runway risk.",
        areas_of_agreement=["Target tier-1 accounts only with existing product capabilities."],
        disagreement_ids=["dis_growth_finance_01"],
        critical_assumption_ids=["asm_win_rate"],
        critical_evidence_gap_ids=["gap_retention_cohort"],
        evidence_sensitive_points=["Enterprise sales cycle duration."],
        unresolved_questions=["Can the current architecture meet SOC-2 compliance?"],
    )

    rb = ReasoningBoard(
        id="rbd_enterprise_01",
        decision_model_id="dec_enterprise_01",
        evidence_package_id="pkg_enterprise_01",
        perspectives=[p_growth, p_finance, p_customer, p_risk],
        disagreements=[dis],
        synthesis=synth,
        created_at=datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc),
    )

    return dm, ep, rb


def build_valid_candidate() -> CandidateDecisionRecommendation:
    """Builds a semantically sound CandidateDecisionRecommendation with valid references."""
    return CandidateDecisionRecommendation(
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute a phased expansion into tier-1 enterprise accounts with milestone gating.",
        executive_rationale=(
            "Empirical evidence demonstrates strong market demand growth (evi_demand_growth). "
            "However, runway constraints necessitate a phased approach rather than unconstrained hiring."
        ),
        supporting_evidence_item_ids=["evi_demand_growth"],
        relevant_assumption_ids=["asm_market_tam", "asm_win_rate"],
        relevant_evidence_gap_ids=["gap_retention_cohort"],
        unresolved_disagreement_ids=["dis_growth_finance_01"],
        alternative_options=[
            CandidateAlternativeOption(
                name="Aggressive Uncapped Expansion",
                description="Hire 10 enterprise Account Executives immediately.",
                tradeoffs=["Faster market capture", "Severe runway depletion risk"],
                why_not_recommended="Violates cnstr_cash runway requirement if conversion lags.",
            ),
            CandidateAlternativeOption(
                name="Pure Status Quo (Mid-Market Only)",
                description="Remain focused exclusively on mid-market accounts.",
                tradeoffs=["Preserves cash", "Misses 28% market category expansion"],
                why_not_recommended="Fails to capture primary growth objective obj_arr.",
            ),
        ],
        uncertainty_assessment=CandidateUncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
            critical_missing_information=["Multi-year enterprise logo retention cohort data"],
            conditions_changing_recommendation=[
                "Enterprise sales win rate falls below 15% across initial pilot accounts.",
                "Competitor initiates predatory discounting exceeding 30%.",
            ],
            assumptions_relied_upon=["asm_win_rate"],
            evidence_gaps_relied_upon=["gap_retention_cohort"],
        ),
        action_plan=CandidateActionPlan(
            summary="Three-stage phased implementation: pilot validation, hiring expansion, enterprise roll-out.",
            actions=[
                CandidateActionItem(
                    title="Enterprise Pilot Validation",
                    objective="Validate enterprise conversion rate on 5 lighthouse accounts.",
                    description="Run targeted outreach to validate sales cycle duration and pricing.",
                    priority=ActionPriority.HIGH,
                    responsible_role="Head of Sales",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    dependencies=[],
                    success_metrics=["Secure 3 signed LOIs with ACV > $100k", "Conversion rate >= 20%"],
                    risk_mitigations=["Cap initial engagement scope to core features"],
                    decision_gates=[
                        CandidateDecisionGate(
                            condition="At least 3 LOIs signed within 90 days",
                            target_milestone="Q1 Pilot Review",
                            verification_method="Audit signed commercial contracts",
                            fallback_action="Pause enterprise hiring and refine mid-market tier",
                        )
                    ],
                    fallback_action="Revert sales capacity to mid-market accounts",
                ),
                CandidateActionItem(
                    title="Security & Compliance Certification",
                    objective="Attain SOC-2 Type II readiness for enterprise buyers.",
                    description="Engage auditor and implement mandatory access controls.",
                    priority=ActionPriority.CRITICAL,
                    responsible_role="VP Engineering",
                    time_horizon=ActionTimeHorizon.NEAR_TERM,
                    dependencies=["Enterprise Pilot Validation"],
                    success_metrics=["SOC-2 readiness report completed"],
                    risk_mitigations=["Retain external virtual CISO advisory"],
                    decision_gates=[],
                    fallback_action=None,
                ),
            ],
            key_milestones=[
                "Day 30: Initial outreach cohort launched",
                "Day 90: Pilot gate evaluation and contract review",
                "Day 180: SOC-2 certification and sales team expansion",
            ],
        ),
    )


# ------------------------------------------------------------------------------
# Test 1: Valid Structured Recommendation
# ------------------------------------------------------------------------------

def test_01_valid_structured_recommendation():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()

    fixed_now = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)
    rec = validate_candidate_recommendation(
        candidate=candidate,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
        clock=lambda: fixed_now,
    )

    assert isinstance(rec, DecisionRecommendation)
    assert rec.decision_status == DecisionStatus.PROCEED
    assert rec.decision_model_id == dm.id
    assert rec.evidence_package_id == ep.id
    assert rec.reasoning_board_id == rb.id
    assert rec.id.startswith("rec_")
    assert len(rec.id) == 36  # "rec_" + 32 chars
    assert rec.created_at == fixed_now

    # Referential checks
    assert rec.supporting_evidence_item_ids == ["evi_demand_growth"]
    assert rec.relevant_assumption_ids == ["asm_market_tam", "asm_win_rate"]
    assert rec.relevant_evidence_gap_ids == ["gap_retention_cohort"]
    assert rec.unresolved_disagreement_ids == ["dis_growth_finance_01"]

    # Action plan
    assert len(rec.action_plan.actions) == 2
    act_1 = rec.action_plan.actions[0]
    act_2 = rec.action_plan.actions[1]
    assert act_1.id == "act_1"
    assert act_2.id == "act_2"
    assert act_1.dependencies == []
    assert act_2.dependencies == ["act_1"]  # Mapped from title to ID
    assert len(act_1.decision_gates) == 1
    assert act_1.decision_gates[0].id == "gate_1_1"

    # Uncertainty
    assert rec.uncertainty_assessment.decision_readiness == DecisionReadiness.READY
    assert rec.uncertainty_assessment.evidence_strength == EvidenceStrength.MODERATE
    assert rec.uncertainty_assessment.recommendation_stability == RecommendationStability.HIGH


# ------------------------------------------------------------------------------
# Test 2: Conditional Recommendation
# ------------------------------------------------------------------------------

def test_02_conditional_recommendation():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()
    candidate.decision_status = DecisionStatus.CONDITIONAL
    candidate.uncertainty_assessment.decision_readiness = DecisionReadiness.CONDITIONAL
    candidate.recommended_action = "Conditionally approve expansion subject to gate passing."

    rec = validate_candidate_recommendation(
        candidate=candidate,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
    )
    assert rec.decision_status == DecisionStatus.CONDITIONAL
    assert rec.uncertainty_assessment.decision_readiness == DecisionReadiness.CONDITIONAL


# ------------------------------------------------------------------------------
# Test 3: Insufficient Evidence Outcome
# ------------------------------------------------------------------------------

def test_03_insufficient_evidence_outcome():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()
    candidate.decision_status = DecisionStatus.INSUFFICIENT_EVIDENCE
    candidate.recommended_action = "Defer expansion decision until customer cohort retention data is gathered."
    candidate.uncertainty_assessment.decision_readiness = DecisionReadiness.NEEDS_VALIDATION
    candidate.uncertainty_assessment.evidence_strength = EvidenceStrength.INSUFFICIENT
    candidate.uncertainty_assessment.recommendation_stability = RecommendationStability.VOLATILE

    rec = validate_candidate_recommendation(
        candidate=candidate,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
    )
    assert rec.decision_status == DecisionStatus.INSUFFICIENT_EVIDENCE
    assert rec.uncertainty_assessment.decision_readiness == DecisionReadiness.NEEDS_VALIDATION
    assert rec.uncertainty_assessment.evidence_strength == EvidenceStrength.INSUFFICIENT


# ------------------------------------------------------------------------------
# Test 4: Invalid Evidence Reference Fails Closed
# ------------------------------------------------------------------------------

def test_04_invalid_evidence_reference_fails_closed():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()
    candidate.supporting_evidence_item_ids = ["evi_demand_growth", "evi_hallucinated_999"]

    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_candidate_recommendation(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "nonexistent evidence item ID" in str(exc_info.value)
    assert exc_info.value.details.get("rule") == "nonexistent_evidence_item_id"


# ------------------------------------------------------------------------------
# Test 5: Invalid Assumption or Gap Reference Fails Closed
# ------------------------------------------------------------------------------

def test_05_invalid_assumption_or_gap_reference_fails_closed():
    dm, ep, rb = build_test_upstream_artifacts()

    # Invalid assumption
    candidate1 = build_valid_candidate()
    candidate1.relevant_assumption_ids = ["asm_unreal_404"]
    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_candidate_recommendation(
            candidate=candidate1,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "nonexistent assumption ID" in str(exc_info.value)

    # Invalid gap
    candidate2 = build_valid_candidate()
    candidate2.relevant_evidence_gap_ids = ["gap_fake_999"]
    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_candidate_recommendation(
            candidate=candidate2,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "nonexistent evidence gap ID" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Test 6: Invalid Disagreement Reference Fails Closed
# ------------------------------------------------------------------------------

def test_06_invalid_disagreement_reference_fails_closed():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()
    candidate.unresolved_disagreement_ids = ["dis_bogus_dispute"]

    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_candidate_recommendation(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "nonexistent disagreement ID" in str(exc_info.value)
    assert exc_info.value.details.get("rule") == "nonexistent_disagreement_id"


# ------------------------------------------------------------------------------
# Test 7: Harmless Placeholder Reference Normalization
# ------------------------------------------------------------------------------

def test_07_placeholder_reference_normalization():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()

    # Inject harmless LLM noise tokens
    candidate.supporting_evidence_item_ids = ["evi_demand_growth", "none", "N/A", "  "]
    candidate.relevant_assumption_ids = ["na", "null", "no_assumptions", "asm_win_rate"]
    candidate.relevant_evidence_gap_ids = ["no_gaps", "gap_retention_cohort", "[]"]
    candidate.unresolved_disagreement_ids = ["none_detected", "no_disagreements"]

    rec = validate_candidate_recommendation(
        candidate=candidate,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
    )
    # Normalized cleanly
    assert rec.supporting_evidence_item_ids == ["evi_demand_growth"]
    assert rec.relevant_assumption_ids == ["asm_win_rate"]
    assert rec.relevant_evidence_gap_ids == ["gap_retention_cohort"]
    assert rec.unresolved_disagreement_ids == []


# ------------------------------------------------------------------------------
# Test 8: Missing Required Fields Fails Closed
# ------------------------------------------------------------------------------

def test_08_missing_required_fields_fails_closed():
    with pytest.raises(Exception):
        # Missing recommended_action and executive_rationale
        CandidateDecisionRecommendation(
            decision_status=DecisionStatus.PROCEED,
        )


# ------------------------------------------------------------------------------
# Test 9: Malformed Model Output / Action Plan Invariants
# ------------------------------------------------------------------------------

def test_09_action_plan_empty_actions_rejected():
    dm, ep, rb = build_test_upstream_artifacts()
    candidate = build_valid_candidate()
    candidate.action_plan.actions = []

    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_candidate_recommendation(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "at least one action item" in str(exc_info.value)


def test_10_action_plan_dependency_validation():
    dm, ep, rb = build_test_upstream_artifacts()

    # 1. Nonexistent dependency target
    candidate1 = build_valid_candidate()
    candidate1.action_plan.actions[1].dependencies = ["act_999_nonexistent"]
    with pytest.raises(RecommendationValidationError) as exc_info1:
        validate_candidate_recommendation(
            candidate=candidate1,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "references nonexistent dependency" in str(exc_info1.value)

    # 2. Self-referential dependency
    candidate2 = build_valid_candidate()
    candidate2.action_plan.actions[0].dependencies = ["act_1"]
    with pytest.raises(RecommendationValidationError) as exc_info2:
        validate_candidate_recommendation(
            candidate=candidate2,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "self-referential dependency" in str(exc_info2.value)

    # 3. Cyclic dependency (act_1 -> act_2, and act_2 -> act_1)
    candidate3 = build_valid_candidate()
    candidate3.action_plan.actions[0].dependencies = ["act_2"]
    candidate3.action_plan.actions[1].dependencies = ["act_1"]
    with pytest.raises(RecommendationValidationError) as exc_info3:
        validate_candidate_recommendation(
            candidate=candidate3,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "Cyclic action dependency detected" in str(exc_info3.value)


# ------------------------------------------------------------------------------
# Test 11: Semantic Decision Consistency
# ------------------------------------------------------------------------------

def test_11_semantic_decision_consistency():
    dm, ep, rb = build_test_upstream_artifacts()

    # A. Insufficient evidence cannot have READY
    cand_a = build_valid_candidate()
    cand_a.decision_status = DecisionStatus.INSUFFICIENT_EVIDENCE
    cand_a.uncertainty_assessment.decision_readiness = DecisionReadiness.READY
    with pytest.raises(RecommendationValidationError) as exc_a:
        validate_candidate_recommendation(cand_a, dm, ep, rb)
    assert "contradictory_readiness_insufficient_evidence" in str(exc_a.value.details.get("rule"))

    # B. Reject cannot have READY
    cand_b = build_valid_candidate()
    cand_b.decision_status = DecisionStatus.REJECT
    cand_b.uncertainty_assessment.decision_readiness = DecisionReadiness.READY
    with pytest.raises(RecommendationValidationError) as exc_b:
        validate_candidate_recommendation(cand_b, dm, ep, rb)
    assert "contradictory_readiness_reject" in str(exc_b.value.details.get("rule"))

    # C. Proceed cannot have BLOCKED
    cand_c = build_valid_candidate()
    cand_c.decision_status = DecisionStatus.PROCEED
    cand_c.uncertainty_assessment.decision_readiness = DecisionReadiness.BLOCKED
    with pytest.raises(RecommendationValidationError) as exc_c:
        validate_candidate_recommendation(cand_c, dm, ep, rb)
    assert "contradictory_readiness_proceed" in str(exc_c.value.details.get("rule"))

    # D. Insufficient evidence cannot declare unconditional proceeding
    cand_d = build_valid_candidate()
    cand_d.decision_status = DecisionStatus.INSUFFICIENT_EVIDENCE
    cand_d.uncertainty_assessment.decision_readiness = DecisionReadiness.NEEDS_VALIDATION
    cand_d.recommended_action = "Proceed immediately with full enterprise rollout regardless of gaps."
    with pytest.raises(RecommendationValidationError) as exc_d:
        validate_candidate_recommendation(cand_d, dm, ep, rb)
    assert "contradictory_action_insufficient_evidence" in str(exc_d.value.details.get("rule"))


# ------------------------------------------------------------------------------
# Test 12: Deadline Propagation and Timeout Behavior
# ------------------------------------------------------------------------------

def test_12_deadline_expired_before_generator_call():
    dm, ep, rb = build_test_upstream_artifacts()
    mock_client = MockLLMClient()
    generator = RecommendationGenerator(llm_client=mock_client)

    # Pass an already expired deadline
    expired_deadline = time.monotonic() - 5.0
    with pytest.raises(RecommendationEvaluationError) as exc_info:
        generator.generate(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            deadline_monotonic=expired_deadline,
        )
    assert "Deadline exceeded prior to recommendation" in str(exc_info.value)
    assert mock_client.call_count == 0  # Zero network/LLM calls


def test_12b_deadline_expired_before_service_call():
    dm, ep, rb = build_test_upstream_artifacts()
    mock_client = MockLLMClient()
    service = RecommendationService.create_default(llm_client=mock_client)

    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(RecommendationServiceError) as exc_info:
        service.generate_recommendation(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            deadline_monotonic=expired_deadline,
        )
    assert "deadline expired before generation" in str(exc_info.value)
    assert mock_client.call_count == 0


def test_12c_llm_timeout_wrapped_cleanly():
    dm, ep, rb = build_test_upstream_artifacts()
    mock_client = MockLLMClient()
    mock_client.raise_exc = LLMTimeoutError("Operation timed out after 30s")
    service = RecommendationService.create_default(llm_client=mock_client)

    with pytest.raises(RecommendationServiceError) as exc_info:
        service.generate_recommendation(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
        )
    assert "timed out" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# Test 13: Deterministic ID Generation
# ------------------------------------------------------------------------------

def test_13_deterministic_id_reproducibility():
    dm, ep, rb = build_test_upstream_artifacts()
    cand = build_valid_candidate()

    rec1 = validate_candidate_recommendation(cand, dm, ep, rb)
    rec2 = validate_candidate_recommendation(cand, dm, ep, rb)

    assert rec1.id == rec2.id
    assert rec1.id.startswith("rec_")
    assert len(rec1.id) == 36

    # Change one field -> ID must differ
    cand_diff = build_valid_candidate()
    cand_diff.recommended_action = "Alternative changed action statement."
    rec3 = validate_candidate_recommendation(cand_diff, dm, ep, rb)
    assert rec1.id != rec3.id


# ------------------------------------------------------------------------------
# Test 14: Upstream Artifact Binding Validation
# ------------------------------------------------------------------------------

def test_14_upstream_binding_mismatch_fails_closed():
    dm, ep, rb = build_test_upstream_artifacts()

    # Mismatched ep.decision_model_id
    ep_bad = copy.deepcopy(ep)
    ep_bad.decision_model_id = "dec_other_999"
    with pytest.raises(RecommendationValidationError) as exc1:
        validate_recommendation_inputs(dm, ep_bad, rb)
    assert "does not match DecisionModel id" in str(exc1.value)

    # Mismatched rb.decision_model_id
    rb_bad1 = copy.deepcopy(rb)
    rb_bad1.decision_model_id = "dec_other_999"
    with pytest.raises(RecommendationValidationError) as exc2:
        validate_recommendation_inputs(dm, ep, rb_bad1)
    assert "does not match DecisionModel id" in str(exc2.value)

    # Mismatched rb.evidence_package_id
    rb_bad2 = copy.deepcopy(rb)
    rb_bad2.evidence_package_id = "pkg_other_999"
    with pytest.raises(RecommendationValidationError) as exc3:
        validate_recommendation_inputs(dm, ep, rb_bad2)
    assert "does not match EvidencePackage id" in str(exc3.value)


# ------------------------------------------------------------------------------
# Test 15: Preservation of Day 4 Upstream Contracts
# ------------------------------------------------------------------------------

def test_15_upstream_contracts_remain_immutable():
    dm, ep, rb = build_test_upstream_artifacts()
    dm_orig = copy.deepcopy(dm)
    ep_orig = copy.deepcopy(ep)
    rb_orig = copy.deepcopy(rb)

    mock_client = MockLLMClient()
    service = RecommendationService.create_default(llm_client=mock_client)
    rec = service.generate_recommendation(dm, ep, rb)

    assert isinstance(rec, DecisionRecommendation)
    assert dm == dm_orig
    assert ep == ep_orig
    assert rb == rb_orig


# ------------------------------------------------------------------------------
# Test 16: Prompt Construction & Injection Defense
# ------------------------------------------------------------------------------

def test_16_prompt_builder_structure_and_bounds():
    dm, ep, rb = build_test_upstream_artifacts()

    system_inst = build_recommendation_system_instruction()
    assert "Decision Recommendation & Action Planning Engine" in system_inst
    assert "<untrusted_source_material>" in system_inst
    assert "NEVER:" in system_inst

    user_prompt = build_recommendation_prompt(dm, ep, rb)
    assert "=== DECISION INQUIRY & PROBLEM CONTEXT ===" in user_prompt
    assert "=== EMPIRICAL EVIDENCE PORTFOLIO ===" in user_prompt
    assert "<untrusted_source_material>" in user_prompt
    assert "</untrusted_source_material>" in user_prompt
    assert "=== AI BOARDROOM DELIBERATION (FOUR PERSPECTIVES) ===" in user_prompt
    assert "=== AUTHORITATIVE REFERENCE CATALOGS ===" in user_prompt
    assert "evi_demand_growth" in user_prompt
    assert "asm_market_tam" in user_prompt
    assert "dis_growth_finance_01" in user_prompt
    assert len(user_prompt) <= MAX_RECOMMENDATION_PROMPT_CHARS


def test_16b_prompt_length_overflow_raises():
    dm, ep, rb = build_test_upstream_artifacts()
    # Inject extremely huge text to exceed bounded limit
    dm_huge = copy.deepcopy(dm)
    dm_huge.decision.raw_prompt = "A" * (MAX_RECOMMENDATION_PROMPT_CHARS + 5000)

    with pytest.raises(RecommendationPromptError) as exc_info:
        build_recommendation_prompt(dm_huge, ep, rb)
    assert "exceeds maximum bounded size" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Test 17: Pure Referential Validator Defense-in-Depth
# ------------------------------------------------------------------------------

def test_17_pure_referential_validator():
    dm, ep, rb = build_test_upstream_artifacts()
    cand = build_valid_candidate()
    rec = validate_candidate_recommendation(cand, dm, ep, rb)

    # Must pass without error
    validate_recommendation_references(rec, dm, ep, rb)

    # Corrupt an evidence ID in the authoritative object
    rec_corrupt = copy.deepcopy(rec)
    rec_corrupt.supporting_evidence_item_ids.append("evi_invalid_foreign_key")
    with pytest.raises(RecommendationValidationError):
        validate_recommendation_references(rec_corrupt, dm, ep, rb)
