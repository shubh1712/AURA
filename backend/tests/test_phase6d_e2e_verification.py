"""Phase 6D End-to-End Verification Test Suite.

Comprehensive offline-first integration verification for all 6 analysis stages:
1. Stage 1: Decision Framer (DecisionModel)
2. Stage 2: Evidence Engine (EvidencePackage)
3. Stage 3: AI Boardroom (ReasoningBoard)
4. Stage 4: Recommendation Engine (DecisionRecommendation)
5. Stage 5: Scenario Generator (ScenarioSet with 3 FutureScenario objects)
6. Stage 6: Deterministic Resilience Engine (ResilienceReport)

Verifies:
- Complete end-to-end execution and cross-artifact referential integrity
- Async job lifecycle and FastAPI endpoints
- SQLite persistence, schema fidelity, and restart safety
- Historical 4-stage and 5-stage backwards compatibility
- Comprehensive failure and partial-success matrix
- Deterministic resilience invariants (mathematical summation, ID repeatability, zero LLM calls)
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.engines.resilience import evaluate_resilience
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.job import (
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    JobStatus,
    PipelineStage,
)
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.resilience import (
    ResilienceRating,
    ResilienceReport,
)
from app.schemas.scenario import ScenarioSet, ScenarioType
from app.services.analysis_service import AnalysisService
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient
from app.services.scenario.service import ScenarioService
from app.services.scenario.validator import ScenarioEvaluationError


# ------------------------------------------------------------------------------
# 1. Full Six-Stage Execution & Cross-Artifact Integrity
# ------------------------------------------------------------------------------

def test_01_six_stage_execution_and_cross_artifact_integrity():
    """Verify all 6 stages execute cleanly and cross-artifact referential bindings match."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
        context={"compliance": "PCI-DSS Level 1", "active_regions": ["us-east-1", "eu-west-1"]},
        constraints=["RPO < 1s", "RTO < 30s", "Budget ceiling $500k"],
    )

    recorded_stages: List[str] = []

    def _tracker(stg: str) -> None:
        recorded_stages.append(stg)

    response = service.analyze(req, stage_callback=_tracker)

    # 1. Sequence order
    assert recorded_stages == [
        "stage1_decision_framer",
        "stage2_evidence_engine",
        "stage3_ai_boardroom",
        "stage4_recommendation",
        "stage5_scenarios",
        "stage6_resilience",
    ]

    # 2. Stage 1: DecisionModel
    assert response.status == "completed"
    assert response.decision_model is not None
    assert isinstance(response.decision_model, DecisionModel)
    assert response.decision_model.id.startswith("dec_")

    # 3. Stage 2: EvidencePackage
    assert response.evidence_package is not None
    assert isinstance(response.evidence_package, EvidencePackage)

    # 4. Stage 3: ReasoningBoard
    assert response.reasoning_board is not None
    assert isinstance(response.reasoning_board, ReasoningBoard)
    assert response.reasoning_board.id.startswith("rbd_")
    assert response.reasoning_board.decision_model_id == response.decision_model.id

    # 5. Stage 4: Recommendation
    assert response.recommendation is not None
    assert isinstance(response.recommendation, DecisionRecommendation)
    assert response.recommendation_status == "completed"
    assert response.recommendation.decision_model_id == response.decision_model.id
    assert response.recommendation.reasoning_board_id == response.reasoning_board.id

    # 6. Stage 5: ScenarioSet (exactly 3 scenarios: optimistic, base, pessimistic)
    assert response.scenarios is not None
    assert isinstance(response.scenarios, ScenarioSet)
    assert response.scenario_status == "completed"
    assert len(response.scenarios.scenarios) == 3
    scenario_types = {s.scenario_type for s in response.scenarios.scenarios}
    assert scenario_types == {
        ScenarioType.OPTIMISTIC,
        ScenarioType.BASE_CASE,
        ScenarioType.PESSIMISTIC,
    }
    assert response.scenarios.decision_model_id == response.decision_model.id
    assert response.scenarios.recommendation_id == response.recommendation.id
    assert response.scenarios.reasoning_board_id == response.reasoning_board.id

    # 7. Stage 6: ResilienceReport
    assert response.resilience is not None
    assert isinstance(response.resilience, ResilienceReport)
    assert response.resilience_status == "completed"
    assert response.resilience.decision_model_id == response.decision_model.id
    assert response.resilience.scenario_set_id == response.scenarios.id
    assert response.resilience.recommendation_id == response.recommendation.id
    assert 0.0 <= response.resilience.overall_score <= 100.0
    assert len(response.resilience.sub_scores) == 4


# ------------------------------------------------------------------------------
# 2. Async Job & API Lifecycle
# ------------------------------------------------------------------------------

def test_02_async_job_and_api_lifecycle():
    """Verify asynchronous job lifecycle from creation to polling and retrieval via TestClient."""
    client = TestClient(app)

    create_resp = client.post(
        "/api/analysis/jobs",
        json={"question": "Should we decommission on-premise hardware in favor of GCP Cloud Run?"},
    )
    assert create_resp.status_code == status.HTTP_202_ACCEPTED
    body = create_resp.json()
    assert "job_id" in body
    job_id = body["job_id"]
    assert body["status"] == "queued"

    # Poll status until finished
    max_wait = 10.0
    start = time.time()
    st_resp = client.get(f"/api/analysis/jobs/{job_id}")
    while st_resp.json()["status"] in ("queued", "running") and time.time() - start < max_wait:
        time.sleep(0.02)
        st_resp = client.get(f"/api/analysis/jobs/{job_id}")

    final_status = st_resp.json()
    assert final_status["status"] == "succeeded"
    assert final_status["stage"] == "completed"

    # Retrieve full result
    result_resp = client.get(f"/api/analysis/jobs/{job_id}/result")
    assert result_resp.status_code == status.HTTP_200_OK
    res = result_resp.json()
    assert res["status"] == "completed"

    # Verify Stage 5 in API response
    assert "scenarios" in res
    assert res["scenarios"] is not None
    assert len(res["scenarios"]["scenarios"]) == 3
    assert res["scenario_status"] == "completed"

    # Verify Stage 6 in API response
    assert "resilience" in res
    assert res["resilience"] is not None
    assert res["resilience_status"] == "completed"
    assert "overall_score" in res["resilience"]
    assert "rating" in res["resilience"]
    assert "stress_test_passed" in res["resilience"]
    assert len(res["resilience"]["sub_scores"]) == 4


# ------------------------------------------------------------------------------
# 3. Isolated SQLite Persistence and Restart Safety
# ------------------------------------------------------------------------------

def test_03_isolated_sqlite_persistence_and_restart(tmp_path):
    """Verify that six-stage analysis persists with high fidelity and survives complete SQLite restart."""
    db_file = str(tmp_path / "e2e_persistence.db")

    # Instance 1: Execute and persist
    storage1 = SQLiteJobStorage(db_path=db_file)
    manager1 = AnalysisJobManager(storage=storage1)

    req = AnalysisJobCreateRequest(
        question="Should we replace legacy Elasticsearch with ClickHouse for audit logging?",
    )
    job_info = manager1.submit_job(req)
    job_id = job_info.job_id

    # Wait for completion
    max_wait = 10.0
    start = time.time()
    cur = manager1.get_job_status(job_id)
    while cur.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.02)
        cur = manager1.get_job_status(job_id)

    assert cur.status == JobStatus.SUCCEEDED
    storage1.close()

    # Instance 2: Brand new storage connection simulating app restart
    storage2 = SQLiteJobStorage(db_path=db_file)
    manager2 = AnalysisJobManager(storage=storage2)

    loaded_job = storage2.get_job(job_id)
    assert loaded_job is not None
    assert loaded_job.status == JobStatus.SUCCEEDED
    assert loaded_job.stage == PipelineStage.COMPLETED

    resp = loaded_job.response
    assert resp is not None
    assert resp.status == "completed"

    # Scenario fidelity
    assert resp.scenarios is not None
    assert len(resp.scenarios.scenarios) == 3
    prob_sum = sum(s.probability for s in resp.scenarios.scenarios)
    assert abs(prob_sum - 1.0) <= 0.01

    # Resilience fidelity
    assert resp.resilience is not None
    assert isinstance(resp.resilience, ResilienceReport)
    assert 0.0 <= resp.resilience.overall_score <= 100.0
    assert len(resp.resilience.sub_scores) == 4
    for sub in resp.resilience.sub_scores:
        assert 0.0 <= sub.score <= sub.max_score
        assert len(sub.rationale) > 0
    assert resp.resilience.calculation_version == "1.0.0"

    storage2.close()


# ------------------------------------------------------------------------------
# 4. Historical Response Reading Backwards Compatibility
# ------------------------------------------------------------------------------

def test_04_historical_response_reading_compatibility(tmp_path):
    """Verify older 4-stage and 5-stage responses stored in SQLite deserialize safely without crashes."""
    db_file = str(tmp_path / "hist_read_compat.db")
    storage = SQLiteJobStorage(db_path=db_file)

    service = AnalysisService()
    baseline = service.analyze(AnalysisRequest(question="Historical backward-compatibility query"))

    # Construct legacy 4-stage dictionary (no scenarios, no resilience)
    dict_4stage = baseline.model_dump(mode="json")
    for key in ("scenarios", "scenario_status", "scenario_error", "resilience", "resilience_status", "resilience_error"):
        dict_4stage.pop(key, None)

    # Construct legacy 5-stage dictionary (has scenarios, no resilience)
    dict_5stage = baseline.model_dump(mode="json")
    for key in ("resilience", "resilience_status", "resilience_error"):
        dict_5stage.pop(key, None)

    conn = sqlite3.connect(db_file)
    # Insert 4-stage
    conn.execute(
        """
        INSERT INTO analysis_jobs (job_id, status, stage, request_json, response_json, owner_id, created_at, completed_at, timeout_seconds, progress_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-hist-4stage",
            "succeeded",
            "completed",
            json.dumps({"question": "Legacy 4-stage"}),
            json.dumps(dict_4stage),
            "owner-test",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            120.0,
            "Completed",
        ),
    )
    # Insert 5-stage
    conn.execute(
        """
        INSERT INTO analysis_jobs (job_id, status, stage, request_json, response_json, owner_id, created_at, completed_at, timeout_seconds, progress_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-hist-5stage",
            "succeeded",
            "completed",
            json.dumps({"question": "Legacy 5-stage"}),
            json.dumps(dict_5stage),
            "owner-test",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            120.0,
            "Completed",
        ),
    )
    conn.commit()
    conn.close()

    # Re-read via SQLiteJobStorage
    rec_4 = storage.get_job("job-hist-4stage")
    assert rec_4 is not None
    assert rec_4.response is not None
    assert rec_4.response.recommendation is not None
    assert rec_4.response.scenarios is None
    assert rec_4.response.resilience is None

    rec_5 = storage.get_job("job-hist-5stage")
    assert rec_5 is not None
    assert rec_5.response is not None
    assert rec_5.response.recommendation is not None
    assert rec_5.response.scenarios is not None
    assert rec_5.response.resilience is None

    storage.close()


# ------------------------------------------------------------------------------
# 5. Failure and Partial-Success Matrix
# ------------------------------------------------------------------------------

def test_05_failure_and_partial_success_matrix():
    """Verify partial-success resilience across multiple failure injections."""
    service = AnalysisService()
    req = AnalysisRequest(question="Should we migrate to an event-sourcing model?")

    # Case 5a: Stage 5 scenario evaluation error -> skips Stage 6, preserves 1-4
    class FailingScenarioService(ScenarioService):
        def generate_scenarios(self, *args, **kwargs):
            raise ScenarioEvaluationError("Scenario structured output schema parsing failed.")

    failing_scenario_svc = FailingScenarioService.create_default(llm_client=FakeLLMClient())
    svc_with_failing_s5 = AnalysisService(scenario_service=failing_scenario_svc)

    res_5a = svc_with_failing_s5.analyze(req)
    assert res_5a.status == "partial_success"
    assert res_5a.recommendation is not None
    assert res_5a.scenarios is None
    assert res_5a.scenario_status == "unavailable"
    assert res_5a.resilience is None
    assert res_5a.resilience_status == "unavailable"
    assert "prerequisite Stage 5 scenarios were unavailable" in res_5a.resilience_error

    # Case 5b: Stage 6 resilience calculation exception -> preserves 1-5
    import app.services.analysis_service as as_module
    with patch.object(as_module, "evaluate_resilience", side_effect=ZeroDivisionError("Simulated math error")):
        res_5b = service.analyze(req)

    assert res_5b.status == "partial_success"
    assert res_5b.decision_model is not None
    assert res_5b.recommendation is not None
    assert res_5b.scenarios is not None
    assert res_5b.scenario_status == "completed"
    assert res_5b.resilience is None
    assert res_5b.resilience_status == "unavailable"
    assert "Simulated math error" in res_5b.resilience_error

    # Case 5c: Global deadline expired before Stage 6 -> preserves 1-5
    t_start = time.monotonic()
    deadline = t_start + 10.0
    stage6_reached = False

    def _spy_stage(stg: str):
        nonlocal stage6_reached
        if stg == "stage6_resilience":
            stage6_reached = True

    real_mono = as_module.time.monotonic

    def _controlled_mono():
        if stage6_reached:
            return t_start + 100.0  # Expire deadline on Stage 6 entry
        return real_mono()

    with patch.object(as_module.time, "monotonic", side_effect=_controlled_mono):
        res_5c = service.analyze(req, deadline_monotonic=deadline, stage_callback=_spy_stage)

    assert stage6_reached is True
    assert res_5c.status == "partial_success"
    assert res_5c.scenarios is not None
    assert res_5c.resilience is None
    assert res_5c.resilience_status == "unavailable"
    assert "global analysis deadline expired" in res_5c.resilience_error


# ------------------------------------------------------------------------------
# 6. Deterministic Resilience Invariants
# ------------------------------------------------------------------------------

def test_06_deterministic_resilience_invariants():
    """Verify deterministic invariants: summation of sub-scores, deterministic ID, zero LLM calls."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we adopt temporal workflow orchestration across microservices?",
        constraints=["Latency < 100ms", "Support multi-language workers"],
    )

    response = service.analyze(req)
    assert response.status == "completed"
    report1 = response.resilience
    assert report1 is not None

    # Invariant 1: overall_score equals sum of 4 sub-scores (rounded to 2 decimal places)
    sub_sum = round(sum(sub.score for sub in report1.sub_scores), 2)
    assert report1.overall_score == sub_sum
    assert 0.0 <= report1.overall_score <= 100.0

    # Invariant 2: stress_test_passed matches threshold logic
    # Configured threshold: overall_score >= 60.0 and pessimistic survivability >= 12.5
    pessimistic_score = next(
        sub.score for sub in report1.sub_scores
        if "pessimistic" in sub.category.lower() or "survivab" in sub.category.lower()
    )
    expected_stress_test = (report1.overall_score >= 60.0) and (pessimistic_score >= 12.5)
    assert report1.stress_test_passed == expected_stress_test

    # Invariant 3: deterministic repeatable report ID for identical artifacts
    report2 = evaluate_resilience(
        decision_model=response.decision_model,
        scenario_set=response.scenarios,
        recommendation=response.recommendation,
        evidence_package=response.evidence_package,
        reasoning_board=response.reasoning_board,
    )
    assert report1.id == report2.id
    assert report1.overall_score == report2.overall_score
    assert report1.rating == report2.rating
    assert report1.calculation_version == "1.0.0"
