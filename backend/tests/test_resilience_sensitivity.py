"""Tests for AURA Deterministic Resilience Engine Sensitivity & Monotonicity (Day 6 Phase 6A).

Covers:
- Pessimistic scenario probability sensitivity (higher probability -> non-increasing survivability)
- Mitigation coverage sensitivity (more mitigated risks -> non-decreasing survivability)
- Decision gates sensitivity (more complete gates -> non-decreasing contingency coverage)
- Action plan mitigation sensitivity (higher ratio of mitigated actions -> non-decreasing coverage)
- Alternative options sensitivity (0 -> 1 -> >=2 options monotonically increasing)
- Evidence gap count and impact sensitivity (more/higher-impact gaps -> non-increasing robustness)
- Assumption confidence level sensitivity (HIGH -> MEDIUM -> LOW -> UNTESTED monotonically decreasing)
- Recommendation stability sensitivity (HIGH -> MODERATE -> VOLATILE monotonically decreasing)
- Evidence strength sensitivity (STRONG -> MODERATE -> LIMITED -> CONTESTED -> INSUFFICIENT)
- Reversibility level sensitivity (REVERSIBLE -> PARTIALLY -> IRREVERSIBLE)
- Hard constraint pressure sensitivity (0 -> 1 -> 2 pressured constraints monotonically decreasing)
"""

import math
from typing import List, Optional
import pytest

from app.engines.resilience import evaluate_resilience
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
    TimeHorizon,
    Tradeoff,
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
from app.schemas.resilience import ResiliencePillar
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
# Sensitivity Fixture Helpers
# ------------------------------------------------------------------------------

def make_decision_model(
    dm_id: str = "dm_sens_01",
    reversibility: ReversibilityLevel = ReversibilityLevel.PARTIALLY_REVERSIBLE,
    constraints: Optional[List[Constraint]] = None,
    assumptions: Optional[List[Assumption]] = None,
) -> DecisionModel:
    if constraints is None:
        constraints = [
            Constraint(id="c1", name="Budget Constraint", description="Maintain budget ceiling", is_hard_constraint=True),
            Constraint(id="c2", name="Headcount Limit", description="Max 5 new hires", is_hard_constraint=True),
        ]
    if assumptions is None:
        assumptions = [
            Assumption(id="a1", statement="Market growth is positive", confidence=ConfidenceLevel.HIGH),
        ]

    return DecisionModel(
        id=dm_id,
        decision=Decision(
            raw_prompt="Expand into new market?",
            summary="Strategic market expansion decision.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Market dynamics.",
            reversibility=reversibility,
        ),
        objectives=[Objective(id="obj1", description="Grow revenue", is_primary=True)],
        variables=[
            Variable(id="v1", name="Market Size", description="Total market size", variable_type=VariableType.NUMERIC),
        ],
        constraints=constraints,
        stakeholders=[],
        tradeoffs=[
            Tradeoff(id="t1", upside="Growth potential", downside="Capital expense"),
        ],
        assumptions=assumptions,
        unknowns=[],
        key_questions=["Can we scale operations?"],
    )


def make_evidence_package(
    dm_id: str = "dm_sens_01",
    gaps: Optional[List[EvidenceGap]] = None,
) -> EvidencePackage:
    if gaps is None:
        gaps = []
    src = Source(
        id="src1",
        title="Report",
        source_type=SourceType.INDUSTRY_REPORT,
        url="https://example.com",
    )
    item = EvidenceItem(id="evi1", source_id="src1", content="Evidence content")
    req = EvidenceRequirement(
        id="req1",
        description="Verify market",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        target_entity_id="obj1",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        status=RequirementStatus.FULFILLED,
    )
    return EvidencePackage(
        id="pkg_sens_01",
        decision_model_id=dm_id,
        summary="Evidence package for sensitivity testing.",
        sources=[src],
        items=[item],
        requirements=[req],
        gaps=gaps,
        claim_links=[],
    )


def make_recommendation(
    dm_id: str = "dm_sens_01",
    actions: Optional[List[ActionItem]] = None,
    alternatives: Optional[List[AlternativeOption]] = None,
    stability: RecommendationStability = RecommendationStability.HIGH,
    evidence_strength: EvidenceStrength = EvidenceStrength.STRONG,
    readiness: DecisionReadiness = DecisionReadiness.READY,
) -> DecisionRecommendation:
    if actions is None:
        actions = [
            ActionItem(
                id="act1",
                title="Action 1",
                objective="Obj 1",
                description="Desc 1",
                priority=ActionPriority.HIGH,
                responsible_role="Lead",
                time_horizon=ActionTimeHorizon.IMMEDIATE,
                dependencies=[],
                success_metrics=["M1"],
                risk_mitigations=["mitigate risk"],
                fallback_action="action fallback",
                decision_gates=[
                    DecisionGate(
                        id="g1",
                        condition="Condition metric verified",
                        target_milestone="M1",
                        verification_method="Audit contracts",
                        fallback_action="Pause rollout",
                    )
                ],
            )
        ]
    if alternatives is None:
        alternatives = [
            AlternativeOption(
                id="alt1",
                name="Status Quo",
                description="Keep current operations",
                tradeoffs=["Tradeoff 1"],
                why_not_recommended="Does not meet goals",
            )
        ]

    rec_id = generate_deterministic_recommendation_id(
        decision_model_id=dm_id,
        evidence_package_id="pkg_sens_01",
        reasoning_board_id="rbd_sens_01",
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute expansion with gating.",
        executive_rationale="Solid empirical support.",
        action_ids=[a.id for a in actions],
    )
    return DecisionRecommendation(
        id=rec_id,
        decision_model_id=dm_id,
        evidence_package_id="pkg_sens_01",
        reasoning_board_id="rbd_sens_01",
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute expansion with gating.",
        executive_rationale="Solid empirical support.",
        supporting_evidence_item_ids=["evi1"],
        relevant_assumption_ids=[],
        relevant_evidence_gap_ids=[],
        unresolved_disagreement_ids=[],
        alternative_options=alternatives,
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=evidence_strength,
            decision_readiness=readiness,
            recommendation_stability=stability,
            critical_missing_information=[],
            conditions_changing_recommendation=[],
            assumptions_relied_upon=[],
            evidence_gaps_relied_upon=[],
        ),
        action_plan=ActionPlan(
            summary="Implementation plan.",
            actions=actions,
            key_milestones=["Milestone 1"],
        ),
    )


def make_scenario_set(
    dm_id: str = "dm_sens_01",
    rec_id: str = "rec_sens_01",
    pessimistic_prob: float = 0.20,
    pessimistic_risks: Optional[List[str]] = None,
    pessimistic_constraint_ids: Optional[List[str]] = None,
) -> ScenarioSet:
    if pessimistic_risks is None:
        pessimistic_risks = ["Risk A unmitigated", "Risk B unmitigated"]
    if pessimistic_constraint_ids is None:
        pessimistic_constraint_ids = []

    opt_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.OPTIMISTIC,
        name="Optimistic",
        probability=0.25,
        key_event_titles=["Early adoption"],
    )
    base_prob = round(1.0 - 0.25 - pessimistic_prob, 2)
    base_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.BASE_CASE,
        name="Base Case",
        probability=base_prob,
        key_event_titles=["Steady progress"],
    )
    pess_id = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.PESSIMISTIC,
        name="Pessimistic",
        probability=pessimistic_prob,
        key_event_titles=["Adverse downturn"],
    )

    scen_opt = FutureScenario(
        id=opt_id,
        scenario_type=ScenarioType.OPTIMISTIC,
        probability=0.25,
        name="Optimistic",
        narrative="Optimistic outcome.",
        key_events=[
            ScenarioKeyEvent(id="ke_o", title="Early adoption", description="Strong demand", timeframe="M3", significance="High")
        ],
        risks=[],
        opportunities=["Growth"],
        timeline=[ScenarioMilestone(id="ms_o", title="M1", description="Completed optimistic rollout", time_horizon="M6", expected_outcome="Target achieved")],
    )
    scen_base = FutureScenario(
        id=base_id,
        scenario_type=ScenarioType.BASE_CASE,
        probability=base_prob,
        name="Base Case",
        narrative="Base case outcome.",
        key_events=[
            ScenarioKeyEvent(id="ke_b", title="Steady progress", description="Normal sales", timeframe="M6", significance="Normal")
        ],
        risks=[],
        opportunities=["Steady"],
        timeline=[ScenarioMilestone(id="ms_b", title="M1", description="Completed steady progress", time_horizon="M6", expected_outcome="Target achieved")],
    )
    scen_pess = FutureScenario(
        id=pess_id,
        scenario_type=ScenarioType.PESSIMISTIC,
        probability=pessimistic_prob,
        name="Pessimistic",
        narrative="Adverse outcome.",
        key_events=[
            ScenarioKeyEvent(id="ke_p", title="Adverse downturn", description="Downturn", timeframe="M6", significance="Critical")
        ],
        risks=pessimistic_risks,
        opportunities=[],
        timeline=[ScenarioMilestone(id="ms_p", title="M1", description="Evaluated cutover threshold", time_horizon="M6", expected_outcome="Cash protected")],
        relevant_constraint_ids=pessimistic_constraint_ids,
    )

    scenarios = [scen_opt, scen_base, scen_pess]
    set_id = generate_deterministic_scenarioset_id(dm_id, rec_id, [s.id for s in scenarios])
    return ScenarioSet(
        id=set_id,
        decision_model_id=dm_id,
        recommendation_id=rec_id,
        summary="Scenario set for sensitivity testing.",
        scenarios=scenarios,
    )


# ------------------------------------------------------------------------------
# 1. Pessimistic Probability Sensitivity
# ------------------------------------------------------------------------------

def test_pessimistic_probability_sensitivity():
    """Higher pessimistic probability must yield non-increasing survivability score."""
    dm = make_decision_model()
    rec = make_recommendation()

    probabilities = [0.05, 0.15, 0.30, 0.50, 0.70]
    scores = []

    for prob in probabilities:
        scen_set = make_scenario_set(rec_id=rec.id, pessimistic_prob=prob)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_b = next(s for s in rep.sub_scores if s.category == ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value)
        scores.append(sub_b.score)

    # Monotonically non-increasing: s[i] >= s[i+1]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Expected {scores[i]} >= {scores[i + 1]} at step {i}"


# ------------------------------------------------------------------------------
# 2. Mitigated vs Unmitigated Risk Sensitivity
# ------------------------------------------------------------------------------

def test_mitigated_risk_sensitivity():
    """Adding mitigation coverage for pessimistic risks must yield non-decreasing survivability."""
    dm = make_decision_model()

    # Three adverse risks:
    # 1. "Currency exchange volatility causes margin collapse."
    # 2. "Supplier component default halts production line."
    # 3. "Cybersecurity attack breaches customer credentials."
    adverse_risks = [
        "Currency exchange volatility causes margin collapse.",
        "Supplier component default halts production line.",
        "Cybersecurity attack breaches customer credentials.",
    ]

    # Vary recommendation action mitigations from 0 to 3 matching keywords:
    mitigation_levels = [
        [],  # 0 mitigated
        ["Currency hedging contract eliminates volatility."],  # 1 mitigated ("currency")
        ["Currency hedging contract eliminates volatility.", "Secondary supplier qualified for component redundancy."],  # 2 mitigated ("supplier")
        ["Currency hedging contract eliminates volatility.", "Secondary supplier qualified for component redundancy.", "Cybersecurity penetration testing and multi-factor auth."],  # 3 mitigated ("cybersecurity")
    ]

    scores = []
    for mits in mitigation_levels:
        act = ActionItem(
            id="act_test",
            title="Operational Strategy",
            objective="Obj",
            description="Operational description",
            priority=ActionPriority.HIGH,
            responsible_role="Role",
            time_horizon=ActionTimeHorizon.IMMEDIATE,
            dependencies=[],
            success_metrics=["M"],
            risk_mitigations=mits,
            decision_gates=[],
        )
        rec = make_recommendation(actions=[act])
        scen_set = make_scenario_set(rec_id=rec.id, pessimistic_prob=0.30, pessimistic_risks=adverse_risks)

        rep = evaluate_resilience(dm, scen_set, rec)
        sub_b = next(s for s in rep.sub_scores if s.category == ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value)
        scores.append(sub_b.score)

    # Monotonically non-decreasing: s[i] <= s[i+1]
    for i in range(len(scores) - 1):
        assert scores[i] <= scores[i + 1], f"Expected {scores[i]} <= {scores[i + 1]} at step {i}"


# ------------------------------------------------------------------------------
# 3. Decision Gates Sensitivity
# ------------------------------------------------------------------------------

def test_decision_gates_sensitivity():
    """Increasing quality and completeness of decision gates must increase Pillar C score."""
    dm = make_decision_model()

    gate_configs = [
        [],  # 0 gates -> 0.0 pts
        [DecisionGate(id="g1", condition="Threshold met", target_milestone="M1", verification_method="Verify ledger", fallback_action="Pause deployment")],  # 1 complete -> 4.0 pts
        [
            DecisionGate(id="g1", condition="Threshold met", target_milestone="M1", verification_method="Verify ledger", fallback_action="Pause deployment"),
            DecisionGate(id="g2", condition="Second threshold", target_milestone="M2", verification_method="Audit report", fallback_action="Halt expansion"),
        ],  # 2 complete -> 8.0 pts
        [
            DecisionGate(id="g1", condition="Threshold met", target_milestone="M1", verification_method="Verify ledger", fallback_action="Pause deployment"),
            DecisionGate(id="g2", condition="Second threshold", target_milestone="M2", verification_method="Audit report", fallback_action="Halt expansion"),
            DecisionGate(id="g3", condition="Third threshold", target_milestone="M3", verification_method="External signoff", fallback_action="Rollback cluster"),
        ],  # 3 complete -> 12.0 pts (max cap)
    ]

    scores = []
    for gates in gate_configs:
        act = ActionItem(
            id="act1",
            title="Action",
            objective="Obj",
            description="Action description",
            priority=ActionPriority.HIGH,
            responsible_role="Role",
            time_horizon=ActionTimeHorizon.IMMEDIATE,
            dependencies=[],
            success_metrics=["M"],
            risk_mitigations=[],
            decision_gates=gates,
        )
        rec = make_recommendation(actions=[act], alternatives=[])
        scen_set = make_scenario_set(rec_id=rec.id)

        rep = evaluate_resilience(dm, scen_set, rec)
        sub_c = next(s for s in rep.sub_scores if s.category == ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value)
        scores.append(sub_c.score)

    for i in range(len(scores) - 1):
        assert scores[i] <= scores[i + 1], f"Expected {scores[i]} <= {scores[i + 1]} at gate step {i}"


# ------------------------------------------------------------------------------
# 4. Alternative Options Sensitivity
# ------------------------------------------------------------------------------

def test_alternative_options_sensitivity():
    """0 alternatives (0.0 pts) < 1 alternative (3.0 pts) < 2 alternatives (5.0 pts)."""
    dm = make_decision_model()

    alt_levels = [
        [],  # 0
        [AlternativeOption(id="a1", name="Alt 1", description="Desc 1", tradeoffs=["T1"], why_not_recommended="Reason 1")],  # 1
        [
            AlternativeOption(id="a1", name="Alt 1", description="Desc 1", tradeoffs=["T1"], why_not_recommended="Reason 1"),
            AlternativeOption(id="a2", name="Alt 2", description="Desc 2", tradeoffs=["T2"], why_not_recommended="Reason 2"),
        ],  # 2
    ]

    scores = []
    for alts in alt_levels:
        rec = make_recommendation(alternatives=alts)
        scen_set = make_scenario_set(rec_id=rec.id)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_c = next(s for s in rep.sub_scores if s.category == ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value)
        scores.append(sub_c.score)

    assert scores[0] < scores[1] < scores[2]
    assert round(scores[1] - scores[0], 1) == 3.0
    assert round(scores[2] - scores[1], 1) == 2.0


# ------------------------------------------------------------------------------
# 5. Evidence Gap Count and Impact Sensitivity
# ------------------------------------------------------------------------------

def test_evidence_gap_sensitivity():
    """Higher number and higher impact of evidence gaps must reduce Information Robustness score."""
    dm = make_decision_model()
    rec = make_recommendation()
    scen_set = make_scenario_set(rec_id=rec.id)

    gap_levels = [
        [],  # 0 gaps -> 6.0 pts
        [EvidenceGap(id="g1", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 1", impact=CriticalityLevel.LOW)],  # penalty 0.5 -> 5.5 pts
        [EvidenceGap(id="g1", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 1", impact=CriticalityLevel.MEDIUM)],  # penalty 1.0 -> 5.0 pts
        [EvidenceGap(id="g1", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 1", impact=CriticalityLevel.HIGH)],  # penalty 2.0 -> 4.0 pts
        [
            EvidenceGap(id="g1", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 1", impact=CriticalityLevel.HIGH),
            EvidenceGap(id="g2", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 2", impact=CriticalityLevel.HIGH),
        ],  # penalty 4.0 -> 2.0 pts
        [
            EvidenceGap(id="g1", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 1", impact=CriticalityLevel.HIGH),
            EvidenceGap(id="g2", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 2", impact=CriticalityLevel.HIGH),
            EvidenceGap(id="g3", gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE, target_entity_id="obj1", target_entity_type=DecisionEntityType.OBJECTIVE, description="Gap 3", impact=CriticalityLevel.HIGH),
        ],  # penalty 6.0 -> 0.0 pts (max cap)
    ]

    scores = []
    for gaps in gap_levels:
        ep = make_evidence_package(gaps=gaps)
        rep = evaluate_resilience(dm, scen_set, rec, evidence_package=ep)
        sub_d = next(s for s in rep.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)
        scores.append(sub_d.score)

    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Expected {scores[i]} >= {scores[i + 1]} at gap step {i}"
    assert scores[0] > scores[-1]


# ------------------------------------------------------------------------------
# 6. Assumption Confidence Sensitivity
# ------------------------------------------------------------------------------

def test_assumption_confidence_sensitivity():
    """Higher assumption confidence levels must yield strictly higher Information Robustness."""
    conf_levels = [
        ConfidenceLevel.HIGH,
        ConfidenceLevel.MEDIUM,
        ConfidenceLevel.LOW,
        ConfidenceLevel.UNTESTED,
    ]
    scores = []

    rec = make_recommendation()
    scen_set = make_scenario_set(rec_id=rec.id)

    for conf in conf_levels:
        asm = [Assumption(id="a1", statement="Key operational hypothesis", confidence=conf)]
        dm = make_decision_model(assumptions=asm)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_d = next(s for s in rep.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)
        scores.append(sub_d.score)

    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1], f"Expected {scores[i]} > {scores[i + 1]} at assumption step {i}"


# ------------------------------------------------------------------------------
# 7. Recommendation Stability Sensitivity
# ------------------------------------------------------------------------------

def test_recommendation_stability_sensitivity():
    """HIGH > MODERATE > VOLATILE recommendation stability."""
    stabilities = [
        RecommendationStability.HIGH,
        RecommendationStability.MODERATE,
        RecommendationStability.VOLATILE,
    ]
    dm = make_decision_model()
    scores = []

    for stab in stabilities:
        rec = make_recommendation(stability=stab)
        scen_set = make_scenario_set(rec_id=rec.id)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_d = next(s for s in rep.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)
        scores.append(sub_d.score)

    assert scores[0] > scores[1] > scores[2]
    assert scores[0] == scores[1] + 2.0
    assert scores[1] == scores[2] + 2.0


# ------------------------------------------------------------------------------
# 8. Evidence Strength Sensitivity
# ------------------------------------------------------------------------------

def test_evidence_strength_sensitivity():
    """STRONG > MODERATE > LIMITED > CONTESTED > INSUFFICIENT evidence strength."""
    strengths = [
        EvidenceStrength.STRONG,
        EvidenceStrength.MODERATE,
        EvidenceStrength.LIMITED,
        EvidenceStrength.CONTESTED,
        EvidenceStrength.INSUFFICIENT,
    ]
    dm = make_decision_model()
    scores = []

    for st in strengths:
        rec = make_recommendation(evidence_strength=st)
        scen_set = make_scenario_set(rec_id=rec.id)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_d = next(s for s in rep.sub_scores if s.category == ResiliencePillar.INFORMATION_ROBUSTNESS.value)
        scores.append(sub_d.score)

    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1], f"Expected {scores[i]} > {scores[i + 1]} at strength step {i}"


# ------------------------------------------------------------------------------
# 9. Reversibility Sensitivity
# ------------------------------------------------------------------------------

def test_reversibility_sensitivity():
    """REVERSIBLE (10.0 pts) > PARTIALLY_REVERSIBLE (6.0 pts) > IRREVERSIBLE (2.0 pts)."""
    reversibilities = [
        ReversibilityLevel.REVERSIBLE,
        ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ReversibilityLevel.IRREVERSIBLE,
    ]
    rec = make_recommendation()
    scen_set = make_scenario_set(rec_id=rec.id)
    scores = []

    for rev in reversibilities:
        dm = make_decision_model(reversibility=rev)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_a = next(s for s in rep.sub_scores if s.category == ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value)
        scores.append(sub_a.score)

    assert scores[0] > scores[1] > scores[2]
    assert round(scores[0] - scores[1], 1) == 4.0
    assert round(scores[1] - scores[2], 1) == 4.0


# ------------------------------------------------------------------------------
# 10. Hard Constraint Pressure Sensitivity
# ------------------------------------------------------------------------------

def test_hard_constraint_pressure_sensitivity():
    """More hard constraints pressured in pessimistic scenario reduces Pillar A score."""
    dm = make_decision_model(
        constraints=[
            Constraint(id="c1", name="Budget Limit", description="Max spend", is_hard_constraint=True),
            Constraint(id="c2", name="Headcount Limit", description="Max hires", is_hard_constraint=True),
        ]
    )
    rec = make_recommendation()

    # Pressure: 0 hard constraints -> 1 hard constraint -> 2 hard constraints
    pressured_levels = [
        [],          # 0/2 -> 15.0 pts
        ["c1"],      # 1/2 -> 7.5 pts
        ["c1", "c2"] # 2/2 -> 0.0 pts
    ]
    scores = []

    for pressured in pressured_levels:
        scen_set = make_scenario_set(rec_id=rec.id, pessimistic_constraint_ids=pressured)
        rep = evaluate_resilience(dm, scen_set, rec)
        sub_a = next(s for s in rep.sub_scores if s.category == ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value)
        scores.append(sub_a.score)

    assert scores[0] > scores[1] > scores[2]
    assert round(scores[0] - scores[1], 1) == 7.5
    assert round(scores[1] - scores[2], 1) == 7.5
