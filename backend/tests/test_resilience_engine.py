"""Tests for AURA Deterministic Resilience Engine (Day 6 Phase 6A).

Covers:
- Exact deterministic golden-score evaluation
- Deterministic repeatability & content-derived ID stability
- Input ordering invariance (scenarios, risks, constraints, assumptions, actions)
- Input immutability (ensuring no input mutation during scoring)
- Referential integrity enforcement across all decision artifacts
- Incomplete and missing inputs policy (no risks, no gates, no actions, no constraints, no package)
- All score & sub-score bounds and finite arithmetic
- Rating boundaries & stress-test pass/fail logic
- Pure offline execution without LLM or network calls
"""

import copy
from datetime import datetime, timezone
import math
from typing import List, Optional
import pytest

from app.engines.resilience import (
    DEFAULT_RESILIENCE_CONFIG,
    ResilienceConfig,
    evaluate_resilience,
)
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
    ActionItem,
    ActionPlan,
    ActionPriority,
    ActionTimeHorizon,
    AlternativeOption,
    DecisionGate,
    DecisionReadiness,
    DecisionRecommendation,
    DecisionStatus,
    EvidenceStrength,
    RecommendationStability,
    UncertaintyAssessment,
    generate_deterministic_recommendation_id,
)
from app.schemas.resilience import (
    ResiliencePillar,
    ResilienceRating,
    ResilienceReport,
)
from app.schemas.scenario import (
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
    generate_deterministic_scenario_id,
    generate_deterministic_scenarioset_id,
)


# ------------------------------------------------------------------------------
# Fixture Builders
# ------------------------------------------------------------------------------

def build_test_decision_model(
    dm_id: str = "dec_enterprise_01",
    reversibility: ReversibilityLevel = ReversibilityLevel.PARTIALLY_REVERSIBLE,
    constraints: Optional[List[Constraint]] = None,
    assumptions: Optional[List[Assumption]] = None,
) -> DecisionModel:
    if constraints is None:
        constraints = [
            Constraint(
                id="cnstr_cash",
                name="Runway Constraint",
                description="Maintain >= 18 months runway",
                is_hard_constraint=True,
            ),
        ]
    if assumptions is None:
        assumptions = [
            Assumption(
                id="asm_market_tam",
                statement="Enterprise TAM exceeds $3B",
                confidence=ConfidenceLevel.MEDIUM,
            ),
            Assumption(
                id="asm_win_rate",
                statement="Enterprise competitive win rate >= 20%",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]

    return DecisionModel(
        id=dm_id,
        decision=Decision(
            raw_prompt="Expand into enterprise tier-1 market?",
            summary="Strategic decision to expand sales team and product for enterprise tier.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="High execution risk and long enterprise sales cycles.",
            reversibility=reversibility,
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
        constraints=constraints,
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
        assumptions=assumptions,
        unknowns=[
            Unknown(id="unk_competitor_pricing", question="Competitor discounting response"),
        ],
        key_questions=["Can product fulfill SOC-2 and enterprise compliance requirements?"],
    )


def build_test_evidence_package(
    dm_id: str = "dec_enterprise_01",
    pkg_id: str = "pkg_enterprise_01",
    gaps: Optional[List[EvidenceGap]] = None,
) -> EvidencePackage:
    if gaps is None:
        gaps = [
            EvidenceGap(
                id="gap_retention_cohort",
                gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE,
                target_entity_id="obj_arr",
                target_entity_type=DecisionEntityType.OBJECTIVE,
                description="No empirical data on multi-year enterprise logo retention.",
                impact=CriticalityLevel.MEDIUM,
            ),
        ]

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

    return EvidencePackage(
        id=pkg_id,
        decision_model_id=dm_id,
        summary="Empirical evidence portfolio for enterprise expansion.",
        sources=[src],
        items=[item],
        requirements=[req],
        gaps=gaps,
        claim_links=[],
    )


def build_test_reasoning_board(
    dm_id: str = "dec_enterprise_01",
    pkg_id: str = "pkg_enterprise_01",
    rb_id: str = "rbd_enterprise_01",
) -> ReasoningBoard:
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
    p_growth = ReasoningPerspective(
        id="persp_growth",
        perspective_type=PerspectiveType.GROWTH,
        summary="Growth perspective advocates aggressive enterprise sales hiring.",
        arguments=[arg_g],
        critical_assumption_ids=["asm_market_tam"],
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
        summary="Customer perspective focuses on enterprise procurement standards.",
        arguments=[],
    )
    p_risk = ReasoningPerspective(
        id="persp_risk",
        perspective_type=PerspectiveType.RISK,
        summary="Risk perspective highlights pricing pressure and competitor discounting.",
        arguments=[],
    )
    dis = ReasoningDisagreement(
        id="dis_growth_finance_01",
        topic="Sales expansion speed vs capital runway preservation",
        perspective_ids=["persp_growth", "persp_finance"],
        argument_ids=["arg_g1", "arg_f1"],
        positions={"persp_growth": "Scale headcount", "persp_finance": "Phase headcount"},
        evidence_item_ids=["evi_demand_growth"],
        nature=DisagreementNature.EVIDENCE_DEPENDENT,
    )
    synth = BoardSynthesis(
        summary="The Board agrees enterprise market demand is real, but split on speed versus runway risk.",
        areas_of_agreement=["Target tier-1 accounts only with existing product capabilities."],
        disagreement_ids=["dis_growth_finance_01"],
        critical_assumption_ids=["asm_market_tam"],
        evidence_sensitive_points=["Enterprise sales cycle duration."],
        unresolved_questions=["Can the current architecture meet SOC-2 compliance?"],
    )
    return ReasoningBoard(
        id=rb_id,
        decision_model_id=dm_id,
        evidence_package_id=pkg_id,
        perspectives=[p_growth, p_finance, p_customer, p_risk],
        disagreements=[dis],
        synthesis=synth,
        created_at=datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc),
    )


def build_test_recommendation(
    dm_id: str = "dec_enterprise_01",
    rec_id: Optional[str] = None,
    actions: Optional[List[ActionItem]] = None,
    alternatives: Optional[List[AlternativeOption]] = None,
    stability: RecommendationStability = RecommendationStability.HIGH,
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE,
    readiness: DecisionReadiness = DecisionReadiness.READY,
) -> DecisionRecommendation:
    if actions is None:
        actions = [
            ActionItem(
                id="act_pilot",
                title="Enterprise Pilot",
                objective="Validate enterprise conversion",
                description="Run targeted outreach to validate sales cycle",
                priority=ActionPriority.HIGH,
                responsible_role="Head of Sales",
                time_horizon=ActionTimeHorizon.IMMEDIATE,
                dependencies=[],
                success_metrics=["3 LOIs signed"],
                risk_mitigations=["Cap pilot scope"],
                fallback_action="Freeze hiring",
                decision_gates=[
                    DecisionGate(
                        id="gate_pilot_review",
                        condition="3 LOIs in 90 days",
                        target_milestone="Pilot Review",
                        verification_method="Audit contracts",
                        fallback_action="Pause hiring",
                    )
                ],
            )
        ]
    if alternatives is None:
        alternatives = [
            AlternativeOption(
                id="alt_status_quo",
                name="Status Quo",
                description="Remain in mid-market only",
                tradeoffs=["Preserves cash", "Misses growth"],
                why_not_recommended="Does not achieve ARR objective",
            )
        ]

    plan = ActionPlan(
        summary="Phased pilot roll-out.",
        actions=actions,
        key_milestones=["Day 90: Pilot Gate"],
    )
    unc = UncertaintyAssessment(
        evidence_strength=evidence_strength,
        decision_readiness=readiness,
        recommendation_stability=stability,
        critical_missing_information=["Logo retention"],
        conditions_changing_recommendation=["Win rate < 15%"],
        assumptions_relied_upon=["asm_win_rate"],
        evidence_gaps_relied_upon=["gap_retention_cohort"],
    )

    if rec_id is None:
        rec_id = generate_deterministic_recommendation_id(
            decision_model_id=dm_id,
            evidence_package_id="pkg_enterprise_01",
            reasoning_board_id="rbd_enterprise_01",
            decision_status=DecisionStatus.PROCEED,
            recommended_action="Execute a phased expansion into tier-1 enterprise accounts with milestone gating.",
            executive_rationale="Empirical evidence demonstrates strong market demand growth.",
            action_ids=[a.id for a in actions],
        )

    return DecisionRecommendation(
        id=rec_id,
        decision_model_id=dm_id,
        evidence_package_id="pkg_enterprise_01",
        reasoning_board_id="rbd_enterprise_01",
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute a phased expansion into tier-1 enterprise accounts with milestone gating.",
        executive_rationale="Empirical evidence demonstrates strong market demand growth.",
        supporting_evidence_item_ids=["evi_demand_growth"],
        relevant_assumption_ids=["asm_market_tam", "asm_win_rate"],
        relevant_evidence_gap_ids=["gap_retention_cohort"],
        unresolved_disagreement_ids=["dis_growth_finance_01"],
        alternative_options=alternatives,
        uncertainty_assessment=unc,
        action_plan=plan,
        created_at=datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc),
    )


def build_test_scenario_set(
    dm_id: str = "dec_enterprise_01",
    rec_id: str = "rec_enterprise_01",
    pessimistic_prob: float = 0.20,
    pessimistic_risks: Optional[List[str]] = None,
    pessimistic_constraint_ids: Optional[List[str]] = None,
) -> ScenarioSet:
    if pessimistic_risks is None:
        # One risk mitigated ("hiring" keyword matches "Pause hiring" gate fallback), one unmitigated
        pessimistic_risks = [
            "Runway depletion risk if hiring freeze is delayed.",
            "Sunk costs in enterprise-specific compliance and security tooling.",
        ]
    if pessimistic_constraint_ids is None:
        pessimistic_constraint_ids = ["cnstr_cash"]

    opt_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.OPTIMISTIC,
        name="Optimistic Expansion",
        probability=0.25,
        key_event_titles=["Lighthouse Closures"],
    )
    base_prob = round(1.0 - 0.25 - pessimistic_prob, 2)
    base_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.BASE_CASE,
        name="Measured Base Case",
        probability=base_prob,
        key_event_titles=["Steady Pilot Progress"],
    )
    pess_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.PESSIMISTIC,
        name="Adverse Stagnation",
        probability=pessimistic_prob,
        key_event_titles=["Price War Escalation"],
    )

    scen_opt = FutureScenario(
        id=opt_id,
        scenario_type=ScenarioType.OPTIMISTIC,
        probability=0.25,
        name="Optimistic Expansion",
        narrative="Rapid enterprise adoption exceeding forecasts with low integration friction.",
        key_events=[
            ScenarioKeyEvent(
                id="ke_opt_1",
                title="Lighthouse Closures",
                description="Early closures validate enterprise conversion.",
                timeframe="Month 3",
                significance="High market momentum.",
            )
        ],
        risks=["Hiring bottleneck."],
        opportunities=["Category leadership."],
        timeline=[
            ScenarioMilestone(
                id="ms_opt_1",
                title="Pilot Milestone",
                description="Pilot conversion completes successfully.",
                time_horizon="Month 6",
                expected_outcome="$3M ARR signed.",
            )
        ],
        supporting_evidence_item_ids=["evi_demand_growth"],
        relevant_assumption_ids=["asm_market_tam"],
        relevant_constraint_ids=[],
        relevant_gap_ids=[],
    )

    scen_base = FutureScenario(
        id=base_id,
        scenario_type=ScenarioType.BASE_CASE,
        probability=base_prob,
        name="Measured Base Case",
        narrative="Disciplined progress meeting targets with normal enterprise sales cycles.",
        key_events=[
            ScenarioKeyEvent(
                id="ke_base_1",
                title="Steady Pilot Progress",
                description="Conversion proceeds at steady rate.",
                timeframe="Month 6",
                significance="Validates baseline plan.",
            )
        ],
        risks=["Long sales cycles."],
        opportunities=["Steady expansion."],
        timeline=[
            ScenarioMilestone(
                id="ms_base_1",
                title="Standard Gate",
                description="Standard pilot evaluation.",
                time_horizon="Month 9",
                expected_outcome="Validation of win rates.",
            )
        ],
        supporting_evidence_item_ids=["evi_demand_growth"],
        relevant_assumption_ids=["asm_win_rate"],
        relevant_constraint_ids=[],
        relevant_gap_ids=[],
    )

    scen_pess = FutureScenario(
        id=pess_id,
        scenario_type=ScenarioType.PESSIMISTIC,
        probability=pessimistic_prob,
        name="Adverse Stagnation",
        narrative="Competitor price war causes sales delays and pressures cash runway.",
        key_events=[
            ScenarioKeyEvent(
                id="ke_pess_1",
                title="Price War Escalation",
                description="Incumbents offer discounts slowing deals.",
                timeframe="Month 4",
                significance="Pressures pilot economics.",
            )
        ],
        risks=pessimistic_risks,
        opportunities=["Operational hardening."],
        timeline=[
            ScenarioMilestone(
                id="ms_pess_1",
                title="Cutover Assessment",
                description="Review for potential pause.",
                time_horizon="Month 6",
                expected_outcome="Protect cash reserves.",
            )
        ],
        supporting_evidence_item_ids=[],
        relevant_assumption_ids=["asm_win_rate"],
        relevant_constraint_ids=pessimistic_constraint_ids,
        relevant_gap_ids=[],
    )

    scenarios = [scen_opt, scen_base, scen_pess]
    set_id = generate_deterministic_scenarioset_id(
        decision_model_id=dm_id,
        recommendation_id=rec_id,
        scenario_ids=[s.id for s in scenarios],
    )
    return ScenarioSet(
        id=set_id,
        decision_model_id=dm_id,
        recommendation_id=rec_id,
        evidence_package_id="pkg_enterprise_01",
        summary="Tri-trajectory future scenarios evaluating market rollout.",
        scenarios=scenarios,
        created_at=datetime(2026, 10, 10, 15, 0, 0, tzinfo=timezone.utc),
    )


# ------------------------------------------------------------------------------
# 1. Exact Golden-Score Tests
# ------------------------------------------------------------------------------

def test_evaluate_resilience_exact_golden_score():
    """Validates the exact mathematical score against manual hand-calculated values."""
    dm = build_test_decision_model()
    ep = build_test_evidence_package()
    rb = build_test_reasoning_board()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    report = evaluate_resilience(
        decision_model=dm,
        scenario_set=scen_set,
        recommendation=rec,
        evidence_package=ep,
        reasoning_board=rb,
    )

    # Hand-calculation breakdown:
    # ---------------------------
    # Pillar A (Constraint Boundary Tolerance):
    # - Reversibility: PARTIALLY_REVERSIBLE -> 6.0 pts
    # - Hard constraints: 1 constraint ("cnstr_cash"), 1 pressured -> ratio 1.0 -> 15.0 * (1 - 1.0) = 0.0 pts
    # - Soft constraints: 0 -> penalty 0.0 pts
    # Pillar A Score = 6.0 + 0.0 = 6.0 pts.
    sub_a = next(s for s in report.sub_scores if s.category == ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value)
    assert sub_a.score == 6.0

    # Pillar B (Pessimistic Scenario Survivability):
    # - p_pess = 0.20
    # - 2 risks:
    #   1. "Runway depletion risk if hiring freeze is delayed." -> matched by "Pause hiring" gate -> mitigated
    #   2. "Sunk costs in enterprise-specific compliance and security tooling." -> unmitigated
    # - unmitigated_ratio = 1 / 2 = 0.50
    # - Survivability = 25.0 * (1.0 - 0.20 * 0.50) = 25.0 * 0.90 = 22.5 pts.
    sub_b = next(s for s in report.sub_scores if s.category == ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value)
    assert sub_b.score == 22.5

    # Pillar C (Contingency and Fallback Coverage):
    # - Gates: 1 gate. Condition >= 5 (1.0) + verification >= 5 (1.5) + fallback >= 5 (1.5) = 4.0 pts
    # - Actions: 1 action, has mitigations & fallback -> 1/1 = 1.0 ratio -> 8.0 pts
    # - Alternatives: 1 alternative -> 3.0 pts
    # Pillar C Score = 4.0 + 8.0 + 3.0 = 15.0 pts.
    sub_c = next(s for s in report.sub_scores if s.category == ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value)
    assert sub_c.score == 15.0

    # Pillar D (Information Robustness):
    # - Stability: HIGH -> 5.0 pts
    # - Evidence Strength: MODERATE -> 3.5 pts
    # - Gaps: 1 medium-impact gap -> penalty = 1.0 -> gap_score = 6.0 - 1.0 = 5.0 pts
    # - Assumptions: 2 assumptions, both MEDIUM confidence (0.6 each) -> (1.2 / 2) * 5.0 = 3.0 pts
    # - Readiness: READY -> 4.0 pts
    # Pillar D Score = 5.0 + 3.5 + 5.0 + 3.0 + 4.0 = 20.5 pts.
    sub_d = next(s for s in report.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)
    assert sub_d.score == 20.5

    # Overall Score = 6.0 + 22.5 + 15.0 + 20.5 = 64.0 pts.
    assert report.overall_score == 64.0
    assert report.rating == ResilienceRating.MODERATE
    assert report.stress_test_passed is True  # 64.0 >= 60.0 and 22.5 >= 12.5

    # Deterministic ID checks
    assert report.id.startswith("res_")
    assert len(report.id) == 36


# ------------------------------------------------------------------------------
# 2. Deterministic Repeatability & Invariance Tests
# ------------------------------------------------------------------------------

def test_deterministic_repeatability():
    """Identical inputs evaluated repeatedly must yield identical output attributes."""
    dm = build_test_decision_model()
    ep = build_test_evidence_package()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    rep1 = evaluate_resilience(dm, scen_set, rec, ep)
    rep2 = evaluate_resilience(dm, scen_set, rec, ep)

    assert rep1.id == rep2.id
    assert rep1.overall_score == rep2.overall_score
    assert rep1.rating == rep2.rating
    assert [s.score for s in rep1.sub_scores] == [s.score for s in rep2.sub_scores]
    assert rep1.critical_vulnerabilities == rep2.critical_vulnerabilities
    assert rep1.recommended_hedges == rep2.recommended_hedges


def test_input_ordering_invariance():
    """Permuting list orders (scenarios, risks, constraints) must not alter the score or report ID."""
    dm = build_test_decision_model()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    # Baseline report
    rep_base = evaluate_resilience(dm, scen_set, rec)

    # 1. Permute scenario list order in ScenarioSet
    scenarios_permuted = [scen_set.scenarios[2], scen_set.scenarios[0], scen_set.scenarios[1]]
    scen_set_perm = ScenarioSet(
        id=scen_set.id,
        decision_model_id=scen_set.decision_model_id,
        recommendation_id=scen_set.recommendation_id,
        evidence_package_id=scen_set.evidence_package_id,
        summary=scen_set.summary,
        scenarios=scenarios_permuted,
    )

    rep_perm = evaluate_resilience(dm, scen_set_perm, rec)
    assert rep_perm.id == rep_base.id
    assert rep_perm.overall_score == rep_base.overall_score
    assert rep_perm.rating == rep_base.rating

    # 2. Permute risks order in pessimistic scenario
    pess = scen_set.scenarios[2]
    pess_perm_risks = FutureScenario(
        id=pess.id,
        scenario_type=pess.scenario_type,
        probability=pess.probability,
        name=pess.name,
        narrative=pess.narrative,
        key_events=pess.key_events,
        risks=list(reversed(pess.risks)),  # reversed order
        opportunities=pess.opportunities,
        timeline=pess.timeline,
        supporting_evidence_item_ids=pess.supporting_evidence_item_ids,
        relevant_assumption_ids=pess.relevant_assumption_ids,
        relevant_constraint_ids=pess.relevant_constraint_ids,
        relevant_gap_ids=pess.relevant_gap_ids,
    )
    scen_set_pess_perm = ScenarioSet(
        id=scen_set.id,
        decision_model_id=scen_set.decision_model_id,
        recommendation_id=scen_set.recommendation_id,
        evidence_package_id=scen_set.evidence_package_id,
        summary=scen_set.summary,
        scenarios=[scen_set.scenarios[0], scen_set.scenarios[1], pess_perm_risks],
    )

    rep_pess_perm = evaluate_resilience(dm, scen_set_pess_perm, rec)
    assert rep_pess_perm.id == rep_base.id
    assert rep_pess_perm.overall_score == rep_base.overall_score
    assert rep_pess_perm.critical_vulnerabilities == rep_base.critical_vulnerabilities


def test_input_immutability():
    """Verifies that none of the input data models are mutated during scoring."""
    dm = build_test_decision_model()
    ep = build_test_evidence_package()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    dm_snapshot = dm.model_dump(mode="json")
    ep_snapshot = ep.model_dump(mode="json")
    rec_snapshot = rec.model_dump(mode="json")
    scen_snapshot = scen_set.model_dump(mode="json")

    _ = evaluate_resilience(dm, scen_set, rec, ep)

    assert dm.model_dump(mode="json") == dm_snapshot
    assert ep.model_dump(mode="json") == ep_snapshot
    assert rec.model_dump(mode="json") == rec_snapshot
    assert scen_set.model_dump(mode="json") == scen_snapshot


# ------------------------------------------------------------------------------
# 3. Referential Integrity Tests
# ------------------------------------------------------------------------------

def test_referential_integrity_mismatches_rejected():
    dm = build_test_decision_model(dm_id="dm_auth_1")
    rec = build_test_recommendation(dm_id="dm_auth_1")
    scen_set = build_test_scenario_set(dm_id="dm_auth_1", rec_id=rec.id)

    # 1. Mismatched scenario_set decision_model_id
    bad_scen_set = ScenarioSet(
        id=scen_set.id,
        decision_model_id="dm_foreign_99",
        recommendation_id=rec.id,
        summary=scen_set.summary,
        scenarios=scen_set.scenarios,
    )
    with pytest.raises(ValueError, match="Referential integrity mismatch: ScenarioSet decision_model_id"):
        evaluate_resilience(dm, bad_scen_set, rec)

    # 2. Mismatched recommendation decision_model_id
    bad_rec = build_test_recommendation(dm_id="dm_foreign_99")
    with pytest.raises(ValueError, match="Referential integrity mismatch: Recommendation decision_model_id"):
        evaluate_resilience(dm, scen_set, bad_rec)

    # 3. Mismatched scenario_set recommendation_id
    bad_scen_rec = ScenarioSet(
        id=scen_set.id,
        decision_model_id=dm.id,
        recommendation_id="rec_foreign_99",
        summary=scen_set.summary,
        scenarios=scen_set.scenarios,
    )
    with pytest.raises(ValueError, match="Referential integrity mismatch: ScenarioSet recommendation_id"):
        evaluate_resilience(dm, bad_scen_rec, rec)

    # 4. Mismatched evidence_package decision_model_id
    bad_ep = build_test_evidence_package(dm_id="dm_foreign_99")
    with pytest.raises(ValueError, match="Referential integrity mismatch: EvidencePackage decision_model_id"):
        evaluate_resilience(dm, scen_set, rec, evidence_package=bad_ep)

    # 5. Mismatched reasoning_board decision_model_id
    bad_rb = build_test_reasoning_board(dm_id="dm_foreign_99")
    with pytest.raises(ValueError, match="Referential integrity mismatch: ReasoningBoard decision_model_id"):
        evaluate_resilience(dm, scen_set, rec, reasoning_board=bad_rb)


# ------------------------------------------------------------------------------
# 4. Incomplete & Missing Input Policies
# ------------------------------------------------------------------------------

def test_missing_pessimistic_risks_handling():
    """Empty risks in pessimistic scenario must not award perfect survivability."""
    dm = build_test_decision_model()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id, pessimistic_risks=[])

    report = evaluate_resilience(dm, scen_set, rec)
    sub_b = next(s for s in report.sub_scores if s.category == ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value)

    # Neutral 0.50 unmitigated ratio applied: 25 * (1 - 0.20 * 0.50) = 22.5
    assert sub_b.score == 22.5
    assert any("neutral uncertainty ratio" in v for v in sub_b.vulnerabilities_detected)


def test_missing_decision_gates_handling():
    """No decision gates in recommendation yields 0 gate points and a critical vulnerability."""
    dm = build_test_decision_model()
    act = ActionItem(
        id="act_simple",
        title="Simple Action",
        objective="Execute task",
        description="Just run it without gates",
        priority=ActionPriority.MEDIUM,
        responsible_role="Lead",
        time_horizon=ActionTimeHorizon.IMMEDIATE,
        dependencies=[],
        success_metrics=["Done"],
        decision_gates=[],  # zero gates
    )
    rec = build_test_recommendation(actions=[act])
    scen_set = build_test_scenario_set(rec_id=rec.id)

    report = evaluate_resilience(dm, scen_set, rec)
    sub_c = next(s for s in report.sub_scores if s.category == ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value)

    assert "No decision gates defined" in sub_c.rationale
    assert any("Zero decision gates established" in v for v in report.critical_vulnerabilities)


def test_missing_constraints_handling():
    """No constraints declared in DecisionModel yields neutral 7.5 baseline, not 15.0."""
    dm = build_test_decision_model(constraints=[])
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    report = evaluate_resilience(dm, scen_set, rec)
    sub_a = next(s for s in report.sub_scores if s.category == ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value)

    # 7.5 cnstr + 6.0 reversibility = 13.5
    assert sub_a.score == 13.5
    assert any("No operational constraints declared" in v for v in sub_a.vulnerabilities_detected)


def test_missing_evidence_package_handling():
    """When EvidencePackage is omitted, a neutral 3.0/6.0 gap score is applied without error."""
    dm = build_test_decision_model()
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    report = evaluate_resilience(dm, scen_set, rec, evidence_package=None)
    sub_d = next(s for s in report.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)

    assert "EvidencePackage not supplied (neutral 3.0/6.0 pts applied)" in sub_d.rationale


def test_missing_assumptions_handling():
    """When DecisionModel has no assumptions, neutral 3.0/5.0 score is applied."""
    dm = build_test_decision_model(assumptions=[])
    rec = build_test_recommendation()
    scen_set = build_test_scenario_set(rec_id=rec.id)

    report = evaluate_resilience(dm, scen_set, rec)
    sub_d = next(s for s in report.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)

    assert "No explicit assumptions documented (neutral 3.0/5.0 pts)" in sub_d.rationale


# ------------------------------------------------------------------------------
# 5. Rating Boundaries and Stress-Test Pass/Fail Tests
# ------------------------------------------------------------------------------

def test_stress_test_failure_on_low_survivability():
    """Even if overall score is moderate, low survivability (< 12.5) fails the stress test."""
    dm = build_test_decision_model(reversibility=ReversibilityLevel.REVERSIBLE)
    rec = build_test_recommendation(
        stability=RecommendationStability.HIGH,
        evidence_strength=EvidenceStrength.STRONG,
    )
    # 60% probability of adverse scenario with 100% unmitigated risks:
    # Pillar B survivability = 25 * (1 - 0.60 * 1.0) = 10.0 (< 12.5)
    unmitigated_risks = [
        "Unprecedented regulatory prohibition.",
        "Total bankruptcy of all target accounts.",
    ]
    scen_set = build_test_scenario_set(
        rec_id=rec.id,
        pessimistic_prob=0.60,
        pessimistic_risks=unmitigated_risks,
    )

    report = evaluate_resilience(dm, scen_set, rec)
    sub_b = next(s for s in report.sub_scores if s.category == ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value)

    assert sub_b.score == 10.0
    assert report.stress_test_passed is False


def test_rating_bands_coverage():
    """Verifies that high, moderate, fragile, and vulnerable ratings are mapped accurately."""
    # High score setup
    dm_high = build_test_decision_model(reversibility=ReversibilityLevel.REVERSIBLE)
    act_high = ActionItem(
        id="act_1",
        title="Action 1",
        objective="Obj 1",
        description="Desc 1",
        priority=ActionPriority.HIGH,
        responsible_role="Lead",
        time_horizon=ActionTimeHorizon.IMMEDIATE,
        dependencies=[],
        success_metrics=["M1"],
        risk_mitigations=["mitigate risk", "proactive response"],
        fallback_action="action fallback",
        decision_gates=[
            DecisionGate(
                id="g1",
                condition="Condition passes",
                target_milestone="M1",
                verification_method="Verify metric",
                fallback_action="Execute fallback",
            ),
            DecisionGate(
                id="g2",
                condition="Condition passes 2",
                target_milestone="M2",
                verification_method="Verify metric 2",
                fallback_action="Execute fallback 2",
            ),
            DecisionGate(
                id="g3",
                condition="Condition passes 3",
                target_milestone="M3",
                verification_method="Verify metric 3",
                fallback_action="Execute fallback 3",
            ),
        ],
    )
    alts_high = [
        AlternativeOption(
            id=f"alt_{i}",
            name=f"Alternative Strategy {i}",
            description=f"Description of strategic alternative option {i}",
            tradeoffs=["Tradeoff upside", "Tradeoff downside"],
            why_not_recommended="Does not satisfy primary objective fully",
        )
        for i in range(2)
    ]
    rec_high = build_test_recommendation(
        actions=[act_high],
        alternatives=alts_high,
        stability=RecommendationStability.HIGH,
        evidence_strength=EvidenceStrength.STRONG,
        readiness=DecisionReadiness.READY,
    )
    scen_high = build_test_scenario_set(
        rec_id=rec_high.id,
        pessimistic_prob=0.05,
        pessimistic_risks=["Operational delay"],
        pessimistic_constraint_ids=[],  # no constraints pressured
    )

    rep_high = evaluate_resilience(dm_high, scen_high, rec_high)
    assert rep_high.rating == ResilienceRating.HIGH
    assert rep_high.overall_score >= 80.0
