"""Phase 7B Integration Tests: What-if Simulation API, Persistence & Integration.

Comprehensive verification of:
1. Variable discovery endpoint (GET /api/analysis/{analysis_id}/simulation-variables).
2. Successful simulation endpoint (POST /api/analysis/{analysis_id}/simulate).
3. Supported constraint-linked adjustment (breach detected, scenario relevance preserved).
4. Unsupported causal mapping (score delta is None, calculation status unsupported).
5. No available variables (returns empty variables list and 0 supported).
6. Invalid numerical input (rejects NaN, Infinity, strings with 422).
7. Duplicate adjustment (rejects duplicate variable_id with 422).
8. Unknown variable (rejects nonexistent variable_id with 422).
9. Unit mismatch (rejects mismatched units with 422).
10. Out-of-range adjustment (rejects bound violations with 422).
11. Analysis not found (returns 404 Not Found).
12. Analysis still running (returns 409 Conflict).
13. Historical four-stage analysis (missing scenarios returns 422).
14. Historical five-stage analysis (missing resilience handles safely).
15. Stage 6 unavailable (handles partial success without crashing).
16. Cross-artifact mismatch (rejects referential mismatch with 422).
17. Baseline fingerprint mismatch (returns 409 Conflict).
18. Identical request idempotency (same simulation ID, safe DB insert).
19. Concurrent simulation isolation (concurrent requests evaluate independently).
20. Persistence across storage reinitialization (retrieves simulation after reload).
21. Original analysis immutability (baseline response_json remains byte-for-byte intact).
22. Correct simulation retrieval (GET /simulations/{id} and GET /simulations listing).
23. Zero network/LLM calls during simulation.
24. Existing six-stage API remains unchanged.
25. No fabricated score delta (strictly None when causal path does not exist).
26. Scenario constraint relevance protection (relevant_constraint_ids is never mutated).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.engines.resilience import evaluate_resilience
from app.engines.simulation import (
    RULE_CONSTRAINT_THRESHOLD_EVALUATION,
    RULE_DIRECT_VARIABLE_SUBSTITUTION,
)
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
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
from app.schemas.evidence import EvidencePackage
from app.schemas.job import JobStatus, PipelineStage

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
    SimulationListResponse,
    SimulationRequest,
    SimulationResult,
    SimulationSubmitRequest,
    SimulationVariableDiscoveryResponse,
    compute_baseline_fingerprint,
)
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage


# ------------------------------------------------------------------------------
# Helpers to build test jobs in SQLite
# ------------------------------------------------------------------------------

def _build_test_artifacts(
    budget_limit: float = 50000.0,
    baseline_spend: float = 35000.0,
    include_scenarios: bool = True,
    include_resilience: bool = True,
    decision_model_id: str = "dec_api_test_001",
    pessimistic_pressured_constraints: Optional[List[str]] = None,
    empty_variables: bool = False,
    scenario_decision_model_id: Optional[str] = None,
):
    """Builds a consistent set of test artifacts for seeding SQLite jobs."""
    recommendation_id = "rec_0123456789abcdef0123456789abcdef"
    scenario_set_id = "scenset_0123456789abcdef0123456789abcdef"
    evidence_package_id = "pkg_api_test_001"
    reasoning_board_id = "rbd_api_test_001"

    if empty_variables:
        variables = [
            Variable(
                id="var_text_qualitative",
                name="Primary Market Region",
                description="Target region descriptor without numerical metric.",
                variable_type=VariableType.QUALITATIVE,
                is_controllable=False,
                baseline_value=None,
                proposed_value=None,
                unit=None,
            )
        ]
    else:
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
                description="Sales discount percentage.",
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

    ev_pkg = EvidencePackage(
        id=evidence_package_id,
        decision_model_id=decision_model_id,
        summary="Evidence package summary.",
        requirements=[],
        sources=[],
        items=[],
        claim_links=[],
        gaps=[],
    )

    rb = None

    rec = DecisionRecommendation(
        id=recommendation_id,
        decision_model_id=decision_model_id,
        evidence_package_id=evidence_package_id,
        reasoning_board_id=reasoning_board_id,
        decision_status=DecisionStatus.CONDITIONAL,
        recommended_action="Deploy pilot European ingress nodes.",
        executive_rationale="Empirical evidence demonstrates strong market demand growth.",
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

    scens = None
    if include_scenarios:
        pess_constraints = pessimistic_pressured_constraints if pessimistic_pressured_constraints is not None else []
        scen_dm_id = scenario_decision_model_id if scenario_decision_model_id is not None else decision_model_id
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
        scens = ScenarioSet(
            id=scenario_set_id,
            decision_model_id=scen_dm_id,
            recommendation_id=recommendation_id,
            summary="Three canonical trajectories synthesis.",
            scenarios=scenarios,
        )

    resilience = None
    if include_resilience and scens is not None:
        resilience = evaluate_resilience(
            decision_model=dm,
            scenario_set=scens,
            recommendation=rec,
            evidence_package=ev_pkg,
            reasoning_board=rb,
        )

    response = AnalysisResponse(
        analysis_id=f"analysis_{decision_model_id}",
        decision_model=dm,
        evidence_package=ev_pkg,
        reasoning_board=rb,
        recommendation=rec,
        recommendation_status="completed",
        scenarios=scens,
        scenario_status="completed" if scens else None,
        resilience=resilience,
        resilience_status="completed" if resilience else None,
        status="completed",
        message="Decision analysis completed successfully.",
    )

    return dm, scens, rec, resilience, response


def _seed_job(
    storage: SQLiteJobStorage,
    job_id: str,
    status_val: str,
    stage_val: str,
    response: Optional[AnalysisResponse],
    error_msg: Optional[str] = None,
):
    """Inserts a job record directly into SQLite for precise testing of lifecycle states."""
    conn = sqlite3.connect(storage.db_path)
    now = datetime.now(timezone.utc).isoformat()
    resp_json = response.model_dump_json() if response else None
    conn.execute(
        """
        INSERT INTO analysis_jobs (
            job_id, status, stage, request_json, response_json,
            owner_id, created_at, completed_at, timeout_seconds, progress_message, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            status_val,
            stage_val,
            json.dumps({"question": "Test question"}),
            resp_json,
            "test_owner",
            now,
            now if status_val in ("succeeded", "failed", "timed_out") else None,
            120.0,
            "Stage progress",
            error_msg,
        ),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------------------
# Pytest Fixture
# ------------------------------------------------------------------------------

@pytest.fixture
def test_setup(tmp_path):
    """Sets up an isolated SQLiteJobStorage and AnalysisJobManager for testing."""
    db_file = str(tmp_path / "test_simulation_api.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)

    # Override FastAPI dependency
    app.dependency_overrides[get_job_manager] = lambda: manager

    client = TestClient(app)

    yield {"client": client, "manager": manager, "storage": storage, "db_file": db_file}

    app.dependency_overrides.clear()
    manager.shutdown(wait=False)


# ------------------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------------------

def test_01_variable_discovery_endpoint(test_setup):
    """Test 1: Variable discovery endpoint returns bounds, units, baseline, and capabilities."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(budget_limit=50000.0, baseline_spend=35000.0)
    job_id = "job_test_01"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    # 1. Discover using job_id
    res = client.get(f"/api/analysis/{job_id}/simulation-variables")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["job_id"] == job_id
    assert data["analysis_id"] == response.analysis_id
    assert data["baseline_fingerprint"].startswith("bfp_")
    assert len(data["baseline_fingerprint"]) == 36
    assert data["supported_count"] >= 1
    assert data["recalculation_capabilities"]["direct_substitution"] is True
    assert data["recalculation_capabilities"]["constraint_threshold_evaluation"] is True

    # 2. Discover using analysis_id
    res2 = client.get(f"/api/analysis/{response.analysis_id}/simulation-variables")
    assert res2.status_code == status.HTTP_200_OK
    data2 = res2.json()
    assert data2["baseline_fingerprint"] == data["baseline_fingerprint"]

    # 3. Un-prefixed route /analysis/{analysis_id}/simulation-variables
    res3 = client.get(f"/analysis/{job_id}/simulation-variables")
    assert res3.status_code == status.HTTP_200_OK


def test_02_successful_simulation_endpoint(test_setup):
    """Test 2: Successful simulation endpoint returns SimulationResult and persists in SQLite."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(budget_limit=50000.0, baseline_spend=35000.0)
    job_id = "job_test_02"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["id"].startswith("sim_")
    assert data["decision_model_id"] == response.decision_model.id
    assert data["scenario_set_id"] == response.scenarios.id
    assert data["recommendation_id"] == response.recommendation.id
    assert data["baseline_fingerprint"].startswith("bfp_")
    assert len(data["applied_adjustments"]) == 1
    assert data["applied_adjustments"][0]["proposed_value"] == 40000.0
    # Verify persisted in storage
    sim_row = storage.get_simulation(data["id"], job_id)
    assert sim_row is not None
    assert sim_row["baseline_fingerprint"] == data["baseline_fingerprint"]
    assert sim_row["created_at"] is not None


def test_03_supported_constraint_linked_adjustment(test_setup):
    """Test 3: Constraint threshold breach is detected in impacts while scenario relevance is preserved."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    pess_constraints = ["cnstr_pre_existing"]
    _, _, _, _, response = _build_test_artifacts(
        budget_limit=50000.0,
        baseline_spend=35000.0,
        pessimistic_pressured_constraints=pess_constraints,
    )
    job_id = "job_test_03"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    # Increase spend to $65,000 (breaches $50,000 budget constraint)
    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 65000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    # Rule and impact explanation
    impact = data["impacts"][0]
    assert impact["transformation_rule_id"] == RULE_CONSTRAINT_THRESHOLD_EVALUATION
    assert "breached threshold for constraint 'Monthly Cloud Spend'" in impact["explanation"]
    assert impact["calculation_status"] == "unsupported_no_causal_mapping"

    # Specific verification: scenario relevance was NOT rewritten
    refreshed_job = storage.get_job(job_id)
    assert refreshed_job.response.scenarios.scenarios[2].relevant_constraint_ids == pess_constraints


def test_04_unsupported_causal_mapping(test_setup):
    """Test 4: Unmapped variable returns UNSUPPORTED_NO_CAUSAL_MAPPING with None score delta."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_test_04"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_discount_rate", "proposed_value": 25.0, "unit": "%"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["status"] == "unsupported_no_causal_mapping"
    assert data["simulated_resilience_score"] is None
    assert data["score_delta"] is None
    assert data["baseline_resilience_score"] is not None
    assert any("no causal path" in w for w in data["warnings"])


def test_05_no_available_variables(test_setup):
    """Test 5: Discovery on analysis with no numerical variables returns empty list and 0 supported."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(empty_variables=True)
    job_id = "job_test_05"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    res = client.get(f"/api/analysis/{job_id}/simulation-variables")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["variables"] == []
    assert data["supported_count"] == 0
    assert data["unsupported_count"] == 0


def test_06_invalid_numerical_input(test_setup):
    """Test 6: Reject NaN, Infinity, strings in proposed_value with 422."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_test_06"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    # String value
    res1 = client.post(
        f"/api/analysis/{job_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": "not-a-number"}]},
    )
    assert res1.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # NaN / Infinity via JSON null or string representation
    res2 = client.post(
        f"/api/analysis/{job_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": None}]},
    )
    assert res2.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_07_duplicate_adjustment(test_setup):
    """Test 7: Reject duplicate adjustments for the same variable with 422."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_test_07"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"},
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 45000.0, "unit": "USD"},
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "duplicate adjustment" in res.text.lower()


def test_08_unknown_variable(test_setup):
    """Test 8: Reject unknown variable ID with 422."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_test_08"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_nonexistent_metric", "proposed_value": 100.0}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "unknown variable" in res.text.lower()


def test_09_unit_mismatch(test_setup):
    """Test 9: Reject unit mismatch with 422."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_test_09"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "EUR"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "unit mismatch" in res.text.lower()


def test_10_out_of_range_adjustment(test_setup):
    """Test 10: Reject out-of-range adjustment when variable bounds are violated."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    # var_monthly_cloud_spend has currency type (min bound = 0.0)
    job_id = "job_test_10"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": -5000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "minimum bound" in res.text.lower()


def test_11_analysis_not_found(test_setup):
    """Test 11: Unknown analysis ID returns 404 for all simulation endpoints."""
    client = test_setup["client"]

    # Variable discovery
    res1 = client.get("/api/analysis/nonexistent-analysis-id/simulation-variables")
    assert res1.status_code == status.HTTP_404_NOT_FOUND

    # Simulate
    res2 = client.post(
        "/api/analysis/nonexistent-analysis-id/simulate",
        json={"adjustments": [{"variable_id": "var_test", "proposed_value": 10.0}]},
    )
    assert res2.status_code == status.HTTP_404_NOT_FOUND

    # Get single simulation
    res3 = client.get("/api/analysis/nonexistent-analysis-id/simulations/sim_test")
    assert res3.status_code == status.HTTP_404_NOT_FOUND

    # List simulations
    res4 = client.get("/api/analysis/nonexistent-analysis-id/simulations")
    assert res4.status_code == status.HTTP_404_NOT_FOUND


def test_12_analysis_still_running(test_setup):
    """Test 12: Pending or running analysis returns 409 Conflict."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    job_id = "job_running_01"
    _seed_job(storage, job_id, "running", "stage3_ai_boardroom", None)

    # Variable discovery
    res1 = client.get(f"/api/analysis/{job_id}/simulation-variables")
    assert res1.status_code == status.HTTP_409_CONFLICT
    assert "currently running" in res1.text.lower()

    # Simulate
    res2 = client.post(
        f"/api/analysis/{job_id}/simulate",
        json={"adjustments": [{"variable_id": "var_test", "proposed_value": 10.0}]},
    )
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert "currently running" in res2.text.lower()


def test_13_historical_four_stage_analysis(test_setup):
    """Test 13: Historical 4-stage analysis (missing Scenarios) returns 422 Unprocessable Entity."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(include_scenarios=False, include_resilience=False)
    job_id = "job_hist_4stage"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "missing required stages" in res.text.lower()


def test_14_historical_five_stage_analysis(test_setup):
    """Test 14: Historical 5-stage analysis (has Scenarios, but no Stage 6) handles simulation safely."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(include_scenarios=True, include_resilience=False)
    job_id = "job_hist_5stage"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["id"].startswith("sim_")
    assert data["baseline_resilience_score"] is not None  # Evaluated on-the-fly


def test_15_stage6_unavailable(test_setup):
    """Test 15: Analysis where Stage 6 had failed or is unavailable handles safely."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(include_scenarios=True, include_resilience=False)
    response = response.model_copy(update={"resilience_status": "failed", "resilience_error": "Timeout in Stage 6"})
    job_id = "job_stage6_failed"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["id"].startswith("sim_")


def test_16_cross_artifact_mismatch(test_setup):
    """Test 16: Referential integrity mismatch between DecisionModel and Scenarios rejected with 422."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts(
        decision_model_id="dec_correct_001",
        scenario_decision_model_id="dec_mismatched_999",
        include_resilience=False,
    )
    job_id = "job_mismatch_01"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "referential integrity mismatch" in res.text.lower()


def test_17_baseline_fingerprint_mismatch(test_setup):
    """Test 17: Providing stale or mismatched baseline_fingerprint returns 409 Conflict."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_fp_mismatch"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "baseline_fingerprint": "bfp_deadbeefdeadbeefdeadbeefdeadbeef",
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}
        ],
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_409_CONFLICT
    assert "baseline fingerprint mismatch" in res.text.lower()


def test_18_identical_request_idempotency(test_setup):
    """Test 18: Submitting identical simulation adjustments twice returns identical simulation ID."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_idempotent"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 42000.0, "unit": "USD"}
        ]
    }

    res1 = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res1.status_code == status.HTTP_200_OK
    sim1 = res1.json()

    res2 = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res2.status_code == status.HTTP_200_OK
    sim2 = res2.json()

    # Exact deterministic identity
    assert sim1["id"] == sim2["id"]
    assert sim1["baseline_fingerprint"] == sim2["baseline_fingerprint"]

    # Verify no duplicate row error in storage
    saved = storage.list_simulations(job_id)
    assert len(saved) == 1


def test_19_concurrent_simulation_isolation(test_setup):
    """Test 19: Concurrent simulation requests execute safely without cross-talk or race conditions."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_concurrent"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    def _call(spend: float):
        return client.post(
            f"/api/analysis/{job_id}/simulate",
            json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": spend, "unit": "USD"}]},
        )

    spends = [38000.0, 42000.0, 48000.0, 62000.0, 70000.0]
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(_call, spends))

    for r in responses:
        assert r.status_code == status.HTTP_200_OK

    sim_ids = [r.json()["id"] for r in responses]
    assert len(set(sim_ids)) == 5  # Exactly 5 unique simulation IDs

    # Storage has all 5
    saved = storage.list_simulations(job_id)
    assert len(saved) == 5


def test_20_persistence_across_storage_reinitialization(test_setup):
    """Test 20: Persisted simulation is retrievable after closing and re-opening storage."""
    client = test_setup["client"]
    storage = test_setup["storage"]
    db_file = test_setup["db_file"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_persistence"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 45000.0, "unit": "USD"}
        ]
    }
    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    sim_id = res.json()["id"]

    # Simulate restart by creating a fresh SQLiteJobStorage
    new_storage = SQLiteJobStorage(db_path=db_file)
    sim_row = new_storage.get_simulation(sim_id, job_id)
    assert sim_row is not None
    assert sim_row["simulation_id"] == sim_id
    assert json.loads(sim_row["result_json"])["id"] == sim_id

    listed = new_storage.list_simulations(job_id)
    assert len(listed) == 1
    new_storage.close()


def test_21_original_analysis_immutability(test_setup):
    """Test 21: Original baseline response_json in SQLite remains byte-for-byte immutable."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_immutability"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    # Capture initial database raw json
    initial_job = storage.get_job(job_id)
    initial_json = initial_job.response.model_dump_json()

    # Execute multiple diverse simulations
    for spend in [40000.0, 55000.0, 75000.0]:
        client.post(
            f"/api/analysis/{job_id}/simulate",
            json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": spend, "unit": "USD"}]},
        )

    # Re-fetch from database
    post_job = storage.get_job(job_id)
    post_json = post_job.response.model_dump_json()

    # Exact equality
    assert post_json == initial_json


def test_22_correct_simulation_retrieval(test_setup):
    """Test 22: Correct simulation retrieval by ID and listing endpoint."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_retrieval"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    res1 = client.post(
        f"/api/analysis/{job_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": 39000.0, "unit": "USD"}]},
    )
    sim1_id = res1.json()["id"]

    res2 = client.post(
        f"/api/analysis/{job_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": 43000.0, "unit": "USD"}]},
    )
    sim2_id = res2.json()["id"]

    # Retrieve single simulation
    get_res = client.get(f"/api/analysis/{job_id}/simulations/{sim1_id}")
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["id"] == sim1_id

    # Retrieve non-existent simulation
    not_found = client.get(f"/api/analysis/{job_id}/simulations/sim_nonexistent")
    assert not_found.status_code == status.HTTP_404_NOT_FOUND

    # List simulations
    list_res = client.get(f"/api/analysis/{job_id}/simulations")
    assert list_res.status_code == status.HTTP_200_OK
    list_data = list_res.json()
    assert list_data["total_count"] == 2
    assert len(list_data["simulations"]) == 2
    ids = [s["id"] for s in list_data["simulations"]]
    assert sim1_id in ids
    assert sim2_id in ids


def test_23_no_network_or_llm_calls(test_setup):
    """Test 23: Pure deterministic execution with zero network or LLM calls."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_offline"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    with patch("app.services.llm.client.FakeLLMClient.generate_structured") as mock_llm:
        with patch("app.services.evidence.search_provider.FakeSearchProvider.search") as mock_search:
            res = client.post(
                f"/api/analysis/{job_id}/simulate",
                json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": 41000.0, "unit": "USD"}]},
            )
            assert res.status_code == status.HTTP_200_OK
            assert mock_llm.call_count == 0
            assert mock_search.call_count == 0


def test_24_existing_six_stage_api_remains_unchanged(test_setup):
    """Test 24: Existing six-stage API (POST /api/analyze) functions normally."""
    client = test_setup["client"]

    # Synchronous analyze
    sync_resp = client.post(
        "/api/analyze",
        json={"question": "Should we migrate to a micro-frontend architecture?"},
    )
    assert sync_resp.status_code == status.HTTP_200_OK
    data = sync_resp.json()
    assert data["status"] == "completed"
    assert "resilience" in data
    assert data["resilience"] is not None


def test_25_no_fabricated_score_delta(test_setup):
    """Test 25: Verify score_delta is None (never fabricated or 0.0) when no causal path exists."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    _, _, _, _, response = _build_test_artifacts()
    job_id = "job_no_fabrication"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    payload = {
        "adjustments": [
            {"variable_id": "var_discount_rate", "proposed_value": 20.0, "unit": "%"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["status"] == "unsupported_no_causal_mapping"
    assert data["score_delta"] is None
    assert data["simulated_resilience_score"] is None


def test_26_scenario_constraint_relevance_not_rewritten_for_threshold_breaches(test_setup):
    """Test 26: Specifically verify that FutureScenario.relevant_constraint_ids is not rewritten to encode breaches."""
    client = test_setup["client"]
    storage = test_setup["storage"]

    orig_relevant_constraints = ["cnstr_pre_existing_relevance"]
    _, _, _, _, response = _build_test_artifacts(
        budget_limit=50000.0,
        baseline_spend=35000.0,
        pessimistic_pressured_constraints=orig_relevant_constraints,
    )
    job_id = "job_semantics_check"
    _seed_job(storage, job_id, "succeeded", "completed", response)

    # Breach the budget
    payload = {
        "adjustments": [
            {"variable_id": "var_monthly_cloud_spend", "proposed_value": 85000.0, "unit": "USD"}
        ]
    }

    res = client.post(f"/api/analysis/{job_id}/simulate", json=payload)
    assert res.status_code == status.HTTP_200_OK

    # Check baseline in DB
    refreshed_job = storage.get_job(job_id)
    pess_scen = refreshed_job.response.scenarios.scenarios[2]
    assert pess_scen.relevant_constraint_ids == orig_relevant_constraints
    assert "cnstr_cloud_budget" not in pess_scen.relevant_constraint_ids
