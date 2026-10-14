"""Phase 7A Unit Tests: Simulation Variable Discovery.

Comprehensive verification of:
1. Discovers only structured, typed numerical variables from DecisionModel.
2. Rejection of unverified prose numbers (e.g. prompt text, narrative descriptions).
3. Preservation of exact source lineage and attribute paths.
4. Stable variable IDs.
5. Distinction between controllable decision levers and non-controllable environmental variables.
6. Exclusion of scenario probabilities from variable discovery.
7. Correct categorization of types (CURRENCY, PERCENTAGE, COUNT, NUMERIC).
8. Return of an empty list when no eligible structured numeric variables exist.
9. Linkage detection to operational constraints.
"""

import pytest

from app.schemas.decision_model import (
    Complexity,
    ComplexityLevel,
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
from app.schemas.scenario import FutureScenario, ScenarioKeyEvent, ScenarioMilestone, ScenarioSet, ScenarioType
from app.schemas.simulation import (
    SimulationVariableType,
)
from app.services.simulation.variables import discover_simulation_variables


def _build_test_decision_model(variables, constraints=None, raw_prompt="Sample prompt with $150,000 budget"):
    return DecisionModel(
        id="dec_test_001",
        decision=Decision(
            raw_prompt=raw_prompt,
            summary="Test decision model for variable discovery.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Test complexity.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(id="obj_1", description="Primary goal.", is_primary=True)
        ],
        variables=variables,
        constraints=constraints or [],
        tradeoffs=[
            Tradeoff(id="trd_1", upside="Cost savings", downside="Delay", affected_variable_ids=[])
        ],
        key_questions=["Can we scale?"],
    )


def test_01_discover_valid_numerical_variables():
    """Verify discovery of typed numeric, currency, and percentage variables."""
    vars_list = [
        Variable(
            id="var_budget",
            name="Infrastructure Budget",
            description="Monthly cloud spending cap.",
            variable_type=VariableType.CURRENCY,
            baseline_value=35000.0,
            unit="USD",
            is_controllable=True,
        ),
        Variable(
            id="var_discount_rate",
            name="Early Adopter Discount",
            description="Percentage discount offered to beta customers.",
            variable_type=VariableType.PERCENTAGE,
            baseline_value=20.0,
            unit="%",
            is_controllable=True,
        ),
        Variable(
            id="var_headcount",
            name="SRE Headcount",
            description="Number of dedicated reliability engineers.",
            variable_type=VariableType.NUMERIC,
            baseline_value=4,
            unit="headcount",
            is_controllable=True,
        ),
    ]
    dm = _build_test_decision_model(vars_list)
    discovered = discover_simulation_variables(dm)

    assert len(discovered) == 3
    # Check budget
    v_budget = next(v for v in discovered if v.variable_id == "var_budget")
    assert v_budget.value_type == SimulationVariableType.CURRENCY
    assert v_budget.baseline_value == 35000.0
    assert v_budget.unit == "USD"
    assert v_budget.source_artifact_id == "dec_test_001"
    assert v_budget.source_field_path == "variables[var_budget].baseline_value"
    assert v_budget.simulation_supported is True

    # Check percentage
    v_discount = next(v for v in discovered if v.variable_id == "var_discount_rate")
    assert v_discount.value_type == SimulationVariableType.PERCENTAGE
    assert v_discount.baseline_value == 20.0

    # Check count
    v_headcount = next(v for v in discovered if v.variable_id == "var_headcount")
    assert v_headcount.value_type == SimulationVariableType.COUNT
    assert v_headcount.baseline_value == 4.0


def test_02_ignore_non_numerical_and_unverified_prose():
    """Verify that qualitative, categorical, and prose-only numbers are never discovered."""
    vars_list = [
        Variable(
            id="var_database_engine",
            name="Database Engine",
            description="Choice between PostgreSQL and CockroachDB.",
            variable_type=VariableType.CATEGORICAL,
            baseline_value="PostgreSQL",
            proposed_value="CockroachDB",
            is_controllable=True,
        ),
        Variable(
            id="var_strategy",
            name="Release Strategy",
            description="Qualitative operational rollout style with $500k implied investment.",
            variable_type=VariableType.QUALITATIVE,
            baseline_value=None,
            proposed_value=None,
            is_controllable=True,
        ),
    ]
    # Even though prompt contains '$150,000 budget' and description contains '$500k',
    # AURA must NOT parse prose into variables!
    dm = _build_test_decision_model(vars_list, raw_prompt="Should we spend $150,000 on CockroachDB with 12,000 customers?")
    discovered = discover_simulation_variables(dm)

    assert discovered == []


def test_03_controllable_vs_external_environmental_variables():
    """Verify distinction between controllable levers and external factors."""
    vars_list = [
        Variable(
            id="var_pricing",
            name="SaaS License Fee",
            description="Our customer seat price.",
            variable_type=VariableType.CURRENCY,
            baseline_value=99.0,
            unit="USD",
            is_controllable=True,
        ),
        Variable(
            id="var_inflation_rate",
            name="Macro Inflation Rate",
            description="Projected macroeconomic annual inflation rate.",
            variable_type=VariableType.PERCENTAGE,
            baseline_value=3.5,
            unit="%",
            is_controllable=False,  # External factor
        ),
    ]
    dm = _build_test_decision_model(vars_list)
    discovered = discover_simulation_variables(dm)

    assert len(discovered) == 2
    pricing = next(v for v in discovered if v.variable_id == "var_pricing")
    inflation = next(v for v in discovered if v.variable_id == "var_inflation_rate")

    assert pricing.simulation_supported is True
    assert inflation.simulation_supported is False
    assert "External environmental variable" in inflation.support_reason


def test_04_scenario_probabilities_strictly_excluded():
    """Verify that scenario probabilities are NEVER returned as adjustable simulation variables."""
    scenarios = [
        FutureScenario(
            id="scen_1111111111111111",
            scenario_type=ScenarioType.OPTIMISTIC,
            probability=0.30,
            name="Optimistic",
            narrative="Smooth scaling trajectory.",
            key_events=[ScenarioKeyEvent(id="ke_1", title="Launch", description="Smooth launch event", timeframe="M1")],
            timeline=[ScenarioMilestone(id="ms_1", title="M1", description="Smooth launch milestone", time_horizon="immediate", expected_outcome="Pass")],
        ),
        FutureScenario(
            id="scen_2222222222222222",
            scenario_type=ScenarioType.BASE_CASE,
            probability=0.50,
            name="Base",
            narrative="Controlled progression.",
            key_events=[ScenarioKeyEvent(id="ke_2", title="Cutover", description="Phased cutover event", timeframe="M2")],
            timeline=[ScenarioMilestone(id="ms_2", title="M2", description="Phased cutover milestone", time_horizon="immediate", expected_outcome="Pass")],
        ),
        FutureScenario(
            id="scen_3333333333333333",
            scenario_type=ScenarioType.PESSIMISTIC,
            probability=0.20,
            name="Pessimistic",
            narrative="Adverse network partition.",
            key_events=[ScenarioKeyEvent(id="ke_3", title="Failover", description="WAN split failover", timeframe="M3")],
            timeline=[ScenarioMilestone(id="ms_3", title="M3", description="Failover audit milestone", time_horizon="immediate", expected_outcome="Pass")],
        ),
    ]
    scen_set = ScenarioSet(
        id="scenset_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_test_001",
        summary="Three canonical trajectories summary.",
        scenarios=scenarios,
    )

    qual_var = [
        Variable(
            id="var_qual",
            name="Architecture Strategy",
            description="High level technical direction.",
            variable_type=VariableType.QUALITATIVE,
            is_controllable=True,
        )
    ]
    dm = _build_test_decision_model(qual_var)
    discovered = discover_simulation_variables(decision_model=dm, scenario_set=scen_set)

    # Must be completely empty: qualitative variable ignored, scenario probabilities never converted
    assert discovered == []


def test_05_detect_linked_operational_constraints():
    """Verify that variables linked to constraints are identified with constraint metadata."""
    vars_list = [
        Variable(
            id="var_monthly_cloud_spend",
            name="Monthly Cloud Spend",
            description="Direct compute budget.",
            variable_type=VariableType.CURRENCY,
            baseline_value=35000.0,
            unit="USD",
            is_controllable=True,
        ),
    ]
    constraints = [
        Constraint(
            id="cnstr_budget",
            name="Monthly Cloud Spend",
            description="Must not exceed $50,000 monthly.",
            is_hard_constraint=True,
            threshold_expression="spend <= 50000",
        )
    ]
    dm = _build_test_decision_model(vars_list, constraints=constraints)
    discovered = discover_simulation_variables(dm)

    assert len(discovered) == 1
    v = discovered[0]
    assert v.simulation_supported is True
    assert "linked to operational constraint 'monthly cloud spend'" in v.support_reason.lower()
    assert "spend <= 50000" in v.support_reason


def test_06_stable_and_repeatable_variable_ids():
    """Verify variable discovery produces identical repeatable variable IDs and order."""
    vars_list = [
        Variable(id="var_alpha", name="Alpha", description="Alpha var", variable_type=VariableType.NUMERIC, baseline_value=1.0),
        Variable(id="var_beta", name="Beta", description="Beta var", variable_type=VariableType.NUMERIC, baseline_value=2.0),
    ]
    dm = _build_test_decision_model(vars_list)

    run_1 = discover_simulation_variables(dm)
    run_2 = discover_simulation_variables(dm)

    assert [v.variable_id for v in run_1] == ["var_alpha", "var_beta"]
    assert [v.variable_id for v in run_1] == [v.variable_id for v in run_2]


def test_07_hospital_radiology_regression_and_scale_aware_bounds():
    """Verify regression fix for hospital radiology case:

    1. 180,000 annual scan volume (count) is discovered with scale-aware bounds.
    2. Currency amounts (e.g. $650,000 OpEx) receive scale-aware bounds.
    3. Percentage metrics (e.g. 25% productivity) receive [0, 100] bounds.
    4. Duration metrics (e.g. 36 hours turnaround) receive realistic bounds.
    5. Invariant minimum_value <= baseline_value <= maximum_value is strictly maintained.
    """
    vars_list = [
        Variable(
            id="var_annual_scan_volume",
            name="Annual Radiology Scan Volume",
            description="Total annual scan throughput across hospital facilities.",
            variable_type=VariableType.NUMERIC,
            baseline_value=180000.0,
            unit="scans",
            is_controllable=True,
        ),
        Variable(
            id="var_recurring_opex",
            name="Annual Operating Cost Addition",
            description="Additional annual operational costs for licensing and personnel.",
            variable_type=VariableType.CURRENCY,
            baseline_value=650000.0,
            unit="USD/yr",
            is_controllable=True,
        ),
        Variable(
            id="var_productivity_gain",
            name="Radiology Productivity Improvement",
            description="Projected operational capacity gain across diagnostic reading stations.",
            variable_type=VariableType.PERCENTAGE,
            baseline_value=25.0,
            unit="%",
            is_controllable=True,
        ),
        Variable(
            id="var_reporting_turnaround",
            name="Reporting Turnaround Time",
            description="Average elapsed time from scan completion to validated radiologist report.",
            variable_type=VariableType.NUMERIC,
            baseline_value=36.0,
            unit="hours",
            is_controllable=False,
        ),
    ]

    constraints = [
        Constraint(
            id="cst_turnaround_time",
            name="Reporting Turnaround Time Limit",
            description="Average reporting turnaround time must be brought below 24 hours.",
            threshold_expression="turnaround_time < 24",
        ),
        Constraint(
            id="cst_min_efficiency_gain",
            name="Minimum Operational Efficiency Gain",
            description="Radiology operational efficiency must improve by at least 15%.",
            threshold_expression="efficiency_gain >= 15",
        ),
    ]

    dm = _build_test_decision_model(vars_list, constraints=constraints)
    discovered = discover_simulation_variables(dm)

    assert len(discovered) == 4

    # 1. 180,000 annual scans
    v_scans = next(v for v in discovered if v.variable_id == "var_annual_scan_volume")
    assert v_scans.value_type == SimulationVariableType.COUNT
    assert v_scans.baseline_value == 180000.0
    assert v_scans.minimum_value == 0.0
    assert v_scans.maximum_value is not None
    assert v_scans.maximum_value >= 180000.0
    assert v_scans.minimum_value <= v_scans.baseline_value <= v_scans.maximum_value
    assert v_scans.simulation_supported is True

    # 2. $650,000 OpEx
    v_opex = next(v for v in discovered if v.variable_id == "var_recurring_opex")
    assert v_opex.value_type == SimulationVariableType.CURRENCY
    assert v_opex.baseline_value == 650000.0
    assert v_opex.minimum_value == 0.0
    assert v_opex.maximum_value is not None
    assert v_opex.maximum_value >= 650000.0
    assert v_opex.minimum_value <= v_opex.baseline_value <= v_opex.maximum_value
    assert v_opex.simulation_supported is True

    # 3. 25% productivity improvement
    v_prod = next(v for v in discovered if v.variable_id == "var_productivity_gain")
    assert v_prod.value_type == SimulationVariableType.PERCENTAGE
    assert v_prod.baseline_value == 25.0
    assert v_prod.minimum_value == 0.0
    assert v_prod.maximum_value == 100.0
    assert v_prod.minimum_value <= v_prod.baseline_value <= v_prod.maximum_value
    assert v_prod.simulation_supported is True

    # 4. 36 hours turnaround (uncontrollable external metric)
    v_tat = next(v for v in discovered if v.variable_id == "var_reporting_turnaround")
    assert v_tat.value_type == SimulationVariableType.COUNT
    assert v_tat.baseline_value == 36.0
    assert v_tat.minimum_value <= v_tat.baseline_value <= v_tat.maximum_value
    assert v_tat.simulation_supported is False
    assert "external environmental variable" in v_tat.support_reason.lower()


def test_08_scale_contradiction_exclusion_with_diagnostic_reason():
    """Verify that a variable with unit '%' but baseline 180,000:

    1. Does NOT crash Pydantic validation.
    2. Preserves the original baseline (180,000) and unit ('%') without clamping.
    3. Is marked simulation_supported=False with an explicit diagnostic reason.
    4. Satisfies minimum_value <= baseline_value <= maximum_value.
    """
    vars_list = [
        Variable(
            id="var_scan_demand_growth",
            name="3-Year Scan Volume Growth",
            description="Anticipated increase in radiology scan volume from baseline 180,000 scans.",
            variable_type=VariableType.PERCENTAGE,
            baseline_value=180000.0,
            proposed_value=20.0,
            unit="%",
            is_controllable=True,
        )
    ]
    dm = _build_test_decision_model(vars_list)
    discovered = discover_simulation_variables(dm)

    assert len(discovered) == 1
    v = discovered[0]
    assert v.baseline_value == 180000.0  # NOT clamped to 100
    assert v.unit == "%"                 # Preserved
    assert v.minimum_value <= v.baseline_value <= v.maximum_value
    assert v.simulation_supported is False
    assert "cannot be safely modeled" in v.support_reason.lower()
    assert "exceeds realistic percentage bounds" in v.support_reason.lower()
