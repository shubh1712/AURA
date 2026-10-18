"""AURA Day 8E: Real-Schema Integration Regression Tests.

Verifies that Action Intelligence prompt builder, generator, and service work
seamlessly with real six-stage Pydantic models and artifacts (not MagicMocks):
- DecisionModel (Stage 1)
- EvidencePackage (Stage 2)
- ReasoningBoard (Stage 3) with real ReasoningDisagreement and BoardSynthesis
- DecisionRecommendation (Stage 4) with real Stage4ActionItem and ActionPlan
- ScenarioSet (Stage 5) with real FutureScenario objects
- ResilienceReport (Stage 6) with real ResilienceSubScore and ResilienceRating

Verifies:
1. Complete prompt construction succeeds without AttributeError.
2. ReasoningBoard disagreements are rendered accurately from .disagreements.
3. ResilienceReport rating (.rating) and critical vulnerabilities (.critical_vulnerabilities) are rendered accurately.
4. Complete generation path: AnalysisResponse -> Service -> PromptBuilder -> Generator -> Validator -> SQLite -> API.
5. Failed generation followed by successful retry.
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
    ActionPriority,
    CandidateActionCriterion,
    CandidateActionItem,
    CandidateActionPlan,
    CandidateDecisionGate,
    ComparisonOperator,
    CriterionType,
    IntelligentActionPlan,
)
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
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
    EvidencePackage,
    Source,
    SourceType,
)
from app.schemas.job import AnalysisJobCreateRequest
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
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
)
from app.services.action_intelligence.prompt_builder import (
    build_action_intelligence_system_instruction,
    build_action_intelligence_user_prompt,
)
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.analysis_service import AnalysisService, get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import LLMConfig, LLMTimeoutError


class MockGeminiClient:
    """Mock LLM client simulating Gemini structured output generation."""

    def __init__(self) -> None:
        self.model_name = "gemini-3.8-flash"
        self.call_count = 0
        self.prompts_received: List[str] = []
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
        self.prompts_received.append(prompt)

        if self.exception_to_raise:
            raise self.exception_to_raise

        if self.candidate_to_return is not None:
            return self.candidate_to_return

        return CandidateActionPlan(
            strategy_summary="Operational plan grounded in Stage 4 recommendation.",
            actions=[
                CandidateActionItem(
                    action_id="act_saas_pilot",
                    source_action_reference="act_saas_pilot",
                    title="Pilot Execution Setup",
                    description="Configure isolated support routing for 1,000 pilot customers.",
                    priority=ActionPriority.HIGH,
                    sequence=1,
                    owner_role="VP Customer Support",
                    dependencies=[],
                    timing="Weeks 1-4",
                    prerequisites=["Approval from Security and Support"],
                    success_criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_pilot_size",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Pilot size bounded to 1,000 customers",
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
                    risk_mitigations=["Manual fallback queue"],
                    contingency_or_rollback="Reroute traffic to human agents",
                    evidence_references=["evi_saas_01"],
                    rationale="Safe phased trial",
                    confidence_label="high",
                    confidence_rationale="Grounded in evidence",
                    missing_information=[],
                )
            ],
            decision_gates=[
                CandidateDecisionGate(
                    gate_id="gate_pilot_review",
                    title="Mid-Pilot Quality Review",
                    checkpoint="Week 4",
                    criteria=[
                        CandidateActionCriterion(
                            criterion_id="crit_gate_csat",
                            criterion_type=CriterionType.HARD_CONSTRAINT,
                            description="Verify CSAT remains at or above 90%",
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
                    related_action_ids=["act_saas_pilot"],
                    failure_response="Initiate immediate fallback to human support.",
                    source_references=["cnstr_csat_floor"],
                    unresolved_conflicts=[],
                )
            ],
            unresolved_questions=[],
            limitations=[],
        )


def build_saas_six_stage_analysis_response(analysis_id: str = "analysis-saas-real-01") -> AnalysisResponse:
    """Builds an authentic, strictly typed six-stage AnalysisResponse."""
    dec_model = DecisionModel(
        id="dec_saas_01",
        decision=Decision(
            raw_prompt="Should we deploy an automated AI assistant for customer support?",
            summary="Deploy AI assistant for tier 1 customer support.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Cross-functional customer operations impact.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_efficiency",
                description="Reduce first-response time",
                is_primary=True,
                target_metric="< 2 minutes",
            )
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
                affected_variable_ids=["var_pilot_size"],
            )
        ],
        key_questions=["Will tier-1 ticket CSAT stay above 90% during pilot?"],
    )

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

    perspectives = [
        ReasoningPerspective(
            id="persp_growth",
            perspective_type=PerspectiveType.GROWTH,
            summary="Enables scaling support without proportional headcount expansion.",
            arguments=[
                ReasoningArgument(
                    id="arg_g1",
                    claim="Automation enables 3x support volume capacity.",
                    direction=ArgumentDirection.FAVORABLE,
                    basis=ReasoningBasis.EVIDENCE,
                    reasoning="Empirical trial evidence indicates high volume capacity.",
                    evidence_item_ids=["evi_saas_01"],
                )
            ],
            opportunities=["Instant response for global users"],
            concerns=["Brand erosion if accuracy is substandard"],
        ),
        ReasoningPerspective(
            id="persp_finance",
            perspective_type=PerspectiveType.FINANCE,
            summary="Reduces cost-per-ticket while capping pilot expenditures under budget.",
            arguments=[
                ReasoningArgument(
                    id="arg_f1",
                    claim="Pilot cloud run-rate remains well within the $20,000 monthly cap.",
                    direction=ArgumentDirection.FAVORABLE,
                    basis=ReasoningBasis.EVIDENCE,
                    reasoning="Projected pilot compute cost is $15,000 per month.",
                    evidence_item_ids=["evi_saas_01"],
                )
            ],
            opportunities=["Deflection savings"],
            concerns=["Uncapped token consumption overruns"],
        ),
        ReasoningPerspective(
            id="persp_customer",
            perspective_type=PerspectiveType.CUSTOMER,
            summary="Prioritizes CSAT preservation; requires immediate human fallback if dissatisfaction arises.",
            arguments=[
                ReasoningArgument(
                    id="arg_c1",
                    claim="Customer trust requires maintaining 90% minimum CSAT.",
                    direction=ArgumentDirection.FAVORABLE,
                    basis=ReasoningBasis.EVIDENCE,
                    reasoning="Telemetry shows satisfaction dips quickly if wrong answers are given.",
                    evidence_item_ids=["evi_saas_01"],
                )
            ],
            opportunities=["Faster resolution"],
            concerns=["Hallucinated answers frustrating VIP customers"],
        ),
        ReasoningPerspective(
            id="persp_risk",
            perspective_type=PerspectiveType.RISK,
            summary="Recommends phased rollout with strict rollback triggers to contain operational blast radius.",
            arguments=[
                ReasoningArgument(
                    id="arg_r1",
                    claim="A 1,000-customer pilot limits operational exposure.",
                    direction=ArgumentDirection.FAVORABLE,
                    basis=ReasoningBasis.EVIDENCE,
                    reasoning="Controlled cohort ensures issue containment.",
                    evidence_item_ids=["evi_saas_01"],
                )
            ],
            opportunities=["Defensive operational posture"],
            concerns=["Failure of fallback routing gateway"],
        ),
    ]

    disagreements = [
        ReasoningDisagreement(
            id="dis_speed_vs_safety",
            topic="Balancing aggressive deflection rate with customer satisfaction safety margins",
            perspective_ids=["persp_growth", "persp_customer"],
            positions={
                "persp_growth": "Maximize deflection to realize cost efficiency early.",
                "persp_customer": "Enforce strict confidence gating and human routing to protect CSAT.",
            },
            evidence_item_ids=["evi_saas_01"],
            nature=DisagreementNature.INTERPRETATION,
        )
    ]

    synthesis = BoardSynthesis(
        summary="The board converges on a controlled pilot rollout, reconciling growth goals with rigorous CSAT protections.",
        areas_of_agreement=[
            "Phased 1,000-customer pilot minimizes operational risk",
            "Human escalation path is non-negotiable",
        ],
        disagreement_ids=["dis_speed_vs_safety"],
    )

    reasoning_board = ReasoningBoard(
        id="rb_01",
        decision_model_id="dec_saas_01",
        evidence_package_id="ev_pkg_01",
        perspectives=perspectives,
        disagreements=disagreements,
        synthesis=synthesis,
    )

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

    recommendation = DecisionRecommendation(
        id="rec_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_saas_01",
        evidence_package_id="ev_pkg_01",
        reasoning_board_id="rb_01",
        decision_status=DecisionStatus.PILOT,
        recommended_action="Proceed with 3-month controlled pilot of AI Support Assistant across 1,000 customers.",
        executive_rationale="Balances operational upside with strict customer satisfaction guardrails.",
        action_plan=Stage4ActionPlan(
            summary="Controlled pilot rollout roadmap.",
            actions=[action_1],
        ),
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=EvidenceStrength.STRONG,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
        ),
    )

    scenarios = ScenarioSet(
        id="scenset_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_saas_01",
        summary="Three stress-test scenarios for AI assistant pilot rollout.",
        scenarios=[
            FutureScenario(
                id="scen_1111222233334444",
                scenario_type=ScenarioType.OPTIMISTIC,
                probability=0.30,
                name="Rapid Adoption & High Deflection",
                narrative="Assistant handles 75% of tier-1 tickets with 93% CSAT and low fallback rate.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_1",
                        title="Early Deflection Surge",
                        description="Customers embrace assistant in week 2.",
                        timeframe="Weeks 2-4",
                    )
                ],
                timeline=[
                    ScenarioMilestone(
                        id="ms_1",
                        title="Month 1 Review",
                        description="Review CSAT telemetry.",
                        time_horizon="immediate",
                        expected_outcome="CSAT >= 92%",
                    )
                ],
            ),
            FutureScenario(
                id="scen_2222333344445555",
                scenario_type=ScenarioType.BASE_CASE,
                probability=0.50,
                name="Steady Pilot Performance",
                narrative="Assistant handles 65% of tickets with 91% CSAT within expected budget limits.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_2",
                        title="Baseline Stabilization",
                        description="Support volume normalizes under pilot load.",
                        timeframe="Weeks 3-6",
                    )
                ],
                timeline=[
                    ScenarioMilestone(
                        id="ms_2",
                        title="Mid-Pilot Checkpoint",
                        description="Evaluate operational metrics.",
                        time_horizon="near_term",
                        expected_outcome="CSAT >= 90%",
                    )
                ],
            ),
            FutureScenario(
                id="scen_3333444455556666",
                scenario_type=ScenarioType.PESSIMISTIC,
                probability=0.20,
                name="Elevated Ambiguity & Fallback Pressure",
                narrative="High volume of complex queries forces 50% fallback rate, pressuring human staff.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_3",
                        title="Fallback Spike",
                        description="Spike in edge-case queries triggers manual queue overflow.",
                        timeframe="Week 3",
                    )
                ],
                timeline=[
                    ScenarioMilestone(
                        id="ms_3",
                        title="Fallback Gate Audit",
                        description="Determine whether to adjust confidence threshold.",
                        time_horizon="near_term",
                        expected_outcome="Rollback triggered if CSAT < 90%",
                    )
                ],
            ),
        ],
    )

    resilience = ResilienceReport(
        id="res_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_saas_01",
        scenario_set_id="scenset_0123456789abcdef0123456789abcdef",
        recommendation_id="rec_0123456789abcdef0123456789abcdef",
        overall_score=82.5,
        rating=ResilienceRating.HIGH,
        sub_scores=[
            ResilienceSubScore(
                category="constraint_boundary_tolerance",
                score=21.0,
                rationale="Pilot size and budget caps strictly enforce boundaries.",
            ),
            ResilienceSubScore(
                category="pessimistic_scenario_survivability",
                score=20.0,
                rationale="Human fallback prevents catastrophic customer churn.",
            ),
            ResilienceSubScore(
                category="contingency_and_fallback_coverage",
                score=21.5,
                rationale="Comprehensive rollback procedures in place.",
            ),
            ResilienceSubScore(
                category="information_robustness",
                score=20.0,
                rationale="Empirical pilot trial provides reliable grounding.",
            ),
        ],
        critical_vulnerabilities=[
            "Fallback routing gateway represents single point of failure under surge."
        ],
        stress_test_passed=True,
    )

    return AnalysisResponse(
        analysis_id=analysis_id,
        status="completed",
        question="Should we deploy an automated AI assistant for customer support?",
        decision_model=dec_model,
        evidence_package=evidence_package,
        reasoning_board=reasoning_board,
        recommendation=recommendation,
        scenarios=scenarios,
        resilience=resilience,
    )


# ------------------------------------------------------------------------------
# 1. Prompt Builder Real-Schema Regression Tests
# ------------------------------------------------------------------------------

def test_prompt_builder_with_real_six_stage_analysis_response():
    """Verifies that prompt builder succeeds with actual six-stage AnalysisResponse models."""
    analysis_resp = build_saas_six_stage_analysis_response()

    # Pass the real Pydantic objects
    prompt = build_action_intelligence_user_prompt(
        decision_model=analysis_resp.decision_model,
        recommendation=analysis_resp.recommendation,
        evidence_package=analysis_resp.evidence_package,
        reasoning_board=analysis_resp.reasoning_board,
        scenario_set=analysis_resp.scenarios,
        resilience_report=analysis_resp.resilience,
    )

    assert isinstance(prompt, str)
    assert len(prompt) > 200

    # 1. Verify Stage 1 Framing
    assert "BASELINE DECISION INQUIRY & CONSTRAINTS" in prompt
    assert "cnstr_csat_floor" in prompt
    assert "cnstr_budget" in prompt

    # 2. Verify Stage 4 Authoritative Actions
    assert "AUTHORITATIVE STAGE 4 DECISION RECOMMENDATION" in prompt
    assert "act_saas_pilot" in prompt
    assert "VP Customer Support" in prompt

    # 3. Verify Stage 2 Evidence
    assert "EMPIRICAL EVIDENCE PACKAGE" in prompt
    assert "evi_saas_01" in prompt
    assert "Enterprise Support Automation Trial" in prompt

    # 4. Verify Stage 3 Reasoning Board (with fix for key_disagreements crash)
    assert "MULTI-PERSPECTIVE BOARDROOM REASONING" in prompt
    assert "Boardroom Collective Synthesis" in prompt
    assert "Perspective [growth]" in prompt
    assert "Perspective [finance]" in prompt
    assert "Perspective [customer]" in prompt
    assert "Perspective [risk]" in prompt
    assert "Key Boardroom Disagreements & Tensions:" in prompt
    assert "Balancing aggressive deflection rate with customer satisfaction safety margins" in prompt
    assert "[interpretation]" in prompt

    # 5. Verify Stage 5 Scenarios
    assert "SCENARIO STRESS TEST PROJECTIONS" in prompt
    assert "Rapid Adoption & High Deflection" in prompt
    assert "Steady Pilot Performance" in prompt
    assert "Elevated Ambiguity & Fallback Pressure" in prompt

    # 6. Verify Stage 6 Resilience (with fix for resilience_rating and key_vulnerabilities)
    assert "COMPOSITE RESILIENCE RATING" in prompt
    assert "Overall Resilience Score: 82.50 (high)" in prompt
    assert "Critical Vulnerabilities: Fallback routing gateway represents single point of failure" in prompt


def test_prompt_builder_from_analysis_service_e2e_run():
    """Runs the real offline 6-stage pipeline and passes its output to the prompt builder."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we migrate payments infrastructure to a multi-region deployment?",
        context={"compliance": "PCI-DSS Level 1"},
        constraints=["Budget ceiling $200k", "CSAT floor >= 95%"],
    )
    result = service.analyze(req)

    assert result.status == "completed"
    assert result.decision_model is not None
    assert result.recommendation is not None
    assert result.evidence_package is not None
    assert result.reasoning_board is not None
    assert result.scenarios is not None
    assert result.resilience is not None

    # Verify prompt builder handles the live pipeline artifacts without any AttributeError
    prompt = build_action_intelligence_user_prompt(
        decision_model=result.decision_model,
        recommendation=result.recommendation,
        evidence_package=result.evidence_package,
        reasoning_board=result.reasoning_board,
        scenario_set=result.scenarios,
        resilience_report=result.resilience,
    )

    assert isinstance(prompt, str)
    assert "=== 1. BASELINE DECISION INQUIRY & CONSTRAINTS ===" in prompt
    assert "=== 2. AUTHORITATIVE STAGE 4 DECISION RECOMMENDATION ===" in prompt
    assert "=== 4. MULTI-PERSPECTIVE BOARDROOM REASONING ===" in prompt
    assert "=== 6. COMPOSITE RESILIENCE RATING ===" in prompt


# ------------------------------------------------------------------------------
# 2. Complete Generation Path Integration Tests
# ------------------------------------------------------------------------------

def test_complete_generation_path_with_real_six_stage_analysis():
    """Tests the full generation lifecycle with mocked Gemini and real six-stage response in SQLite."""
    storage = SQLiteJobStorage(db_path=":memory:")
    job_mgr = AnalysisJobManager(storage=storage)
    mock_llm = MockGeminiClient()

    app.dependency_overrides[get_job_manager] = lambda: job_mgr
    app.dependency_overrides[get_llm_client] = lambda: mock_llm

    try:
        client = TestClient(app)
        analysis_id = "analysis-saas-real-01"

        # 1. Create and complete the job in SQLite
        create_req = AnalysisJobCreateRequest(
            question="Evaluate pilot rollout of AI customer support assistant.",
            owner_id="owner_shubh",
        )
        job = storage.create_job(create_req, job_id=analysis_id)
        real_response = build_saas_six_stage_analysis_response(analysis_id=analysis_id)
        storage.complete_job(job.job_id, response=real_response)

        # 2. Check initial action plan status (not_generated)
        status_res = client.get(
            f"/api/analysis/{analysis_id}/action-plan/status",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert status_res.status_code == status.HTTP_200_OK
        assert status_res.json()["status"] == "not_generated"

        # 3. Trigger generation via POST
        gen_res = client.post(
            f"/api/analysis/{analysis_id}/action-plan/generate",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert gen_res.status_code == status.HTTP_200_OK
        gen_data = gen_res.json()
        assert gen_data["status"] == "ready"
        assert gen_data["cached"] is False
        assert "plan" in gen_data
        plan = gen_data["plan"]
        assert plan["analysis_id"] == analysis_id
        assert len(plan["actions"]) == 1
        assert plan["actions"][0]["action_id"] == "act_saas_pilot"
        assert len(plan["decision_gates"]) == 1

        # 4. Verify that LLM was invoked exactly once with prompt containing real artifacts
        assert mock_llm.call_count == 1
        prompt = mock_llm.prompts_received[0]
        assert "Key Boardroom Disagreements & Tensions:" in prompt
        assert "Overall Resilience Score: 82.50 (high)" in prompt

        # 5. Subsequent call returns cached plan without calling Gemini
        gen_res_cached = client.post(
            f"/api/analysis/{analysis_id}/action-plan/generate",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert gen_res_cached.status_code == status.HTTP_200_OK
        assert gen_res_cached.json()["cached"] is True
        assert mock_llm.call_count == 1  # No additional call

        # 6. GET /action-plan returns the persisted plan envelope
        get_res = client.get(
            f"/api/analysis/{analysis_id}/action-plan",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert get_res.status_code == status.HTTP_200_OK
        get_body = get_res.json()
        assert get_body["status"] == "ready"
        assert get_body["plan"]["plan_id"] == plan["plan_id"]

    finally:
        app.dependency_overrides.clear()


def test_generation_failure_followed_by_successful_retry():
    """Verifies that an LLM failure is handled cleanly and a subsequent retry succeeds."""
    storage = SQLiteJobStorage(db_path=":memory:")
    job_mgr = AnalysisJobManager(storage=storage)
    mock_llm = MockGeminiClient()

    app.dependency_overrides[get_job_manager] = lambda: job_mgr
    app.dependency_overrides[get_llm_client] = lambda: mock_llm

    try:
        client = TestClient(app)
        analysis_id = "analysis-retry-test-01"

        create_req = AnalysisJobCreateRequest(
            question="Evaluate pilot rollout of AI customer support assistant.",
            owner_id="owner_shubh",
        )
        job = storage.create_job(create_req, job_id=analysis_id)
        real_response = build_saas_six_stage_analysis_response(analysis_id=analysis_id)
        storage.complete_job(job.job_id, response=real_response)

        # 1. Simulate Gemini timeout failure
        mock_llm.exception_to_raise = LLMTimeoutError("Gemini call timed out after 30s")

        res_fail = client.post(
            f"/api/analysis/{analysis_id}/action-plan/generate",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert res_fail.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "exceeded allowed processing time" in res_fail.json()["detail"]

        # Check status after failure: claim cleared or status failed
        status_res = client.get(
            f"/api/analysis/{analysis_id}/action-plan/status",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert status_res.status_code == status.HTTP_200_OK
        assert status_res.json()["status"] in ("failed", "not_generated")

        # 2. Reset mock LLM to succeed
        mock_llm.exception_to_raise = None

        res_retry = client.post(
            f"/api/analysis/{analysis_id}/action-plan/generate",
            headers={"X-Owner-Id": "owner_shubh"},
        )
        assert res_retry.status_code == status.HTTP_200_OK
        retry_data = res_retry.json()
        assert retry_data["status"] == "ready"
        assert retry_data["cached"] is False
        assert retry_data["plan"]["analysis_id"] == analysis_id

    finally:
        app.dependency_overrides.clear()


def test_prompt_builder_disagreements_and_synthesis_formatting():
    """Verifies that disagreements and synthesis are formatted accurately."""
    resp = build_saas_six_stage_analysis_response()
    rb = resp.reasoning_board

    prompt = build_action_intelligence_user_prompt(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        reasoning_board=rb,
    )

    # Disagreements formatting
    assert "Key Boardroom Disagreements & Tensions:" in prompt
    assert "* Tension [interpretation]: Balancing aggressive deflection rate with customer satisfaction safety margins" in prompt
    assert "- persp_growth: Maximize deflection to realize cost efficiency early." in prompt
    assert "- persp_customer: Enforce strict confidence gating and human routing to protect CSAT." in prompt

    # Synthesis formatting
    assert "Boardroom Collective Synthesis: The board converges on a controlled pilot rollout" in prompt
    assert "Key Convergence Areas: Phased 1,000-customer pilot minimizes operational risk" in prompt


def test_prompt_builder_resilience_rating_and_vulnerabilities():
    """Verifies that ResilienceReport rating (.rating) and critical vulnerabilities are formatted."""
    resp = build_saas_six_stage_analysis_response()
    res = resp.resilience

    prompt = build_action_intelligence_user_prompt(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        resilience_report=res,
    )

    assert "Overall Resilience Score: 82.50 (high)" in prompt
    assert "Critical Vulnerabilities: Fallback routing gateway represents single point of failure under surge." in prompt


def test_prompt_builder_with_optional_artifacts_none():
    """Verifies that prompt builder works cleanly when optional stages 2, 3, 5, 6 are None."""
    resp = build_saas_six_stage_analysis_response()

    prompt = build_action_intelligence_user_prompt(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        evidence_package=None,
        reasoning_board=None,
        scenario_set=None,
        resilience_report=None,
    )

    assert "=== 1. BASELINE DECISION INQUIRY & CONSTRAINTS ===" in prompt
    assert "=== 2. AUTHORITATIVE STAGE 4 DECISION RECOMMENDATION ===" in prompt
    assert "=== 3. EMPIRICAL EVIDENCE PACKAGE" not in prompt
    assert "=== 4. MULTI-PERSPECTIVE BOARDROOM REASONING ===" not in prompt
    assert "=== 5. SCENARIO STRESS TEST PROJECTIONS ===" not in prompt
    assert "=== 6. COMPOSITE RESILIENCE RATING ===" not in prompt
    assert "=== GENERATION DIRECTIVE ===" in prompt

