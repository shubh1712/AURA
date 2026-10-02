"""Unit tests for AURA DecisionModel and sub-models."""

import json
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
    ReversibilityLevel,
    Stakeholder,
    TimeHorizon,
    Tradeoff,
    Unknown,
    Variable,
    VariableType,
)


# ------------------------------------------------------------------------------
# Test Fixtures & Valid Factory
# ------------------------------------------------------------------------------

def create_valid_decision_model_data() -> dict:
    """Returns valid dictionary representation of a SaaS pricing decision."""
    return {
        "id": "dec_saas_pricing_001",
        "decision": {
            "raw_prompt": "Should our SaaS startup reduce pricing by 20% to acquire more customers?",
            "summary": "Evaluate lowering core subscription pricing by 20% to accelerate customer acquisition.",
            "decision_type": "strategic_direction",
            "time_horizon": "short_term",
        },
        "complexity": {
            "level": "medium",
            "reasoning": "Interacting trade-offs between acquisition volume, revenue per user, and churn risk.",
            "reversibility": "partially_reversible",
        },
        "objectives": [
            {
                "id": "obj_primary",
                "description": "Increase new customer acquisition rate.",
                "is_primary": True,
                "target_metric": "+35% monthly active customer additions",
            },
            {
                "id": "obj_secondary",
                "description": "Maintain gross margin above operating thresholds.",
                "is_primary": False,
                "target_metric": "Gross margin >= 70%",
            },
        ],
        "variables": [
            {
                "id": "var_price_discount",
                "name": "Price Discount Percentage",
                "description": "Percentage discount applied to standard subscription tier.",
                "variable_type": "percentage",
                "baseline_value": 0.0,
                "proposed_value": 20.0,
                "unit": "%",
                "is_controllable": True,
            },
            {
                "id": "var_acquisition_rate",
                "name": "Customer Acquisition Rate",
                "description": "Number of new paying accounts added per month.",
                "variable_type": "numeric",
                "baseline_value": 150,
                "proposed_value": 205,
                "unit": "accounts/month",
                "is_controllable": False,
            },
        ],
        "constraints": [
            {
                "id": "cnstr_runway",
                "name": "Cash Runway Boundary",
                "description": "Cash runway must not drop below 12 months.",
                "is_hard_constraint": True,
                "threshold_expression": "runway_months >= 12",
                "source": "user_specified",
            }
        ],
        "stakeholders": [
            {
                "id": "stk_existing_users",
                "group": "Existing Customers",
                "impact_nature": "Potential dissatisfaction if not grandfathered into new pricing.",
                "influence_level": "high",
            },
            {
                "id": "stk_investors",
                "group": "Investors",
                "impact_nature": "Scrutiny over short-term revenue contraction and unit economics.",
                "influence_level": "high",
            },
        ],
        "tradeoffs": [
            {
                "id": "trd_volume_vs_arpu",
                "upside": "Accelerated customer logo growth and market share expansion.",
                "downside": "20% reduction in average revenue per user (ARPU) and margin compression.",
                "affected_variable_ids": ["var_price_discount", "var_acquisition_rate"],
            }
        ],
        "assumptions": [
            {
                "id": "asm_elasticity",
                "statement": "Demand for the product is price-elastic enough to offset lower unit revenue.",
                "confidence": "medium",
                "falsification_condition": "Acquisition increases by less than 15% within 60 days.",
            }
        ],
        "unknowns": [
            {
                "id": "unk_competitor_reaction",
                "question": "Will primary competitors match the 20% discount within the quarter?",
                "criticality": "high",
                "potential_sources": ["Competitor Sales Intel", "Win/Loss Reports"],
            }
        ],
        "key_questions": [
            "What is the customer payback period at the discounted price point?",
            "Will existing cohort churn increase if the discount is only offered to new users?",
        ],
    }


# ------------------------------------------------------------------------------
# 1. Valid Instantiation & Serialization Tests
# ------------------------------------------------------------------------------

def test_valid_decision_model_instantiation() -> None:
    """Verifies that a comprehensive DecisionModel instantiates cleanly."""
    data = create_valid_decision_model_data()
    model = DecisionModel.model_validate(data)

    assert model.id == "dec_saas_pricing_001"
    assert model.decision.decision_type == DecisionType.STRATEGIC_DIRECTION
    assert model.decision.time_horizon == TimeHorizon.SHORT_TERM
    assert model.complexity.level == ComplexityLevel.MEDIUM
    assert model.complexity.reversibility == ReversibilityLevel.PARTIALLY_REVERSIBLE
    assert len(model.objectives) == 2
    assert model.objectives[0].is_primary is True
    assert len(model.variables) == 2
    assert model.variables[0].variable_type == VariableType.PERCENTAGE
    assert len(model.constraints) == 1
    assert model.constraints[0].is_hard_constraint is True
    assert len(model.stakeholders) == 2
    assert len(model.tradeoffs) == 1
    assert len(model.assumptions) == 1
    assert len(model.unknowns) == 1
    assert len(model.key_questions) == 2


def test_decision_model_json_serialization_roundtrip() -> None:
    """Verifies complete JSON serialization and deserialization roundtrip."""
    data = create_valid_decision_model_data()
    model = DecisionModel.model_validate(data)

    json_str = model.model_dump_json()
    assert isinstance(json_str, str)

    restored = DecisionModel.model_validate_json(json_str)
    assert restored.id == model.id
    assert restored.decision.summary == model.decision.summary
    assert restored.variables[0].proposed_value == 20.0


def test_minimal_valid_decision_model() -> None:
    """Verifies valid creation with minimal required fields and default empty lists."""
    minimal_data = {
        "id": "dec_minimal_01",
        "decision": {
            "raw_prompt": "Should we switch our testing framework to pytest?",
            "summary": "Decide on standardizing backend tests on pytest.",
            "decision_type": "architecture_technology",
            "time_horizon": "immediate",
        },
        "complexity": {
            "level": "low",
            "reasoning": "Internal tooling with minimal external dependencies.",
            "reversibility": "reversible",
        },
        "objectives": [
            {
                "id": "obj_speed",
                "description": "Improve test execution speed.",
                "is_primary": True,
            }
        ],
        "variables": [
            {
                "id": "var_framework",
                "name": "Testing Framework",
                "description": "Test runner selection.",
                "variable_type": "categorical",
                "baseline_value": "unittest",
                "proposed_value": "pytest",
            }
        ],
        # constraints, stakeholders, assumptions, unknowns default to []
        "tradeoffs": [
            {
                "id": "trd_migration_cost",
                "upside": "Higher test velocity and cleaner fixtures.",
                "downside": "Time spent converting old test suites.",
            }
        ],
        "key_questions": [
            "Are all existing test assertions compatible with pytest plugins?",
        ],
    }

    model = DecisionModel.model_validate(minimal_data)
    assert model.id == "dec_minimal_01"
    assert model.constraints == []
    assert model.stakeholders == []
    assert model.assumptions == []
    assert model.unknowns == []


# ------------------------------------------------------------------------------
# 2. Validation Failure Tests (Invalid Data)
# ------------------------------------------------------------------------------

def test_missing_primary_objective_raises() -> None:
    """Fails when no objective has is_primary=True."""
    data = create_valid_decision_model_data()
    for obj in data["objectives"]:
        obj["is_primary"] = False

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "must contain at least one primary objective" in str(exc_info.value)


def test_empty_variables_list_raises() -> None:
    """Fails when variables list is empty (min_length=1)."""
    data = create_valid_decision_model_data()
    data["variables"] = []

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "variables" in str(exc_info.value)


def test_empty_tradeoffs_list_raises() -> None:
    """Fails when tradeoffs list is empty (min_length=1)."""
    data = create_valid_decision_model_data()
    data["tradeoffs"] = []

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "tradeoffs" in str(exc_info.value)


def test_empty_key_questions_list_raises() -> None:
    """Fails when key_questions list is empty (min_length=1)."""
    data = create_valid_decision_model_data()
    data["key_questions"] = []

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "key_questions" in str(exc_info.value)


def test_duplicate_entity_ids_in_collection_raises() -> None:
    """Fails when duplicate IDs exist within a single collection."""
    data = create_valid_decision_model_data()
    # Duplicate variable id
    data["variables"].append({
        "id": "var_price_discount",  # Duplicate
        "name": "Second Discount",
        "description": "Another discount lever.",
        "variable_type": "percentage",
    })

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "Duplicate ID 'var_price_discount' found in 'variables' collection" in str(exc_info.value)


def test_invalid_tradeoff_variable_reference_raises() -> None:
    """Fails when a tradeoff references a variable ID that does not exist."""
    data = create_valid_decision_model_data()
    data["tradeoffs"][0]["affected_variable_ids"] = ["var_non_existent"]

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "references non-existent variable ID 'var_non_existent'" in str(exc_info.value)


def test_whitespace_only_strings_rejected() -> None:
    """Fails when string fields are empty or only whitespace."""
    data = create_valid_decision_model_data()
    data["decision"]["summary"] = "     "

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "summary" in str(exc_info.value)


def test_invalid_enum_values_rejected() -> None:
    """Fails when an unsupported enum value is passed."""
    data = create_valid_decision_model_data()
    data["complexity"]["level"] = "astronomical"  # Invalid

    with pytest.raises(ValidationError) as exc_info:
        DecisionModel.model_validate(data)
    assert "complexity.level" in str(exc_info.value)
