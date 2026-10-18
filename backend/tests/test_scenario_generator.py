"""Tests for AURA Scenario Generator & Engine Backend (Phase 5A).

Deterministic test suite covering:
1. Valid structured 3-scenario generation (optimistic, base case, pessimistic).
2. ScenarioService facade orchestration with injected MockLLMClient.
3. Invalid evidence reference fails closed (ScenarioValidationError).
4. Invalid assumption reference fails closed (ScenarioValidationError).
5. Invalid constraint reference fails closed (ScenarioValidationError).
6. Invalid evidence gap reference fails closed (ScenarioValidationError).
7. Harmless placeholder reference normalization ('none', 'N/A', 'null', '[]').
8. Missing or duplicate canonical scenario types in candidate fails closed.
9. Probability sum deviation (> 0.01 from 1.0) fails closed.
10. NaN and infinite probabilities fail closed.
11. Missing required content (empty key events, empty milestones, short narrative) fails closed.
12. Upstream artifact ID binding mismatch fails closed.
13. Monotonic deadline expiration before execution raises cleanly.
14. Upstream LLMTimeoutError wrapped cleanly.
15. Upstream LLMResponseValidationError wrapped cleanly.
16. Content-derived deterministic scenario and scenario set IDs repeatability.
17. Prompt builder bounded length enforcement and prompt injection isolation.
18. Distinguishing assumptions from supported evidence in grounding references.
"""

from datetime import datetime, timezone
import copy
import math
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
)
from app.services.recommendation.validator import validate_candidate_recommendation
from app.schemas.scenario import (
    CandidateFutureScenario,
    CandidateScenarioKeyEvent,
    CandidateScenarioMilestone,
    CandidateScenarioSet,
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
    generate_deterministic_scenario_id,
    generate_deterministic_scenarioset_id,
)
from app.services.llm.client import (
    LLMClient,
    LLMConfig,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.scenario.generator import ScenarioGenerator
from app.services.scenario.prompt_builder import (
    MAX_SCENARIO_PROMPT_CHARS,
    build_scenario_prompt,
    build_scenario_system_instruction,
)
from app.services.scenario.service import ScenarioService
from app.services.scenario.validator import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioPromptError,
    ScenarioServiceError,
    ScenarioValidationError,
    clean_id_list,
    validate_candidate_scenario_set,
    validate_scenario_inputs,
)


# ------------------------------------------------------------------------------
# Test Doubles & Fixtures
# ------------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Deterministic in-memory test double for structured scenario generation."""

    def __init__(self, response_candidate: Optional[CandidateScenarioSet] = None) -> None:
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

        return build_valid_candidate_scenario_set()

    def generate_text(self, *args, **kwargs):
        raise NotImplementedError("generate_text not used in scenario engine.")


def build_test_upstream_artifacts():
    """Builds valid, authoritative upstream artifacts (Stages 1-4)."""
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

    rec_cand = CandidateDecisionRecommendation(
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute a phased expansion into tier-1 enterprise accounts with milestone gating.",
        executive_rationale="Empirical evidence demonstrates strong market demand growth.",
        supporting_evidence_item_ids=["evi_demand_growth"],
        relevant_assumption_ids=["asm_market_tam", "asm_win_rate"],
        relevant_evidence_gap_ids=["gap_retention_cohort"],
        unresolved_disagreement_ids=["dis_growth_finance_01"],
        alternative_options=[
            CandidateAlternativeOption(
                name="Status Quo",
                description="Remain in mid-market only",
                tradeoffs=["Preserves cash", "Misses growth"],
                why_not_recommended="Does not achieve ARR objective",
            )
        ],
        uncertainty_assessment=CandidateUncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
            critical_missing_information=["Logo retention"],
            conditions_changing_recommendation=["Win rate < 15%"],
            assumptions_relied_upon=["asm_win_rate"],
            evidence_gaps_relied_upon=["gap_retention_cohort"],
        ),
        action_plan=CandidateActionPlan(
            summary="Phased pilot roll-out.",
            actions=[
                CandidateActionItem(
                    title="Enterprise Pilot",
                    objective="Validate enterprise conversion",
                    description="Run targeted outreach to validate sales cycle",
                    priority=ActionPriority.HIGH,
                    responsible_role="Head of Sales",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    dependencies=[],
                    success_metrics=["3 LOIs signed"],
                    risk_mitigations=["Cap pilot scope"],
                    decision_gates=[
                        CandidateDecisionGate(
                            condition="3 LOIs in 90 days",
                            target_milestone="Pilot Review",
                            verification_method="Audit contracts",
                            fallback_action="Pause hiring",
                        )
                    ],
                )
            ],
            key_milestones=["Day 90: Pilot Gate"],
        ),
    )

    fixed_now = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)
    rec = validate_candidate_recommendation(
        candidate=rec_cand,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
        clock=lambda: fixed_now,
    )

    return dm, ep, rb, rec


def build_valid_candidate_scenario_set() -> CandidateScenarioSet:
    """Builds a semantically sound CandidateScenarioSet with valid upstream references."""
    return CandidateScenarioSet(
        summary="Comprehensive future scenario simulations evaluating enterprise expansion under varying market conditions.",
        scenarios=[
            CandidateFutureScenario(
                scenario_type=ScenarioType.OPTIMISTIC,
                probability=0.25,
                name="Enterprise Rapid Adoption & Category Leadership",
                narrative=(
                    "Under this optimistic trajectory, enterprise market demand accelerates faster than expected. "
                    "Initial lighthouse accounts convert within 4 months with minimal custom engineering, validating "
                    "the $20M ARR trajectory while keeping burn well within the 18-month runway ceiling."
                ),
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Early Lighthouse Closures",
                        description="Three Fortune 500 accounts sign multi-year agreements in Q1.",
                        timeframe="Month 3-6",
                        significance="Validates product-market fit and enterprise willingness to pay.",
                    ),
                    CandidateScenarioKeyEvent(
                        title="SOC-2 Accelerated Sign-off",
                        description="Audit completed ahead of schedule with zero material findings.",
                        timeframe="Month 6",
                        significance="Unlocks enterprise procurement queues across all target accounts.",
                    ),
                ],
                risks=[
                    "Implementation team capacity stretched thin across simultaneous rollouts.",
                    "Aggressive hiring competition from legacy incumbents.",
                ],
                opportunities=[
                    "Land-and-expand revenue growth exceeding 140% net revenue retention.",
                    "Strategic co-marketing and Tier-1 cloud partnership opportunities.",
                ],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Pilot Success",
                        description="First 3 Enterprise Contracts Signed and commercial pilots underway.",
                        time_horizon="Month 6",
                        expected_outcome="$3M incremental ARR contracted.",
                    ),
                    CandidateScenarioMilestone(
                        title="Enterprise Scaling",
                        description="Full Enterprise Tier Scaling across tier-1 account base.",
                        time_horizon="Month 18",
                        expected_outcome="Enterprise ARR exceeds $15M with positive unit economics.",
                    ),
                ],
                supporting_evidence_item_ids=["evi_demand_growth"],
                relevant_assumption_ids=["asm_market_tam", "asm_win_rate"],
                relevant_constraint_ids=["cnstr_cash"],
                relevant_gap_ids=["gap_retention_cohort"],
            ),
            CandidateFutureScenario(
                scenario_type=ScenarioType.BASE_CASE,
                probability=0.55,
                name="Measured Phased Expansion with Milestone Gating",
                narrative=(
                    "Under the base case, the organization executes disciplined milestone-gated expansion. "
                    "Enterprise conversion achieves the modeled 20% win rate, but sales cycles stretch to 7 months. "
                    "Runway remains protected above the 18-month requirement through selective headcount additions."
                ),
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Pilot Milestone Gate Achieved",
                        description="Pilot accounts reach commercial agreement validating the core value proposition.",
                        timeframe="Month 6-9",
                        significance="Authorizes stage-two enterprise hiring per recommendation decision gates.",
                    ),
                    CandidateScenarioKeyEvent(
                        title="Compliance Requirements Addressed",
                        description="SOC-2 certification completed, enabling standard enterprise contracting.",
                        timeframe="Month 9",
                        significance="Removes legal procurement blockers.",
                    ),
                ],
                risks=[
                    "Longer procurement cycles causing temporary revenue recognition delays.",
                    "Moderate margin compression due to initial customer success support needs.",
                ],
                opportunities=[
                    "Establishment of referenceable flagship customers in financial and healthcare sectors.",
                    "Disciplined capital allocation preserving optionality.",
                ],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Pilot Gate Review",
                        description="Evaluation of pilot metrics and Stage-2 Hiring Authorization.",
                        time_horizon="Month 9",
                        expected_outcome="Validation of 20% win rate and positive pilot NPS.",
                    ),
                    CandidateScenarioMilestone(
                        title="Steady-State Production",
                        description="Steady-State Enterprise Sales Production and predictable closing cadence.",
                        time_horizon="Month 24",
                        expected_outcome="Reaching $20M ARR run-rate with 18+ months runway intact.",
                    ),
                ],
                supporting_evidence_item_ids=["evi_demand_growth"],
                relevant_assumption_ids=["asm_win_rate"],
                relevant_constraint_ids=["cnstr_cash"],
                relevant_gap_ids=["gap_retention_cohort"],
            ),
            CandidateFutureScenario(
                scenario_type=ScenarioType.PESSIMISTIC,
                probability=0.20,
                name="Sales Stagnation & Incumbent Retaliation",
                narrative=(
                    "Under the pessimistic scenario, enterprise sales cycles exceed 12 months as incumbent vendors "
                    "initiate aggressive bundled discounting. Pilot conversion falls below 15%, triggering the "
                    "contingency fallback action to freeze hiring and protect cash runway before breaching limits."
                ),
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Incumbent Aggressive Bundling",
                        description="Major incumbent offers free migration and 40% discount to protect turf.",
                        timeframe="Month 4-8",
                        significance="Slows pilot deal closing velocity and depresses initial ACV.",
                    ),
                    CandidateScenarioKeyEvent(
                        title="Decision Gate Fallback Triggered",
                        description="Pilot review confirms conversion fell below 15% threshold; hiring paused.",
                        timeframe="Month 9",
                        significance="Preserves cash runway and redirects capacity back to mid-market tier.",
                    ),
                ],
                risks=[
                    "Runway depletion risk if hiring freeze is delayed.",
                    "Sunk costs in enterprise-specific compliance and security tooling.",
                ],
                opportunities=[
                    "Refocusing on high-velocity mid-market tier where win rates exceed 35%.",
                    "Strengthening product differentiation before re-attempting enterprise tier.",
                ],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Pilot Gate Failure",
                        description="Decision gate triggered to freeze hiring and initiate contingency plan.",
                        time_horizon="Month 9",
                        expected_outcome="Hiring frozen; marketing spend reallocated to mid-market.",
                    ),
                    CandidateScenarioMilestone(
                        title="Mid-Market Consolidation",
                        description="Refocusing sales on mid-market accounts and runway stabilization.",
                        time_horizon="Month 18",
                        expected_outcome="Runway stabilized above 24 months with renewed mid-market growth.",
                    ),
                ],
                supporting_evidence_item_ids=["evi_demand_growth"],
                relevant_assumption_ids=["asm_win_rate"],
                relevant_constraint_ids=["cnstr_cash"],
                relevant_gap_ids=["gap_retention_cohort"],
            ),
        ]
    )


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------

def test_01_valid_structured_scenario_generation():
    """Verifies successful generation and validation of a canonical 3-scenario portfolio."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    mock_llm = MockLLMClient(response_candidate=candidate)

    generator = ScenarioGenerator(llm_client=mock_llm)
    fixed_now = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)

    scenario_set = generator.generate(
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
        recommendation=rec,
        clock=lambda: fixed_now,
    )

    assert isinstance(scenario_set, ScenarioSet)
    assert scenario_set.decision_model_id == dm.id
    assert scenario_set.evidence_package_id == ep.id
    assert scenario_set.reasoning_board_id == rb.id
    assert scenario_set.recommendation_id == rec.id
    assert scenario_set.created_at == fixed_now
    assert scenario_set.id.startswith("scenset_")

    # Cardinality and canonical types
    assert len(scenario_set.scenarios) == 3
    scen_by_type = {s.scenario_type: s for s in scenario_set.scenarios}
    assert set(scen_by_type.keys()) == {
        ScenarioType.OPTIMISTIC,
        ScenarioType.BASE_CASE,
        ScenarioType.PESSIMISTIC,
    }

    # Probabilities
    total_prob = sum(s.probability for s in scenario_set.scenarios)
    assert pytest.approx(total_prob, abs=1e-5) == 1.0
    assert scen_by_type[ScenarioType.OPTIMISTIC].probability == 0.25
    assert scen_by_type[ScenarioType.BASE_CASE].probability == 0.55
    assert scen_by_type[ScenarioType.PESSIMISTIC].probability == 0.20

    # Stable deterministic IDs
    for s in scenario_set.scenarios:
        assert s.id.startswith("scen_")
        assert len(s.key_events) >= 1
        assert len(s.timeline) >= 1
        assert len(s.narrative) >= 50
        assert s.supporting_evidence_item_ids == ["evi_demand_growth"]
        assert s.relevant_constraint_ids == ["cnstr_cash"]


def test_02_scenario_service_orchestration():
    """Verifies ScenarioService factory and orchestration facade."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    mock_llm = MockLLMClient(response_candidate=candidate)

    fixed_now = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
    service = ScenarioService.create_default(
        llm_client=mock_llm,
        clock=lambda: fixed_now,
        scenario_operation_timeout_seconds=45.0,
    )

    scenario_set = service.generate_scenarios(
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
        recommendation=rec,
    )

    assert isinstance(scenario_set, ScenarioSet)
    assert scenario_set.created_at == fixed_now
    assert mock_llm.call_count == 1
    assert "Expand into enterprise tier-1 market?" in mock_llm.last_prompt
    assert "Future Scenario Engine for AURA" in mock_llm.last_system_instruction


def test_03_invalid_evidence_reference_fails_closed():
    """Verifies that referencing a non-existent evidence ID fails closed with ScenarioValidationError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    # Inject fabricated evidence ID into optimistic scenario
    candidate.scenarios[0].supporting_evidence_item_ids.append("evi_fabricated_id")

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "evi_fabricated_id" in str(exc_info.value)
    assert exc_info.value.rule == "nonexistent_evidence_reference"


def test_04_invalid_assumption_reference_fails_closed():
    """Verifies that referencing a non-existent assumption ID fails closed with ScenarioValidationError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    candidate.scenarios[1].relevant_assumption_ids.append("asm_unsupported_id")

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "asm_unsupported_id" in str(exc_info.value)
    assert exc_info.value.rule == "nonexistent_assumption_reference"


def test_05_invalid_constraint_reference_fails_closed():
    """Verifies that referencing a non-existent constraint ID fails closed with ScenarioValidationError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    candidate.scenarios[2].relevant_constraint_ids.append("cnstr_fake_id")

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "cnstr_fake_id" in str(exc_info.value)
    assert exc_info.value.rule == "nonexistent_constraint_reference"


def test_06_invalid_evidence_gap_reference_fails_closed():
    """Verifies that referencing a non-existent evidence gap ID fails closed with ScenarioValidationError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()
    candidate.scenarios[0].relevant_gap_ids.append("gap_nonexistent_id")

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "gap_nonexistent_id" in str(exc_info.value)
    assert exc_info.value.rule == "nonexistent_gap_reference"


def test_07_placeholder_reference_normalization():
    """Verifies that harmless placeholder reference tokens are cleaned rather than crashing."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()

    # Add placeholder tokens
    candidate.scenarios[0].supporting_evidence_item_ids.extend(["none", "N/A", "null", "[]"])
    candidate.scenarios[1].relevant_assumption_ids.extend(["none", "N/A"])
    candidate.scenarios[2].relevant_constraint_ids.extend(["none"])

    scenario_set = validate_candidate_scenario_set(
        candidate=candidate,
        decision_model=dm,
        evidence_package=ep,
        reasoning_board=rb,
        recommendation=rec,
    )

    assert scenario_set.scenarios[0].supporting_evidence_item_ids == ["evi_demand_growth"]
    assert scenario_set.scenarios[1].relevant_assumption_ids == ["asm_win_rate"]
    assert scenario_set.scenarios[2].relevant_constraint_ids == ["cnstr_cash"]


def test_08_missing_or_duplicate_scenario_types_in_candidate_fails():
    """Verifies that candidate sets missing a canonical type or duplicating one fail validation."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()

    # Turn pessimistic into a duplicate base case
    candidate.scenarios[2].scenario_type = ScenarioType.BASE_CASE

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "missing" in str(exc_info.value).lower()
    assert exc_info.value.rule == "canonical_types_required"


def test_09_probability_sum_deviation_fails():
    """Verifies that probabilities not summing to 1.0 (beyond 0.01 tolerance) are rejected."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()

    # 0.40 + 0.55 + 0.20 = 1.15
    candidate.scenarios[0].probability = 0.40

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "must sum to 1.0" in str(exc_info.value).lower()
    assert exc_info.value.rule == "probability_sum_tolerance"


def test_10_nan_and_infinite_probabilities_fail():
    """Verifies that non-finite probabilities (NaN, Infinity) fail closed."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    candidate = build_valid_candidate_scenario_set()

    candidate.scenarios[0].probability = float("nan")

    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "finite" in str(exc_info.value).lower() or "probability" in str(exc_info.value).lower()


def test_11_missing_required_content_fails():
    """Verifies that empty key events or milestones in candidate fail validation."""
    dm, ep, rb, rec = build_test_upstream_artifacts()

    # Empty key events
    cand1 = build_valid_candidate_scenario_set()
    cand1.scenarios[0].key_events = []
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=cand1,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )
    assert exc_info.value.rule == "key_events_required"

    # Empty timeline milestones
    cand2 = build_valid_candidate_scenario_set()
    cand2.scenarios[1].timeline = []
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=cand2,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )
    assert exc_info.value.rule == "timeline_required"

    # Short narrative
    cand3 = build_valid_candidate_scenario_set()
    cand3.scenarios[2].narrative = "          "
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_candidate_scenario_set(
            candidate=cand3,
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )
    assert exc_info.value.rule == "short_narrative"


def test_12_upstream_artifact_id_mismatch_fails_closed():
    """Verifies that mismatched upstream artifact IDs are detected and rejected."""
    dm, ep, rb, rec = build_test_upstream_artifacts()

    # Mismatched EvidencePackage
    bad_ep = ep.model_copy(update={"decision_model_id": "dec_wrong_id"})
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_scenario_inputs(dm, bad_ep, rb, rec)
    assert "EvidencePackage decision_model_id" in str(exc_info.value)
    assert "does not match DecisionModel.id" in str(exc_info.value)

    # Mismatched ReasoningBoard
    bad_rb = rb.model_copy(update={"decision_model_id": "dec_wrong_id"})
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_scenario_inputs(dm, ep, bad_rb, rec)
    assert "ReasoningBoard decision_model_id" in str(exc_info.value)
    assert "does not match DecisionModel.id" in str(exc_info.value)

    # Mismatched DecisionRecommendation
    bad_rec = rec.model_copy(update={"decision_model_id": "dec_wrong_id"})
    with pytest.raises(ScenarioValidationError) as exc_info:
        validate_scenario_inputs(dm, ep, rb, bad_rec)
    assert "DecisionRecommendation decision_model_id" in str(exc_info.value)
    assert "does not match DecisionModel.id" in str(exc_info.value)


def test_13_monotonic_deadline_expiration_handling():
    """Verifies that expired monotonic deadlines halt execution without calling LLM."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    mock_llm = MockLLMClient()
    service = ScenarioService.create_default(llm_client=mock_llm)

    # Pre-expired deadline
    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(ScenarioServiceError) as exc_info:
        service.generate_scenarios(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
            deadline_monotonic=expired_deadline,
        )

    assert "deadline expired" in str(exc_info.value).lower()
    assert mock_llm.call_count == 0


def test_14_llm_timeout_wrapped_cleanly():
    """Verifies that provider LLMTimeoutError is captured and wrapped into ScenarioServiceError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    mock_llm = MockLLMClient()
    mock_llm.raise_exc = LLMTimeoutError("Operation exceeded 45.0s timeout")
    service = ScenarioService.create_default(llm_client=mock_llm)

    with pytest.raises(ScenarioServiceError) as exc_info:
        service.generate_scenarios(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "timed out" in str(exc_info.value).lower()
    assert exc_info.value.details.get("error_type") == "timeout"


def test_15_llm_response_validation_error_wrapped():
    """Verifies that malformed provider output is wrapped into ScenarioEvaluationError / ScenarioServiceError."""
    dm, ep, rb, rec = build_test_upstream_artifacts()
    mock_llm = MockLLMClient()
    mock_llm.raise_exc = LLMResponseValidationError("Gemini structured output failed schema validation")
    service = ScenarioService.create_default(llm_client=mock_llm)

    with pytest.raises(ScenarioServiceError) as exc_info:
        service.generate_scenarios(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            recommendation=rec,
        )

    assert "structured response validation failed" in str(exc_info.value).lower()
    assert exc_info.value.details.get("error_type") == "invalid_output"


def test_16_deterministic_id_generation_repeatability():
    """Verifies that identical scenarios and sets produce repeatable, deterministic IDs."""
    candidate = build_valid_candidate_scenario_set()
    dm, ep, rb, rec = build_test_upstream_artifacts()

    set_1 = validate_candidate_scenario_set(candidate, dm, ep, rb, rec)
    set_2 = validate_candidate_scenario_set(candidate, dm, ep, rb, rec)

    assert set_1.id == set_2.id
    for s1, s2 in zip(set_1.scenarios, set_2.scenarios):
        assert s1.id == s2.id
        assert s1.scenario_type == s2.scenario_type


def test_17_prompt_builder_bounded_length_and_injection_defense():
    """Verifies that prompt builder respects MAX_SCENARIO_PROMPT_CHARS and secures injection."""
    dm, ep, rb, rec = build_test_upstream_artifacts()

    # Normal prompt within bounds
    normal_prompt = build_scenario_prompt(dm, ep, rb, rec)
    assert len(normal_prompt) <= MAX_SCENARIO_PROMPT_CHARS

    # Oversized prompt triggers ScenarioPromptError
    huge_prompt = "Enterprise Expansion? " + ("A" * 50000)
    oversized_dm = dm.model_copy(
        update={"decision": dm.decision.model_copy(update={"raw_prompt": huge_prompt})}
    )
    with pytest.raises(ScenarioPromptError) as exc_info:
        build_scenario_prompt(oversized_dm, ep, rb, rec)
    assert "exceeds ceiling" in str(exc_info.value).lower()

    # Check system instruction defenses
    instruction = build_scenario_system_instruction()
    assert "You are the Future Scenario Engine for AURA" in instruction
    assert "MANDATE & ROLE" in instruction
    assert "CARDINAL INVARIANTS & PROBABILITY CONTRACT" in instruction
    assert "REFERENCE GROUNDING CONTRACT" in instruction
    assert "PROMPT INJECTION DEFENSE" in instruction
