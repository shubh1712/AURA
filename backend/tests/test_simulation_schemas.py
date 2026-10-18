"""Phase 7A Unit Tests: Simulation Schemas.

Comprehensive verification of:
1. Valid construction of SimulationVariable, SimulationAdjustment, SimulationRequest, SimulationImpact, and SimulationResult.
2. Rejection of NaN and infinite floats across all numeric fields.
3. Strict bounds validation (minimum > maximum, baseline out of bounds).
4. Rejection of duplicate adjustments in SimulationRequest.
5. Rejection of empty adjustments.
6. Deterministic simulation ID generation (format, repeatability, order invariance, sensitivity).
7. Complete Pydantic v2 serialization round-trip fidelity.
"""

import math
import pytest
from pydantic import ValidationError

from app.schemas.simulation import (
    SimulationAdjustment,
    SimulationCalculationStatus,
    SimulationImpact,
    SimulationRequest,
    SimulationResult,
    SimulationUnit,
    SimulationVariable,
    SimulationVariableType,
    generate_deterministic_simulation_id,
)


def test_01_valid_simulation_variable_construction():
    """Verify valid construction of SimulationVariable with various types and units."""
    var = SimulationVariable(
        variable_id="var_marketing_budget",
        label="Marketing Budget",
        description="Quarterly performance marketing budget allocation.",
        unit="USD",
        value_type=SimulationVariableType.CURRENCY,
        baseline_value=150000.0,
        minimum_value=0.0,
        maximum_value=500000.0,
        source_artifact_id="dec_model_001",
        source_field_path="variables[var_marketing_budget].baseline_value",
        simulation_supported=True,
        support_reason="Linked to hard budget ceiling constraint.",
    )
    assert var.variable_id == "var_marketing_budget"
    assert var.baseline_value == 150000.0
    assert var.unit == "USD"
    assert var.value_type == SimulationVariableType.CURRENCY
    assert var.simulation_supported is True


def test_02_simulation_variable_rejects_nan_and_infinity():
    """Verify SimulationVariable rejects NaN, +inf, and -inf across all numeric fields."""
    # NaN baseline
    with pytest.raises(ValidationError, match="finite number"):
        SimulationVariable(
            variable_id="var_nan",
            label="Invalid",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=float("nan"),
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )

    # +inf baseline
    with pytest.raises(ValidationError, match="finite number"):
        SimulationVariable(
            variable_id="var_inf",
            label="Invalid",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=float("inf"),
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )

    # -inf min bound
    with pytest.raises(ValidationError, match="finite number"):
        SimulationVariable(
            variable_id="var_min_inf",
            label="Invalid",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=10.0,
            minimum_value=float("-inf"),
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )


def test_03_simulation_variable_bounds_validation():
    """Verify bounds enforcement: min <= max and min <= baseline <= max."""
    # min > max
    with pytest.raises(ValidationError, match="minimum_value .* cannot exceed maximum_value"):
        SimulationVariable(
            variable_id="var_bounds",
            label="Inverted",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=50.0,
            minimum_value=100.0,
            maximum_value=20.0,
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )

    # baseline < min
    with pytest.raises(ValidationError, match="baseline_value .* is below minimum_value"):
        SimulationVariable(
            variable_id="var_below_min",
            label="Below Min",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=5.0,
            minimum_value=10.0,
            maximum_value=100.0,
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )

    # baseline > max
    with pytest.raises(ValidationError, match="baseline_value .* exceeds maximum_value"):
        SimulationVariable(
            variable_id="var_above_max",
            label="Above Max",
            description="Test",
            value_type=SimulationVariableType.NUMERIC,
            baseline_value=150.0,
            minimum_value=10.0,
            maximum_value=100.0,
            source_artifact_id="dec_01",
            source_field_path="path",
            support_reason="reason",
        )


def test_04_valid_simulation_adjustment():
    """Verify SimulationAdjustment construction and NaN rejection."""
    adj = SimulationAdjustment(
        variable_id="var_budget",
        proposed_value=75000.0,
        unit="USD",
    )
    assert adj.variable_id == "var_budget"
    assert adj.proposed_value == 75000.0
    assert adj.unit == "USD"

    # NaN proposed_value
    with pytest.raises(ValidationError, match="finite number"):
        SimulationAdjustment(
            variable_id="var_budget",
            proposed_value=float("nan"),
        )

    # Infinite proposed_value
    with pytest.raises(ValidationError, match="finite number"):
        SimulationAdjustment(
            variable_id="var_budget",
            proposed_value=float("inf"),
        )


def test_05_simulation_request_rejects_duplicates_and_empty():
    """Verify SimulationRequest rejects duplicate variable adjustments and empty lists."""
    adj1 = SimulationAdjustment(variable_id="var_1", proposed_value=10.0)
    adj2 = SimulationAdjustment(variable_id="var_1", proposed_value=20.0)  # duplicate

    with pytest.raises(ValidationError, match="Duplicate adjustment for variable 'var_1'"):
        SimulationRequest(
            decision_model_id="dec_01",
            scenario_set_id="scenset_01",
            recommendation_id="rec_01",
            adjustments=[adj1, adj2],
        )

    # Empty adjustments list
    with pytest.raises(ValidationError):
        SimulationRequest(
            decision_model_id="dec_01",
            scenario_set_id="scenset_01",
            recommendation_id="rec_01",
            adjustments=[],
        )


def test_06_simulation_impact_construction():
    """Verify SimulationImpact fields and validation."""
    impact = SimulationImpact(
        variable_id="var_budget",
        original_value=50000.0,
        adjusted_value=65000.0,
        transformation_rule_id="RULE_CONSTRAINT_THRESHOLD_EVALUATION",
        affected_fields=["decision_model.variables[var_budget].proposed_value", "scenarios[pessimistic].relevant_constraint_ids"],
        calculation_status=SimulationCalculationStatus.CALCULATED,
        explanation="Adjustment breached hard budget threshold.",
    )
    assert impact.variable_id == "var_budget"
    assert impact.calculation_status == SimulationCalculationStatus.CALCULATED


def test_07_deterministic_simulation_id_invariants():
    """Verify SHA-256 simulation ID repeatability, format, and order invariance."""
    adjs_a = [
        SimulationAdjustment(variable_id="var_alpha", proposed_value=100.0, unit="USD"),
        SimulationAdjustment(variable_id="var_beta", proposed_value=25.0, unit="%"),
    ]
    # Reversed adjustment order
    adjs_b = [
        SimulationAdjustment(variable_id="var_beta", proposed_value=25.0, unit="%"),
        SimulationAdjustment(variable_id="var_alpha", proposed_value=100.0, unit="USD"),
    ]

    id_a = generate_deterministic_simulation_id("dec_1", "scen_1", "rec_1", adjs_a)
    id_b = generate_deterministic_simulation_id("dec_1", "scen_1", "rec_1", adjs_b)

    # 1. Format check: sim_ + 32 hex chars
    assert id_a.startswith("sim_")
    assert len(id_a) == 36
    assert int(id_a[4:], 16) >= 0

    # 2. Order invariance
    assert id_a == id_b

    # 3. Sensitivity to value change
    adjs_changed = [
        SimulationAdjustment(variable_id="var_alpha", proposed_value=100.001, unit="USD"),
        SimulationAdjustment(variable_id="var_beta", proposed_value=25.0, unit="%"),
    ]
    id_changed = generate_deterministic_simulation_id("dec_1", "scen_1", "rec_1", adjs_changed)
    assert id_changed != id_a

    # 4. Sensitivity to artifact identity change
    id_diff_art = generate_deterministic_simulation_id("dec_2", "scen_1", "rec_1", adjs_a)
    assert id_diff_art != id_a


def test_08_simulation_result_serialization_round_trip():
    """Verify SimulationResult JSON serialization and deserialization."""
    adjs = [SimulationAdjustment(variable_id="var_spend", proposed_value=45000.0)]
    impact = SimulationImpact(
        variable_id="var_spend",
        original_value=50000.0,
        adjusted_value=45000.0,
        transformation_rule_id="RULE_DIRECT_VARIABLE_SUBSTITUTION",
        affected_fields=["decision_model.variables[var_spend].proposed_value"],
        calculation_status=SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING,
        explanation="Direct parameter adjustment recorded.",
    )
    sim_id = generate_deterministic_simulation_id("dec_01", "scen_01", "rec_01", adjs)

    result = SimulationResult(
        id=sim_id,
        decision_model_id="dec_01",
        scenario_set_id="scen_01",
        recommendation_id="rec_01",
        applied_adjustments=adjs,
        impacts=[impact],
        baseline_resilience_score=72.5,
        simulated_resilience_score=None,
        score_delta=None,
        warnings=["Unmapped variable."],
        status=SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING,
    )

    data = result.model_dump(mode="json")
    parsed = SimulationResult.model_validate(data)

    assert parsed.id == result.id
    assert parsed.baseline_resilience_score == 72.5
    assert parsed.simulated_resilience_score is None
    assert parsed.score_delta is None
    assert parsed.status == SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
