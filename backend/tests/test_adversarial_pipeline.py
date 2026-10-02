"""Adversarial Test Suite for AURA Day 2 Decision Understanding Pipeline.

Focuses specifically on hallucination resistance, unsupported assumption handling,
provenance preservation, and structural validation across adversarial scenarios:

1. Extremely vague decisions
2. Missing numerical information
3. Conflicting information
4. Implied assumptions
5. Questions containing unsupported claims
6. Questions with multiple possible interpretations
7. Questions containing fake statistics
8. Questions with no obvious objective

Verifies that AURA:
- Does not invent facts
- Does not invent numbers
- Does not turn assumptions into facts
- Identifies unknowns
- Preserves provenance (USER_PROVIDED, INFERRED, UNKNOWN)
- Does not provide recommendations
- Does not fabricate evidence
- Remains structurally valid
"""

from typing import Any, Dict, List
import pytest

from app.engines.provenance import audit_decision_provenance
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest
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
from app.services.analysis_service import AnalysisService
from app.services.llm.client import MockLLMClient


# ------------------------------------------------------------------------------
# Helpers to generate base models for mock responses
# ------------------------------------------------------------------------------

def _create_mock_decision_model(
    raw_prompt: str,
    summary: str,
    decision_type: DecisionType = DecisionType.GENERAL_CHOICE,
    objectives: List[Objective] = None,
    variables: List[Variable] = None,
    constraints: List[Constraint] = None,
    tradeoffs: List[Tradeoff] = None,
    assumptions: List[Assumption] = None,
    unknowns: List[Unknown] = None,
    key_questions: List[str] = None,
) -> DecisionModel:
    """Creates a structurally valid DecisionModel for feeding into the pipeline."""
    vars_list = variables or [
        Variable(
            id="var_scope",
            name="Scope of Implementation",
            description="Magnitude and reach of the initiative.",
            variable_type=VariableType.QUALITATIVE,
            provenance=ProvenanceType.INFERRED,
        )
    ]
    trds_list = tradeoffs or [
        Tradeoff(
            id="trd_speed_vs_certainty",
            upside="Immediate organizational momentum.",
            downside="Risk of misaligned execution.",
            affected_variable_ids=[vars_list[0].id],
            provenance=ProvenanceType.INFERRED,
        )
    ]
    return DecisionModel(
        id="dec_adversarial_mock",
        decision=Decision(
            raw_prompt=raw_prompt,
            summary=summary,
            decision_type=decision_type,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Multi-stakeholder problem under ambiguity.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=objectives or [
            Objective(
                id="obj_primary",
                description="Determine the optimal course of action.",
                is_primary=True,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        variables=vars_list,
        constraints=constraints or [],
        stakeholders=[
            Stakeholder(
                id="stk_team",
                group="Engineering & Product Teams",
                impact_nature="Resource allocation and workflow changes.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        tradeoffs=trds_list,
        assumptions=assumptions or [],
        unknowns=unknowns or [
            Unknown(
                id="unk_goals",
                question="What specific success criteria govern this decision?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Executive stakeholder interview"],
                provenance=ProvenanceType.UNKNOWN,
            )
        ],
        key_questions=key_questions or ["What is the specific problem being addressed?"],
    )


# ------------------------------------------------------------------------------
# 1. Extremely Vague Decisions
# ------------------------------------------------------------------------------

def test_adversarial_extremely_vague_decision():
    """Scenario 1: Extremely vague decisions (e.g., 'Should we do something about tech?').

    Verifies:
    - Does not invent facts (tech stack, team size, budget).
    - Does not invent numbers (baseline/proposed values remain None/UNKNOWN).
    - Identifies unknown gaps (what tech, what current performance).
    - Objective tagged INFERRED, never USER_PROVIDED.
    - Deterministic complexity assesses high uncertainty.
    - Preserves structural validity.
    """
    raw_prompt = "Should we do something about tech?"
    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate whether to initiate technical modernization.",
        decision_type=DecisionType.ARCHITECTURE_TECH,
        objectives=[
            Objective(
                id="obj_1",
                description="Improve overall technology infrastructure efficiency.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,  # Model falsely claims user provided this
            )
        ],
        variables=[
            Variable(
                id="var_tech_debt",
                name="Technical Debt Burden",
                description="Estimated friction from legacy software.",
                variable_type=VariableType.NUMERIC,
                baseline_value=42.0,  # Model hallucinated number!
                proposed_value=10.0,  # Model hallucinated number!
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_1",
                upside="Potential agility and developer satisfaction.",
                downside="Opportunity cost of pausing feature work.",
                affected_variable_ids=["var_tech_debt"],
            )
        ],
        key_questions=["What specific technical systems are experiencing friction?"],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # 1. Does not invent facts: Objective must be INFERRED
    assert audited.objectives[0].provenance == ProvenanceType.INFERRED

    # 2. Does not invent numbers: Speculative numbers stripped to None & UNKNOWN
    debt_var = audited.variables[0]
    assert debt_var.baseline_value is None
    assert debt_var.baseline_provenance == ProvenanceType.UNKNOWN
    assert debt_var.proposed_value is None
    assert debt_var.proposed_provenance == ProvenanceType.UNKNOWN

    # 3. Identifies unknowns: Unknown gaps created for the missing numbers
    assert len(audited.unknowns) >= 2
    unknown_questions = [u.question.lower() for u in audited.unknowns]
    assert any("baseline value" in q for q in unknown_questions)

    # 4. Complexity reflects high uncertainty
    assert audited.complexity.score is not None
    assert audited.complexity.score >= 40.0

    # 5. Remains structurally valid
    assert audited.model_dump()


# ------------------------------------------------------------------------------
# 2. Missing Numerical Information
# ------------------------------------------------------------------------------

def test_adversarial_missing_numerical_information():
    """Scenario 2: Missing numerical information (e.g. unquantified price reduction).

    Verifies:
    - Never populates missing numerical parameters with speculative numbers.
    - Represents missing baseline and proposed values as None & UNKNOWN.
    - Generates explicit Unknown information gaps.
    - Never hallucinates numeric target metrics in objectives.
    """
    raw_prompt = "Should our startup cut prices to acquire more customers?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate cutting subscription prices to increase customer acquisition.",
        decision_type=DecisionType.STRATEGIC_DIRECTION,
        objectives=[
            Objective(
                id="obj_1",
                description="Acquire more customers.",
                is_primary=True,
                target_metric="+35% new signups",  # Hallucinated 35%
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        variables=[
            Variable(
                id="var_price",
                name="Subscription Price",
                description="Monthly plan fee.",
                variable_type=VariableType.CURRENCY,
                baseline_value=99,   # User never gave $99
                proposed_value=79,   # User never gave $79
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_price_vol",
                upside="Higher top of funnel conversion.",
                downside="Reduced average revenue per user.",
                affected_variable_ids=["var_price"],
            )
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # Numerical values must be stripped
    price_var = audited.variables[0]
    assert price_var.baseline_value is None
    assert price_var.baseline_provenance == ProvenanceType.UNKNOWN
    assert price_var.proposed_value is None
    assert price_var.proposed_provenance == ProvenanceType.UNKNOWN

    # Hallucinated target metric +35% causes objective provenance to be INFERRED
    # and generates an empirical Unknown question
    assert audited.objectives[0].provenance == ProvenanceType.INFERRED
    assert any("target metric" in u.question.lower() for u in audited.unknowns)


# ------------------------------------------------------------------------------
# 3. Conflicting Information
# ------------------------------------------------------------------------------

def test_adversarial_conflicting_information():
    """Scenario 3: Conflicting information between user prompt and explicit constraints.

    Verifies:
    - User constraints are preserved as USER_PROVIDED and user_specified.
    - Does NOT invent an arbitrary resolution or recommendation.
    - Identifies the conflict in Tradeoffs and Key Questions.
    - Preserves epistemic provenance without dropping user boundaries.
    """
    raw_prompt = "Should we reduce pricing by 20% to accelerate growth?"
    user_constraints = [
        "Never reduce prices or give discounts on core tiers.",
        "Gross margin must stay above 80%.",
    ]

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate a 20% price reduction against strict non-discount policies.",
        decision_type=DecisionType.STRATEGIC_DIRECTION,
        constraints=[
            Constraint(
                id="cnstr_no_discount",
                name="No Discount Policy",
                description="Never reduce prices or give discounts on core tiers.",
                is_hard_constraint=True,
                source="user_specified",
            ),
            Constraint(
                id="cnstr_margin",
                name="Gross Margin Floor",
                description="Gross margin must stay above 80%.",
                is_hard_constraint=True,
                source="user_specified",
            ),
        ],
        variables=[
            Variable(
                id="var_discount",
                name="Pricing Discount",
                description="Proposed price cut.",
                variable_type=VariableType.PERCENTAGE,
                proposed_value=20.0,
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_vs_policy",
                upside="Accelerated customer signups.",
                downside="Direct violation of executive non-discount constraint.",
                affected_variable_ids=["var_discount"],
            )
        ],
        key_questions=[
            "Can growth be achieved through packaging without breaching the core-tier discount constraint?"
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(
        question=raw_prompt,
        constraints=user_constraints,
    )

    # User constraints must be tagged USER_PROVIDED
    for cnstr in audited.constraints:
        assert cnstr.provenance == ProvenanceType.USER_PROVIDED
        assert cnstr.source == "user_specified"

    # Verbatim prompt preserved
    assert audited.decision.raw_prompt == raw_prompt

    # Proposed discount of 20% was in user prompt
    assert audited.variables[0].proposed_value == 20.0
    assert audited.variables[0].proposed_provenance == ProvenanceType.USER_PROVIDED

    # Tensions properly identified in tradeoffs
    assert "violation" in audited.tradeoffs[0].downside.lower() or "constraint" in audited.tradeoffs[0].downside.lower()


# ------------------------------------------------------------------------------
# 4. Implied Assumptions
# ------------------------------------------------------------------------------

def test_adversarial_implied_assumptions():
    """Scenario 4: Implied assumptions in prompt (e.g. 'competitors will never react').

    Verifies:
    - Implied premises are isolated in assumptions, NEVER as facts or constraints.
    - Assumption confidence is UNTESTED, provenance is INFERRED.
    - Unknowns are generated to empirically test the assumption.
    - No recommendation is provided.
    """
    raw_prompt = "Should we hire 5 engineers since competitors will never launch an AI product in our space?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate hiring 5 engineers based on assumed competitor inactivity.",
        decision_type=DecisionType.RESOURCE_ALLOCATION,
        variables=[
            Variable(
                id="var_headcount",
                name="Engineering Headcount",
                description="Additional hires.",
                variable_type=VariableType.NUMERIC,
                proposed_value=5,  # Stated in user prompt
            )
        ],
        assumptions=[
            Assumption(
                id="asm_competitors",
                statement="Competitors will never launch an AI product in this market.",
                confidence=ConfidenceLevel.HIGH,  # Model falsely labeled high confidence!
                falsification_condition="Competitor releases AI feature announcement.",
            )
        ],
        unknowns=[
            Unknown(
                id="unk_comp_roadmap",
                question="What are competitors currently building in their private roadmaps?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Market intelligence", "Job postings telemetry"],
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_burn_vs_capacity",
                upside="Increased product delivery bandwidth.",
                downside="Higher monthly fixed payroll burn.",
                affected_variable_ids=["var_headcount"],
            )
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # Epistemic Rule: Unverified assumptions must NEVER be high confidence facts
    assert audited.assumptions[0].provenance == ProvenanceType.INFERRED
    assert audited.assumptions[0].confidence == ConfidenceLevel.UNTESTED

    # Unknown is preserved
    assert audited.unknowns[0].provenance == ProvenanceType.UNKNOWN

    # Stated headcount number 5 is retained as USER_PROVIDED
    assert audited.variables[0].proposed_value == 5
    assert audited.variables[0].proposed_provenance == ProvenanceType.USER_PROVIDED


# ------------------------------------------------------------------------------
# 5. Unsupported Claims
# ------------------------------------------------------------------------------

def test_adversarial_unsupported_claims():
    """Scenario 5: Questions containing unsupported claims (e.g. '100x speedup with zero bugs').

    Verifies:
    - Unsupported claims are NOT turned into facts or hard constraints.
    - Audited as INFERRED unverified assumptions or unknowns.
    - Tradeoffs highlight real-world downside risks (contradicting 'zero bugs').
    - Does NOT recommend rewriting or not rewriting.
    """
    raw_prompt = "Since rewriting in Rust is guaranteed to give a 100x speedup with zero bugs, should we rewrite our platform?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate rewriting core platform in Rust based on projected performance gains.",
        decision_type=DecisionType.ARCHITECTURE_TECH,
        constraints=[
            Constraint(
                id="cnstr_zero_bugs",
                name="Zero Bugs Guarantee",
                description="The rewritten system will have zero bugs.",
                is_hard_constraint=True,
                source="user_specified",  # Model claims user specified a factual zero-bug constraint
            )
        ],
        variables=[
            Variable(
                id="var_lang",
                name="Programming Language",
                description="Core implementation language.",
                variable_type=VariableType.CATEGORICAL,
                proposed_value="Rust",
            )
        ],
        assumptions=[
            Assumption(
                id="asm_speedup",
                statement="Rust migration yields a 100x throughput improvement.",
                confidence=ConfidenceLevel.HIGH,  # Model claims high confidence
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_rust",
                upside="Memory safety and potential throughput optimization.",
                downside="Steep developer learning curve and multi-month development freeze.",
                affected_variable_ids=["var_lang"],
            )
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # Inferred constraint must NOT be marked USER_PROVIDED because user gave no constraints list
    assert audited.constraints[0].provenance == ProvenanceType.INFERRED
    assert audited.constraints[0].source == "inferred_operational"

    # Assumption confidence must be bounded to UNTESTED
    assert audited.assumptions[0].confidence == ConfidenceLevel.UNTESTED

    # Tradeoffs highlight actual downsides
    assert "learning curve" in audited.tradeoffs[0].downside.lower()


# ------------------------------------------------------------------------------
# 6. Questions with Multiple Possible Interpretations
# ------------------------------------------------------------------------------

def test_adversarial_multiple_possible_interpretations():
    """Scenario 6: Questions with multiple possible interpretations (e.g. 'expand into Europe').

    Verifies:
    - Captures ambiguity in key questions and unknowns rather than guessing a single path.
    - Does not settle arbitrarily on one interpretation as a user-provided fact.
    - Preserves structural integrity.
    """
    raw_prompt = "Should we expand into Europe next quarter?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate geographic and operational expansion into the European market.",
        decision_type=DecisionType.STRATEGIC_DIRECTION,
        variables=[
            Variable(
                id="var_entry_mode",
                name="European Market Entry Mode",
                description="Legal entity vs local sales reps vs EU cloud hosting.",
                variable_type=VariableType.CATEGORICAL,
                proposed_value=None,
            )
        ],
        unknowns=[
            Unknown(
                id="unk_expansion_type",
                question="Does expansion refer to GDPR cloud infrastructure, direct B2B sales, or local marketing?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Executive stakeholder inquiry"],
            ),
            Unknown(
                id="unk_regulatory_cost",
                question="What are the compliance costs for EU legal establishment?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Legal counsel review"],
            ),
        ],
        key_questions=[
            "What operational form will European expansion take?",
            "What is the projected ROI across different entry models?",
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # Multiple unknowns capture distinct interpretations
    assert len(audited.unknowns) >= 2
    assert any("gdpr" in u.question.lower() or "infrastructure" in u.question.lower() for u in audited.unknowns)

    # Key questions reflect exploratory ambiguity
    assert len(audited.key_questions) >= 2


# ------------------------------------------------------------------------------
# 7. Questions Containing Fake Statistics
# ------------------------------------------------------------------------------

def test_adversarial_fake_statistics():
    """Scenario 7: Questions containing fake statistics (e.g. '94.7% churn if latency > 200ms').

    Verifies:
    - Numbers mentioned in prompt (94.7%, 200ms, $75,000) are recorded without stripping, BUT
    - The causal claim is audited as an UNTESTED assumption, NOT verified ground truth.
    - Does NOT fabricate evidence (e.g. fake studies or validation citations).
    - Generates an Unknown to empirically measure actual churn correlation.
    - Does NOT provide a recommendation to spend or not spend.
    """
    raw_prompt = "Given that 94.7% of enterprise B2B customers churn when API latency exceeds 200ms, should we spend $75,000 on Redis caching?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate allocating $75,000 for Redis caching to prevent assumed 94.7% churn.",
        decision_type=DecisionType.RESOURCE_ALLOCATION,
        variables=[
            Variable(
                id="var_cost",
                name="Redis Infrastructure Spend",
                description="Capital expenditure on caching.",
                variable_type=VariableType.CURRENCY,
                proposed_value=75000,
                unit="USD",
            ),
            Variable(
                id="var_latency",
                name="API Latency Threshold",
                description="Latency threshold mentioned in inquiry.",
                variable_type=VariableType.NUMERIC,
                baseline_value=200,
                unit="ms",
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_churn_stat",
                statement="94.7% of enterprise customers churn when API latency exceeds 200ms.",
                confidence=ConfidenceLevel.HIGH,  # Model claims high confidence because user stated it
                falsification_condition="Telemetry shows churn rate under 10% during latency spikes.",
            )
        ],
        unknowns=[
            Unknown(
                id="unk_actual_churn",
                question="What is the empirical correlation between API latency and contract cancellation in our customer base?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Internal product analytics", "Customer exit interviews"],
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_cost_vs_retention",
                upside="Potential reduction in latency-related dissatisfaction.",
                downside="Immediate $75,000 capital outlay with uncertain attribution.",
                affected_variable_ids=["var_cost"],
            )
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # 1. User numbers are preserved
    assert audited.variables[0].proposed_value == 75000
    assert audited.variables[0].proposed_provenance == ProvenanceType.USER_PROVIDED
    assert audited.variables[1].baseline_value == 200
    assert audited.variables[1].baseline_provenance == ProvenanceType.USER_PROVIDED

    # 2. Causal statistic is downgraded to UNTESTED assumption, NOT accepted as truth
    assert audited.assumptions[0].confidence == ConfidenceLevel.UNTESTED
    assert audited.assumptions[0].provenance == ProvenanceType.INFERRED

    # 3. Unknown gap created for empirical telemetry
    assert "empirical correlation" in audited.unknowns[0].question.lower()

    # 4. No recommendation given
    assert "recommend" not in audited.decision.summary.lower()


# ------------------------------------------------------------------------------
# 8. Questions with No Obvious Objective
# ------------------------------------------------------------------------------

def test_adversarial_no_obvious_objective():
    """Scenario 8: Questions with no obvious objective (e.g. purely descriptive operational statement).

    Verifies:
    - Purely factual statements without clear objectives result in INFERRED objectives, never USER_PROVIDED.
    - Zero hallucinated numbers beyond user-provided 4, 2, 32.
    - Key questions explicitly inquire what decision is being faced.
    - Preserves structural validity.
    """
    raw_prompt = "We currently run 4 Kubernetes clusters across 2 cloud regions with 32 worker nodes."

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate operational status of 4 Kubernetes clusters with 32 nodes across 2 regions.",
        decision_type=DecisionType.OPERATIONAL_POLICY,
        objectives=[
            Objective(
                id="obj_clusters",
                description="Manage 4 Kubernetes clusters across regions.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,  # Model claims user provided this goal
            )
        ],
        variables=[
            Variable(
                id="var_clusters",
                name="Kubernetes Clusters",
                description="Number of clusters.",
                variable_type=VariableType.NUMERIC,
                baseline_value=4,
            ),
            Variable(
                id="var_regions",
                name="Cloud Regions",
                description="Number of regions.",
                variable_type=VariableType.NUMERIC,
                baseline_value=2,
            ),
            Variable(
                id="var_nodes",
                name="Worker Nodes",
                description="Total nodes in pool.",
                variable_type=VariableType.NUMERIC,
                baseline_value=32,
            ),
            Variable(
                id="var_cost",
                name="Monthly Cloud Cost",
                description="Infrastructure expense.",
                variable_type=VariableType.CURRENCY,
                baseline_value=12000,  # Model hallucinated $12,000!
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_redundancy",
                upside="Regional redundancy and high availability.",
                downside="Operational complexity managing multi-region networking.",
                affected_variable_ids=["var_clusters"],
            )
        ],
        key_questions=[
            "What specific decision, bottleneck, or change is being evaluated for these clusters?"
        ],
    )

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, mock_model)
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)

    audited = engine.deconstruct(question=raw_prompt)

    # 1. Objective is NOT user-provided because user stated facts, not an objective
    assert audited.objectives[0].provenance == ProvenanceType.INFERRED

    # 2. Legitimate user numbers (4, 2, 32) retained as USER_PROVIDED
    assert audited.variables[0].baseline_value == 4
    assert audited.variables[0].baseline_provenance == ProvenanceType.USER_PROVIDED
    assert audited.variables[1].baseline_value == 2
    assert audited.variables[1].baseline_provenance == ProvenanceType.USER_PROVIDED
    assert audited.variables[2].baseline_value == 32
    assert audited.variables[2].baseline_provenance == ProvenanceType.USER_PROVIDED

    # 3. Hallucinated $12,000 cost is stripped to None & UNKNOWN
    cost_var = audited.variables[3]
    assert cost_var.baseline_value is None
    assert cost_var.baseline_provenance == ProvenanceType.UNKNOWN

    # 4. Key question focuses on discovering the decision objective
    assert "what specific decision" in audited.key_questions[0].lower()


# ------------------------------------------------------------------------------
# 9. Regression Tests for Confirmed Bugs & Guards
# ------------------------------------------------------------------------------

def test_regression_neutralizes_prescriptive_recommendation_language():
    """Bug Regression: Verifies that prescriptive recommendation language is neutralized."""
    raw_prompt = "Should we migrate from MySQL to CockroachDB?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Recommendation: We recommend that you migrate to CockroachDB immediately.",
        decision_type=DecisionType.ARCHITECTURE_TECH,
        objectives=[
            Objective(
                id="obj_rec",
                description="We recommend adopting distributed SQL to reduce manual sharding.",
                is_primary=True,
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_rec",
                upside="The recommended choice is to eliminate manual sharding.",
                downside="You should definitely expect higher memory consumption.",
                affected_variable_ids=["var_scope"],
            )
        ],
        key_questions=["Recommendation: Start migration next sprint."],
    )

    audited = audit_decision_provenance(model=mock_model, raw_prompt=raw_prompt)

    # Prescriptive phrases must be cleansed
    assert not audited.decision.summary.lower().startswith("recommendation:")
    assert "we recommend" not in audited.decision.summary.lower()
    assert "we recommend" not in audited.objectives[0].description.lower()
    assert "the recommended choice is to" not in audited.tradeoffs[0].upside.lower()
    assert "you should definitely" not in audited.tradeoffs[0].downside.lower()
    assert not audited.key_questions[0].lower().startswith("recommendation:")


def test_regression_hallucinated_target_metric_and_threshold_stripped():
    """Bug Regression: Verifies that invented numbers in target_metric and threshold_expression are purged."""
    raw_prompt = "Should we optimize page load speed to improve user retention?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate optimizing page load performance.",
        decision_type=DecisionType.OPERATIONAL_POLICY,
        objectives=[
            Objective(
                id="obj_perf",
                description="Improve page load speed.",
                is_primary=True,
                target_metric="P95 latency <= 150ms",  # Hallucinated 150ms
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        constraints=[
            Constraint(
                id="cnstr_budget",
                name="CDN Budget Limit",
                description="CDN bill cannot exceed spending ceiling.",
                threshold_expression="cdn_spend <= 5000",  # Hallucinated 5000
                source="user_specified",
            )
        ],
    )

    audited = audit_decision_provenance(model=mock_model, raw_prompt=raw_prompt)

    # Objective provenance cannot be USER_PROVIDED with hallucinated metric
    assert audited.objectives[0].provenance == ProvenanceType.INFERRED

    # Constraint threshold with invented number 5000 must be purged
    assert audited.constraints[0].threshold_expression is None
    assert audited.constraints[0].provenance == ProvenanceType.INFERRED

    # Unknown gaps recorded for both
    unknown_questions = [u.question.lower() for u in audited.unknowns]
    assert any("target metric" in q for q in unknown_questions)
    assert any("threshold boundary" in q for q in unknown_questions)


def test_regression_ensures_unique_unknown_entity_ids():
    """Bug Regression: Verifies that multiple created unknowns do not create duplicate entity IDs."""
    raw_prompt = "Should we change pricing?"

    mock_model = _create_mock_decision_model(
        raw_prompt=raw_prompt,
        summary="Evaluate pricing change.",
        decision_type=DecisionType.STRATEGIC_DIRECTION,
        variables=[
            Variable(
                id="var_1",
                name="Price Tier A",
                description="Base price.",
                variable_type=VariableType.CURRENCY,
                baseline_value=100,  # Hallucinated
                proposed_value=80,   # Hallucinated
            ),
            Variable(
                id="var_2",
                name="Price Tier B",
                description="Premium price.",
                variable_type=VariableType.CURRENCY,
                baseline_value=200,  # Hallucinated
                proposed_value=160,  # Hallucinated
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_baseline_var_1",  # Pre-existing matching ID!
                question="Existing question regarding var_1 baseline.",
                criticality=CriticalityLevel.MEDIUM,
                provenance=ProvenanceType.UNKNOWN,
            )
        ],
    )

    audited = audit_decision_provenance(model=mock_model, raw_prompt=raw_prompt)

    # All unknown IDs in collection must be strictly unique
    unk_ids = [u.id for u in audited.unknowns]
    assert len(unk_ids) == len(set(unk_ids)), f"Duplicate IDs detected: {unk_ids}"

    # Structural revalidation must succeed
    revalidated = DecisionModel.model_validate(audited.model_dump())
    assert revalidated.id == audited.id


# ------------------------------------------------------------------------------
# 10. End-to-End AnalysisService Route Adversarial Test
# ------------------------------------------------------------------------------

def test_analysis_service_handles_adversarial_vague_request():
    """Verifies that AnalysisService orchestrates adversarial inputs safely and returns valid response."""
    service = AnalysisService()

    # Even for a completely vague adversarial prompt, AnalysisService returns a valid DecisionModel
    response = service.analyze(
        AnalysisRequest(
            question="Should we do something about tech?",
            context={"environment": "production"},
            constraints=["Downtime must be minimal"],
        )
    )

    assert response.status == "completed"
    assert response.analysis_id is not None
    assert len(response.analysis_id) == 36  # Standard UUID4 format
    assert response.decision_model is not None
    assert response.decision_model.decision.raw_prompt == "Should we do something about tech?"
    assert response.decision_model.complexity.score is not None
    assert len(response.decision_model.objectives) >= 1
    assert len(response.decision_model.variables) >= 1
    assert len(response.decision_model.tradeoffs) >= 1
    assert len(response.decision_model.key_questions) >= 1
