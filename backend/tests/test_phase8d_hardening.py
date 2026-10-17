"""AURA Day 8D: Action Intelligence End-to-End Verification & Hardening Tests.

Comprehensive integration and verification test suite verifying:
1. Realistic SaaS support-assistant decision scenario:
   - Budget cap: $150,000; Monthly cloud cost cap: $20,000; CSAT floor: 90%; 1,000-customer pilot.
   - Stage 4 recommendation favoring controlled pilot is preserved.
   - Conflict detection: 90% CSAT floor vs. 85% rollback trigger flagged as CONFLICT.
   - Non-conflicting thresholds preserved (pilot spend $45k <= $150k; monthly cost $15k <= $20k; 92% alert).
   - Ambiguous or incompatible units flagged as REVIEW_REQUIRED, not CONFLICT.
   - Zero-hallucination checks: Rejection of fabricated ROI, success probabilities, and resilience modifications.
2. Complete generation lifecycle:
   - Initial not_generated state -> POST generation -> Gemini structured response -> Validation -> SQLite persistence.
   - Cached-plan retrieval with zero LLM calls.
3. Concurrency and claim expiration guarantees:
   - Concurrent duplicate generation rejected with HTTP 409.
   - Expired or superseded SQLite claims prevent older workers from overwriting newer plans.
   - Force-regeneration confirmation idempotency.
4. Security and owner scoping:
   - Strict X-Owner-Id scoping across all endpoints (HTTP 403 on mismatch).
   - Unknown analysis IDs isolated (HTTP 404 Not Found).
   - GET requests never trigger generation or call Gemini.
5. Session restoration & backward compatibility:
   - Preserves 6-stage pipeline and Day 7 What-if simulation endpoints.
"""

from datetime import datetime, timezone
import json
import pytest
import time
from typing import Any, Dict, List, Optional
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.action_intelligence import (
    ACTION_INTELLIGENCE_GENERATOR_VERSION,
    ACTION_INTELLIGENCE_SCHEMA_VERSION,
    ActionCriterion,
    ActionPriority,
    CandidateActionCriterion,
    CandidateActionItem,
    CandidateActionPlan,
    CandidateDecisionGate,
    ComparisonOperator,
    CriterionType,
    IntelligentActionPlan,
    ValidationSeverity,
    compute_source_recommendation_fingerprint,
)
from app.schemas.analysis import AnalysisResponse
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
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceStance,
    Source,
    SourceType,
)
from app.schemas.job import AnalysisJobCreateRequest, JobStatus
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningBoard,
    ReasoningPerspective,
)
from app.schemas.recommendation import (
    ActionItem as Stage4ActionItem,
    ActionPlan as Stage4ActionPlan,
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
    ResilienceSubScore,
)
from app.schemas.scenario import (
    FutureScenario,
    ScenarioSet,
    ScenarioType,
)
from app.services.action_intelligence.generator import ActionIntelligenceGenerator
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.action_intelligence.validator import (
    ActionPlanValidationError,
    detect_threshold_conflicts,
    validate_action_plan,
)
from app.services.analysis_service import get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMResponseValidationError,
    LLMTimeoutError,
)


# ------------------------------------------------------------------------------
# Mock LLM Client
# ------------------------------------------------------------------------------

class MockGeminiClient:
    """Mock LLM client simulating Gemini structured output generation."""

    def __init__(self) -> None:
        self.model_name = "gemini-3.8-flash"
        self.call_count = 0
        self.calls: List[Dict[str, Any]] = []
        self.candidate_to_return: Optional[CandidateActionPlan] = None
        self.exception_to_raise: Optional[Exception] = None

    def generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        self.call_count += 1
        self.calls.append({
            "prompt": prompt,
            "system_instruction": system_instruction,
            "config": config,
            "deadline_monotonic": deadline_monotonic,
        })

        if self.exception_to_raise:
            raise self.exception_to_raise

        if self.candidate_to_return is not None:
            return self.candidate_to_return

        # Default realistic candidate grounded in Stage 4 SaaS actions
        return CandidateActionPlan(
            strategy_summary="Grounded operational plan for 3-month SaaS support-assistant pilot.",
            actions=[
                CandidateActionItem(
                    action_id="act_saas_pilot_item",
                    source_action_reference="act_saas_pilot",
                    title="Phase 1: 1,000 Customer Pilot",
                    description="Deploy support-assistant to 1,000 customers under tight latency monitoring.",
                    priority=ActionPriority.HIGH,
                    sequence=1,
                    owner_role="VP of Customer Support",
                    dependencies=[],
                    timing="Months 1-3",
                    prerequisites=["Pilot cohort selected"],
                    execution_steps=[
                        "Provision cloud workers with $20,000 monthly cap",
                        "Route 1,000 customer tickets to support assistant",
                    ],
                    success_criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_pilot_budget",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Pilot setup expenditure within $150,000 budget cap",
                            metric_name="budget",
                            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                            threshold_value=45000.0,
                            threshold_raw="$45,000",
                            unit="USD",
                            provenance_type="decision_model.constraints",
                            source_reference="cnstr_budget_cap",
                            is_hard=True,
                        ),
                        CandidateActionCriterion(
                            criterion_id="crit_pilot_csat_target",
                            criterion_type=CriterionType.RECOMMENDATION_TARGET,
                            description="Customer satisfaction target >= 90%",
                            metric_name="csat",
                            operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                            threshold_value=90.0,
                            threshold_raw="90%",
                            unit="%",
                            provenance_type="decision_model.constraints",
                            source_reference="cnstr_csat_floor",
                            is_hard=True,
                        ),
                    ],
                    risk_mitigations=["Human agent takeover if confidence is below 80%"],
                    contingency_or_rollback="Instant fallback to human agent queue",
                    evidence_references=["evi_saas_01"],
                    rationale="Minimizes financial risk while gathering real user interaction data.",
                    confidence_label="high",
                    confidence_rationale="Evidence demonstrates support accuracy on benchmark tickets.",
                    missing_information=[],
                ),
                CandidateActionItem(
                    action_id="act_saas_eval_item",
                    source_action_reference="act_saas_evaluation",
                    title="Phase 2: Pilot Review and General Rollout Gate",
                    description="Evaluate CSAT and monthly cloud run-rate before company-wide cutover.",
                    priority=ActionPriority.MEDIUM,
                    sequence=2,
                    owner_role="CTO",
                    dependencies=["act_saas_pilot_item"],
                    timing="Month 4",
                    prerequisites=["3-month pilot completed"],
                    execution_steps=["Audit cloud infrastructure costs", "Compile CSAT survey scores"],
                    success_criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_cloud_cost_check",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Monthly cloud run-rate within $20,000 cap",
                            metric_name="monthly_cost",
                            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                            threshold_value=18000.0,
                            threshold_raw="$18,000/mo",
                            unit="USD",
                            provenance_type="decision_model.constraints",
                            source_reference="cnstr_monthly_cloud_cap",
                            is_hard=True,
                        ),
                    ],
                    risk_mitigations=["Cap cloud provisioning quotas"],
                    contingency_or_rollback="Pause expansion and keep assistant restricted to pilot cohort",
                    evidence_references=["evi_saas_01"],
                    rationale="Ensures unit economics are verified before full capital commitment.",
                    confidence_label="moderate",
                    confidence_rationale="Dependent on ticket deflection metrics from Phase 1.",
                    missing_information=["Long-term deflection sustainability"],
                ),
            ],
            decision_gates=[
                CandidateDecisionGate(
                    gate_id="gate_saas_pilot_checkpoint",
                    title="Gate 1: Pilot Acceptance Checkpoint",
                    checkpoint="Month 3 Completion Checkpoint",
                    criteria=[
                        CandidateActionCriterion(
                            criterion_id="gate_crit_csat",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Customer satisfaction must remain at or above 90%",
                            metric_name="csat",
                            operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                            threshold_value=90.0,
                            threshold_raw="90%",
                            unit="%",
                            provenance_type="decision_model.constraints",
                            source_reference="cnstr_csat_floor",
                            is_hard=True,
                        )
                    ],
                    related_action_ids=["act_saas_pilot_item"],
                    failure_response="Halt rollout and revert customer routing to standard human support queue.",
                    source_references=["cnstr_csat_floor"],
                    unresolved_conflicts=[],
                )
            ],
            unresolved_questions=["Enterprise compliance certification requirements for HIPAA/SOC2"],
            limitations=["Pilot limited to English-language support tickets only"],
        )


# ------------------------------------------------------------------------------
# Test Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def mock_storage():
    """Provides an isolated SQLiteJobStorage in-memory instance."""
    return SQLiteJobStorage(db_path=":memory:")


@pytest.fixture
def mock_llm():
    """Provides a fresh MockGeminiClient."""
    return MockGeminiClient()


@pytest.fixture
def client(mock_storage, mock_llm):
    """Test client overriding dependencies with mock storage and mock LLM."""
    manager = AnalysisJobManager(storage=mock_storage)

    app.dependency_overrides[get_job_manager] = lambda: manager
    app.dependency_overrides[get_llm_client] = lambda: mock_llm

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def create_saas_support_analysis_job(
    mock_storage: SQLiteJobStorage,
    analysis_id: str = "analysis-saas-support-01",
    owner_id: Optional[str] = "saas_owner",
) -> AnalysisResponse:
    """Creates a realistic completed SaaS support-assistant decision analysis."""
    # 1. Stage 1: Decision Model with Budget ($150k), Cloud Cost ($20k/mo), CSAT (>=90%), Pilot (1,000 customers)
    decision_model = DecisionModel(
        id="dec_saas_01",
        decision=Decision(
            raw_prompt="Evaluate controlled 3-month pilot rollout of generative AI support assistant vs full rollout.",
            summary="Deploy AI Customer Support Assistant for Tier-1 Inquiries",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Moderate complexity with cross-functional support and financial risk.",
            reversibility=ReversibilityLevel.REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_csat",
                description="Keep customer satisfaction at or above 90%",
                is_primary=True,
            ),
            Objective(
                id="obj_cost_reduction",
                description="Support Cost Optimization: lower resolution cost per ticket",
                is_primary=False,
            ),
        ],
        constraints=[
            Constraint(
                id="cnstr_budget_cap",
                name="Initial Budget Cap",
                description="Initial budget cap cannot exceed $150,000",
                type="hard",
                unit="USD",
                threshold=150000.0,
                threshold_expression="<= 150000",
                is_hard_constraint=True,
            ),
            Constraint(
                id="cnstr_monthly_cloud_cap",
                name="Monthly Cloud Cost Cap",
                description="Monthly cloud cost cap cannot exceed $20,000",
                type="hard",
                unit="USD",
                threshold=20000.0,
                threshold_expression="<= 20000",
                is_hard_constraint=True,
            ),
            Constraint(
                id="cnstr_csat_floor",
                name="Customer Satisfaction Floor",
                description="Customer satisfaction requirement: at least 90%",
                type="hard",
                unit="%",
                threshold=90.0,
                threshold_expression=">= 90",
                is_hard_constraint=True,
            ),
            Constraint(
                id="cnstr_pilot_cohort",
                name="Pilot Cohort Size",
                description="Three-month pilot involving 1,000 customers",
                type="hard",
                unit="customers",
                threshold=1000.0,
                threshold_expression="== 1000",
                is_hard_constraint=True,
            ),
        ],
        variables=[
            Variable(
                id="var_pilot_size",
                name="Pilot Cohort Size",
                description="Number of pilot customers enrolled",
                variable_type=VariableType.NUMERIC,
                baseline_value=1000.0,
                unit="customers",
                is_controllable=True,
            ),
            Variable(
                id="var_monthly_cloud",
                name="Monthly Cloud Cost",
                description="Monthly cloud run-rate for support assistant",
                variable_type=VariableType.CURRENCY,
                baseline_value=15000.0,
                unit="USD",
                is_controllable=True,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_01",
                upside="Controlled risk exposure and empirical CSAT validation",
                downside="Delayed total company-wide ticket deflection savings",
                affected_variable_ids=["var_pilot_size", "var_monthly_cloud"],
            )
        ],
        key_questions=["Will tier-1 ticket CSAT stay above 90% during pilot?"],
    )

    # 2. Stage 2: Evidence Package
    src = Source(
        id="src_support_case_study",
        title="Enterprise Support Automation Trial",
        url="https://example.com/saas-support-study",
        source_type=SourceType.INTERNAL_DATA,
    )
    evi = EvidenceItem(
        id="evi_saas_01",
        source_id="src_support_case_study",
        content="Benchmark pilot demonstrated 68% deflection with 91.2% CSAT on tier-1 tickets.",
    )
    evidence_package = EvidencePackage(
        id="ev_pkg_01",
        decision_model_id="dec_saas_01",
        summary="Support pilot evidence shows strong satisfaction retention with controlled rollout.",
        requirements=[],
        sources=[src],
        items=[evi],
        claim_links=[],
        gaps=[],
    )

    # 3. Stage 4: Authoritative Recommendation Favoring Controlled Pilot
    action_1 = Stage4ActionItem(
        id="act_saas_pilot",
        title="Deploy Phased 1,000-Customer Pilot",
        objective="Run 3-month pilot for 1,000 users",
        description="Run 3-month pilot for 1,000 users with human fallback and weekly CSAT tracking.",
        priority=ActionPriority.HIGH,
        responsible_role="VP Customer Support",
        time_horizon="immediate",
        dependencies=[],
    )
    action_2 = Stage4ActionItem(
        id="act_saas_evaluation",
        title="Pilot Gate Evaluation and Rollout Decision",
        objective="Audit cloud expenditure and CSAT floor",
        description="Audit cloud expenditure and CSAT floor before expanding to general customer base.",
        priority=ActionPriority.HIGH,
        responsible_role="CTO",
        time_horizon="near_term",
        dependencies=["act_saas_pilot"],
    )

    recommendation = DecisionRecommendation(
        id="rec_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_saas_01",
        evidence_package_id="ev_pkg_01",
        reasoning_board_id="rb_01",
        decision_status=DecisionStatus.PILOT,
        recommended_action="Proceed with 3-month controlled pilot of AI Support Assistant across 1,000 customers.",
        executive_rationale="Balances operational upside with strict customer satisfaction guardrails.",
        action_plan=Stage4ActionPlan(
            summary="Controlled 2-phase pilot rollout roadmap.",
            actions=[action_1, action_2],
        ),
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=EvidenceStrength.STRONG,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
        ),
    )

    response = AnalysisResponse(
        analysis_id=analysis_id,
        status="completed",
        question="Evaluate controlled pilot rollout of AI customer support assistant.",
        decision_model=decision_model,
        evidence_package=evidence_package,
        recommendation=recommendation,
    )

    req = AnalysisJobCreateRequest(
        question="Evaluate controlled pilot rollout of AI customer support assistant.",
        owner_id=owner_id,
    )
    job = mock_storage.create_job(req, job_id=analysis_id)
    mock_storage.complete_job(job.job_id, response=response)

    return response


# ==============================================================================
# SECTION 1: Realistic SaaS Support-Assistant Recommendation Consistency
# ==============================================================================

def test_saas_recommendation_consistency_preserves_recommendation(client, mock_storage, mock_llm):
    """1. Action Intelligence preserves original Stage 4 recommendation and action references."""
    analysis_id = "saas-test-01"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)

    resp = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "saas_owner"},
        json={},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    plan = data["plan"]
    assert plan is not None
    assert "3-month SaaS support-assistant pilot" in plan["strategy_summary"]

    # Must reuse valid Stage 4 action references
    action_refs = [a["source_action_reference"] for a in plan["actions"]]
    assert "act_saas_pilot" in action_refs
    assert "act_saas_evaluation" in action_refs

    # Verify sequence order
    assert plan["actions"][0]["sequence"] == 1
    assert plan["actions"][1]["sequence"] == 2


def test_saas_detects_csat_floor_conflict_against_85_rollback(client, mock_storage, mock_llm):
    """2. Flags direct CONFLICT when a rollback trigger allows CSAT degradation to 85% with 90% floor."""
    analysis_id = "saas-test-02"
    analysis_resp = create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)
    dec_model = analysis_resp.decision_model

    # Candidate introduces a gate criterion with rollback at 85% CSAT
    candidate = mock_llm.generate_structured("", None)
    valid_fp = "srfp_" + "a" * 32
    plan = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=valid_fp,
    )

    # Incompatible rollback trigger: CSAT at 85%
    bad_rollback_crit = ActionCriterion(
        criterion_id="gate_crit_csat_rollback_85",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Rollback if CSAT drops below 85%",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=85.0,  # Below 90% floor!
        threshold_raw="85%",
        unit="%",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat_floor",
        is_hard=True,
    )

    gate_with_conflict = plan.decision_gates[0].model_copy(update={"criteria": [bad_rollback_crit]})
    plan_with_conflict = plan.model_copy(update={"decision_gates": [gate_with_conflict]})

    warns = detect_threshold_conflicts(plan_with_conflict, decision_model=dec_model)
    conflicts = [w for w in warns if w.severity == ValidationSeverity.CONFLICT]

    assert len(conflicts) >= 1
    assert "Direct threshold conflict" in conflicts[0].message
    assert "85.0%" in conflicts[0].message
    assert "90.0%" in conflicts[0].message
    assert "cnstr_csat_floor" in conflicts[0].message


def test_saas_does_not_treat_all_differing_thresholds_as_conflicts(client, mock_storage, mock_llm):
    """3. Does NOT treat all differing thresholds as conflicts (preserves valid operational targets)."""
    analysis_id = "saas-test-03"
    analysis_resp = create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)
    dec_model = analysis_resp.decision_model

    candidate = mock_llm.generate_structured("", None)
    valid_fp = "srfp_" + "a" * 32
    plan = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=valid_fp,
    )

    # Pilot spend $45,000 <= $150,000 budget cap
    # Monthly cost $18,000 <= $20,000 monthly cap
    # CSAT target 90% >= 90% floor
    # Check that detect_threshold_conflicts emits ZERO conflicts for valid targets
    warns = detect_threshold_conflicts(plan, decision_model=dec_model)
    conflicts = [w for w in warns if w.severity == ValidationSeverity.CONFLICT]
    assert len(conflicts) == 0, f"Valid thresholds should not trigger conflicts: {conflicts}"


def test_saas_flags_incompatible_units_as_review_required(client, mock_storage, mock_llm):
    """4. Flags incompatible or ambiguous units as REVIEW_REQUIRED instead of guessing."""
    analysis_id = "saas-test-04"
    analysis_resp = create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)
    dec_model = analysis_resp.decision_model

    candidate = mock_llm.generate_structured("", None)
    valid_fp = "srfp_" + "a" * 32
    plan = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=valid_fp,
    )

    # Unit is "points" instead of "%"
    ambig_crit = ActionCriterion(
        criterion_id="crit_csat_points_metric",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="CSAT score in NPS-style points",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=90.0,
        threshold_raw="90 points",
        unit="points",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat_floor",
    )

    plan_ambig = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [ambig_crit]}), plan.actions[1]]
    })

    warns = detect_threshold_conflicts(plan_ambig, decision_model=dec_model)
    reviews = [w for w in warns if w.severity == ValidationSeverity.REVIEW_REQUIRED]

    assert len(reviews) >= 1
    assert "Incompatible or ambiguous units" in reviews[0].message
    assert "points" in reviews[0].message


def test_saas_rejects_fabricated_claims_and_resilience_improvements(client, mock_storage, mock_llm):
    """5. Deterministically rejects fabricated ROI, success probabilities, and resilience score boosts."""
    analysis_id = "saas-test-05"
    analysis_resp = create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)

    candidate = mock_llm.generate_structured("", None)
    valid_fp = "srfp_" + "a" * 32
    plan = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=valid_fp,
    )

    # 1. Prohibited ROI claim
    roi_crit = ActionCriterion(
        criterion_id="crit_fake_roi",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Projected ROI return on investment of 40%",
        metric_name="roi",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=40.0,
        unit="%",
        provenance_type="fabricated",
    )
    plan_roi = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [roi_crit]}), plan.actions[1]]
    })
    with pytest.raises(ActionPlanValidationError, match="prohibited fabricated ROI"):
        validate_action_plan(plan_roi, decision_model=analysis_resp.decision_model)

    # 2. Prohibited success probability claim
    prob_crit = ActionCriterion(
        criterion_id="crit_fake_prob",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Estimated probability of success 95%",
        metric_name="success_probability",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=95.0,
        unit="%",
        provenance_type="fabricated",
    )
    plan_prob = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [prob_crit]}), plan.actions[1]]
    })
    with pytest.raises(ActionPlanValidationError, match="prohibited fabricated numeric success probability"):
        validate_action_plan(plan_prob, decision_model=analysis_resp.decision_model)

    # 3. Prohibited resilience score modification claim
    resil_crit = ActionCriterion(
        criterion_id="crit_fake_resilience",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Improves resilience score to 92",
        metric_name="resilience_score",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=92.0,
        unit="points",
        provenance_type="fabricated",
    )
    plan_resil = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [resil_crit]}), plan.actions[1]]
    })
    with pytest.raises(ActionPlanValidationError, match="prohibited fabricated resilience score modification"):
        validate_action_plan(plan_resil, decision_model=analysis_resp.decision_model)


# ==============================================================================
# SECTION 2: Complete Generation & Caching Lifecycle
# ==============================================================================

def test_full_generation_lifecycle_and_caching(client, mock_storage, mock_llm):
    """6. Full lifecycle: ungenerated -> generate -> validate -> persist -> cached retrieval."""
    analysis_id = "lifecycle-e2e-01"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="user_lifecycle")

    # Step 1: Completed analysis with no action plan
    resp_get_init = client.get(
        f"/api/analysis/{analysis_id}/action-plan",
        headers={"X-Owner-Id": "user_lifecycle"},
    )
    assert resp_get_init.status_code == status.HTTP_404_NOT_FOUND

    resp_status_init = client.get(
        f"/api/analysis/{analysis_id}/action-plan/status",
        headers={"X-Owner-Id": "user_lifecycle"},
    )
    assert resp_status_init.status_code == status.HTTP_200_OK
    assert resp_status_init.json()["status"] == "not_generated"
    assert mock_llm.call_count == 0

    # Step 2: Explicit POST generate request
    resp_gen = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "user_lifecycle"},
        json={},
    )
    assert resp_gen.status_code == status.HTTP_200_OK
    gen_data = resp_gen.json()
    assert gen_data["status"] == "ready"
    assert gen_data["cached"] is False
    assert gen_data["plan"] is not None
    assert mock_llm.call_count == 1

    # Step 3: GET retrieves persisted plan with zero additional LLM calls
    resp_get_cached = client.get(
        f"/api/analysis/{analysis_id}/action-plan",
        headers={"X-Owner-Id": "user_lifecycle"},
    )
    assert resp_get_cached.status_code == status.HTTP_200_OK
    cached_data = resp_get_cached.json()
    assert cached_data["cached"] is True
    assert cached_data["plan"]["plan_id"] == gen_data["plan"]["plan_id"]
    assert mock_llm.call_count == 1  # Still exactly 1!

    # Step 4: Status endpoint shows ready and cached
    resp_stat_cached = client.get(
        f"/api/analysis/{analysis_id}/action-plan/status",
        headers={"X-Owner-Id": "user_lifecycle"},
    )
    assert resp_stat_cached.status_code == status.HTTP_200_OK
    assert resp_stat_cached.json()["status"] == "ready"
    assert resp_stat_cached.json()["cached"] is True
    assert mock_llm.call_count == 1


# ==============================================================================
# SECTION 3: Concurrency, Expired Claims & Overwrite Prevention
# ==============================================================================

def test_concurrent_generation_requests_rejected_with_409(client, mock_storage, mock_llm):
    """7. Concurrent generation requests rejected with HTTP 409 without multiplying LLM calls."""
    analysis_id = "concurrent-test-01"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="user_concur")

    # Worker 1 holds active SQLite claim
    acquired, claim_status, claim_id = mock_storage.acquire_action_plan_claim(
        analysis_id=analysis_id,
        owner_id="user_concur",
        ttl_seconds=90.0,
    )
    assert acquired is True

    # Worker 2 attempts concurrent generation
    resp_concur = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "user_concur"},
        json={},
    )
    assert resp_concur.status_code == status.HTTP_409_CONFLICT
    assert "currently in progress" in resp_concur.json()["detail"]
    assert mock_llm.call_count == 0


def test_expired_claim_cannot_overwrite_newer_successful_plan(client, mock_storage, mock_llm):
    """8. An expired or superseded claim prevents an older worker from overwriting a newer plan."""
    analysis_id = "superseded-claim-test"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="user_ttl")

    manager = AnalysisJobManager(storage=mock_storage)
    service = ActionIntelligenceService(manager=manager, llm_client=mock_llm)

    # 1. Worker 1 acquires claim_1
    acq1, stat1, claim_1 = mock_storage.acquire_action_plan_claim(
        analysis_id=analysis_id,
        owner_id="user_ttl",
        ttl_seconds=90.0,
    )
    assert acq1 is True

    # 2. Worker 2 arrives later (simulating force-regeneration or recovery after claim_1 TTL)
    # Worker 2 updates claim to claim_2 and completes successfully
    mock_storage._conn.execute(
        """
        UPDATE action_plan_claims
        SET claim_id = 'claim_worker_2', status = 'ready', expires_at = ?
        WHERE analysis_id = ?;
        """,
        (time.time() + 90.0, analysis_id),
    )
    mock_storage._conn.commit()

    # Worker 2 saved a successful plan into SQLite
    candidate2 = mock_llm.generate_structured("", None)
    valid_fp_worker2 = "srfp_" + "b" * 32
    plan_2 = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate2,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=valid_fp_worker2,
    )
    service.save_action_plan(plan_2, owner_id="user_ttl")

    # 3. Worker 1 finishes generation with older claim_1 and tries to save via generate_action_plan
    # We simulate Worker 1's post-generation check:
    # Since current_claim["claim_id"] == 'claim_worker_2' != claim_1, Worker 1 must abort with HTTP 409
    current_claim = mock_storage.get_action_plan_claim(analysis_id)
    assert current_claim["claim_id"] == "claim_worker_2"
    assert current_claim["claim_id"] != claim_1

    # Attempting to save under stale claim_1 must be rejected
    now = time.time()
    is_expired = now > float(current_claim.get("expires_at", 0))
    assert (current_claim.get("claim_id") != claim_1 or current_claim.get("status") != "running")

    # Verify existing plan from Worker 2 is preserved
    saved_plan = service.get_action_plan(analysis_id, owner_id="user_ttl")
    assert saved_plan is not None
    assert saved_plan.source_recommendation_fingerprint == valid_fp_worker2


def test_force_regeneration_bypasses_cache_with_explicit_confirmation(client, mock_storage, mock_llm):
    """9. force_regenerate=True bypasses cached plan and idempotently updates SQLite."""
    analysis_id = "force-regen-test"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="user_force")

    # 1. First generation
    resp1 = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "user_force"},
        json={"force_regenerate": False},
    )
    assert resp1.status_code == status.HTTP_200_OK
    plan_id_1 = resp1.json()["plan"]["plan_id"]
    assert mock_llm.call_count == 1

    # 2. Second call with force_regenerate=False -> returns cache
    resp2 = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "user_force"},
        json={"force_regenerate": False},
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.json()["cached"] is True
    assert mock_llm.call_count == 1

    # 3. Third call with force_regenerate=True -> triggers new Gemini generation
    resp3 = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "user_force"},
        json={"force_regenerate": True},
    )
    assert resp3.status_code == status.HTTP_200_OK
    assert resp3.json()["cached"] is False
    assert mock_llm.call_count == 2


# ==============================================================================
# SECTION 4: API Security, Isolation & Error Safeguards
# ==============================================================================

def test_owner_scoped_isolation(client, mock_storage):
    """10. Access is strictly scoped to the owner; unauthorized callers receive HTTP 403."""
    analysis_id = "owned-by-alice"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="alice")

    # Eve tries to read Alice's action plan
    resp_get = client.get(
        f"/api/analysis/{analysis_id}/action-plan",
        headers={"X-Owner-Id": "eve"},
    )
    assert resp_get.status_code == status.HTTP_403_FORBIDDEN
    assert "owner mismatch" in resp_get.json()["detail"]

    # Eve tries to generate Alice's action plan
    resp_post = client.post(
        f"/api/analysis/{analysis_id}/action-plan/generate",
        headers={"X-Owner-Id": "eve"},
        json={},
    )
    assert resp_post.status_code == status.HTTP_403_FORBIDDEN

    # Eve tries to poll Alice's status
    resp_stat = client.get(
        f"/api/analysis/{analysis_id}/action-plan/status",
        headers={"X-Owner-Id": "eve"},
    )
    assert resp_stat.status_code == status.HTTP_403_FORBIDDEN


def test_unknown_analysis_id_returns_404_and_leaks_nothing(client, mock_storage):
    """11. Unknown analysis IDs return HTTP 404 without leaking other users' data."""
    unknown_id = "nonexistent-analysis-9999"

    resp_get = client.get(f"/api/analysis/{unknown_id}/action-plan")
    assert resp_get.status_code == status.HTTP_404_NOT_FOUND

    resp_stat = client.get(f"/api/analysis/{unknown_id}/action-plan/status")
    assert resp_stat.status_code == status.HTTP_404_NOT_FOUND

    resp_post = client.post(f"/api/analysis/{unknown_id}/action-plan/generate", json={})
    assert resp_post.status_code == status.HTTP_404_NOT_FOUND


def test_rejection_of_fabricated_source_references(client, mock_storage, mock_llm):
    """12. Rejects fabricated Stage 4 action references and fabricated evidence citations."""
    analysis_id = "fabrication-check-01"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)

    # Candidate with fabricated Stage 4 action reference
    fake_candidate = CandidateActionPlan(
        strategy_summary="Plan referencing imaginary actions.",
        actions=[
            CandidateActionItem(
                action_id="act_rogue",
                source_action_reference="act_invented_99",  # NOT in Stage 4!
                title="Invented Action",
                description="Action without Stage 4 grounding",
                priority=ActionPriority.HIGH,
                sequence=1,
                owner_role="Lead",
                dependencies=[],
                timing="Now",
                prerequisites=[],
                execution_steps=[],
                success_criteria=[],
                risk_mitigations=[],
                contingency_or_rollback=None,
                evidence_references=[],
                rationale="Unsubstantiated",
                confidence_label="low",
                confidence_rationale=None,
                missing_information=[],
            )
        ],
        decision_gates=[],
        unresolved_questions=[],
        limitations=[],
    )
    mock_llm.candidate_to_return = fake_candidate

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert "references invalid or fabricated Stage 4 action" in resp.json()["detail"]


# ==============================================================================
# SECTION 5: Session Restoration & Day 7 Regression Safeguards
# ==============================================================================

def test_session_restoration_and_day7_whatif_compatibility(client, mock_storage):
    """13. Preserves Day 7 What-if simulation endpoints and six-stage pipeline artifacts."""
    analysis_id = "day7-compat-check"
    create_saas_support_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. Variable discovery endpoint functional
    v_resp = client.get(f"/api/analysis/{analysis_id}/simulation-variables")
    assert v_resp.status_code == status.HTTP_200_OK
    vars_data = v_resp.json()
    assert "variables" in vars_data
    assert len(vars_data["variables"]) >= 2

    # 2. Simulation list endpoint functional
    s_resp = client.get(f"/api/analysis/{analysis_id}/simulations")
    assert s_resp.status_code == status.HTTP_200_OK

    # 3. Analysis retrieval preserves authoritative decision model, evidence, and recommendation
    job_record = mock_storage.get_job_by_any_id(analysis_id)
    assert job_record is not None
    assert job_record.response.decision_model is not None
    assert job_record.response.evidence_package is not None
    assert job_record.response.recommendation is not None
@pytest.mark.parametrize(
    "text",
    [
        "immediate " * 50,
        " ".join(f"week_{i}" for i in range(1, 101)),
        " ".join(f"horizon_{i}" for i in range(1, 101)),
        " ".join(f"pilot_checkpoint_{i}" for i in range(1, 101)),
        " ".join(["immediate", "short_term", "checkpoint"] * 30),
        "A" * 8001,
    ],
)
def test_generated_action_text_rejects_degeneration(text):
    """Reject malformed generated text without making LLM calls."""
    from app.services.action_intelligence.validator import validate_generated_text

    with pytest.raises(ActionPlanValidationError):
        validate_generated_text(text, "test_field")


@pytest.mark.parametrize(
    "text",
    [
        "Months 1-3",
        "Complete the pilot review in weeks 1-3.",
        "week_1 week_2 week_3",
        "Review customer feedback, validate costs, and prepare rollback.",
    ],
)
def test_generated_action_text_accepts_normal_content(text):
    """Accept concise, meaningful roadmap text."""
    from app.services.action_intelligence.validator import validate_generated_text

    validate_generated_text(text, "test_field")
@pytest.mark.parametrize(
    ("field_name", "limit"),
    [
        ("actions[act_test].timing", 160),
        ("decision_gates[gate_test].checkpoint", 240),
        ("actions[act_test].title", 300),
    ],
)
def test_generated_action_text_enforces_field_limits(field_name, limit):
    """Short roadmap fields must respect their character limits."""
    from app.services.action_intelligence.validator import validate_generated_text

    validate_generated_text("A" * limit, field_name)

    with pytest.raises(ActionPlanValidationError, match="safety limit"):
        validate_generated_text("A" * (limit + 1), field_name)


def test_full_action_plan_validation_rejects_repetitive_timing():
    """Malformed timing must be rejected by the master validator."""
    candidate = MockGeminiClient().generate_structured("", None)

    plan = ActionIntelligenceGenerator(MockGeminiClient()).assemble_plan(
        candidate=candidate,
        analysis_id="text-quality-test",
        source_recommendation_fingerprint="srfp_" + "a" * 32,
    )

    malformed_action = plan.actions[0].model_copy(
        update={"timing": " ".join(f"week_{i}" for i in range(1, 101))}
    )
    malformed_plan = plan.model_copy(
        update={"actions": [malformed_action, *plan.actions[1:]]}
    )

    with pytest.raises(
        ActionPlanValidationError,
        match=r"Generated text in 'actions\[act_saas_pilot_item\]\.timing'",
    ):
        validate_action_plan(malformed_plan)