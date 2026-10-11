"""Phase 6B Integration Tests: Resilience Engine Pipeline Integration.

Comprehensive, deterministic verification covering:
1. Successful six-stage execution (Decision Framer -> Evidence Engine -> AI Boardroom -> Recommendation -> Scenarios -> Resilience).
2. Correct authoritative input handoff (exact non-mutated upstream artifacts, referential integrity).
3. Deterministic scoring with no LLM call during Stage 6.
4. Stage 6 lifecycle and progress reporting (stage6_resilience -> completed).
5. Stage 5 failure causing Stage 6 skip (safe dependency explanation, partial_success).
6. Stage 6 calculation failure and partial success (sanitized error, no fabricated score).
7. Parent deadline expired before Stage 6 (controlled monotonic clock, partial_success).
8. Preservation of Stages 1–5 artifacts.
9. SQLite persistence and restart retrieval.
10. Historical response compatibility (4-stage and 5-stage records without resilience fields).
11. API response compatibility (synchronous /api/analyze and async /api/analysis/jobs).
12. Repeatable resilience report ID for identical inputs (SHA-256 deterministic ID).
"""

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
from app.services.analysis_service import AnalysisService, AnalysisTimeoutError
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient
from app.services.scenario.service import ScenarioService
from app.services.scenario.validator import ScenarioEvaluationError


# ------------------------------------------------------------------------------
# 1. Successful Six-Stage Execution
# ------------------------------------------------------------------------------

def test_01_successful_six_stage_execution():
    """Verify standard analysis request executes across all 6 stages and returns valid ResilienceReport."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we migrate from a monolithic database to a distributed architecture?",
        context={"team_size": 30, "latency_sla_ms": 50},
        constraints=["Zero downtime migration", "Budget capped at $150k"],
    )

    stage_events: List[str] = []

    def _tracker(stage_name: str) -> None:
        stage_events.append(stage_name)

    response = service.analyze(req, stage_callback=_tracker)

    # 1. Verify all 6 stage callbacks were invoked in exact order
    assert stage_events == [
        "stage1_decision_framer",
        "stage2_evidence_engine",
        "stage3_ai_boardroom",
        "stage4_recommendation",
        "stage5_scenarios",
        "stage6_resilience",
    ]

    # 2. Verify all six stages returned authoritative artifacts
    assert response.status == "completed"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert response.recommendation_status == "completed"
    assert response.recommendation_error is None

    assert response.scenarios is not None
    assert isinstance(response.scenarios, ScenarioSet)
    assert response.scenario_status == "completed"
    assert response.scenario_error is None

    assert response.resilience is not None
    assert isinstance(response.resilience, ResilienceReport)
    assert response.resilience_status == "completed"
    assert response.resilience_error is None

    # 3. Verify resilience report invariants
    report = response.resilience
    assert 0.0 <= report.overall_score <= 100.0
    assert report.rating in [
        ResilienceRating.HIGH,
        ResilienceRating.MODERATE,
        ResilienceRating.FRAGILE,
        ResilienceRating.VULNERABLE,
    ]
    assert len(report.sub_scores) == 4
    for sub in report.sub_scores:
        assert 0.0 <= sub.score <= sub.max_score
        assert sub.rationale != ""
    assert isinstance(report.critical_vulnerabilities, list)
    assert isinstance(report.stress_test_passed, bool)
    assert isinstance(report.recommended_hedges, list)
    assert len(report.recommended_hedges) > 0
    assert report.calculation_version == "1.0.0"

    # 4. Message contains completion confirmation
    assert "decision resilience evaluation completed successfully" in response.message.lower()


# ------------------------------------------------------------------------------
# 2. Correct Authoritative Input Handoff
# ------------------------------------------------------------------------------

def test_02_correct_authoritative_input_handoff():
    """Verify evaluate_resilience receives exact, non-mutated upstream artifacts."""
    received_args: Dict[str, Any] = {}

    import app.services.analysis_service as as_module
    original_eval = as_module.evaluate_resilience

    def _spy_evaluate_resilience(*args, **kwargs):
        received_args.update(kwargs)
        return original_eval(*args, **kwargs)

    with patch.object(as_module, "evaluate_resilience", side_effect=_spy_evaluate_resilience):
        service = AnalysisService()
        req = AnalysisRequest(question="Should we expand our cloud footprint to Europe?")
        response = service.analyze(req)

    assert response.status == "completed"
    assert received_args["decision_model"] is response.decision_model
    assert received_args["scenario_set"] is response.scenarios
    assert received_args["recommendation"] is response.recommendation
    assert received_args["evidence_package"] is response.evidence_package
    assert received_args["reasoning_board"] is response.reasoning_board

    # Referential integrity bindings
    assert response.resilience is not None
    assert response.resilience.decision_model_id == response.decision_model.id
    assert response.resilience.scenario_set_id == response.scenarios.id
    assert response.resilience.recommendation_id == response.recommendation.id


# ------------------------------------------------------------------------------
# 3. Deterministic Scoring With No LLM Call
# ------------------------------------------------------------------------------

def test_03_deterministic_scoring_with_no_llm_call():
    """Verify that Stage 6 execution does not invoke any LLM or search calls."""
    service = AnalysisService()
    fake_client = service.get_default_client()
    initial_llm_calls = len(getattr(fake_client, "history", []))

    stage_events: List[str] = []
    llm_calls_at_stage6_entry = -1

    def _tracker(stage_name: str) -> None:
        nonlocal llm_calls_at_stage6_entry
        stage_events.append(stage_name)
        if stage_name == "stage6_resilience":
            llm_calls_at_stage6_entry = len(getattr(fake_client, "history", []))

    response = service.analyze(
        AnalysisRequest(question="Should we adopt GraphQL over REST?"),
        stage_callback=_tracker,
    )

    llm_calls_at_completion = len(getattr(fake_client, "history", []))

    assert "stage6_resilience" in stage_events
    assert llm_calls_at_stage6_entry >= 0
    # Exactly zero LLM calls during Stage 6
    assert llm_calls_at_completion == llm_calls_at_stage6_entry
    assert response.resilience is not None


# ------------------------------------------------------------------------------
# 4. Stage 6 Lifecycle and Progress Reporting
# ------------------------------------------------------------------------------

def test_04_stage6_lifecycle_and_progress_reporting(tmp_path):
    """Verify stage6_resilience appears during asynchronous execution and updates job state."""
    db_file = str(tmp_path / "test_lifecycle_stage6.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)

    recorded_stages: List[PipelineStage] = []
    original_update_stage = storage.update_stage

    def _spy_update_stage(jid: str, stg: PipelineStage, msg: str) -> None:
        recorded_stages.append(stg)
        original_update_stage(jid, stg, msg)

    storage.update_stage = _spy_update_stage

    req = AnalysisJobCreateRequest(
        question="Should we replace our message broker with Apache Kafka?",
    )
    job_status_resp = manager.submit_job(req)
    job_id = job_status_resp.job_id

    assert job_status_resp.status == JobStatus.QUEUED
    assert job_status_resp.stage == PipelineStage.QUEUED

    # Poll until completed
    max_wait = 10.0
    start = time.time()
    current = manager.get_job_status(job_id)

    while current.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.01)
        current = manager.get_job_status(job_id)

    assert current.status == JobStatus.SUCCEEDED
    assert current.stage == PipelineStage.COMPLETED
    assert PipelineStage.STAGE6_RESILIENCE in recorded_stages

    # Verify result retrieval contains resilience
    result = manager.get_job_result(job_id)
    assert result.status == "completed"
    assert result.resilience is not None
    assert result.resilience_status == "completed"
    assert result.resilience_error is None
    storage.close()


# ------------------------------------------------------------------------------
# 5. Stage 5 Failure Causing Stage 6 Skip
# ------------------------------------------------------------------------------

def test_05_stage5_failure_causes_stage6_skip():
    """Verify that Stage 5 failure skips Stage 6, preserves Stages 1-4, and sets partial_success."""
    class FailingScenarioService(ScenarioService):
        def generate_scenarios(self, *args, **kwargs):
            raise ScenarioEvaluationError("Scenario simulation failed due to LLM provider outage.")

    failing_service = FailingScenarioService.create_default(llm_client=FakeLLMClient())
    service = AnalysisService(scenario_service=failing_service)

    req = AnalysisRequest(question="Should we invest in quantum computing research?")
    response = service.analyze(req)

    # Partial success
    assert response.status == "partial_success"

    # Upstream Stages 1-4 preserved
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert response.recommendation_status == "completed"

    # Stage 5 unavailable
    assert response.scenarios is None
    assert response.scenario_status == "unavailable"
    assert "Scenario simulation failed" in (response.scenario_error or "")

    # Stage 6 skipped due to dependency policy
    assert response.resilience is None
    assert response.resilience_status == "unavailable"
    assert response.resilience_error == "Stage 6 resilience evaluation skipped: prerequisite Stage 5 scenarios were unavailable."


# ------------------------------------------------------------------------------
# 6. Stage 6 Calculation Failure and Partial Success
# ------------------------------------------------------------------------------

def test_06_stage6_calculation_failure_partial_success():
    """Verify that if evaluate_resilience raises an error, Stages 1-5 are preserved as partial_success."""
    import app.services.analysis_service as as_module

    def _failing_evaluate_resilience(*args, **kwargs):
        raise ValueError("Simulated mathematical constraint bounds violation in engine.")

    with patch.object(as_module, "evaluate_resilience", side_effect=_failing_evaluate_resilience):
        service = AnalysisService()
        req = AnalysisRequest(question="Should we refactor legacy authentication service?")
        response = service.analyze(req)

    # Status must be partial_success
    assert response.status == "partial_success"

    # All Stages 1-5 outputs preserved
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert response.recommendation_status == "completed"
    assert response.scenarios is not None
    assert response.scenario_status == "completed"

    # Stage 6 failed safely
    assert response.resilience is None
    assert response.resilience_status == "unavailable"
    assert "Simulated mathematical constraint bounds violation" in (response.resilience_error or "")
    assert "resilience stage unavailable" in response.message.lower()


# ------------------------------------------------------------------------------
# 7. Parent Deadline Expired Before Stage 6
# ------------------------------------------------------------------------------

def test_07_parent_deadline_expired_before_stage6():
    """Verify that if the monotonic deadline expires before Stage 6, Stage 6 is skipped safely."""
    service = AnalysisService()
    req = AnalysisRequest(question="Should we deprecate the v1 REST API?")

    t_real = time.monotonic()
    deadline = t_real + 100.0
    stage_6_entered = False

    def _stage_spy(stage_name: str) -> None:
        nonlocal stage_6_entered
        if stage_name == "stage6_resilience":
            stage_6_entered = True

    import app.services.analysis_service as as_module
    real_monotonic = as_module.time.monotonic

    def _controlled_monotonic() -> float:
        if stage_6_entered:
            return t_real + 200.0
        return real_monotonic()

    with patch.object(as_module.time, "monotonic", side_effect=_controlled_monotonic):
        response = service.analyze(req, deadline_monotonic=deadline, stage_callback=_stage_spy)

    assert stage_6_entered is True
    assert response.status == "partial_success"
    assert response.scenarios is not None
    assert response.resilience is None
    assert response.resilience_status == "unavailable"
    assert response.resilience_error == "Stage 6 resilience evaluation skipped: global analysis deadline expired."


# ------------------------------------------------------------------------------
# 8. Preservation of Stages 1–5
# ------------------------------------------------------------------------------

def test_08_preservation_of_stages_1_to_5():
    """Verify that both successful and failed Stage 6 runs preserve complete Stages 1-5 outputs."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we migrate to serverless compute for our backend workers?",
        context={"workload": "event-driven", "peak_concurrency": 500},
        constraints=["Cold start latency under 200ms"],
    )

    # 1. Successful run
    resp_success = service.analyze(req)
    assert resp_success.status == "completed"
    assert resp_success.decision_model is not None
    assert resp_success.decision_model.decision.summary != ""
    assert resp_success.evidence_package is not None
    assert resp_success.reasoning_board is not None
    assert len(resp_success.reasoning_board.perspectives) == 4
    assert resp_success.recommendation is not None
    assert resp_success.scenarios is not None
    assert len(resp_success.scenarios.scenarios) == 3
    assert resp_success.resilience is not None

    # 2. Stage 6 failure run
    import app.services.analysis_service as as_module
    with patch.object(as_module, "evaluate_resilience", side_effect=RuntimeError("Transient error")):
        resp_failed_s6 = service.analyze(req)

    assert resp_failed_s6.status == "partial_success"
    assert resp_failed_s6.decision_model is not None
    assert resp_failed_s6.evidence_package is not None
    assert resp_failed_s6.reasoning_board is not None
    assert resp_failed_s6.recommendation is not None
    assert resp_failed_s6.scenarios is not None
    assert resp_failed_s6.resilience is None


# ------------------------------------------------------------------------------
# 9. SQLite Persistence and Restart Retrieval
# ------------------------------------------------------------------------------

def test_09_sqlite_persistence_and_restart_retrieval(tmp_path):
    """Verify that 6-stage AnalysisResponse persists in SQLite and survives restart."""
    db_file = str(tmp_path / "test_persistence_stage6.db")

    # Step 1: Execute job and persist in SQLite
    storage1 = SQLiteJobStorage(db_path=db_file)
    manager1 = AnalysisJobManager(storage=storage1)

    req = AnalysisJobCreateRequest(
        question="Should we invest in building a real-time event streaming platform?",
    )
    job_status = manager1.submit_job(req)
    job_id = job_status.job_id

    # Wait for completion
    max_wait = 10.0
    start = time.time()
    cur = manager1.get_job_status(job_id)
    while cur.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.02)
        cur = manager1.get_job_status(job_id)

    assert cur.status == JobStatus.SUCCEEDED
    storage1.close()

    # Step 2: Simulate complete process restart with fresh storage connection
    storage2 = SQLiteJobStorage(db_path=db_file)
    manager2 = AnalysisJobManager(storage=storage2)

    retrieved_job = storage2.get_job(job_id)
    assert retrieved_job is not None
    assert retrieved_job.status == JobStatus.SUCCEEDED
    assert retrieved_job.stage == PipelineStage.COMPLETED

    res = retrieved_job.response
    assert res is not None
    assert res.status == "completed"

    # Validate resilience was deserialized correctly from response_json
    assert res.resilience is not None
    assert isinstance(res.resilience, ResilienceReport)
    assert res.resilience_status == "completed"
    assert res.resilience_error is None
    assert 0.0 <= res.resilience.overall_score <= 100.0
    assert len(res.resilience.sub_scores) == 4
    assert res.resilience.calculation_version == "1.0.0"

    # Also test manager.get_job_result
    result_from_manager = manager2.get_job_result(job_id)
    assert result_from_manager.resilience is not None
    assert result_from_manager.resilience.id == res.resilience.id

    storage2.close()


# ------------------------------------------------------------------------------
# 10. Historical Response Compatibility
# ------------------------------------------------------------------------------

def test_10_historical_response_compatibility(tmp_path):
    """Verify non-destructive compatibility when reading historical 4-stage and 5-stage jobs."""
    db_file = str(tmp_path / "historical_responses.db")
    storage = SQLiteJobStorage(db_path=db_file)

    base_svc = AnalysisService()
    full_resp = base_svc.analyze(AnalysisRequest(question="Historical analysis compatibility test"))

    # 1. Historical 4-stage response (no scenarios, no resilience)
    four_stage_dict = full_resp.model_dump(mode="json")
    four_stage_dict.pop("scenarios", None)
    four_stage_dict.pop("scenario_status", None)
    four_stage_dict.pop("scenario_error", None)
    four_stage_dict.pop("resilience", None)
    four_stage_dict.pop("resilience_status", None)
    four_stage_dict.pop("resilience_error", None)

    # 2. Historical 5-stage response (has scenarios, but no resilience fields)
    five_stage_dict = full_resp.model_dump(mode="json")
    five_stage_dict.pop("resilience", None)
    five_stage_dict.pop("resilience_status", None)
    five_stage_dict.pop("resilience_error", None)

    # Directly validate with AnalysisResponse
    parsed_4 = AnalysisResponse.model_validate(four_stage_dict)
    assert parsed_4.status == "completed"
    assert parsed_4.recommendation is not None
    assert parsed_4.scenarios is None
    assert parsed_4.resilience is None
    assert parsed_4.resilience_status is None
    assert parsed_4.resilience_error is None

    parsed_5 = AnalysisResponse.model_validate(five_stage_dict)
    assert parsed_5.status == "completed"
    assert parsed_5.scenarios is not None
    assert parsed_5.resilience is None
    assert parsed_5.resilience_status is None
    assert parsed_5.resilience_error is None

    # Insert into database to verify SQLiteJobStorage reading historical rows
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        INSERT INTO analysis_jobs (
            job_id, status, stage, request_json, response_json,
            owner_id, created_at, completed_at, timeout_seconds, progress_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-hist-5stage",
            "succeeded",
            "completed",
            json.dumps({"question": "Historical 5-stage inquiry"}),
            json.dumps(five_stage_dict),
            "owner-test",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            120.0,
            "Completed successfully",
        ),
    )
    conn.commit()
    conn.close()

    hist_record = storage.get_job("job-hist-5stage")
    assert hist_record is not None
    assert hist_record.response is not None
    assert hist_record.response.scenarios is not None
    assert hist_record.response.resilience is None
    assert hist_record.response.resilience_status is None
    assert hist_record.response.resilience_error is None
    storage.close()


# ------------------------------------------------------------------------------
# 11. API Endpoints Compatibility
# ------------------------------------------------------------------------------

def test_11_api_endpoints_compatibility():
    """Verify synchronous POST /api/analyze and async /api/analysis/jobs contracts."""
    client = TestClient(app)

    # 1. Synchronous POST /api/analyze
    sync_resp = client.post(
        "/api/analyze",
        json={"question": "Should we build a centralized design system for all teams?"},
    )
    assert sync_resp.status_code == status.HTTP_200_OK
    data = sync_resp.json()
    assert data["status"] == "completed"
    assert "resilience" in data
    assert data["resilience"] is not None
    assert data["resilience_status"] == "completed"
    assert data["resilience_error"] is None
    assert "overall_score" in data["resilience"]
    assert "sub_scores" in data["resilience"]
    assert len(data["resilience"]["sub_scores"]) == 4

    # 2. Asynchronous POST /api/analysis/jobs
    job_create_resp = client.post(
        "/api/analysis/jobs",
        json={
            "question": "Should we migrate to Rust for performance-critical backend services?",
        },
    )
    assert job_create_resp.status_code == status.HTTP_202_ACCEPTED
    job_id = job_create_resp.json()["job_id"]

    # Poll status
    max_wait = 10.0
    start = time.time()
    status_resp = client.get(f"/api/analysis/jobs/{job_id}")
    while status_resp.json()["status"] in ("queued", "running") and time.time() - start < max_wait:
        time.sleep(0.02)
        status_resp = client.get(f"/api/analysis/jobs/{job_id}")

    assert status_resp.json()["status"] == "succeeded"

    # Retrieve result
    result_resp = client.get(f"/api/analysis/jobs/{job_id}/result")
    assert result_resp.status_code == status.HTTP_200_OK
    res_data = result_resp.json()
    assert res_data["status"] == "completed"
    assert res_data["resilience"] is not None
    assert res_data["resilience_status"] == "completed"
    assert res_data["resilience_error"] is None


# ------------------------------------------------------------------------------
# 12. Repeatable Resilience Report ID for Identical Inputs
# ------------------------------------------------------------------------------

def test_12_repeatable_resilience_report_id_for_identical_inputs():
    """Verify deterministic resilience report ID repeatability for identical inputs."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we implement automated blue-green deployments?",
        context={"environments": ["staging", "prod"]},
        constraints=["Zero downtime"],
    )

    response = service.analyze(req)
    assert response.status == "completed"
    assert response.resilience is not None

    report1 = response.resilience

    # Re-evaluate directly with exact same authoritative inputs
    report2 = evaluate_resilience(
        decision_model=response.decision_model,
        scenario_set=response.scenarios,
        recommendation=response.recommendation,
        evidence_package=response.evidence_package,
        reasoning_board=response.reasoning_board,
    )

    # Identical deterministic IDs
    assert report1.id == report2.id
    assert report1.overall_score == report2.overall_score
    assert report1.rating == report2.rating
    assert report1.id.startswith("res_")
    assert len(report1.id) == 36  # 'res_' + 32 hex chars
