"""Unit Tests for AURA Provenance & Epistemic Verification.

Tests coverage:
1. User-provided information: accurately tagged as USER_PROVIDED.
2. Inferred information: AI-synthesized assumptions/constraints tagged as INFERRED, never USER_PROVIDED.
3. Missing information: represented as UNKNOWN, never populated with fabricated defaults.
4. Hallucinated numerical information: speculative numbers stripped, baseline marked UNKNOWN, and Unknown gap created.
5. Mixed user-provided and inferred information: strict separation without provenance leakage.
6. QuestionUnderstandingEngine end-to-end integration: prompt -> structured LLM -> provenance audit -> deterministic complexity.
"""

from typing import Any, Dict
import pytest

from app.engines.provenance import audit_decision_provenance
from app.engines.question_understanding import QuestionUnderstandingEngine
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
from app.services.llm.client import MockLLMClient


@pytest.fixture
def base_decision_model() -> DecisionModel:
    """Creates a basic DecisionModel for testing provenance transformations."""
    return DecisionModel(
        id="dec_test_prov",
        decision=Decision(
            raw_prompt="Should our SaaS startup reduce pricing by 20% to acquire more customers?",
            summary="Evaluate cutting subscription prices by 20% to boost customer acquisition.",
            decision_type=DecisionType.STRATEGIC_DIRECTION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Multi-variable pricing tension.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_1",
                description="Acquire more customers through attractive pricing.",
                is_primary=True,
                target_metric="+20% customer signups",
                provenance=ProvenanceType.INFERRED,
            ),
            Objective(
                id="obj_2",
                description="Prevent enterprise churn and protect net revenue retention.",
                is_primary=False,
                target_metric="NRR >= 110%",
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        variables=[
            Variable(
                id="var_price_discount",
                name="Pricing Discount",
                description="Percentage price reduction.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=None,
                proposed_value=20.0,
                unit="%",
                provenance=ProvenanceType.INFERRED,
            ),
            Variable(
                id="var_churn",
                name="Monthly Churn Rate",
                description="Uncontrollable cancellation rate.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=None,
                proposed_value=None,
                unit="%",
                is_controllable=False,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        constraints=[
            Constraint(
                id="cnstr_margin",
                name="Gross Margin Floor",
                description="Gross margin must not fall below 70%.",
                is_hard_constraint=True,
                source="user_specified",
            )
        ],
        stakeholders=[
            Stakeholder(
                id="stk_customers",
                group="Prospective Customers",
                impact_nature="Benefit from lower barrier to entry.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_1",
                upside="Faster top-of-funnel customer growth.",
                downside="Lower revenue per account.",
                affected_variable_ids=["var_price_discount"],
                provenance=ProvenanceType.INFERRED,
            )
        ],
        assumptions=[
            Assumption(
                id="asm_1",
                statement="Lower price directly improves conversion rates.",
                confidence=ConfidenceLevel.UNTESTED,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        unknowns=[
            Unknown(
                id="unk_1",
                question="How will competitors react to the price change?",
                criticality=CriticalityLevel.MEDIUM,
                potential_sources=["Market intelligence"],
                provenance=ProvenanceType.UNKNOWN,
            )
        ],
        key_questions=["Will the volume increase offset the 20% margin reduction?"],
    )


# ------------------------------------------------------------------------------
# 1. User-Provided Information
# ------------------------------------------------------------------------------

def test_user_provided_information(base_decision_model: DecisionModel):
    """Verifies that explicitly stated user parameters are marked as USER_PROVIDED."""
    raw_prompt = "Should our SaaS startup reduce pricing by 20% to acquire more customers?"
    user_constraints = ["Gross margin must not fall below 70%."]

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
        constraints=user_constraints,
    )

    # Constraint was explicitly provided by user
    assert audited.constraints[0].provenance == ProvenanceType.USER_PROVIDED
    assert audited.constraints[0].source == "user_specified"

    # Proposed discount of 20% was explicitly in prompt
    assert audited.variables[0].proposed_value == 20.0
    assert audited.variables[0].proposed_provenance == ProvenanceType.USER_PROVIDED

    # Primary objective was directly derived from user question
    assert audited.objectives[0].provenance == ProvenanceType.USER_PROVIDED


# ------------------------------------------------------------------------------
# 2. Inferred Information
# ------------------------------------------------------------------------------

def test_inferred_information(base_decision_model: DecisionModel):
    """Verifies that AI-deduced assumptions, tradeoffs, and secondary objectives are INFERRED."""
    raw_prompt = "Should we reduce pricing by 20%?"

    # Model invented a secondary constraint not mentioned by user
    base_decision_model.constraints.append(
        Constraint(
            id="cnstr_compliance",
            name="Stripe Billing Tier",
            description="Must stay within Stripe standard fee limits.",
            source="user_specified",  # Model falsely claimed user specified this
        )
    )

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
        constraints=[],  # User specified NO constraints
    )

    # Inferred constraint must be tagged INFERRED, never USER_PROVIDED
    inferred_cnstr = audited.constraints[1]
    assert inferred_cnstr.provenance == ProvenanceType.INFERRED
    assert inferred_cnstr.source == "inferred_operational"

    # Secondary objective not in prompt must be INFERRED
    assert audited.objectives[1].provenance == ProvenanceType.INFERRED

    # Assumptions and Tradeoffs are always INFERRED
    assert audited.assumptions[0].provenance == ProvenanceType.INFERRED
    assert audited.tradeoffs[0].provenance == ProvenanceType.INFERRED


# ------------------------------------------------------------------------------
# 3. Missing Information
# ------------------------------------------------------------------------------

def test_missing_information(base_decision_model: DecisionModel):
    """Verifies that missing information is represented as UNKNOWN, not synthetic constants."""
    raw_prompt = "Should we cut pricing?"

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
    )

    # Churn variable has no baseline or proposed value provided
    churn_var = audited.variables[1]
    assert churn_var.baseline_value is None
    assert churn_var.baseline_provenance == ProvenanceType.UNKNOWN
    assert churn_var.proposed_value is None
    assert churn_var.proposed_provenance == ProvenanceType.UNKNOWN

    # Unknowns must have UNKNOWN provenance
    assert audited.unknowns[0].provenance == ProvenanceType.UNKNOWN


# ------------------------------------------------------------------------------
# 4. Hallucinated Numerical Information
# ------------------------------------------------------------------------------

def test_hallucinated_numerical_information(base_decision_model: DecisionModel):
    """Verifies that unstated numerical values invented by LLM are purged and tracked as UNKNOWN."""
    raw_prompt = "Should we cut pricing by 20%?"

    # LLM hallucinates that current baseline price is $100 and baseline churn is 4.5%
    base_decision_model.variables[0].baseline_value = 100.0  # User NEVER said $100
    base_decision_model.variables[1].baseline_value = 4.5    # User NEVER said 4.5%

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
        context=None,
        constraints=None,
    )

    # Hallucinated baseline values must be stripped to None
    assert audited.variables[0].baseline_value is None
    assert audited.variables[0].baseline_provenance == ProvenanceType.UNKNOWN

    assert audited.variables[1].baseline_value is None
    assert audited.variables[1].baseline_provenance == ProvenanceType.UNKNOWN

    # Explicit Unknowns must be added to track the missing baselines
    unknown_questions = [u.question for u in audited.unknowns]
    assert any("Pricing Discount" in q for q in unknown_questions)
    assert any("Monthly Churn Rate" in q for q in unknown_questions)


def test_user_provided_numerical_information_retained(base_decision_model: DecisionModel):
    """Verifies that when the user DOES provide numerical values, they are retained as USER_PROVIDED."""
    raw_prompt = "Should we cut pricing by 20%?"
    user_context = {"current_price": 100.0, "current_churn": "4.5%"}

    base_decision_model.variables[0].baseline_value = 100.0
    base_decision_model.variables[1].baseline_value = 4.5

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
        context=user_context,
    )

    # Because numbers were in user context, they are legitimate USER_PROVIDED values
    assert audited.variables[0].baseline_value == 100.0
    assert audited.variables[0].baseline_provenance == ProvenanceType.USER_PROVIDED

    assert audited.variables[1].baseline_value == 4.5
    assert audited.variables[1].baseline_provenance == ProvenanceType.USER_PROVIDED


# ------------------------------------------------------------------------------
# 5. Mixed User-Provided and Inferred Information
# ------------------------------------------------------------------------------

def test_mixed_user_provided_and_inferred_information(base_decision_model: DecisionModel):
    """Verifies clean separation in a realistic mixed decision model."""
    raw_prompt = "Should we migrate from Postgres to CockroachDB to eliminate weekend scaling alerts?"
    user_context = {"weekend_alerts_count": 8}
    user_constraints = ["Migration downtime must be 0 minutes"]

    # Configure a mixed model
    base_decision_model.decision.raw_prompt = raw_prompt
    base_decision_model.constraints = [
        Constraint(
            id="cnstr_1",
            name="Zero Downtime",
            description="Migration downtime must be 0 minutes",
            source="user_specified",
        ),
        Constraint(
            id="cnstr_2",
            name="Cloud Cost",
            description="Infrastructure bill cannot double during replication",
            source="user_specified",  # Model claims user specified this
        ),
    ]

    base_decision_model.variables = [
        Variable(
            id="var_alerts",
            name="Weekend Alerts",
            description="Count of paging alerts.",
            variable_type=VariableType.NUMERIC,
            baseline_value=8,     # In user context
            proposed_value=0,     # In user prompt ("eliminate")
        ),
        Variable(
            id="var_cost",
            name="Monthly Cloud Cost",
            description="Database infrastructure bill.",
            variable_type=VariableType.CURRENCY,
            baseline_value=15000, # NOT in user input (hallucination)
            proposed_value=22000, # NOT in user input (hallucination)
        ),
    ]

    audited = audit_decision_provenance(
        model=base_decision_model,
        raw_prompt=raw_prompt,
        context=user_context,
        constraints=user_constraints,
    )

    # Constraint 1: User specified
    assert audited.constraints[0].provenance == ProvenanceType.USER_PROVIDED
    assert audited.constraints[0].source == "user_specified"

    # Constraint 2: Inferred by model
    assert audited.constraints[1].provenance == ProvenanceType.INFERRED
    assert audited.constraints[1].source == "inferred_operational"

    # Variable 1: Alerts (Both numbers are user provided)
    assert audited.variables[0].baseline_value == 8
    assert audited.variables[0].baseline_provenance == ProvenanceType.USER_PROVIDED
    assert audited.variables[0].proposed_value == 0
    assert audited.variables[0].proposed_provenance == ProvenanceType.USER_PROVIDED

    # Variable 2: Cost (Numbers were hallucinated by model -> stripped to None / UNKNOWN)
    assert audited.variables[1].baseline_value is None
    assert audited.variables[1].baseline_provenance == ProvenanceType.UNKNOWN
    # Proposed value was model hallucination -> stripped to None / UNKNOWN
    assert audited.variables[1].proposed_value is None
    assert audited.variables[1].proposed_provenance == ProvenanceType.UNKNOWN


# ------------------------------------------------------------------------------
# 6. QuestionUnderstandingEngine Integration
# ------------------------------------------------------------------------------

def test_question_understanding_engine_deconstruct(base_decision_model: DecisionModel):
    """Verifies that QuestionUnderstandingEngine coordinates LLM generation, provenance audit, and complexity."""
    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, base_decision_model)

    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    question = "Should our SaaS startup reduce pricing by 20% to acquire more customers?"
    result = engine.deconstruct(
        question=question,
        context={"team_size": 15},
        constraints=["Gross margin must not fall below 70%."],
    )

    assert isinstance(result, DecisionModel)
    assert result.decision.raw_prompt == question
    # Provenance verified
    assert result.constraints[0].provenance == ProvenanceType.USER_PROVIDED
    # Deterministic complexity populated
    assert result.complexity.score is not None
    assert 0.0 <= result.complexity.score <= 100.0
    assert result.complexity.level in (ComplexityLevel.LOW, ComplexityLevel.MEDIUM, ComplexityLevel.HIGH)
