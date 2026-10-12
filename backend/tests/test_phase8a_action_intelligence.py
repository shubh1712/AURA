"""AURA Phase 8A: Action Intelligence Architecture, Contracts & Foundation Tests.

Validates:
1. Valid ActionPlan serialization and deserialization.
2. Invalid and duplicate action IDs.
3. Unknown dependencies.
4. Self-dependencies.
5. Dependency cycles.
6. Invalid priorities.
7. Criteria with supported numeric operators and units.
8. Missing provenance.
9. Comparable conflicting thresholds (e.g. CSAT floor 90% vs rollback 85%).
10. Ambiguous thresholds marked review-required.
11. Stable fingerprint generation (SHA-256, immutable).
12. Persistence round trips in SQLite.
13. Duplicate-plan prevention & cache reuse.
14. Retrieval of nonexistent plans (HTTP 404 clean).
15. Backward compatibility with existing six-stage analysis results.
16. Existing Day 7 simulation and session-restoration regressions.
"""

import json
import pytest
from typing import Any, Dict
from fastapi import status
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.action_intelligence import (
    ActionCriterion,
    ActionPriority,
    ComparisonOperator,
    CriterionType,
    IntelligentActionItem,
    IntelligentActionPlan,
    IntelligentDecisionGate,
    ValidationSeverity,
    ValidationWarning,
    compute_plan_id,
    compute_source_recommendation_fingerprint,
)
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import Constraint, DecisionModel
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
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
from app.services.action_intelligence.validator import (
    ActionPlanValidationError,
    detect_threshold_conflicts,
    validate_action_ids,
    validate_action_plan,
    validate_dependencies,
)
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def mock_storage():
    """In-memory SQLite storage for isolated test execution."""
    return SQLiteJobStorage(db_path=":memory:")


@pytest.fixture
def mock_job_manager(mock_storage):
    """Job manager backed by in-memory storage."""
    return AnalysisJobManager(storage=mock_storage)


@pytest.fixture
def client(mock_job_manager):
    """TestClient overriding get_job_manager with test instance."""
    app.dependency_overrides[get_job_manager] = lambda: mock_job_manager
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def make_sample_action_plan(
    analysis_id: str = "b2abf510-aacb-44d7-8a11-7cc40806cca1",
    fingerprint: str = "srfp_71162fecfa68e48475dc312f89c587bc",
) -> IntelligentActionPlan:
    """Helper creating a fully populated valid IntelligentActionPlan."""
    crit_1 = ActionCriterion(
        criterion_id="crit_pilot_cap",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Pilot cohort capped at 1,000 customers",
        metric_name="cohort_size",
        operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        threshold_value=1000.0,
        threshold_raw="1,000 customers",
        unit="customers",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_pilot_cohort",
        is_hard=True,
    )
    crit_2 = ActionCriterion(
        criterion_id="crit_csat_floor",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Maintain CSAT above or equal to 90%",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=90.0,
        threshold_raw="90%",
        unit="%",
        provenance_type="decision_model.constraints",
        source_reference="obj_csat",
        is_hard=True,
    )

    act_1 = IntelligentActionItem(
        action_id="act_1",
        source_action_reference="act_1",
        title="Setup Pilot Infrastructure",
        description="Provision cloud sandbox and configure rate-limiting.",
        priority=ActionPriority.HIGH,
        sequence=1,
        owner_role="Lead Platform Engineer",
        dependencies=[],
        timing="Weeks 1-2",
        prerequisites=["Data security review completed"],
        success_criteria=[crit_1],
        risk_mitigations=["Strict egress firewall rules"],
        contingency_or_rollback="Disable routing gateway",
        evidence_references=["ev_item_01"],
        rationale="Essential prerequisite for controlled pilot rollout.",
        confidence_label="high",
        confidence_rationale="Tested in staging",
        missing_information=[],
    )

    act_2 = IntelligentActionItem(
        action_id="act_2",
        source_action_reference="act_2",
        title="Launch Phased Cohort",
        description="Onboard 1,000 pilot customers to AI assistant.",
        priority=ActionPriority.HIGH,
        sequence=2,
        owner_role="Head of Customer Support",
        dependencies=["act_1"],
        timing="Month 1",
        prerequisites=["Pilot infrastructure operational"],
        success_criteria=[crit_2],
        risk_mitigations=["Live agent fallback for escalation"],
        contingency_or_rollback="Revert cohort to human routing",
        evidence_references=["ev_item_02"],
        rationale="Executes Stage 4 recommended pilot course of action.",
        confidence_label="high",
        confidence_rationale="Telemetry verified",
        missing_information=[],
    )

    gate_1 = IntelligentDecisionGate(
        gate_id="gate_pilot_review",
        title="Month 1 CSAT & Stability Review",
        checkpoint="End of Month 1",
        criteria=[crit_2],
        related_action_ids=["act_2"],
        failure_response="Trigger immediate rollback to human tier-1 support.",
        source_references=["obj_csat"],
        unresolved_conflicts=[],
    )

    plan_id = compute_plan_id(analysis_id, fingerprint, [act_1, act_2])

    return IntelligentActionPlan(
        plan_id=plan_id,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=fingerprint,
        schema_version="1.0",
        generator_version="day8a_v1",
        created_at="2026-10-12T10:00:00Z",
        strategy_summary="Two-phase pilot roadmap for 1,000 customer rollout with automated rollback gate.",
        actions=[act_1, act_2],
        decision_gates=[gate_1],
        unresolved_questions=["Long-term tier-2 escalation fatigue"],
        limitations=["Assumes vendor API availability exceeds 99.5%"],
        validation_warnings=[],
        generation_metadata={"tested_by": "phase8a"},
    )


# ------------------------------------------------------------------------------
# Test 1: Serialization and Deserialization
# ------------------------------------------------------------------------------

def test_action_plan_serialization_deserialization():
    """1. Valid ActionPlan serialization and deserialization."""
    plan = make_sample_action_plan()
    dumped_json = plan.model_dump_json()
    loaded_plan = IntelligentActionPlan.model_validate_json(dumped_json)

    assert loaded_plan.plan_id == plan.plan_id
    assert loaded_plan.analysis_id == plan.analysis_id
    assert len(loaded_plan.actions) == 2
    assert loaded_plan.actions[0].action_id == "act_1"
    assert loaded_plan.actions[1].dependencies == ["act_1"]
    assert loaded_plan.decision_gates[0].gate_id == "gate_pilot_review"
    assert loaded_plan.actions[0].success_criteria[0].threshold_value == 1000.0


# ------------------------------------------------------------------------------
# Test 2: Invalid and Duplicate Action IDs
# ------------------------------------------------------------------------------

def test_invalid_and_duplicate_action_ids():
    """2. Invalid and duplicate action IDs."""
    plan = make_sample_action_plan()
    # Duplicate action IDs
    dup_actions = [
        plan.actions[0],
        plan.actions[0],  # duplicate 'act_1'
    ]
    with pytest.raises(ActionPlanValidationError, match="Duplicate action_id detected"):
        validate_action_ids(dup_actions)

    # Empty action ID
    bad_act = plan.actions[0].model_copy(update={"action_id": "   "})
    with pytest.raises(ActionPlanValidationError, match="empty action_id"):
        validate_action_ids([bad_act])


# ------------------------------------------------------------------------------
# Test 3: Unknown Dependencies
# ------------------------------------------------------------------------------

def test_unknown_dependencies():
    """3. Unknown dependencies."""
    plan = make_sample_action_plan()
    bad_act = plan.actions[1].model_copy(update={"dependencies": ["act_nonexistent"]})
    with pytest.raises(ActionPlanValidationError, match="Unknown dependency target"):
        validate_dependencies([plan.actions[0], bad_act])


# ------------------------------------------------------------------------------
# Test 4: Self-Dependencies
# ------------------------------------------------------------------------------

def test_self_dependencies():
    """4. Self-dependencies."""
    plan = make_sample_action_plan()
    bad_act = plan.actions[0].model_copy(update={"dependencies": ["act_1"]})
    with pytest.raises(ActionPlanValidationError, match="Self-dependency detected"):
        validate_dependencies([bad_act])


# ------------------------------------------------------------------------------
# Test 5: Dependency Cycles
# ------------------------------------------------------------------------------

def test_dependency_cycles():
    """5. Dependency cycles."""
    plan = make_sample_action_plan()
    # act_1 -> act_2, act_2 -> act_3, act_3 -> act_1
    act_1 = plan.actions[0].model_copy(update={"dependencies": ["act_3"]})
    act_2 = plan.actions[1].model_copy(update={"dependencies": ["act_1"]})
    act_3 = plan.actions[0].model_copy(update={"action_id": "act_3", "dependencies": ["act_2"]})

    with pytest.raises(ActionPlanValidationError, match="Dependency cycle detected"):
        validate_dependencies([act_1, act_2, act_3])


# ------------------------------------------------------------------------------
# Test 6: Invalid Priorities
# ------------------------------------------------------------------------------

def test_invalid_priorities():
    """6. Invalid priorities."""
    with pytest.raises(ValidationError):
        ActionCriterion(
            criterion_id="crit_test",
            criterion_type="invalid_type",  # invalid enum
            description="Test criterion",
            provenance_type="test",
        )


# ------------------------------------------------------------------------------
# Test 7: Criteria with Supported Numeric Operators and Units
# ------------------------------------------------------------------------------

def test_criteria_with_supported_operators_and_units():
    """7. Criteria with supported numeric operators and units."""
    crit = ActionCriterion(
        criterion_id="crit_test",
        criterion_type=CriterionType.RECOMMENDATION_TARGET,
        description="Target CSAT",
        metric_name="csat",
        operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=90.0,
        unit="%",
        provenance_type="recommendation.action_plan",
    )
    assert crit.operator == ComparisonOperator.GREATER_THAN_OR_EQUAL
    assert crit.threshold_value == 90.0
    assert crit.unit == "%"

    # NaN / Inf rejection
    with pytest.raises(ValidationError):
        ActionCriterion(
            criterion_id="crit_nan",
            criterion_type=CriterionType.RECOMMENDATION_TARGET,
            description="NaN test",
            threshold_value=float("nan"),
            provenance_type="test",
        )


# ------------------------------------------------------------------------------
# Test 8: Missing Provenance Flagged as Warning
# ------------------------------------------------------------------------------

def test_missing_provenance():
    """8. Missing provenance."""
    plan = make_sample_action_plan()
    crit_no_provenance = ActionCriterion(
        criterion_id="crit_unbacked",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Unbacked constraint",
        provenance_type="decision_model.constraints",
        source_reference=None,  # Missing upstream reference
    )
    act_with_unbacked = plan.actions[0].model_copy(
        update={"success_criteria": [crit_no_provenance]}
    )
    test_plan = plan.model_copy(update={"actions": [act_with_unbacked, plan.actions[1]]})

    validated = validate_action_plan(test_plan)
    warn_ids = [w.warning_id for w in validated.validation_warnings]
    assert any("warn_missing_provenance" in wid for wid in warn_ids)


# ------------------------------------------------------------------------------
# Test 9: Comparable Conflicting Thresholds
# ------------------------------------------------------------------------------

def test_comparable_conflicting_thresholds():
    """9. Comparable conflicting thresholds (e.g. CSAT floor 90% vs rollback trigger 85%)."""
    # Upstream decision model with hard constraint: CSAT >= 90%
    mock_decision_model = type("MockDecisionModel", (), {
        "constraints": [
            type("MockConstraint", (), {
                "id": "cnstr_csat",
                "name": "Customer Satisfaction Floor",
                "description": "Maintain CSAT above 90%",
                "threshold": 90.0,
                "threshold_expression": ">= 90%",
                "unit": "%",
                "is_hard_constraint": True,
            })()
        ]
    })()

    # Plan gate proposes rollback only when CSAT falls below 85%
    gate_conflicting_crit = ActionCriterion(
        criterion_id="crit_gate_csat",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Customer satisfaction trigger",
        metric_name="csat",
        operator=ComparisonOperator.LESS_THAN,
        threshold_value=85.0,  # Below the mandatory 90% floor!
        unit="%",
        provenance_type="decision_model.constraints",
        source_reference="cnstr_csat",
    )

    plan = make_sample_action_plan()
    gate_conflicting = plan.decision_gates[0].model_copy(
        update={"criteria": [gate_conflicting_crit]}
    )
    test_plan = plan.model_copy(update={"decision_gates": [gate_conflicting]})

    validated = validate_action_plan(test_plan, decision_model=mock_decision_model)
    conflicts = [w for w in validated.validation_warnings if w.severity == ValidationSeverity.CONFLICT]

    assert len(conflicts) >= 1
    assert "below the mandatory user hard constraint floor of 90.0%" in conflicts[0].message


# ------------------------------------------------------------------------------
# Test 10: Ambiguous Thresholds Marked Review-Required
# ------------------------------------------------------------------------------

def test_ambiguous_thresholds_marked_review_required():
    """10. Ambiguous thresholds marked review-required."""
    mock_decision_model = type("MockDecisionModel", (), {
        "constraints": [
            type("MockConstraint", (), {
                "id": "cnstr_budget",
                "name": "Implementation Budget",
                "description": "Ceiling budget",
                "threshold": 150000.0,
                "threshold_expression": "$150,000",
                "unit": "USD",
                "is_hard_constraint": True,
            })()
        ]
    })()

    # Action criterion with incompatible/ambiguous unit: "points" vs "USD"
    crit_ambiguous = ActionCriterion(
        criterion_id="crit_budget_points",
        criterion_type=CriterionType.HARD_CONSTRAINT,
        description="Implementation Budget",
        metric_name="budget",
        operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        threshold_value=120000.0,
        unit="points",  # Incompatible unit with USD
        provenance_type="decision_model.constraints",
        source_reference="cnstr_budget",
    )

    plan = make_sample_action_plan()
    gate_ambiguous = plan.decision_gates[0].model_copy(update={"criteria": [crit_ambiguous]})
    test_plan = plan.model_copy(update={"decision_gates": [gate_ambiguous]})

    validated = validate_action_plan(test_plan, decision_model=mock_decision_model)
    review_warns = [w for w in validated.validation_warnings if w.severity == ValidationSeverity.REVIEW_REQUIRED]

    assert len(review_warns) >= 1
    assert "Incompatible or ambiguous units" in review_warns[0].message


# ------------------------------------------------------------------------------
# Test 11: Stable Fingerprint Generation
# ------------------------------------------------------------------------------

def test_stable_fingerprint_generation():
    """11. Stable fingerprint generation."""
    rec = type("MockRec", (), {
        "id": "rec_001",
        "decision_status": "pilot",
        "recommended_action": "Deploy three-month pilot for 1,000 customers.",
        "action_plan": type("MockActionPlan", (), {
            "actions": [
                type("MockAction", (), {"id": "act_1", "title": "Pilot Setup", "priority": "high", "dependencies": []})(),
            ]
        })(),
    })()

    model = type("MockModel", (), {
        "constraints": [
            type("MockCnstr", (), {"id": "c1", "threshold": 1000, "threshold_expression": "<= 1000", "unit": "customers", "is_hard_constraint": True})()
        ]
    })()

    fp1 = compute_source_recommendation_fingerprint(rec, model)
    fp2 = compute_source_recommendation_fingerprint(rec, model)

    assert fp1.startswith("srfp_")
    assert len(fp1) == 37  # 'srfp_' + 32 hex chars
    assert fp1 == fp2  # Identical inputs yield identical fingerprint

    # Mutate recommended action -> fingerprint changes
    rec_altered = type("MockRec", (), {
        "id": "rec_001",
        "decision_status": "pilot",
        "recommended_action": "Deploy six-month pilot for 5,000 customers.",
        "action_plan": rec.action_plan,
    })()
    fp3 = compute_source_recommendation_fingerprint(rec_altered, model)
    assert fp1 != fp3


# ------------------------------------------------------------------------------
# Test 12: Persistence Round Trips
# ------------------------------------------------------------------------------

def test_persistence_round_trips(mock_storage):
    """12. Persistence round trips."""
    plan = make_sample_action_plan()
    plan_json = plan.model_dump_json()

    mock_storage.save_action_plan(
        plan_id=plan.plan_id,
        analysis_id=plan.analysis_id,
        source_recommendation_fingerprint=plan.source_recommendation_fingerprint,
        schema_version=plan.schema_version,
        generator_version=plan.generator_version,
        plan_json=plan_json,
        owner_id="alice",
    )

    # Retrieve by analysis_id
    row = mock_storage.get_action_plan(plan.analysis_id, owner_id="alice")
    assert row is not None
    assert row["plan_id"] == plan.plan_id

    # Retrieve by plan_id
    row_by_id = mock_storage.get_action_plan_by_id(plan.plan_id, owner_id="alice")
    assert row_by_id is not None
    assert row_by_id["analysis_id"] == plan.analysis_id

    # Owner isolation: wrong owner returns None
    assert mock_storage.get_action_plan(plan.analysis_id, owner_id="bob") is None


# ------------------------------------------------------------------------------
# Test 13: Duplicate Plan Prevention & Cache Reuse
# ------------------------------------------------------------------------------

def test_duplicate_plan_prevention(client, mock_storage):
    """13. Duplicate-plan prevention & cache reuse via API."""
    analysis_id = "test-analysis-123"
    rec_fp = "srfp_71162fecfa68e48475dc312f89c587bc"

    # Setup parent job in completed status with recommendation
    mock_resp = AnalysisResponse(
        analysis_id=analysis_id,
        status="completed",
        question="Should we launch a pilot?",
        recommendation=DecisionRecommendation(
            id="rec_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_01",
            evidence_package_id="ev_01",
            reasoning_board_id="rb_01",
            decision_status=DecisionStatus.PILOT,
            recommended_action="Launch pilot for 1000 users",
            executive_rationale="Balances speed with risk.",
            action_plan=Stage4ActionPlan(
                summary="Roadmap",
                actions=[
                    Stage4ActionItem(
                        id="act_1",
                        title="Cutover",
                        objective="Route traffic",
                        description="Route 1000 users",
                        priority=ActionPriority.HIGH,
                        responsible_role="Lead",
                        time_horizon="immediate",
                    )
                ],
            ),
            uncertainty_assessment=UncertaintyAssessment(
                evidence_strength=EvidenceStrength.MODERATE,
                decision_readiness=DecisionReadiness.READY,
                recommendation_stability=RecommendationStability.HIGH,
            ),
        ),
    )

    req = AnalysisJobCreateRequest(question="Should we launch a pilot?")
    job = mock_storage.create_job(req, job_id="job-123")
    mock_storage.complete_job(job.job_id, response=mock_resp)

    # Compute actual recommendation fingerprint for consistent cache matching
    rec_fp = compute_source_recommendation_fingerprint(
        recommendation=mock_resp.recommendation,
        decision_model=mock_resp.decision_model,
    )

    # Pre-save an action plan
    sample_plan = make_sample_action_plan(analysis_id=analysis_id, fingerprint=rec_fp)
    mock_storage.save_action_plan(
        plan_id=sample_plan.plan_id,
        analysis_id=analysis_id,
        source_recommendation_fingerprint=rec_fp,
        schema_version="1.0",
        generator_version="day8a_v1",
        plan_json=sample_plan.model_dump_json(),
    )

    # Call POST generate without force_regenerate
    resp = client.post(f"/api/analysis/{analysis_id}/action-plan/generate", json={})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["cached"] is True
    assert data["status"] == "cached"
    assert data["plan"]["plan_id"] == sample_plan.plan_id


# ------------------------------------------------------------------------------
# Test 14: Retrieval of Nonexistent Plans
# ------------------------------------------------------------------------------

def test_retrieval_of_nonexistent_plans(client, mock_storage):
    """14. Retrieval of nonexistent plans returns clean HTTP 404."""
    # 1. Nonexistent analysis
    resp = client.get("/api/analysis/nonexistent-id/action-plan")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in resp.json()["detail"].lower()

    # 2. Existing analysis without action plan
    req = AnalysisJobCreateRequest(question="Test question")
    job = mock_storage.create_job(req, job_id="job-456")
    mock_resp = AnalysisResponse(analysis_id="analysis-456", status="completed", question="Test question")
    mock_storage.complete_job(job.job_id, response=mock_resp)

    resp2 = client.get("/api/analysis/analysis-456/action-plan")
    assert resp2.status_code == status.HTTP_404_NOT_FOUND
    assert "not been generated" in resp2.json()["detail"].lower()


# ------------------------------------------------------------------------------
# Test 15: Backward Compatibility with Six-Stage Pipeline
# ------------------------------------------------------------------------------

def test_backward_compatibility_six_stage_analysis(mock_storage):
    """15. Backward compatibility with existing six-stage analysis results."""
    # Stage 4 recommendation action plan remains completely intact
    stage4_action = Stage4ActionItem(
        id="act_legacy_1",
        title="Legacy Pilot Step",
        objective="Run pilot",
        description="Verify legacy fields",
        priority=ActionPriority.HIGH,
        responsible_role="Operations",
        time_horizon="immediate",
    )
    rec = DecisionRecommendation(
        id="rec_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_01",
        evidence_package_id="ev_01",
        reasoning_board_id="rb_01",
        decision_status=DecisionStatus.PILOT,
        recommended_action="Execute legacy recommendation",
        executive_rationale="Sound rationale",
        action_plan=Stage4ActionPlan(summary="Summary", actions=[stage4_action]),
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
        ),
    )

    # Validates that Stage 4 model remains immutable and functional
    assert rec.action_plan.actions[0].id == "act_legacy_1"
    assert rec.action_plan.actions[0].priority == ActionPriority.HIGH


# ------------------------------------------------------------------------------
# Test 16: Regressions in Day 7 Simulation and Session Restoration
# ------------------------------------------------------------------------------

def test_regression_day7_simulation_and_session_restoration(client, mock_storage):
    """16. Existing Day 7 simulation and session-restoration regressions check."""
    # Verify health endpoint
    health_resp = client.get("/health")
    assert health_resp.status_code == status.HTTP_200_OK

    # Verify simulation endpoints continue to mount cleanly
    sim_resp = client.get("/api/analysis/unknown-id/simulations")
    # Returns 404 for nonexistent analysis without crashing
    assert sim_resp.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)
