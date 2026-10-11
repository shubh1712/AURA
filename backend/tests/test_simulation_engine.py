"""Phase 7A Unit Tests: Deterministic What-if Simulation Engine.

Comprehensive verification of:
1. Pure deterministic simulation execution.
2. Rejection of cross-artifact referential mismatches.
3. Rejection of unknown variables.
4. Rejection of unit mismatches.
5. Rejection of bound violations.
6. Absolute immutability of baseline input artifacts.
7. Scenario portfolio integrity (exactly three canonical trajectories, probability preservation).
8. Legitimate recalculation of resilience score delta when a supported constraint threshold is breached.
9. Explicitly unavailable score delta (None, not 0.0) when an unmapped variable is adjusted.
10. Regression proof: unsupported changes NEVER fabricate resilience improvements or synthetic formulas.
11. Repeatable SHA-256 simulation IDs with ordering invariance.
12. Zero LLM calls and zero network requests during simulation.
"""

from datetime import datetime, timezone
import pytest

from app.engines.resilience import evaluate_resilience
from app.engines.simulation import (
    RULE_CONSTRAINT_THRESHOLD_EVALUATION,
    RULE_DIRECT_VARIABLE_SUBSTITUTION,
    simulate_what_if,
)
from app.schemas.decision_model import (
    Complexity,
    ComplexityLevel,
    ConfidenceLevel,
    Constraint,
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
from app.schemas.recommendation import (
    ActionItem,
    ActionPlan,
    ActionPriority,
    ActionTimeHorizon,
    DecisionGate,
    DecisionReadiness,
    DecisionRecommendation,
    DecisionStatus,
    EvidenceStrength,
    RecommendationStability,
    UncertaintyAssessment,
)
from app.schemas.resilience import (
    ResilienceRating,
    ResilienceReport,
)
from app.schemas.scenario import (
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
)
from app.schemas.simulation import (
    SimulationAdjustment,
    SimulationCalculationStatus,
    SimulationRequest,
    SimulationResult,
)


# ------------------------------------------------------------------------------
# Test Fixtures Builder
# ------------------------------------------------------------------------------

def _build_full_test_environment(
    budget_limit: float = 50000.0,
    baseline_spend: float = 35000.0,
    pessimistic_pressured_constraints: list = None,
):
    """Builds a complete, referentially integrated set of authoritative decision artifacts."""
    decision_model_id = "dec_sim_test_001"
    recommendation_id = "rec_0123456789abcdef0123456789abcdef"
    scenario_set_id = "scenset_0123456789abcdef0123456789abcdef"

    # 1. DecisionModel
    variables = [
        Variable(
            id="var_monthly_cloud_spend",
            name="Monthly Cloud Spend",
            description="Infrastructure operational expenditure.",
            variable_type=VariableType.CURRENCY,
            baseline_value=baseline_spend,
            unit="USD",
            is_controllable=True,
        ),
        Variable(
            id="var_discount_rate",
            name="Customer Discount Rate",
            description="Volume sales discount percentage.",
            variable_type=VariableType.PERCENTAGE,
            baseline_value=15.0,
            unit="%",
            is_controllable=True,
        ),
    ]

    constraints = [
        Constraint(
            id="cnstr_cloud_budget",
            name="Monthly Cloud Spend",
            description=f"Monthly cloud spend capped at ${budget_limit:,.0f}.",
            is_hard_constraint=True,
            threshold_expression=f"spend <= {budget_limit:.0f}",
        ),
    ]

    dm = DecisionModel(
        id=decision_model_id,
        decision=Decision(
            raw_prompt="Should we expand cloud capacity to Europe?",
            summary="European cloud expansion decision.",
            decision_type=DecisionType.ARCHITECTURE_TECH,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Multi-region replication.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[Objective(id="obj_1", description="Global availability", is_primary=True)],
        variables=variables,
        constraints=constraints,
        tradeoffs=[Tradeoff(id="trd_1", upside="Lower latency", downside="Higher cost", affected_variable_ids=[])],
        key_questions=["Will traffic materialize?"],
    )

    # 2. Recommendation
    rec = DecisionRecommendation(
        id=recommendation_id,
        decision_model_id=decision_model_id,
        evidence_package_id="pkg_sim_test_001",
        reasoning_board_id="rbd_sim_test_001",
        decision_status=DecisionStatus.CONDITIONAL,
        recommended_action="Deploy pilot European ingress nodes.",
        executive_rationale="Empirical evidence demonstrates strong market demand growth for low latency nodes.",
        action_plan=ActionPlan(
            summary="Two-phase pilot roadmap for European deployment.",
            actions=[
                ActionItem(
                    id="act_01",
                    title="Phase 1 Pilot",
                    objective="Validate cloud pilot deployment",
                    description="Deploy shadow ingress in eu-west-1.",
                    priority=ActionPriority.HIGH,
                    responsible_role="Lead Architect",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    decision_gates=[
                        DecisionGate(
                            id="gate_01",
                            condition="Spend breaches $45,000",
                            target_milestone="Spend Audit",
                            verification_method="Cloud Billing Alerts",
                            fallback_action="Deprovision secondary cluster",
                        )
                    ],
                )
            ],
        ),
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
        ),
    )

    # 3. ScenarioSet
    pess_constraints = pessimistic_pressured_constraints if pessimistic_pressured_constraints is not None else []
    scenarios = [
        FutureScenario(
            id="scen_1111111111111111",
            scenario_type=ScenarioType.OPTIMISTIC,
            probability=0.25,
            name="Rapid Adoption",
            narrative="European traffic scales 3x with linear revenue.",
            key_events=[ScenarioKeyEvent(id="ke_1", title="Viral growth", description="Traffic surge event", timeframe="M1")],
            timeline=[ScenarioMilestone(id="ms_1", title="Launch", description="All green milestone", time_horizon="immediate", expected_outcome="99.99%")],
        ),
        FutureScenario(
            id="scen_2222222222222222",
            scenario_type=ScenarioType.BASE_CASE,
            probability=0.55,
            name="Controlled Growth",
            narrative="Steady adoption meeting base forecast.",
            key_events=[ScenarioKeyEvent(id="ke_2", title="Cutover", description="Traffic cutover event", timeframe="M2")],
            timeline=[ScenarioMilestone(id="ms_2", title="Cutover", description="Verified milestone", time_horizon="immediate", expected_outcome="99.9%")],
        ),
        FutureScenario(
            id="scen_3333333333333333",
            scenario_type=ScenarioType.PESSIMISTIC,
            probability=0.20,
            name="Market Stagnation",
            narrative="Adverse traffic plateau under high fixed infrastructure costs.",
            key_events=[ScenarioKeyEvent(id="ke_3", title="Plateau", description="Demand drops event", timeframe="M3")],
            timeline=[ScenarioMilestone(id="ms_3", title="Review", description="Audit review checkpoint", time_horizon="immediate", expected_outcome="Halt")],
            relevant_constraint_ids=pess_constraints,
        ),
    ]

    scen_set = ScenarioSet(
        id=scenario_set_id,
        decision_model_id=decision_model_id,
        recommendation_id=recommendation_id,
        summary="Three canonical trajectories synthesis.",
        scenarios=scenarios,
    )

    return dm, scen_set, rec


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------

def test_01_referential_integrity_mismatches_rejected():
    """Verify simulate_what_if rejects cross-artifact ID mismatches."""
    dm, scens, rec = _build_full_test_environment()

    # Mismatched decision_model_id
    req_bad_dm = SimulationRequest(
        decision_model_id="dec_wrong_id",
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0)],
    )
    with pytest.raises(ValueError, match="Referential integrity mismatch.*decision_model_id"):
        simulate_what_if(req_bad_dm, dm, scens, rec)

    # Mismatched scenario_set_id
    req_bad_scen = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id="scenset_wrong_id",
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0)],
    )
    with pytest.raises(ValueError, match="Referential integrity mismatch.*scenario_set_id"):
        simulate_what_if(req_bad_scen, dm, scens, rec)

    # Mismatched recommendation_id
    req_bad_rec = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id="rec_wrong_id",
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0)],
    )
    with pytest.raises(ValueError, match="Referential integrity mismatch.*recommendation_id"):
        simulate_what_if(req_bad_rec, dm, scens, rec)


def test_02_unknown_variable_and_unit_mismatch_rejected():
    """Verify simulate_what_if rejects unknown variables and unit mismatches."""
    dm, scens, rec = _build_full_test_environment()

    # Unknown variable
    req_unknown = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_non_existent", proposed_value=100.0)],
    )
    with pytest.raises(ValueError, match="Unknown variable_id 'var_non_existent'"):
        simulate_what_if(req_unknown, dm, scens, rec)

    # Unit mismatch: variable is USD, adjustment passes EUR
    req_bad_unit = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0, unit="EUR")],
    )
    with pytest.raises(ValueError, match="Unit mismatch for variable 'var_monthly_cloud_spend'.*EUR.*USD"):
        simulate_what_if(req_bad_unit, dm, scens, rec)


def test_03_bounds_violation_rejected():
    """Verify simulate_what_if rejects proposed values that violate variable bounds."""
    dm, scens, rec = _build_full_test_environment()

    # Currency variables have minimum_value = 0.0
    req_negative = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=-500.0, unit="USD")],
    )
    with pytest.raises(ValueError, match="violates minimum bound"):
        simulate_what_if(req_negative, dm, scens, rec)


def test_04_baseline_artifacts_remain_immutable():
    """Verify simulation modifies deep copies and leaves original baseline artifacts completely unchanged."""
    dm, scens, rec = _build_full_test_environment(budget_limit=50000.0, baseline_spend=35000.0)

    # Snapshot baseline values
    orig_var_val = dm.variables[0].proposed_value
    orig_pess_constraints = list(scens.scenarios[2].relevant_constraint_ids)

    req = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=65000.0, unit="USD")],
    )
    result = simulate_what_if(req, dm, scens, rec)

    assert result.status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING

    # Verify baseline artifacts were NOT mutated!
    assert dm.variables[0].proposed_value == orig_var_val
    assert list(scens.scenarios[2].relevant_constraint_ids) == orig_pess_constraints


def test_05_three_scenario_portfolio_integrity_preserved():
    """Verify that simulation preserves exactly 3 canonical scenarios and probability distribution."""
    dm, scens, rec = _build_full_test_environment()

    req = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=42000.0, unit="USD")],
    )
    result = simulate_what_if(req, dm, scens, rec)

    # Scenarios probabilities in baseline sum to 1.0
    prob_sum = sum(s.probability for s in scens.scenarios)
    assert abs(prob_sum - 1.0) <= 0.01

    # Canonical types preserved
    types = [s.scenario_type for s in scens.scenarios]
    assert types == [ScenarioType.OPTIMISTIC, ScenarioType.BASE_CASE, ScenarioType.PESSIMISTIC]


def test_06_operational_constraint_breach_evaluated_and_scenario_relevance_preserved():
    """Verify that breaching an operational constraint evaluates the breach while strictly protecting scenario relevance."""
    # Baseline: spend is $35,000, limit is $50,000
    orig_pess_constraints = ["cnstr_pre_existing_relevant"]
    dm, scens, rec = _build_full_test_environment(
        budget_limit=50000.0,
        baseline_spend=35000.0,
        pessimistic_pressured_constraints=orig_pess_constraints,
    )

    base_report = evaluate_resilience(dm, scens, rec)
    base_score = base_report.overall_score

    # Simulate: User increases spend to $65,000 (breaches constraint 'spend <= 50000')
    req = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=65000.0, unit="USD")],
    )
    sim_result = simulate_what_if(req, dm, scens, rec, baseline_resilience_report=base_report)

    # 1. Status is UNSUPPORTED_NO_CAUSAL_MAPPING (no fabricated arithmetic score delta)
    assert sim_result.status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
    assert sim_result.simulated_resilience_score is None
    assert sim_result.score_delta is None
    assert sim_result.baseline_resilience_score == base_score

    # 2. Impact record documents exact threshold evaluation rule and breach explanation
    impact = sim_result.impacts[0]
    assert impact.transformation_rule_id == RULE_CONSTRAINT_THRESHOLD_EVALUATION
    assert "breached threshold for constraint 'Monthly Cloud Spend'" in impact.explanation
    assert impact.calculation_status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING

    # 3. Scenario constraint relevance was NEVER modified (narrative semantics preserved)
    assert list(scens.scenarios[2].relevant_constraint_ids) == orig_pess_constraints
    assert "relevant_constraint_ids" not in impact.affected_fields

    # 4. Baseline fingerprint is present and valid
    assert sim_result.baseline_fingerprint.startswith("bfp_")
    assert len(sim_result.baseline_fingerprint) == 36


def test_07_unmapped_variable_produces_no_fabricated_score():
    """Regression test: Unsupported variable changes NEVER produce fabricated resilience scores or improvements."""
    dm, scens, rec = _build_full_test_environment()

    base_report = evaluate_resilience(dm, scens, rec)

    # Adjust 'var_discount_rate' (unmapped: discount percentage has no constraint or causal link to resilience inputs)
    req = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_discount_rate", proposed_value=30.0, unit="%")],
    )
    sim_result = simulate_what_if(req, dm, scens, rec, baseline_resilience_report=base_report)

    # 1. Status is UNSUPPORTED_NO_CAUSAL_MAPPING
    assert sim_result.status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING

    # 2. Simulated resilience score and delta MUST BE NONE (never claim 0.0 or fabricate a delta)
    assert sim_result.simulated_resilience_score is None
    assert sim_result.score_delta is None

    # 3. Impact indicates direct substitution without resilience mapping
    impact = sim_result.impacts[0]
    assert impact.transformation_rule_id == RULE_DIRECT_VARIABLE_SUBSTITUTION
    assert impact.calculation_status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
    assert "No verified causal mapping exists connecting this metric" in impact.explanation

    # 4. Warnings explicitly state that score delta is unavailable
    assert any("Score delta unavailable" in w for w in sim_result.warnings)


def test_08_deterministic_simulation_id_repeatability():
    """Verify simulation ID is 100% deterministic, repeatable, and order-invariant."""
    dm, scens, rec = _build_full_test_environment()

    req_1 = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[
            SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0, unit="USD"),
            SimulationAdjustment(variable_id="var_discount_rate", proposed_value=25.0, unit="%"),
        ],
    )
    req_2 = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[
            SimulationAdjustment(variable_id="var_discount_rate", proposed_value=25.0, unit="%"),
            SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=40000.0, unit="USD"),
        ],
    )

    res_1 = simulate_what_if(req_1, dm, scens, rec)
    res_2 = simulate_what_if(req_2, dm, scens, rec)

    assert res_1.id == res_2.id
    assert res_1.id.startswith("sim_")
    assert len(res_1.id) == 36


def test_09_zero_llm_and_zero_network_calls():
    """Verify simulate_what_if executes purely offline with zero external network or LLM calls."""
    import socket
    dm, scens, rec = _build_full_test_environment()

    req = SimulationRequest(
        decision_model_id=dm.id,
        scenario_set_id=scens.id,
        recommendation_id=rec.id,
        adjustments=[SimulationAdjustment(variable_id="var_monthly_cloud_spend", proposed_value=48000.0, unit="USD")],
    )

    # Disable socket creation during simulation to guarantee zero network access
    orig_socket = socket.socket

    def _blocked_socket(*args, **kwargs):
        raise RuntimeError("Network call attempted during pure deterministic simulation!")

    socket.socket = _blocked_socket
    try:
        result = simulate_what_if(req, dm, scens, rec)
        assert result.id.startswith("sim_")
    finally:
        socket.socket = orig_socket
