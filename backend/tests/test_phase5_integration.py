"""Phase 5 Integration Tests: Pipeline Integration, Persistence & API for Stage 4.

Deterministic verification covering:
1. Successful four-stage execution.
2. Correct Stage 4 input artifacts (binding IDs, non-mutated upstream artifacts).
3. Recommendation schema serialization and deserialization round-trip.
4. SQLite persistence round-trip through AnalysisJobManager and SQLiteJobStorage.
5. Historical Day 4 job compatibility (missing columns/fields, non-destructive migration).
6. Stage 4 timeout preserves Boardroom output as partial_success.
7. Stage 4 malformed LLM output preserves Boardroom output.
8. Stage 4 failure with preserved Boardroom perspectives, disagreements, and synthesis.
9. Correct partial-success status reporting through async job lifecycle and API endpoints.
10. Global deadline propagation and budget exhaustion handling.
11. Existing Day 4 API compatibility (requests without recommendation timeout fields).
"""

from datetime import datetime, timezone
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
import pytest
from fastapi import status
from fastapi.testclient import TestClient

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
from app.schemas.recommendation import (
    ActionPriority,
    ActionTimeHorizon,
    CandidateActionItem,
    CandidateActionPlan,
    CandidateAlternativeOption,
    CandidateDecisionRecommendation,
    CandidateUncertaintyAssessment,
    DecisionReadiness,
    DecisionRecommendation,
    DecisionStatus,
    EvidenceStrength,
    RecommendationStability,
)
from app.services.analysis_service import AnalysisService
from app.services.evidence import FakeSearchProvider
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.recommendation.service import RecommendationService
from app.services.recommendation.validator import RecommendationServiceError


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------

def build_valid_candidate() -> CandidateDecisionRecommendation:
    """Builds a semantically sound CandidateDecisionRecommendation with empty references for mock tests."""
    return CandidateDecisionRecommendation(
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Execute phased integration across core systems.",
        executive_rationale="Empirical indicators and strategic goals align with execution under milestone checkpoints.",
        supporting_evidence_item_ids=[],
        relevant_assumption_ids=[],
        relevant_evidence_gap_ids=[],
        unresolved_disagreement_ids=[],
        alternative_options=[
            CandidateAlternativeOption(
                name="Defer Indefinitely",
                description="Take no immediate action and preserve working capital.",
                tradeoffs=["Preserves cash", "Loses strategic market window"],
                why_not_recommended="Fails to satisfy primary growth objectives.",
            )
        ],
        uncertainty_assessment=CandidateUncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
            critical_missing_information=[],
            conditions_changing_recommendation=[],
            assumptions_relied_upon=[],
            evidence_gaps_relied_upon=[],
        ),
        action_plan=CandidateActionPlan(
            summary="Three-stage rollout plan with validation gates.",
            actions=[
                CandidateActionItem(
                    title="Pilot Validation",
                    objective="Verify core operational parameters",
                    description="Run controlled pilot across selected segments.",
                    priority=ActionPriority.HIGH,
                    responsible_role="Project Lead",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    dependencies=[],
                    success_metrics=["Pilot milestones achieved"],
                    risk_mitigations=["Regular checkpoints"],
                    decision_gates=[],
                    fallback_action="Halt and review",
                )
            ],
            key_milestones=["Milestone 1", "Milestone 2"],
        ),
    )


# ------------------------------------------------------------------------------
# 1. Successful Four-Stage Execution
# ------------------------------------------------------------------------------

def test_01_successful_four_stage_execution():
    """Verify that AnalysisService.analyze completes all 4 pipeline stages with recommendation."""
    stage_events: List[str] = []

    def stage_cb(stage: str) -> None:
        stage_events.append(stage)

    service = AnalysisService()
    req = AnalysisRequest(question="Should we migrate backend systems to Rust?")

    response = service.analyze(req, stage_callback=stage_cb)

    assert response.status == "completed"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert isinstance(response.recommendation, DecisionRecommendation)
    assert response.recommendation_status == "completed"
    assert response.recommendation_error is None

    # Verify stage progression across all 4 stages
    assert "stage1_decision_framer" in stage_events
    assert "stage2_evidence_engine" in stage_events
    assert "stage3_ai_boardroom" in stage_events
    assert "stage4_recommendation" in stage_events


# ------------------------------------------------------------------------------
# 2. Correct Stage 4 Input Artifacts
# ------------------------------------------------------------------------------

def test_02_correct_stage_4_input_artifacts():
    """Verify Stage 4 recommendation consumes and binds to validated Stage 1-3 artifacts."""
    service = AnalysisService()
    req = AnalysisRequest(question="Should we launch an enterprise tier?")

    response = service.analyze(req)

    rec = response.recommendation
    assert rec is not None
    # Referential binding to upstream IDs
    assert rec.decision_model_id == response.decision_model.id
    assert rec.evidence_package_id == response.evidence_package.id
    assert rec.reasoning_board_id == response.reasoning_board.id

    # Verify upstream artifacts remain intact and valid
    assert response.decision_model.decision.raw_prompt == req.question
    assert len(response.reasoning_board.perspectives) == 4
    assert response.reasoning_board.synthesis is not None


# ------------------------------------------------------------------------------
# 3. Recommendation Schema Serialization Round-Trip
# ------------------------------------------------------------------------------

def test_03_recommendation_schema_serialization():
    """Verify AnalysisResponse with recommendation survives full JSON serialization round-trip."""
    service = AnalysisService()
    req = AnalysisRequest(question="Should we expand international operations?")

    response = service.analyze(req)
    assert response.recommendation is not None

    dumped_json = response.model_dump_json()
    reloaded = AnalysisResponse.model_validate_json(dumped_json)

    assert reloaded.status == response.status
    assert reloaded.recommendation_status == "completed"
    assert reloaded.recommendation is not None
    assert reloaded.recommendation.id == response.recommendation.id
    assert reloaded.recommendation.decision_status == response.recommendation.decision_status
    assert reloaded.recommendation.recommended_action == response.recommendation.recommended_action
    assert len(reloaded.recommendation.action_plan.actions) == len(response.recommendation.action_plan.actions)
    assert reloaded.recommendation.action_plan.actions[0].title == response.recommendation.action_plan.actions[0].title
    assert reloaded.recommendation.uncertainty_assessment.decision_readiness == response.recommendation.uncertainty_assessment.decision_readiness


# ------------------------------------------------------------------------------
# 4. SQLite Persistence Round-Trip
# ------------------------------------------------------------------------------

def test_04_sqlite_persistence_round_trip(tmp_path):
    """Verify async job persistence, recommendation round-trip, and timeout configuration."""
    db_file = str(tmp_path / "test_persistence.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)

    req = AnalysisJobCreateRequest(
        question="Should we restructure engineering squads into pods?",
        recommendation_operation_timeout_seconds=45.0,
    )
    job_resp = manager.submit_job(req)
    job_id = job_resp.job_id

    # Poll until complete
    max_wait = 10.0
    start = time.time()
    job_status = manager.get_job_status(job_id)
    while job_status.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.05)
        job_status = manager.get_job_status(job_id)

    assert job_status.status == JobStatus.SUCCEEDED
    assert job_status.stage == PipelineStage.COMPLETED

    # Retrieve record from storage
    record = storage.get_job(job_id)
    assert record is not None
    assert record.recommendation_timeout_seconds == 45.0
    assert record.response is not None
    assert isinstance(record.response, AnalysisResponse)
    assert record.response.status == "completed"
    assert record.response.recommendation is not None
    assert record.response.recommendation_status == "completed"
    assert record.response.recommendation.decision_model_id == record.response.decision_model.id


# ------------------------------------------------------------------------------
# 5. Historical Day 4 Job Compatibility
# ------------------------------------------------------------------------------

def test_05_historical_day4_job_compatibility(tmp_path):
    """Verify non-destructive migration and backward compatibility with Day 4 database rows."""
    db_file = str(tmp_path / "legacy_day4.db")

    # 1. Create a legacy Day 4 SQLite schema without recommendation_timeout_seconds column
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE analysis_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT,
            error_message TEXT,
            error_status_code INTEGER,
            owner_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            timeout_seconds REAL NOT NULL,
            framer_timeout_seconds REAL,
            boardroom_timeout_seconds REAL,
            progress_message TEXT NOT NULL
        )
    """)

    # 2. Insert a historical Day 4 completed job (no recommendation fields in response_json)
    base_svc = AnalysisService()
    hist_resp = base_svc.analyze(AnalysisRequest(question="Historical Day 4 strategic question"))
    day4_result = hist_resp.model_dump(mode="json")
    day4_result.pop("recommendation", None)
    day4_result.pop("recommendation_status", None)
    day4_result.pop("recommendation_error", None)

    req_data = {
        "question": "Historical Day 4 strategic question",
    }

    conn.execute(
        """
        INSERT INTO analysis_jobs (
            job_id, status, stage, request_json, response_json,
            owner_id, created_at, completed_at, timeout_seconds, progress_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "hist-job-12345",
            "succeeded",
            "stage3_ai_boardroom",
            json.dumps(req_data),
            json.dumps(day4_result),
            "owner_legacy",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            300.0,
            "Completed successfully",
        ),
    )
    conn.commit()
    conn.close()

    # 3. Instantiate SQLiteJobStorage - triggers additive migration safely
    storage = SQLiteJobStorage(db_path=db_file)

    # 4. Read the legacy job back
    record = storage.get_job("hist-job-12345")
    assert record is not None
    assert record.job_id == "hist-job-12345"
    assert record.recommendation_timeout_seconds is None  # Defaults safely
    assert record.response is not None
    assert record.response.status == "completed"
    assert record.response.recommendation is None
    assert record.response.recommendation_status is None
    assert record.response.recommendation_error is None

    # 5. Verify API endpoint serves the historical record cleanly
    client = TestClient(app)
    from app.services.jobs.manager import get_job_manager
    manager = get_job_manager()
    orig_storage = manager.storage
    manager.storage = storage

    try:
        resp = client.get("/api/analysis/jobs/hist-job-12345/result")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["analysis_id"] == day4_result["analysis_id"]
        assert data["status"] == "completed"
        assert data.get("recommendation") is None
        assert data.get("recommendation_status") is None
    finally:
        manager.storage = orig_storage


# ------------------------------------------------------------------------------
# 6. Stage 4 Timeout Preserves Boardroom as Partial Success
# ------------------------------------------------------------------------------

def test_06_stage4_timeout_preserves_boardroom_as_partial_success():
    """Verify that Stage 4 timeout preserves Stages 1-3 and marks recommendation unavailable."""
    fake_llm = FakeLLMClient()
    rec_service = RecommendationService.create_default(llm_client=fake_llm)

    def timeout_generator(*args, **kwargs):
        raise RecommendationServiceError(
            "Recommendation operation timed out: LLM generation exceeded 30.0s.",
            details={"stage": "stage4_recommendation", "timeout_source": "operation"},
        )

    rec_service.generate_recommendation = timeout_generator

    service = AnalysisService(
        llm_client=fake_llm,
        recommendation_service=rec_service,
    )
    req = AnalysisRequest(question="Strategic question with Stage 4 timeout")

    response = service.analyze(req)

    # Crucial failure policy check:
    assert response.status == "partial_success"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"
    assert response.recommendation_error is not None
    assert "timed out" in response.recommendation_error


# ------------------------------------------------------------------------------
# 7. Stage 4 Malformed LLM Output Preserves Boardroom Output
# ------------------------------------------------------------------------------

def test_07_stage4_malformed_llm_output():
    """Verify that candidate validation failure in Stage 4 does not discard Boardroom output."""
    fake_llm = FakeLLMClient()
    rec_service = RecommendationService.create_default(llm_client=fake_llm)

    def malformed_generator(*args, **kwargs):
        raise RecommendationServiceError(
            "Recommendation candidate validation failed: cyclic dependency detected in action plan.",
            details={"stage": "stage4_recommendation", "validation_error": "cycle"},
        )

    rec_service.generate_recommendation = malformed_generator

    service = AnalysisService(
        llm_client=fake_llm,
        recommendation_service=rec_service,
    )
    req = AnalysisRequest(question="Strategic question with malformed Stage 4 candidate")

    response = service.analyze(req)

    assert response.status == "partial_success"
    assert response.decision_model is not None
    assert response.reasoning_board is not None
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"
    assert "validation failed" in response.recommendation_error


# ------------------------------------------------------------------------------
# 8. Stage 4 Failure Preserves Boardroom Perspectives, Disagreements, Synthesis
# ------------------------------------------------------------------------------

def test_08_stage4_failure_preserves_boardroom_output():
    """Verify that Boardroom perspectives, disagreements, and synthesis remain 100% intact on Stage 4 failure."""
    fake_llm = FakeLLMClient()
    rec_service = RecommendationService.create_default(llm_client=fake_llm)

    def failing_generator(*args, **kwargs):
        raise RuntimeError("Unexpected internal engine fault in Stage 4")

    rec_service.generate_recommendation = failing_generator

    service = AnalysisService(
        llm_client=fake_llm,
        recommendation_service=rec_service,
    )
    req = AnalysisRequest(question="Evaluate expansion into new vertical")

    response = service.analyze(req)

    assert response.status == "partial_success"
    rb = response.reasoning_board
    assert rb is not None
    assert len(rb.perspectives) == 4
    assert rb.synthesis is not None
    assert len(rb.synthesis.areas_of_agreement) > 0
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"


# ------------------------------------------------------------------------------
# 9. Correct Partial-Success Status Reporting via Async Job & API
# ------------------------------------------------------------------------------

def test_09_correct_partial_success_status_reporting(tmp_path):
    """Verify that partial success reports JobStatus.SUCCEEDED and yields HTTP 200 with partial_success."""
    db_file = str(tmp_path / "test_partial_job.db")
    storage = SQLiteJobStorage(db_path=db_file)

    fake_llm = FakeLLMClient()
    rec_service = RecommendationService.create_default(llm_client=fake_llm)

    def failing_rec(*args, **kwargs):
        raise RecommendationServiceError(
            "Recommendation LLM call failed.",
            details={"stage": "stage4_recommendation"},
        )

    rec_service.generate_recommendation = failing_rec

    svc = AnalysisService(
        llm_client=fake_llm,
        recommendation_service=rec_service,
    )
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    req = AnalysisJobCreateRequest(question="Will Stage 4 partial success be handled cleanly?")
    job_resp = manager.submit_job(req)
    job_id = job_resp.job_id

    # Wait for completion
    max_wait = 10.0
    start = time.time()
    job_status = manager.get_job_status(job_id)
    while job_status.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.05)
        job_status = manager.get_job_status(job_id)

    # Job status must be SUCCEEDED (not FAILED or 504), allowing the frontend to retrieve the Boardroom output
    assert job_status.status == JobStatus.SUCCEEDED
    assert "recommendation stage unavailable" in job_status.progress_message.lower()

    # Result retrieval
    record = storage.get_job(job_id)
    assert record is not None
    assert record.response is not None
    assert record.response.status == "partial_success"
    assert record.response.recommendation is None
    assert record.response.recommendation_status == "unavailable"
    assert record.response.reasoning_board is not None


# ------------------------------------------------------------------------------
# 10. Global Deadline Propagation
# ------------------------------------------------------------------------------

def test_10_global_deadline_propagation(monkeypatch):
    """Verify that Stage 4 evaluates remaining global analysis deadline and exhausts gracefully."""
    service = AnalysisService()
    req = AnalysisRequest(question="Global deadline test")

    # 1. Set deadline already in the past - fails Stage 1 immediately with 504
    past_deadline = time.monotonic() - 1.0
    with pytest.raises(Exception) as exc_info:
        service.analyze(req, deadline_monotonic=past_deadline)
    assert exc_info.value.status_code == 504

    # 2. Deconstruct upstream and test RecommendationService directly with exhausted deadline
    dm = service.engine.deconstruct(question=req.question)
    ep = service.evidence_service.build_evidence_package(dm)
    rb = service.reasoning_service.build_reasoning_board(decision_model=dm, evidence_package=ep)

    with pytest.raises(RecommendationServiceError) as rec_exc:
        service.recommendation_service.generate_recommendation(
            decision_model=dm,
            evidence_package=ep,
            reasoning_board=rb,
            deadline_monotonic=time.monotonic() - 5.0,
        )
    assert "timed out" in str(rec_exc.value).lower()

    # 3. Test deadline expiring right before Stage 4 in AnalysisService.analyze
    # Use a controlled monotonic clock to deterministically simulate deadline expiration
    # specifically after Stage 3 completes and before Stage 4 starts.
    clock_time = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: clock_time)

    deadline = clock_time + 100.0
    orig_build = service.reasoning_service.build_reasoning_board

    def board_and_expire(*args, **kwargs):
        nonlocal clock_time
        res = orig_build(*args, **kwargs)
        # Advance the controlled clock past the deadline immediately after Stage 3 completes
        clock_time = deadline + 1.0
        return res

    service.reasoning_service.build_reasoning_board = board_and_expire

    response = service.analyze(req, deadline_monotonic=deadline)
    assert response.status == "partial_success"
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"
    assert response.recommendation_error is not None
    assert "deadline" in response.recommendation_error.lower()
    assert response.reasoning_board is not None


# ------------------------------------------------------------------------------
# 11. Existing Day 4 API Compatibility
# ------------------------------------------------------------------------------

def test_11_existing_day4_api_compatibility():
    """Verify that POST /api/analysis/jobs accepts Day 4 payloads without recommendation timeouts."""
    client = TestClient(app)

    # Payload matching Day 4 request format (no recommendation timeout)
    day4_payload = {
        "question": "Should our company expand into new geographical regions?",
        "context": {"current_region": "North America"},
        "constraints": ["Maintain current profit margin"],
        "framer_operation_timeout_seconds": 30.0,
        "evidence_operation_timeout_seconds": 60.0,
        "boardroom_operation_timeout_seconds": 90.0,
        "analysis_timeout_seconds": 300.0,
    }

    resp = client.post("/api/analysis/jobs", json=day4_payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["stage"] == "queued"

    # Poll status
    job_id = data["job_id"]
    status_resp = client.get(f"/api/analysis/jobs/{job_id}")
    assert status_resp.status_code == status.HTTP_200_OK
    status_data = status_resp.json()
    assert status_data["job_id"] == job_id
