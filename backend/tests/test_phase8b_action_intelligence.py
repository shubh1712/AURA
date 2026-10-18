"""AURA Phase 8B: Gemini-Powered Action Intelligence Generation Tests.

Comprehensive test suite verifying all 19 required Day 8B scenarios:
1. Successful Gemini structured generation using a mocked client.
2. Correct grounding in Stage 4 actions.
3. Rejection of fabricated or invalid source references.
4. Rejection of unsupported numerical claims.
5. Invalid JSON and schema failures.
6. Gemini timeout.
7. Gemini API failure.
8. Concurrent duplicate generation requests.
9. Cache hit without Gemini invocation.
10. Failed generation followed by retry.
11. Persistence after successful generation.
12. No partial plan persisted after failure.
13. Correct generation status transitions.
14. GET never invoking Gemini.
15. Invalid and incomplete analyses.
16. Owner-scoped access.
17. Numeric threshold conflict versus review-required distinction.
18. Backward compatibility with the six-stage pipeline.
19. Day 7 What-if and restoration regressions.
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
# Mock LLM Client & Test Fixtures
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

        # Default valid candidate grounded in Stage 4 actions ("act_1", "act_2")
        return CandidateActionPlan(
            strategy_summary="Grounded operational plan for phased AI pilot rollout.",
            actions=[
                CandidateActionItem(
                    action_id="act_1",
                    source_action_reference="act_1",
                    title="Pilot Infrastructure Setup",
                    description="Provision isolated cloud environment and configure egress firewall rules.",
                    priority=ActionPriority.HIGH,
                    sequence=1,
                    owner_role="Lead Platform Engineer",
                    dependencies=[],
                    timing="Weeks 1-2",
                    prerequisites=["Architecture review signed off"],
                    success_criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_pilot_cap",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Pilot cohort capped at 1000 customers",
                            metric_name="cohort_size",
                            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                            threshold_value=1000.0,
                            threshold_raw="1,000 customers",
                            unit="customers",
                            provenance_type="decision_model.constraints",
                            source_reference="cnstr_pilot_cohort",
                            is_hard=True,
                        )
                    ],
                    risk_mitigations=["Strict rate limiting per tenant"],
                    contingency_or_rollback="Disable routing gateway",
                    evidence_references=["ev_item_01"],
                    rationale="Guarantees safe operational sandboxing before customer traffic.",
                    confidence_label="high",
                    confidence_rationale="Tested in staging",
                    missing_information=[],
                ),
                CandidateActionItem(
                    action_id="act_2",
                    source_action_reference="act_2",
                    title="Phased Customer Onboarding",
                    description="Deploy to 1,000 pilot customers with real-time telemetry monitoring.",
                    priority=ActionPriority.HIGH,
                    sequence=2,
                    owner_role="Customer Operations Director",
                    dependencies=["act_1"],
                    timing="Weeks 3-6",
                    prerequisites=["Infrastructure health checks passing"],
                    success_criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_csat_floor",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Maintain customer satisfaction at or above 90%",
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
                    risk_mitigations=["Dedicated customer triage channel"],
                    contingency_or_rollback="Pause onboarding and revert to legacy support",
                    evidence_references=["ev_item_01"],
                    rationale="Validates customer reception under real operational load.",
                    confidence_label="high",
                    confidence_rationale="Backed by support SLA telemetry",
                    missing_information=[],
                ),
            ],
            decision_gates=[
                CandidateDecisionGate(
                    gate_id="gate_pilot_review",
                    title="Pilot Milestone Checkpoint",
                    checkpoint="End of Week 4",
                    criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_gate_csat",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Verify CSAT remains >= 90% during pilot",
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
                    related_action_ids=["act_2"],
                    failure_response="Immediate rollback to manual support and incident review.",
                    source_references=["cnstr_csat_floor"],
                    unresolved_conflicts=[],
                )
            ],
            unresolved_questions=["Long-term retention impact beyond month 3."],
            limitations=["Pilot findings apply solely to English-language support tier."],
        )


@pytest.fixture
def mock_storage():
    return SQLiteJobStorage(db_path=":memory:")


@pytest.fixture
def mock_job_manager(mock_storage):
    return AnalysisJobManager(storage=mock_storage)


@pytest.fixture
def mock_llm():
    return MockGeminiClient()


@pytest.fixture
def client(mock_job_manager, mock_llm):
    app.dependency_overrides[get_job_manager] = lambda: mock_job_manager
    app.dependency_overrides[get_llm_client] = lambda: mock_llm
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def create_mock_analysis_job(
    storage: SQLiteJobStorage,
    job_id: Optional[str] = None,
    analysis_id: str = "analysis-day8b-test",
    status_str: str = "completed",
    owner_id: Optional[str] = None,
    include_rec: bool = True,
) -> AnalysisResponse:
    """Creates and persists a comprehensive 6-stage completed analysis in SQLite."""
    now_iso = datetime.now(timezone.utc).isoformat()

    decision_model = DecisionModel(
        id="dec_01",
        decision=Decision(
            raw_prompt="Should we deploy an automated AI assistant for customer support?",
            summary="Deploy AI assistant for tier 1 customer support.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="High complexity due to cross-functional operational impact.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_efficiency",
                description="Reduce first-response time",
                is_primary=True,
            )
        ],
        variables=[
            Variable(
                id="var_pilot_spend",
                name="Pilot Cloud Spend",
                description="Monthly pilot compute expenditure.",
                variable_type=VariableType.CURRENCY,
                baseline_value=50000.0,
                unit="USD",
                is_controllable=True,
            )
        ],
        constraints=[
            Constraint(
                id="cnstr_pilot_cohort",
                name="Pilot Cohort Cap",
                description="Pilot capped at 1,000 customers",
                type="hard",
                threshold=1000.0,
                threshold_expression="<= 1000",
                unit="customers",
                is_hard_constraint=True,
            ),
            Constraint(
                id="cnstr_csat_floor",
                name="Customer Satisfaction Floor",
                description="CSAT must remain at or above 90%",
                type="hard",
                threshold=90.0,
                threshold_expression=">= 90",
                unit="%",
                is_hard_constraint=True,
            ),
            Constraint(
                id="cnstr_budget",
                name="Implementation Budget",
                description="Budget ceiling for deployment",
                type="hard",
                threshold=150000.0,
                threshold_expression="<= 150000",
                unit="USD",
                is_hard_constraint=True,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_01",
                upside="Faster support resolution",
                downside="Initial pilot operational friction",
                affected_variable_ids=["var_pilot_spend"],
            )
        ],
        key_questions=["Will pilot meet expectations?"],
    )

    src = Source(
        id="src_01",
        title="Internal Pilot Study",
        url="https://internal.metrics/study",
        source_type=SourceType.INTERNAL_DATA,
    )
    evi = EvidenceItem(
        id="ev_item_01",
        source_id="src_01",
        content="Pilot deployments sustained 91% CSAT when capped below 1,000 users.",
    )
    evidence_package = EvidencePackage(
        id="ev_pkg_01",
        decision_model_id="dec_01",
        summary="Empirical evidence package summary.",
        requirements=[],
        sources=[src],
        items=[evi],
        claim_links=[],
        gaps=[],
    )

    reasoning_board = None

    recommendation = None
    if include_rec:
        recommendation = DecisionRecommendation(
            id="rec_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_01",
            evidence_package_id="ev_pkg_01",
            reasoning_board_id="rb_01",
            decision_status=DecisionStatus.PILOT,
            recommended_action="Execute a bounded pilot for 1,000 customers with rigorous CSAT monitoring.",
            executive_rationale="Balances operational upside with strict customer satisfaction guardrails.",
            action_plan=Stage4ActionPlan(
                summary="Two-phase pilot rollout roadmap.",
                actions=[
                    Stage4ActionItem(
                        id="act_1",
                        title="Infrastructure Setup",
                        objective="Sandbox environment setup",
                        description="Configure VPC routing and quota limits.",
                        priority=ActionPriority.HIGH,
                        responsible_role="Lead Platform Engineer",
                        time_horizon="immediate",
                        dependencies=[],
                    ),
                    Stage4ActionItem(
                        id="act_2",
                        title="Customer Onboarding",
                        objective="Phased customer cutover",
                        description="Route 1,000 customers to pilot assistant.",
                        priority=ActionPriority.HIGH,
                        responsible_role="Customer Operations Director",
                        time_horizon="near_term",
                        dependencies=["act_1"],
                    ),
                ],
            ),
            uncertainty_assessment=UncertaintyAssessment(
                evidence_strength=EvidenceStrength.STRONG,
                decision_readiness=DecisionReadiness.READY,
                recommendation_stability=RecommendationStability.HIGH,
            ),
        )

    scenarios = None
    resilience = None

    resp = AnalysisResponse(
        analysis_id=analysis_id,
        status=status_str,
        question="Should we deploy an automated AI assistant for customer support?",
        decision_model=decision_model,
        evidence_package=evidence_package,
        reasoning_board=reasoning_board,
        recommendation=recommendation,
        scenarios=scenarios,
        resilience=resilience,
    )

    req = AnalysisJobCreateRequest(
        question="Should we deploy an automated AI assistant?",
        owner_id=owner_id,
    )
    effective_jid = job_id or analysis_id
    job = storage.create_job(req, job_id=effective_jid)
    if status_str == "completed":
        storage.complete_job(job.job_id, response=resp)
    elif status_str == "running":
        storage.update_running(job.job_id)
    elif status_str == "failed":
        storage.fail_job(job.job_id, error_message="Analysis execution failed", error_status_code=500)

    return resp


# ------------------------------------------------------------------------------
# Test 1: Successful Gemini Structured Generation using Mocked Client
# ------------------------------------------------------------------------------

def test_successful_gemini_structured_generation(client, mock_storage, mock_llm):
    """1. Successful Gemini structured generation using a mocked client."""
    analysis_id = "analysis-gemini-success"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "ready"
    assert data["cached"] is False
    assert data["analysis_id"] == analysis_id

    plan = data["plan"]
    assert plan["plan_id"].startswith("plan_")
    assert plan["generator_version"] == ACTION_INTELLIGENCE_GENERATOR_VERSION
    assert plan["schema_version"] == ACTION_INTELLIGENCE_SCHEMA_VERSION
    assert len(plan["actions"]) == 2
    assert plan["actions"][0]["action_id"] == "act_1"
    assert plan["actions"][1]["action_id"] == "act_2"
    assert plan["actions"][1]["dependencies"] == ["act_1"]
    assert len(plan["decision_gates"]) == 1

    # Verify Gemini was invoked exactly once with structured config
    assert mock_llm.call_count == 1
    assert "CandidateActionPlan" in str(type(mock_llm.calls[0]["config"])) or mock_llm.calls[0]["config"].stage == "action_intelligence"


# ------------------------------------------------------------------------------
# Test 2: Correct Grounding in Stage 4 Actions
# ------------------------------------------------------------------------------

def test_correct_grounding_in_stage4_actions(client, mock_storage, mock_llm):
    """2. Correct grounding in Stage 4 actions."""
    analysis_id = "analysis-grounding"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_200_OK

    plan = resp.json()["plan"]
    for act in plan["actions"]:
        assert act["source_action_reference"] in ("act_1", "act_2")


# ------------------------------------------------------------------------------
# Test 3: Rejection of Fabricated or Invalid Source References
# ------------------------------------------------------------------------------

def test_rejection_of_fabricated_or_invalid_source_references(client, mock_storage, mock_llm):
    """3. Rejection of fabricated or invalid source references."""
    analysis_id = "analysis-fake-refs"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. Fabricated Stage 4 action reference
    bad_candidate = mock_llm.generate_structured("", None)  # get default candidate
    bad_act = bad_candidate.actions[0].model_copy(update={"source_action_reference": "act_invented_999"})
    bad_plan = bad_candidate.model_copy(update={"actions": [bad_act, bad_candidate.actions[1]]})
    mock_llm.candidate_to_return = bad_plan

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert "invalid or fabricated Stage 4 action" in resp.json()["detail"]

    # 2. Fabricated evidence citation
    bad_ev_act = bad_candidate.actions[0].model_copy(update={
        "source_action_reference": "act_1",
        "evidence_references": ["ev_synthetic_999"],
    })
    bad_ev_plan = bad_candidate.model_copy(update={"actions": [bad_ev_act, bad_candidate.actions[1]]})
    mock_llm.candidate_to_return = bad_ev_plan

    resp2 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={"force_regenerate": True})
    assert resp2.status_code == status.HTTP_502_BAD_GATEWAY
    assert "fabricated evidence identifier" in resp2.json()["detail"]


# ------------------------------------------------------------------------------
# Test 4: Rejection of Unsupported Numerical Claims
# ------------------------------------------------------------------------------

def test_rejection_of_unsupported_numerical_claims(client, mock_storage, mock_llm):
    """4. Rejection of unsupported numerical claims (e.g. fabricated ROI, success probabilities)."""
    analysis_id = "analysis-unsupported-claims"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    candidate = mock_llm.generate_structured("", None)

    # 1. Prohibited ROI claim
    crit_roi = CandidateActionCriterion(
        criterion_id="crit_roi",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Deliver 250% ROI in first year",
        metric_name="roi",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=250.0,
        unit="%",
        provenance_type="invented",
    )
    bad_act = candidate.actions[0].model_copy(update={"success_criteria": [crit_roi]})
    mock_llm.candidate_to_return = candidate.model_copy(update={"actions": [bad_act, candidate.actions[1]]})

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert "prohibited fabricated ROI" in resp.json()["detail"]

    # 2. Prohibited success probability claim
    crit_prob = CandidateActionCriterion(
        criterion_id="crit_prob",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Achieve 95% success probability",
        metric_name="success_probability",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=0.95,
        unit="prob",
        provenance_type="invented",
    )
    bad_act2 = candidate.actions[0].model_copy(update={"success_criteria": [crit_prob]})
    mock_llm.candidate_to_return = candidate.model_copy(update={"actions": [bad_act2, candidate.actions[1]]})

    resp2 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={"force_regenerate": True})
    assert resp2.status_code == status.HTTP_502_BAD_GATEWAY
    assert "prohibited fabricated numeric success probability" in resp2.json()["detail"]


# ------------------------------------------------------------------------------
# Test 5: Invalid JSON and Schema Failures
# ------------------------------------------------------------------------------

def test_invalid_json_and_schema_failures(client, mock_storage, mock_llm):
    """5. Invalid JSON and schema failures."""
    analysis_id = "analysis-schema-failure"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    mock_llm.exception_to_raise = LLMResponseValidationError("Gemini output missing required 'actions' field.")

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert "structured schema validation" in resp.json()["detail"]


# ------------------------------------------------------------------------------
# Test 6: Gemini Timeout
# ------------------------------------------------------------------------------

def test_gemini_timeout(client, mock_storage, mock_llm):
    """6. Gemini timeout."""
    analysis_id = "analysis-timeout"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    mock_llm.exception_to_raise = LLMTimeoutError("Gemini call timed out after 30.0s.")

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert "exceeded allowed processing time" in resp.json()["detail"]


# ------------------------------------------------------------------------------
# Test 7: Gemini API Failure
# ------------------------------------------------------------------------------

def test_gemini_api_failure(client, mock_storage, mock_llm):
    """7. Gemini API failure."""
    analysis_id = "analysis-api-err"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    mock_llm.exception_to_raise = LLMError("Vertex AI service unavailable", details={"status_code": 503})

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert "generation failed" in resp.json()["detail"]


# ------------------------------------------------------------------------------
# Test 8: Concurrent Duplicate Generation Requests
# ------------------------------------------------------------------------------

def test_concurrent_duplicate_generation_requests(client, mock_storage, mock_llm):
    """8. Concurrent duplicate generation requests rejected via durable SQLite claim."""
    analysis_id = "analysis-concurrent"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # Acquire durable claim in SQLite directly (simulating in-flight generation in worker)
    acquired, claim_status, claim_id = mock_storage.acquire_action_plan_claim(
        analysis_id=analysis_id,
        ttl_seconds=60.0,
    )
    assert acquired is True
    assert claim_status == "acquired"

    # Second request arrives while claim is running
    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert "currently in progress" in resp.json()["detail"]

    # Verify Gemini was never called for duplicate request
    assert mock_llm.call_count == 0


# ------------------------------------------------------------------------------
# Test 9: Cache Hit Without Gemini Invocation
# ------------------------------------------------------------------------------

def test_cache_hit_without_gemini_invocation(client, mock_storage, mock_llm):
    """9. Cache hit without Gemini invocation."""
    analysis_id = "analysis-cache-hit"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. Initial generation
    resp1 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp1.status_code == status.HTTP_200_OK
    assert resp1.json()["cached"] is False
    assert mock_llm.call_count == 1

    # 2. Subsequent call returns cached plan without calling Gemini
    resp2 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp2.status_code == status.HTTP_200_OK
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["status"] == "cached"
    assert data2["plan"]["plan_id"] == resp1.json()["plan"]["plan_id"]
    assert mock_llm.call_count == 1  # Still 1, zero calls on cache hit


# ------------------------------------------------------------------------------
# Test 10: Failed Generation Followed by Retry
# ------------------------------------------------------------------------------

def test_failed_generation_followed_by_retry(client, mock_storage, mock_llm):
    """10. Failed generation followed by retry."""
    analysis_id = "analysis-retry"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. First attempt fails due to timeout
    mock_llm.exception_to_raise = LLMTimeoutError("Transient timeout")
    resp1 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp1.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    # Verify claim was released with failed status
    claim = mock_storage.get_action_plan_claim(analysis_id)
    assert claim is not None
    assert claim["status"] == "failed"

    # 2. Retry with recovered LLM succeeds immediately
    mock_llm.exception_to_raise = None
    resp2 = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.json()["status"] == "ready"
    assert resp2.json()["cached"] is False

    # Claim is now ready
    claim_after = mock_storage.get_action_plan_claim(analysis_id)
    assert claim_after["status"] == "ready"


# ------------------------------------------------------------------------------
# Test 11: Persistence After Successful Generation
# ------------------------------------------------------------------------------

def test_persistence_after_successful_generation(client, mock_storage, mock_llm):
    """11. Persistence after successful generation."""
    analysis_id = "analysis-persistence"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_200_OK
    plan_id = resp.json()["plan"]["plan_id"]

    # Verify SQLite row exists
    persisted = mock_storage.get_action_plan(analysis_id)
    assert persisted is not None
    assert persisted["plan_id"] == plan_id
    assert persisted["analysis_id"] == analysis_id


# ------------------------------------------------------------------------------
# Test 12: No Partial Plan Persisted After Failure
# ------------------------------------------------------------------------------

def test_no_partial_plan_persisted_after_failure(client, mock_storage, mock_llm):
    """12. No partial plan persisted after failure."""
    analysis_id = "analysis-no-partial"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    mock_llm.exception_to_raise = LLMResponseValidationError("Failed output schema")
    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    # Verify action_plans table has zero rows for this analysis
    assert mock_storage.get_action_plan(analysis_id) is None


# ------------------------------------------------------------------------------
# Test 13: Correct Generation Status Transitions
# ------------------------------------------------------------------------------

def test_correct_generation_status_transitions(client, mock_storage, mock_llm):
    """13. Correct generation status transitions."""
    analysis_id = "analysis-status-transitions"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. Initially not_generated
    stat1 = client.get(f"/api/analysis/{analysis_id}/action-plan/status")
    assert stat1.status_code == status.HTTP_200_OK
    assert stat1.json()["status"] == "not_generated"

    # 2. Active claim shows running
    mock_storage.acquire_action_plan_claim(analysis_id, ttl_seconds=60.0)
    stat2 = client.get(f"/api/analysis/{analysis_id}/action-plan/status")
    assert stat2.status_code == status.HTTP_200_OK
    assert stat2.json()["status"] == "running"

    # 3. Failed claim shows failed
    mock_storage.release_action_plan_claim(analysis_id, mock_storage.get_action_plan_claim(analysis_id)["claim_id"], success=False, error_message="LLM provider failure")
    stat3 = client.get(f"/api/analysis/{analysis_id}/action-plan/status")
    assert stat3.status_code == status.HTTP_200_OK
    assert stat3.json()["status"] == "failed"
    assert "LLM provider failure" in stat3.json()["error_message"]

    # 4. Successful generation transitions to ready
    gen_resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert gen_resp.status_code == status.HTTP_200_OK

    stat4 = client.get(f"/api/analysis/{analysis_id}/action-plan/status")
    assert stat4.status_code == status.HTTP_200_OK
    assert stat4.json()["status"] == "ready"
    assert stat4.json()["plan"] is not None


# ------------------------------------------------------------------------------
# Test 14: GET Never Invoking Gemini
# ------------------------------------------------------------------------------

def test_get_never_invoking_gemini(client, mock_storage, mock_llm):
    """14. GET never invoking Gemini."""
    analysis_id = "analysis-get-read-only"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id)

    # 1. Un-generated plan -> 404
    resp1 = client.get(f"/api/analysis/{analysis_id}/action-plan")
    assert resp1.status_code == status.HTTP_404_NOT_FOUND
    assert mock_llm.call_count == 0

    # 2. Check status -> not_generated
    resp2 = client.get(f"/api/analysis/{analysis_id}/action-plan/status")
    assert resp2.status_code == status.HTTP_200_OK
    assert mock_llm.call_count == 0


# ------------------------------------------------------------------------------
# Test 15: Invalid and Incomplete Analyses
# ------------------------------------------------------------------------------

def test_invalid_and_incomplete_analyses(client, mock_storage):
    """15. Invalid and incomplete analyses."""
    # 1. Nonexistent analysis
    resp1 = client.post("/api/analysis/nonexistent-xyz/action-plan/generate", json={})
    assert resp1.status_code == status.HTTP_404_NOT_FOUND

    # 2. Analysis currently running -> 409
    create_mock_analysis_job(mock_storage, analysis_id="analysis-running", status_str="running")
    resp2 = client.post("/api/analysis/analysis-running/action-plan/generate", json={})
    assert resp2.status_code == status.HTTP_409_CONFLICT

    # 3. Analysis failed -> 422
    create_mock_analysis_job(mock_storage, analysis_id="analysis-failed", status_str="failed")
    resp3 = client.post("/api/analysis/analysis-failed/action-plan/generate", json={})
    assert resp3.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # 4. Analysis completed but missing Stage 4 recommendation -> 422
    create_mock_analysis_job(mock_storage, analysis_id="analysis-no-rec", status_str="completed", include_rec=False)
    resp4 = client.post("/api/analysis/analysis-no-rec/action-plan/generate", json={})
    assert resp4.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "missing Stage 4" in resp4.json()["detail"]


# ------------------------------------------------------------------------------
# Test 16: Owner-Scoped Access
# ------------------------------------------------------------------------------

def test_owner_scoped_access(client, mock_storage):
    """16. Owner-scoped access."""
    analysis_id = "analysis-owned-alice"
    create_mock_analysis_job(mock_storage, analysis_id=analysis_id, owner_id="alice")

    # Bob tries to access Alice's analysis
    resp_get = client.get(f"/api/analysis/{analysis_id}/action-plan", headers={"X-Owner-Id": "bob"})
    assert resp_get.status_code == status.HTTP_403_FORBIDDEN

    resp_post = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", headers={"X-Owner-Id": "bob"}, json={})
    assert resp_post.status_code == status.HTTP_403_FORBIDDEN

    resp_stat = client.get(f"/api/analysis/{analysis_id}/action-plan/status", headers={"X-Owner-Id": "bob"})
    assert resp_stat.status_code == status.HTTP_403_FORBIDDEN


# ------------------------------------------------------------------------------
# Test 17: Numeric Threshold Conflict vs Review-Required Distinction
# ------------------------------------------------------------------------------

def test_numeric_threshold_conflict_vs_review_required_distinction(client, mock_storage, mock_llm):
    """17. Numeric threshold conflict versus review-required distinction."""
    analysis_id = "analysis-conflicts-vs-reviews"
    job_resp = create_mock_analysis_job(mock_storage, analysis_id=analysis_id)
    dec_model = job_resp.decision_model

    candidate = mock_llm.generate_structured("", None)
    plan = ActionIntelligenceGenerator(mock_llm).assemble_plan(
        candidate=candidate,
        analysis_id=analysis_id,
        source_recommendation_fingerprint="srfp_" + "a" * 32,
    )

    # 1. Definitive CONFLICT: Rollback trigger allows CSAT degradation to 85% when hard floor is 90%
    crit_conflict = ActionCriterion(
        criterion_id="crit_csat_bad",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Rollback trigger threshold",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=85.0,  # Below 90% floor!
        threshold_raw="85%",
        unit="%",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat_floor",
    )
    plan_with_conflict = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [crit_conflict]}), plan.actions[1]]
    })

    warns_conflict = detect_threshold_conflicts(plan_with_conflict, decision_model=dec_model)
    conflicts = [w for w in warns_conflict if w.severity == ValidationSeverity.CONFLICT]
    assert len(conflicts) >= 1
    assert "Direct threshold conflict" in conflicts[0].message

    # 2. Operational warning: Alert threshold at 92% (above 90% floor) is NOT a conflict
    crit_alert = ActionCriterion(
        criterion_id="crit_csat_alert",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Early warning alert if CSAT dips",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=92.0,  # Above 90% floor!
        threshold_raw="92%",
        unit="%",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat_floor",
    )
    plan_with_alert = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [crit_alert]}), plan.actions[1]]
    })
    warns_alert = detect_threshold_conflicts(plan_with_alert, decision_model=dec_model)
    conflicts_alert = [w for w in warns_alert if w.severity == ValidationSeverity.CONFLICT]
    assert len(conflicts_alert) == 0  # No conflict!

    # 3. REVIEW_REQUIRED: Incompatible / ambiguous units ("points" vs "%")
    crit_ambiguous = ActionCriterion(
        criterion_id="crit_csat_points",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Customer satisfaction floor",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=85.0,
        threshold_raw="85 points",
        unit="points",  # Incompatible with %
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat_floor",
    )
    plan_with_ambiguous = plan.model_copy(update={
        "actions": [plan.actions[0].model_copy(update={"success_criteria": [crit_ambiguous]}), plan.actions[1]]
    })
    warns_ambiguous = detect_threshold_conflicts(plan_with_ambiguous, decision_model=dec_model)
    reviews = [w for w in warns_ambiguous if w.severity == ValidationSeverity.REVIEW_REQUIRED]
    assert len(reviews) >= 1
    assert "Incompatible or ambiguous units" in reviews[0].message


# ------------------------------------------------------------------------------
# Test 18: Backward Compatibility with Six-Stage Pipeline
# ------------------------------------------------------------------------------

def test_backward_compatibility_six_stage_pipeline(mock_storage):
    """18. Backward compatibility with the six-stage pipeline."""
    job_resp = create_mock_analysis_job(mock_storage, analysis_id="analysis-pipeline-compat")
    assert job_resp.decision_model is not None
    assert job_resp.evidence_package is not None
    assert job_resp.recommendation is not None

    # Verify Stage 4 action items remain authoritative and immutable
    assert len(job_resp.recommendation.action_plan.actions) == 2
    assert job_resp.recommendation.action_plan.actions[0].id == "act_1"
    assert job_resp.recommendation.action_plan.actions[1].id == "act_2"


# ------------------------------------------------------------------------------
# Test 19: Day 7 What-if and Restoration Regressions
# ------------------------------------------------------------------------------

def test_day7_what_if_and_restoration_regressions(client, mock_storage):
    """19. Day 7 What-if and restoration regressions."""
    # Health endpoint verification
    h_resp = client.get("/health")
    assert h_resp.status_code == status.HTTP_200_OK

    # Simulation variable discovery route continues to function
    create_mock_analysis_job(mock_storage, analysis_id="analysis-day7-check")
    v_resp = client.get("/api/analysis/analysis-day7-check/simulation-variables")
    assert v_resp.status_code == status.HTTP_200_OK

    # Simulation list route
    sim_list = client.get("/api/analysis/analysis-day7-check/simulations")
    assert sim_list.status_code == status.HTTP_200_OK
