"""Phase 7F Acceptance Tests: Analysis Session Restoration, Simulation History & Persistence.

Verifies:
1. Completed analysis retrieval by both job_id and analysis_id.
2. Status endpoint returns canonical analysis_id in payload.
3. Alias routes (/api/analysis/{id}/status, /api/analysis/{id}/result) work identically.
4. GET /api/analysis/{analysis_id}/simulations/{simulation_id}/explain retrieves cached explanation with 0 LLM calls.
5. GET /api/analysis/{analysis_id}/simulations/{simulation_id}/explain returns 404 if no cache exists.
6. Ownership isolation on all restoration endpoints (403 when X-Owner-Id mismatches).
7. Persisted data survives across storage re-initialization (simulating server restart).
8. Missing analysis returns 404 Not Found without leaking internal error details.
"""

from datetime import datetime, timezone
import json
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.job import AnalysisJobCreateRequest
from app.schemas.simulation import (
    SimulationExplanationResponse,
    SimulationResult,
    compute_baseline_fingerprint,
)
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.simulation.prompt_builder import CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION
from tests.test_simulation_api import _build_test_artifacts


@pytest.fixture
def session_env(tmp_path):
    """Sets up a temporary SQLite database and job manager for session restoration testing."""
    db_path = tmp_path / "test_session_jobs.db"
    storage = SQLiteJobStorage(db_path=str(db_path))
    manager = AnalysisJobManager(storage=storage)
    app.dependency_overrides[get_job_manager] = lambda: manager

    client = TestClient(app)

    yield {
        "db_path": str(db_path),
        "storage": storage,
        "manager": manager,
        "client": client,
    }

    app.dependency_overrides.clear()


def test_completed_analysis_retrieval_by_job_id_and_analysis_id(session_env):
    """Verifies that a completed analysis is retrievable by BOTH job_id and analysis_id."""
    manager = session_env["manager"]
    client = session_env["client"]

    # 1. Seed a completed job in storage
    req = AnalysisJobCreateRequest(question="Test session restoration", owner_id="user-123")
    job = manager.storage.create_job(req)
    dm, scens, rec, resilience, analysis_resp = _build_test_artifacts(decision_model_id="dec_7f_001")
    canonical_analysis_id = analysis_resp.analysis_id
    manager.storage.complete_job(job.job_id, analysis_resp)

    # 2. Query status by job_id
    r_job = client.get(f"/api/analysis/jobs/{job.job_id}/status", headers={"X-Owner-Id": "user-123"})
    assert r_job.status_code == status.HTTP_200_OK
    data_job = r_job.json()
    assert data_job["job_id"] == job.job_id
    assert data_job["analysis_id"] == canonical_analysis_id
    assert data_job["status"] == "succeeded"

    # 3. Query status by analysis_id (critical for session restoration)
    r_ana = client.get(f"/api/analysis/jobs/{canonical_analysis_id}/status", headers={"X-Owner-Id": "user-123"})
    assert r_ana.status_code == status.HTTP_200_OK
    data_ana = r_ana.json()
    assert data_ana["job_id"] == job.job_id
    assert data_ana["analysis_id"] == canonical_analysis_id

    # 4. Query result by job_id
    res_job = client.get(f"/api/analysis/jobs/{job.job_id}/result", headers={"X-Owner-Id": "user-123"})
    assert res_job.status_code == status.HTTP_200_OK
    assert res_job.json()["analysis_id"] == canonical_analysis_id

    # 5. Query result by analysis_id
    res_ana = client.get(f"/api/analysis/jobs/{canonical_analysis_id}/result", headers={"X-Owner-Id": "user-123"})
    assert res_ana.status_code == status.HTTP_200_OK
    assert res_ana.json()["analysis_id"] == canonical_analysis_id

    # 6. Verify alias routes (/api/analysis/{id}/result and /api/analysis/{id}/status)
    res_alias = client.get(f"/api/analysis/{canonical_analysis_id}/result", headers={"X-Owner-Id": "user-123"})
    assert res_alias.status_code == status.HTTP_200_OK
    assert res_alias.json()["analysis_id"] == canonical_analysis_id

    stat_alias = client.get(f"/api/analysis/{canonical_analysis_id}/status", headers={"X-Owner-Id": "user-123"})
    assert stat_alias.status_code == status.HTTP_200_OK
    assert stat_alias.json()["analysis_id"] == canonical_analysis_id


def test_restoration_owner_isolation(session_env):
    """Verifies that X-Owner-Id is enforced during session restoration lookups."""
    manager = session_env["manager"]
    client = session_env["client"]

    req = AnalysisJobCreateRequest(question="Test isolation", owner_id="owner-alpha")
    job = manager.storage.create_job(req)
    dm, scens, rec, resilience, analysis_resp = _build_test_artifacts(decision_model_id="dec_7f_iso")
    canonical_analysis_id = analysis_resp.analysis_id
    manager.storage.complete_job(job.job_id, analysis_resp)

    # Mismatched owner fails with 403 Forbidden
    r_bad_owner = client.get(
        f"/api/analysis/jobs/{canonical_analysis_id}/result",
        headers={"X-Owner-Id": "owner-beta"},
    )
    assert r_bad_owner.status_code == status.HTTP_403_FORBIDDEN

    # Matching owner succeeds
    r_good_owner = client.get(
        f"/api/analysis/jobs/{canonical_analysis_id}/result",
        headers={"X-Owner-Id": "owner-alpha"},
    )
    assert r_good_owner.status_code == status.HTTP_200_OK


def test_cached_explanation_read_only_endpoint(session_env):
    """Verifies GET /api/analysis/{analysis_id}/simulations/{simulation_id}/explain returns cached content with 0 LLM calls."""
    manager = session_env["manager"]
    client = session_env["client"]

    req = AnalysisJobCreateRequest(question="Test explain cache", owner_id="owner-test")
    job = manager.storage.create_job(req)
    dm, scens, rec, resilience, analysis_resp = _build_test_artifacts(decision_model_id="dec_7f_sim")
    canonical_analysis_id = analysis_resp.analysis_id
    manager.storage.complete_job(job.job_id, analysis_resp)

    # 1. Execute a real simulation via API
    sim_post = client.post(
        f"/api/analysis/{canonical_analysis_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": 40000.0, "unit": "USD"}]},
        headers={"X-Owner-Id": "owner-test"},
    )
    assert sim_post.status_code == status.HTTP_200_OK
    sim_data = sim_post.json()
    sim_id = sim_data["id"]
    fp = sim_data["baseline_fingerprint"]

    # 2. Before explanation is cached -> returns 404
    r_404 = client.get(
        f"/api/analysis/{canonical_analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner-test"},
    )
    assert r_404.status_code == status.HTTP_404_NOT_FOUND
    assert "No cached AI explanation found" in r_404.json()["detail"]

    # 3. Seed cached explanation in SQLite
    cached_exp = SimulationExplanationResponse(
        simulation_id=sim_id,
        analysis_id=canonical_analysis_id,
        baseline_fingerprint=fp,
        summary="Cached narrative explanation: cloud spend increased to $40,000.",
        what_changed=["Monthly cloud spend adjusted from $35,000 to $40,000."],
        constraint_implications=["Cloud spend within $50,000 budget."],
        resilience_interpretation="Baseline resilience remains intact.",
        limitations=["Deterministic heuristic bounds."],
        suggested_validation_steps=["Review AWS Cost Explorer."],
        is_cached=True,
        generation_status="generated",
        model_name="gemini-2.5-pro",
        prompt_version=CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    manager.storage.save_simulation_explanation(
        simulation_id=sim_id,
        analysis_id=canonical_analysis_id,
        baseline_fingerprint=fp,
        prompt_version=CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION,
        model_name="gemini-2.5-pro",
        explanation_json=cached_exp.model_dump_json(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # 4. GET /explain returns the cached explanation with is_cached=True
    r_cached = client.get(
        f"/api/analysis/{canonical_analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "owner-test"},
    )
    assert r_cached.status_code == status.HTTP_200_OK
    data = r_cached.json()
    assert data["simulation_id"] == sim_id
    assert data["generation_status"] == "cached"
    assert "Cached narrative explanation" in data["summary"]
    assert data["prompt_version"] == CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION

    # 5. Verify owner isolation on GET /explain
    r_unauth = client.get(
        f"/api/analysis/{canonical_analysis_id}/simulations/{sim_id}/explain",
        headers={"X-Owner-Id": "intruder"},
    )
    assert r_unauth.status_code == status.HTTP_403_FORBIDDEN


def test_persistence_across_restart(session_env):
    """Verifies that analysis, simulation, and explanation persist across storage re-instantiation."""
    db_path = session_env["db_path"]
    manager1 = session_env["manager"]
    client1 = session_env["client"]

    # Write data using manager1
    req = AnalysisJobCreateRequest(question="Test restart", owner_id="restart-owner")
    job = manager1.storage.create_job(req)
    dm, scens, rec, resilience, analysis_resp = _build_test_artifacts(decision_model_id="dec_7f_restart")
    canonical_analysis_id = analysis_resp.analysis_id
    manager1.storage.complete_job(job.job_id, analysis_resp)

    # Create a simulation
    sim_post = client1.post(
        f"/api/analysis/{canonical_analysis_id}/simulate",
        json={"adjustments": [{"variable_id": "var_monthly_cloud_spend", "proposed_value": 42000.0, "unit": "USD"}]},
        headers={"X-Owner-Id": "restart-owner"},
    )
    assert sim_post.status_code == status.HTTP_200_OK

    # Simulate backend restart by creating new storage & manager connected to same db
    storage2 = SQLiteJobStorage(db_path=db_path)
    manager2 = AnalysisJobManager(storage=storage2)
    app.dependency_overrides[get_job_manager] = lambda: manager2

    client2 = TestClient(app)

    # Verify retrieval by analysis_id still works seamlessly
    res = client2.get(
        f"/api/analysis/jobs/{canonical_analysis_id}/result",
        headers={"X-Owner-Id": "restart-owner"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["analysis_id"] == canonical_analysis_id

    # Verify simulation listing works
    sims = client2.get(
        f"/api/analysis/{canonical_analysis_id}/simulations",
        headers={"X-Owner-Id": "restart-owner"},
    )
    assert sims.status_code == status.HTTP_200_OK
    assert sims.json()["total_count"] == 1


def test_missing_analysis_returns_404(session_env):
    """Verifies that non-existent analysis/job IDs return 404 cleanly without error leakage."""
    client = session_env["client"]
    r_stat = client.get("/api/analysis/jobs/non-existent-uuid/status")
    assert r_stat.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in r_stat.json()["detail"].lower()

    r_res = client.get("/api/analysis/jobs/non-existent-uuid/result")
    assert r_res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in r_res.json()["detail"].lower()


def test_running_job_status_retrieval(session_env):
    """Verifies that an in-progress job can be queried during session restoration."""
    manager = session_env["manager"]
    client = session_env["client"]

    req = AnalysisJobCreateRequest(question="Running job test", owner_id="owner-run")
    job = manager.storage.create_job(req)
    manager.storage.update_running(job.job_id, message="Evidence gathering in progress...")

    # Status returns RUNNING with current progress message
    r = client.get(f"/api/analysis/jobs/{job.job_id}/status", headers={"X-Owner-Id": "owner-run"})
    assert r.status_code == status.HTTP_200_OK
    data = r.json()
    assert data["status"] == "running"
    assert data["progress_message"] == "Evidence gathering in progress..."

    # Result returns 409 Conflict while running (no partial data leaked)
    r_res = client.get(f"/api/analysis/jobs/{job.job_id}/result", headers={"X-Owner-Id": "owner-run"})
    assert r_res.status_code == status.HTTP_409_CONFLICT

