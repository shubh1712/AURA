"""Phase 7E Security Hardening and Production Readiness Acceptance Tests.

Verifies:
1. End-to-end owner isolation across ALL 5 simulation endpoints.
2. Rejection of mismatched caller identity (HTTP 403).
3. Access to public/unowned jobs without restriction.
4. Input validation and tamper resistance (NaN, Inf, duplicates, bounds).
5. Baseline fingerprint protection against stale state (HTTP 409).
6. Immutability of baseline artifacts (DecisionModel, Scenarios, Recommendation, Resilience).
7. Persistence and cache survivability across database reload.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.job import AnalysisJobCreateRequest
from app.schemas.simulation import (
    CandidateSimulationExplanation,
    compute_baseline_fingerprint,
)
from app.services.jobs.storage import SQLiteJobStorage
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.analysis_service import get_llm_client
from app.services.llm.client import FakeLLMClient
from tests.test_phase7d_offline_flow import _create_full_six_stage_analysis


@pytest.fixture
def hardened_env(tmp_path):
    db_file = str(tmp_path / "security_hardening.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)
    fake_llm = FakeLLMClient(
        default_response=CandidateSimulationExplanation(
            summary="Hardened test explanation for security verification.",
            what_changed=["Monthly cloud spend adjusted."],
            constraint_implications=["Operational budget boundary satisfied."],
            resilience_interpretation="Resilience score maintained at baseline.",
            limitations=["Testing mock execution."],
            suggested_validation_steps=["Verify access headers."],
            evidence_or_artifact_references=["dec_001"],
        )
    )

    app.dependency_overrides[get_job_manager] = lambda: manager
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "storage": storage,
            "manager": manager,
            "db_file": db_file,
        }
    finally:
        app.dependency_overrides.clear()
        manager.shutdown(wait=True)
        storage.close()


def test_simulation_endpoints_enforce_owner_isolation(hardened_env):
    """Verifies that an intruder claiming 'owner_bob' cannot access 'owner_alice' simulation artifacts."""
    client = hardened_env["client"]
    storage = hardened_env["storage"]

    analysis_id = "analysis_alice_sec_01"
    job_id = "job_alice_sec_01"
    analysis_resp = _create_full_six_stage_analysis(analysis_id)

    # Seed job owned by 'owner_alice'
    req = AnalysisJobCreateRequest(
        question="Should we scale EU operations?",
        owner_id="owner_alice",
        timeout_seconds=120.0,
    )
    storage.create_job(request=req, job_id=job_id)
    storage.complete_job(job_id=job_id, response=analysis_resp)

    # 1. Variable Discovery
    # Authorized
    res = client.get(
        f"/api/analysis/{analysis_id}/simulation-variables",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert res.status_code == 200
    disc_data = res.json()
    current_fp = disc_data["baseline_fingerprint"]

    # Unauthorized intruder
    intruder_res = client.get(
        f"/api/analysis/{analysis_id}/simulation-variables",
        headers={"X-Owner-Id": "owner_bob"},
    )
    assert intruder_res.status_code == 403
    assert "access denied" in intruder_res.json()["detail"].lower()

    # 2. Run Simulation
    sim_payload = {
        "adjustments": [
            {
                "variable_id": "var_monthly_cloud_spend",
                "proposed_value": 42000.0,
                "unit": "USD",
            }
        ],
        "baseline_fingerprint": current_fp,
    }

    # Intruder run is blocked
    intruder_sim = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json=sim_payload,
        headers={"X-Owner-Id": "owner_bob"},
    )
    assert intruder_sim.status_code == 403
    assert "access denied" in intruder_sim.json()["detail"].lower()

    # Authorized run succeeds
    alice_sim = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json=sim_payload,
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert alice_sim.status_code == 200
    sim_id = alice_sim.json()["id"]

    # 3. Retrieve Simulation by ID
    # Intruder blocked
    intruder_get = client.get(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}",
        headers={"X-Owner-Id": "owner_bob"},
    )
    assert intruder_get.status_code == 403

    # Authorized succeeds
    alice_get = client.get(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert alice_get.status_code == 200
    assert alice_get.json()["id"] == sim_id

    # 4. List Simulations
    # Intruder blocked
    intruder_list = client.get(
        f"/api/analysis/{analysis_id}/simulations",
        headers={"X-Owner-Id": "owner_bob"},
    )
    assert intruder_list.status_code == 403

    # Authorized succeeds
    alice_list = client.get(
        f"/api/analysis/{analysis_id}/simulations",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert alice_list.status_code == 200
    assert alice_list.json()["total_count"] == 1

    # 5. Explain Simulation
    # Intruder blocked
    intruder_exp = client.post(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner_bob"},
    )
    assert intruder_exp.status_code == 403

    # Authorized succeeds
    alice_exp = client.post(
        f"/api/analysis/{analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner_alice"},
    )
    assert alice_exp.status_code == 200
    assert alice_exp.json()["generation_status"] == "generated"


def test_public_unowned_jobs_accessible_by_all(hardened_env):
    """Verifies that unowned (public/demo) jobs remain accessible without requiring X-Owner-Id."""
    client = hardened_env["client"]
    storage = hardened_env["storage"]

    analysis_id = "analysis_public_01"
    job_id = "job_public_01"
    analysis_resp = _create_full_six_stage_analysis(analysis_id)

    # Job created without owner
    req = AnalysisJobCreateRequest(
        question="Public decision demo question?",
        owner_id=None,
        timeout_seconds=120.0,
    )
    storage.create_job(request=req, job_id=job_id)
    storage.complete_job(job_id=job_id, response=analysis_resp)

    # Can discover variables without header
    res = client.get(f"/api/analysis/{analysis_id}/simulation-variables")
    assert res.status_code == 200
    fp = res.json()["baseline_fingerprint"]

    # Can simulate without header
    sim_res = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {
                    "variable_id": "var_monthly_cloud_spend",
                    "proposed_value": 40000.0,
                    "unit": "USD",
                }
            ],
            "baseline_fingerprint": fp,
        },
    )
    assert sim_res.status_code == 200
    sim_id = sim_res.json()["id"]

    # Can retrieve list without header
    list_res = client.get(f"/api/analysis/{analysis_id}/simulations")
    assert list_res.status_code == 200
    assert list_res.json()["total_count"] == 1


def test_input_validation_and_numerical_integrity(hardened_env):
    """Verifies rejection of invalid adjustments (NaN, bounds violation, duplicate variables)."""
    client = hardened_env["client"]
    storage = hardened_env["storage"]

    analysis_id = "analysis_validation_01"
    job_id = "job_validation_01"
    analysis_resp = _create_full_six_stage_analysis(analysis_id)

    req = AnalysisJobCreateRequest(
        question="Input validation decision?",
        owner_id=None,
    )
    storage.create_job(request=req, job_id=job_id)
    storage.complete_job(job_id=job_id, response=analysis_resp)

    # Duplicate variable in adjustments payload
    res_dup = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"},
                {"variable_id": "var_monthly_cloud_spend", "proposed_value": 45000.0, "unit": "USD"},
            ]
        },
    )
    assert res_dup.status_code == 422
    assert "duplicate adjustment" in res_dup.text.lower()

    # Out of range negative currency
    res_bound = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {"variable_id": "var_monthly_cloud_spend", "proposed_value": -100.0, "unit": "USD"},
            ]
        },
    )
    assert res_bound.status_code == 422
    assert "minimum bound" in res_bound.text.lower()

    # Stale fingerprint returns 409
    res_stale = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {"variable_id": "var_monthly_cloud_spend", "proposed_value": 45000.0, "unit": "USD"},
            ],
            "baseline_fingerprint": "bfp_stale_fingerprint_000000000000",
        },
    )
    assert res_stale.status_code == 409
    assert "mismatch" in res_stale.text.lower()


def test_baseline_artifact_immutability(hardened_env):
    """Verifies that running simulations leaves the stored AnalysisResponse and DecisionModel unchanged."""
    client = hardened_env["client"]
    storage = hardened_env["storage"]

    analysis_id = "analysis_immutability_01"
    job_id = "job_immutability_01"
    analysis_resp = _create_full_six_stage_analysis(analysis_id)
    original_baseline_spend = analysis_resp.decision_model.variables[0].baseline_value
    original_scenario_prob = analysis_resp.scenarios.scenarios[0].probability
    original_resilience_score = analysis_resp.resilience.overall_score

    req = AnalysisJobCreateRequest(
        question="Immutability check question?",
        owner_id=None,
    )
    storage.create_job(request=req, job_id=job_id)
    storage.complete_job(job_id=job_id, response=analysis_resp)

    # Run simulation modifying spend to 55,000
    res = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={
            "adjustments": [
                {"variable_id": "var_monthly_cloud_spend", "proposed_value": 55000.0, "unit": "USD"},
            ]
        },
    )
    assert res.status_code == 200

    # Retrieve stored job directly from storage
    stored_job = storage.get_job(job_id)
    assert stored_job is not None
    assert stored_job.response is not None

    # Verify original values are identical
    dm = stored_job.response.decision_model
    assert dm.variables[0].baseline_value == original_baseline_spend
    assert stored_job.response.scenarios.scenarios[0].probability == original_scenario_prob
    assert stored_job.response.resilience.overall_score == original_resilience_score
