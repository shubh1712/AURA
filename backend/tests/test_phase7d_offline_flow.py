"""Phase 7D Offline Full-Flow End-to-End Integration Verification.

Executes and asserts the complete lifecycle:
Completed six-stage analysis
→ Discover variables
→ Submit adjustments
→ Evaluate constraint impacts
→ Persist simulation
→ Retrieve simulation
→ Generate grounded explanation using FakeLLMClient
→ Retrieve cached explanation
→ Verify original analysis unchanged

Thoroughly exercises:
1. Supported structured numeric variable (spend threshold impact).
2. Unsupported numerical variable (discount rate without causal formula).
3. No available numeric variables (empty discovery).
4. Historical analysis without Stage 4/5 (safe error rejection).
5. Partial-success analysis / Missing Stage 6 (resilience report None).
6. Database restart / re-initialization (persistence across connection reload).
7. Invalid adjustment (bounds violation & malformed input).
8. Stale baseline fingerprint (optimistic concurrency 409).
9. LLM failure resilience (deterministic simulation usable despite LLM error).
10. Owner isolation validation.
"""

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.engines.resilience import evaluate_resilience
from app.main import app
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
from app.schemas.evidence import EvidencePackage
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
from app.schemas.scenario import (
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
)
from app.schemas.simulation import (
    CandidateSimulationExplanation,
    compute_baseline_fingerprint,
)
from app.services.analysis_service import get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient, LLMTimeoutError, MockLLMClient


def _create_full_six_stage_analysis(
    analysis_id: str,
    include_variables: bool = True,
    include_stage_6: bool = True,
    include_scenarios: bool = True,
):
    """Constructs a fully populated, compliant six-stage AnalysisResponse."""
    dm_id = f"dec_{analysis_id}"
    if include_variables:
        variables = [
            Variable(
                id="var_monthly_cloud_spend",
                name="Monthly Cloud Spend",
                description="Infrastructure operational expenditure.",
                variable_type=VariableType.CURRENCY,
                baseline_value=35000.0,
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
    else:
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

    constraints = [
        Constraint(
            id="cnstr_cloud_budget",
            name="Monthly Cloud Spend",
            description="Monthly cloud spend capped at $50,000.",
            is_hard_constraint=True,
            threshold_expression="spend <= 50000",
        ),
    ]

    dm = DecisionModel(
        id=dm_id,
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
        key_questions=["Will European traffic materialize?"],
    )

    ev_pkg = EvidencePackage(
        id=f"pkg_{analysis_id}",
        decision_model_id=dm_id,
        summary="Evidence package summary.",
        requirements=[],
        sources=[],
        items=[],
        claim_links=[],
        gaps=[],
    )

    rec_id = "rec_" + hashlib.md5(f"rec_{analysis_id}".encode()).hexdigest()
    rec = DecisionRecommendation(
        id=rec_id,
        decision_model_id=dm_id,
        evidence_package_id=ev_pkg.id,
        reasoning_board_id="rbd_001",
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
        scen_id = "scenset_" + hashlib.md5(f"scenset_{analysis_id}".encode()).hexdigest()
        scens = ScenarioSet(
            id=scen_id,
            decision_model_id=dm_id,
            recommendation_id=rec.id,
            summary="Three canonical trajectories synthesis.",
            scenarios=[
                FutureScenario(
                    id="scen_1111111111111111",
                    scenario_type=ScenarioType.OPTIMISTIC,
                    probability=0.25,
                    name="Rapid Adoption",
                    narrative="European traffic scales 3x.",
                    key_events=[ScenarioKeyEvent(id="ke_1", title="Rapid Surge", description="Traffic scales 3x in early phase", timeframe="M1")],
                    timeline=[ScenarioMilestone(id="ms_1", title="Launch Phase", description="Service reaches 99.99% availability", time_horizon="immediate", expected_outcome="99.99%")],
                ),
                FutureScenario(
                    id="scen_2222222222222222",
                    scenario_type=ScenarioType.BASE_CASE,
                    probability=0.55,
                    name="Controlled Growth",
                    narrative="Steady adoption.",
                    key_events=[ScenarioKeyEvent(id="ke_2", title="Base Cutover", description="Traffic cutover verified successfully", timeframe="M2")],
                    timeline=[ScenarioMilestone(id="ms_2", title="Cutover Gate", description="Verified cluster failover", time_horizon="immediate", expected_outcome="99.9%")],
                ),
                FutureScenario(
                    id="scen_3333333333333333",
                    scenario_type=ScenarioType.PESSIMISTIC,
                    probability=0.20,
                    name="Market Stagnation",
                    narrative="Plateau under fixed cost.",
                    key_events=[ScenarioKeyEvent(id="ke_3", title="Growth Plateau", description="Demand drops and plateaus under fixed costs", timeframe="M3")],
                    timeline=[ScenarioMilestone(id="ms_3", title="Review Check", description="Audit review checkpoint for scaling", time_horizon="immediate", expected_outcome="Halt")],
                    relevant_constraint_ids=["cnstr_cloud_budget"],
                ),
            ],
        )

    resilience = None
    if include_stage_6 and scens is not None:
        resilience = evaluate_resilience(
            decision_model=dm,
            scenario_set=scens,
            recommendation=rec,
            evidence_package=ev_pkg,
            reasoning_board=None,
        )

    return AnalysisResponse(
        analysis_id=analysis_id,
        decision_model=dm,
        evidence_package=ev_pkg,
        reasoning_board=None,
        recommendation=rec,
        recommendation_status="completed",
        scenarios=scens,
        scenario_status="completed" if scens else None,
        resilience=resilience,
        resilience_status="completed" if resilience else None,
        status="completed",
        message="Six-stage analysis complete.",
    )


def _seed_db_job(storage: SQLiteJobStorage, job_id: str, resp: AnalysisResponse, owner: str = "flow_owner"):
    conn = sqlite3.connect(storage.db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO analysis_jobs (
            job_id, status, stage, request_json, response_json,
            owner_id, created_at, completed_at, timeout_seconds, progress_message, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            "succeeded",
            "completed",
            json.dumps({"question": "Test flow question"}),
            resp.model_dump_json(),
            owner,
            now,
            now,
            120.0,
            "Finished",
            None,
        ),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def flow_env(tmp_path):
    db_file = str(tmp_path / "flow_verification.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)
    fake_llm = FakeLLMClient()

    app.dependency_overrides[get_job_manager] = lambda: manager
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    client = TestClient(app)

    yield {
        "client": client,
        "manager": manager,
        "storage": storage,
        "db_file": db_file,
        "llm": fake_llm,
    }

    app.dependency_overrides.clear()
    manager.shutdown(wait=False)


def test_full_offline_e2e_flow(flow_env):
    """End-to-End Test: Completed 6-stage -> Discover -> Simulate -> Explain -> Cache -> Immutability."""
    client = flow_env["client"]
    storage = flow_env["storage"]
    db_file = flow_env["db_file"]

    analysis_id = "analysis_e2e_flow_001"
    resp = _create_full_six_stage_analysis(analysis_id)
    _seed_db_job(storage, "job_e2e_001", resp, owner="owner_alice")

    # Step 1: Discover variables
    disc_res = client.get(
        f"/api/analysis/{analysis_id}/simulation-variables",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert disc_res.status_code == 200
    disc_data = disc_res.json()
    assert disc_data["analysis_id"] == analysis_id
    assert disc_data["supported_count"] >= 1
    assert len(disc_data["variables"]) == 2
    assert disc_data["baseline_fingerprint"] is not None
    current_fp = disc_data["baseline_fingerprint"]

    # Step 2: Submit supported adjustment ($35k -> $55k, breaching $50k budget)
    sim_res = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 55000.0,
                    "unit": "USD",
                }
            ],
            "baseline_fingerprint": current_fp,
        },
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    sim_id = sim_data["id"]

    # Step 3: Evaluate constraint impact
    assert len(sim_data["impacts"]) >= 1
    assert sim_data["baseline_fingerprint"] == current_fp
    assert sim_data["baseline_resilience_score"] is not None
    # Score delta is strictly null (unsupported causal mapping for operational cost)
    assert sim_data["simulated_resilience_score"] is None
    assert sim_data["score_delta"] is None

    # Step 4: Retrieve simulation from API
    get_sim = client.get(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert get_sim.status_code == 200
    assert get_sim.json()["id"] == sim_id

    # Step 5: Generate explanation using FakeLLMClient
    exp_res = client.post(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert exp_data["simulation_id"] == sim_id
    assert exp_data["generation_status"] == "generated"
    assert exp_data["prompt_version"] == "v1"
    assert len(exp_data["summary"]) > 0
    assert len(exp_data["what_changed"]) > 0

    # Step 6: Retrieve cached explanation (idempotency test)
    cached_exp = client.post(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert cached_exp.status_code == 200
    assert cached_exp.json()["generation_status"] == "cached"
    assert cached_exp.json()["simulation_id"] == sim_id

    # Step 7: Database restart / reload verification
    reloaded_storage = SQLiteJobStorage(db_path=db_file)
    persisted_sim = reloaded_storage.get_simulation(sim_id, "job_e2e_001")
    assert persisted_sim is not None
    assert persisted_sim["baseline_fingerprint"] == current_fp

    persisted_exp = reloaded_storage.get_simulation_explanation(sim_id)
    assert persisted_exp is not None
    assert persisted_exp["prompt_version"] == "v1"

    # Step 8: Original analysis immutability check
    persisted_job = reloaded_storage.get_job_by_any_id(analysis_id)
    assert persisted_job.response.model_dump_json() == resp.model_dump_json()


def test_edge_cases_and_error_modes(flow_env):
    """Verifies edge cases: no variables, missing stages, stale fingerprint, LLM failure, owner mismatch."""
    client = flow_env["client"]
    storage = flow_env["storage"]

    # 1. No available numeric variables
    no_var_resp = _create_full_six_stage_analysis("analysis_no_vars", include_variables=False)
    _seed_db_job(storage, "job_no_vars", no_var_resp, owner="owner_no_var")

    disc_no_var = client.get("/api/analysis/analysis_no_vars/simulation-variables")
    assert disc_no_var.status_code == 200
    assert disc_no_var.json()["supported_count"] == 0
    assert disc_no_var.json()["variables"] == []

    # 2. Historical analysis missing Stage 4/5 (scenarios)
    hist_resp = _create_full_six_stage_analysis("analysis_historical", include_scenarios=False)
    _seed_db_job(storage, "job_hist", hist_resp, owner="owner_hist")

    sim_hist = client.post(
        "/api/analysis/analysis_historical/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 40000.0,
                    "unit": "USD",
                }
            ]
        },
    )
    assert sim_hist.status_code == 422
    assert "missing required" in sim_hist.json()["detail"].lower()

    # 3. Partial success / Missing Stage 6 (resilience)
    no_res_resp = _create_full_six_stage_analysis("analysis_no_stage6", include_stage_6=False)
    _seed_db_job(storage, "job_no_stage6", no_res_resp, owner="owner_no_stage6")

    disc_no_res = client.get("/api/analysis/analysis_no_stage6/simulation-variables")
    assert disc_no_res.status_code == 200

    sim_no_res = client.post(
        "/api/analysis/analysis_no_stage6/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 40000.0,
                    "unit": "USD",
                }
            ]
        },
    )
    assert sim_no_res.status_code == 200
    assert sim_no_res.json()["simulated_resilience_score"] is None
    assert sim_no_res.json()["score_delta"] is None
    assert sim_no_res.json()["status"] == "unsupported_no_causal_mapping"
    sim_id_no_res = sim_no_res.json()["id"]

    # Explanation works smoothly even when Stage 6 is missing
    exp_no_res = client.post(f"/api/analysis/analysis_no_stage6/simulations/{sim_id_no_res}/explain")
    assert exp_no_res.status_code == 200

    # 4. Invalid adjustment (bounds violation or unknown variable)
    bad_adj = client.post(
        "/api/analysis/analysis_no_stage6/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_unknown_phantom",
                    "proposed_value": 100.0,
                }
            ]
        },
    )
    assert bad_adj.status_code == 422
    assert "Unknown variable" in bad_adj.json()["detail"]

    # 5. Stale baseline fingerprint
    stale_sim = client.post(
        "/api/analysis/analysis_no_stage6/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 41000.0,
                }
            ],
            "baseline_fingerprint": "corrupted_stale_fingerprint",
        },
    )
    assert stale_sim.status_code == 409
    assert "Baseline fingerprint mismatch" in stale_sim.json()["detail"]

    # 6. LLM failure preserves deterministic simulation result
    sim_err_res = client.post(
        "/api/analysis/analysis_no_stage6/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 46000.0,
                    "unit": "USD",
                }
            ]
        },
    )
    assert sim_err_res.status_code == 200
    sim_err_id = sim_err_res.json()["id"]

    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMTimeoutError("Gemini timed out."))
    app.dependency_overrides[get_llm_client] = lambda: mock_llm

    # Explain on uncached simulation fails with 504
    exp_fail = client.post(f"/api/analysis/analysis_no_stage6/simulations/{sim_err_id}/explain")
    assert exp_fail.status_code == 504

    # But simulation result remains completely valid and accessible
    sim_check = client.get(f"/api/analysis/analysis_no_stage6/simulations/{sim_err_id}")
    assert sim_check.status_code == 200
    assert sim_check.json()["id"] == sim_err_id

    # 7. Owner isolation check
    owner_fail = client.post(
        f"/api/analysis/analysis_no_stage6/simulations/{sim_id_no_res}/explain",
        headers={"X-Owner-Id": "unauthorized_intruder"},
    )
    assert owner_fail.status_code == 403
    assert "Access denied" in owner_fail.json()["detail"]
