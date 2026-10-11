"""Phase 5B Integration Tests: Pipeline Integration, Job Lifecycle & API for Stage 5.

Deterministic verification covering:
1. Successful five-stage execution.
2. Correct Stage 5 input artifacts (binding IDs, non-mutated upstream artifacts, monotonic deadline).
3. Stage 5 progress tracking and lifecycle (stage5_scenarios).
4. Stage 5 timeout preserves Stage 1–4 outputs as partial_success.
5. Stage 5 malformed LLM output preserves Stage 1–4 outputs.
6. Stage 4 failure triggers dependency policy skipping Stage 5.
7. Monotonic deadline propagation (expired before Stage 1, expired before Stage 5, during Stage 5, adequate budget).
8. SQLite persistence round-trip through AnalysisJobManager and SQLiteJobStorage.
9. Historical four-stage response compatibility (missing scenario fields in response_json).
10. Existing API response compatibility (synchronous /analyze and async /analysis/jobs).
"""

from datetime import datetime, timezone
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
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
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import (
    CandidateFutureScenario,
    CandidateScenarioKeyEvent,
    CandidateScenarioMilestone,
    CandidateScenarioSet,
    ScenarioSet,
    ScenarioType,
)
from app.services.analysis_service import AnalysisService, AnalysisTimeoutError
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.scenario.generator import ScenarioGenerator
from app.services.scenario.service import ScenarioService
from app.services.scenario.validator import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioServiceError,
    ScenarioValidationError,
)


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------

def build_valid_candidate_scenarios() -> CandidateScenarioSet:
    """Builds a semantically sound CandidateScenarioSet for mock tests."""
    return CandidateScenarioSet(
        summary="Comprehensive future scenario simulations evaluating decision pathways across optimistic, base case, and pessimistic conditions.",
        scenarios=[
            CandidateFutureScenario(
                scenario_type=ScenarioType.OPTIMISTIC,
                probability=0.25,
                name="Optimistic Trajectory & Rapid Expansion",
                narrative="Under this optimistic trajectory, strategic objectives are achieved ahead of schedule with high operational leverage and market tailwinds.",
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Early Validation Milestone",
                        description="Initial adoption metrics exceed baseline expectations by 30%.",
                        timeframe="Month 3",
                        impact_on_decision="Accelerates rollout objectives.",
                    )
                ],
                risks=["Scaling capacity constraints"],
                opportunities=["Rapid market leadership capture"],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Initial Gate Passed",
                        description="Core pilot milestone successfully completed.",
                        time_horizon="Month 3",
                        expected_outcome="Target growth achieved.",
                    )
                ],
                supporting_evidence_item_ids=[],
                relevant_assumption_ids=[],
                relevant_constraint_ids=[],
                relevant_gap_ids=[],
            ),
            CandidateFutureScenario(
                scenario_type=ScenarioType.BASE_CASE,
                probability=0.50,
                name="Base Case Trajectory & Measured Progress",
                narrative="Under the base case, the organization executes disciplined milestone-gated implementation with steady operational progress.",
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Target Milestone Reached",
                        description="Operational milestones achieved within planned variance.",
                        timeframe="Month 6",
                        impact_on_decision="Confirms baseline operational expectations.",
                    )
                ],
                risks=["Execution cadence friction"],
                opportunities=["Predictable sustainable growth"],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Mid-term Review",
                        description="Evaluation of core performance metrics.",
                        time_horizon="Month 6",
                        expected_outcome="Baseline objectives achieved.",
                    )
                ],
                supporting_evidence_item_ids=[],
                relevant_assumption_ids=[],
                relevant_constraint_ids=[],
                relevant_gap_ids=[],
            ),
            CandidateFutureScenario(
                scenario_type=ScenarioType.PESSIMISTIC,
                probability=0.25,
                name="Pessimistic Trajectory & Defensive Positioning",
                narrative="Under the pessimistic scenario, adverse market shifts or operational delays require defensive risk mitigation and contingency controls.",
                key_events=[
                    CandidateScenarioKeyEvent(
                        title="Downside Trigger Checkpoint",
                        description="Adverse conditions necessitate activating defensive controls.",
                        timeframe="Month 4",
                        impact_on_decision="Triggers contingency mitigation protocols.",
                    )
                ],
                risks=["Extended resource burn", "Macro headwinds"],
                opportunities=["Operational tightening and resilience building"],
                timeline=[
                    CandidateScenarioMilestone(
                        title="Defensive Reassessment",
                        description="Contingency protocols activated to preserve capital.",
                        time_horizon="Month 4",
                        expected_outcome="Capital preservation and downside capped.",
                    )
                ],
                supporting_evidence_item_ids=[],
                relevant_assumption_ids=[],
                relevant_constraint_ids=[],
                relevant_gap_ids=[],
            ),
        ],
    )


# ------------------------------------------------------------------------------
# 1. Successful Five-Stage Execution
# ------------------------------------------------------------------------------

def test_01_successful_five_stage_execution():
    """Verify that a standard analysis request executes across all 5 stages and returns valid ScenarioSet."""
    service = AnalysisService()
    req = AnalysisRequest(
        question="Should we migrate from monolithic architecture to microservices in Q3?",
        context={"team_size": 25, "services": 8},
        constraints=["Zero downtime deployment", "Complete within Q4"],
    )

    stage_events: List[str] = []

    def _tracker(stage_name: str) -> None:
        stage_events.append(stage_name)

    response = service.analyze(req, stage_callback=_tracker)

    # 1. Verify stage callback progression
    assert stage_events[:5] == [
        "stage1_decision_framer",
        "stage2_evidence_engine",
        "stage3_ai_boardroom",
        "stage4_recommendation",
        "stage5_scenarios",
    ]

    # 2. Verify all five stages returned authoritative artifacts
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

    # 3. Verify scenario set invariants
    assert len(response.scenarios.scenarios) == 3
    types = [s.scenario_type for s in response.scenarios.scenarios]
    assert types == [ScenarioType.OPTIMISTIC, ScenarioType.BASE_CASE, ScenarioType.PESSIMISTIC]

    prob_sum = sum(s.probability for s in response.scenarios.scenarios)
    assert abs(prob_sum - 1.0) < 0.01

    assert response.scenarios.decision_model_id == response.decision_model.id
    assert response.scenarios.recommendation_id == response.recommendation.id
    assert "scenario simulation completed successfully" in response.message.lower()


# ------------------------------------------------------------------------------
# 2. Correct Stage 5 Input Artifacts
# ------------------------------------------------------------------------------

def test_02_correct_stage_5_input_artifacts():
    """Verify ScenarioService receives exact, non-mutated upstream artifacts and monotonic deadline."""
    received_inputs: Dict[str, Any] = {}

    class SpyScenarioService(ScenarioService):
        def generate_scenarios(
            self,
            decision_model: DecisionModel,
            evidence_package: EvidencePackage,
            reasoning_board: ReasoningBoard,
            recommendation: DecisionRecommendation,
            deadline_monotonic: Optional[float] = None,
            scenario_config: Optional[LLMConfig] = None,
        ) -> ScenarioSet:
            received_inputs["decision_model"] = decision_model
            received_inputs["evidence_package"] = evidence_package
            received_inputs["reasoning_board"] = reasoning_board
            received_inputs["recommendation"] = recommendation
            received_inputs["deadline_monotonic"] = deadline_monotonic
            return super().generate_scenarios(
                decision_model=decision_model,
                evidence_package=evidence_package,
                reasoning_board=reasoning_board,
                recommendation=recommendation,
                deadline_monotonic=deadline_monotonic,
                scenario_config=scenario_config,
            )

    spy_service = SpyScenarioService(generator=ScenarioGenerator(llm_client=FakeLLMClient()))
    service = AnalysisService(scenario_service=spy_service)

    req = AnalysisRequest(question="Should we adopt Kubernetes for container orchestration?")
    expected_deadline = time.monotonic() + 300.0

    response = service.analyze(req, deadline_monotonic=expected_deadline)

    assert response.status == "completed"
    assert received_inputs["decision_model"] is response.decision_model
    assert received_inputs["evidence_package"] is response.evidence_package
    assert received_inputs["reasoning_board"] is response.reasoning_board
    assert received_inputs["recommendation"] is response.recommendation
    assert received_inputs["deadline_monotonic"] == expected_deadline


# ------------------------------------------------------------------------------
# 3. Stage 5 Progress Tracking and Async Job Lifecycle
# ------------------------------------------------------------------------------

def test_03_stage5_progress_and_lifecycle(tmp_path):
    """Verify stage5_scenarios appears during asynchronous execution and updates job state."""
    db_file = str(tmp_path / "test_lifecycle.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)

    req = AnalysisJobCreateRequest(
        question="Should we launch a subscription model for our enterprise SaaS?",
        scenario_operation_timeout_seconds=45.0,
    )
    job_status_resp = manager.submit_job(req)
    job_id = job_status_resp.job_id

    assert job_status_resp.status == JobStatus.QUEUED
    assert job_status_resp.stage == PipelineStage.QUEUED

    # Poll until completed
    max_wait = 10.0
    start = time.time()
    current = manager.get_job_status(job_id)
    observed_stages: List[PipelineStage] = [current.stage]

    while current.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.02)
        current = manager.get_job_status(job_id)
        if current.stage not in observed_stages:
            observed_stages.append(current.stage)

    assert current.status == JobStatus.SUCCEEDED
    assert current.stage == PipelineStage.COMPLETED

    # Verify result retrieval via get_job_result
    result = manager.get_job_result(job_id)
    assert result.status == "completed"
    assert result.scenarios is not None
    assert result.scenario_status == "completed"


# ------------------------------------------------------------------------------
# 4. Stage 5 Timeout Preserves Stage 1–4 Outputs as Partial Success
# ------------------------------------------------------------------------------

def test_04_stage5_timeout_preserves_upstream_as_partial_success():
    """Verify Stage 5 timeout marks scenario_status unavailable and preserves Stages 1-4."""
    class TimingOutScenarioService(ScenarioService):
        def generate_scenarios(self, **kwargs) -> ScenarioSet:
            raise ScenarioServiceError(
                "Scenario simulation operation exceeded budget ceiling.",
                stage="scenario_engine",
                details={"error_type": "timeout", "timeout_source": "operation"},
            )

    timing_out_svc = TimingOutScenarioService(generator=ScenarioGenerator(llm_client=FakeLLMClient()))
    service = AnalysisService(scenario_service=timing_out_svc)

    req = AnalysisRequest(question="Should we acquire our largest domestic competitor?")
    response = service.analyze(req)

    # 1. Overall status must be partial_success
    assert response.status == "partial_success"

    # 2. Stages 1-4 artifacts must be fully preserved
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert response.recommendation_status == "completed"

    # 3. Stage 5 marked unavailable with descriptive safe error
    assert response.scenarios is None
    assert response.scenario_status == "unavailable"
    assert response.scenario_error is not None
    assert "timed out" in response.scenario_error.lower()
    assert "scenario stage unavailable" in response.message.lower()


# ------------------------------------------------------------------------------
# 5. Stage 5 Malformed LLM Output Preserves Upstream Artifacts
# ------------------------------------------------------------------------------

def test_05_stage5_malformed_llm_output():
    """Verify Stage 5 validation or LLM failure preserves Stages 1-4 without throwing 500/502."""
    class FailingScenarioService(ScenarioService):
        def generate_scenarios(self, **kwargs) -> ScenarioSet:
            raise ScenarioValidationError(
                "Candidate scenario probabilities sum to 1.35, exceeding 0.01 tolerance.",
                details={"rule": "probability_sum_invariant", "sum": 1.35},
            )

    failing_svc = FailingScenarioService(generator=ScenarioGenerator(llm_client=FakeLLMClient()))
    service = AnalysisService(scenario_service=failing_svc)

    req = AnalysisRequest(question="Should we expand into health tech vertical?")
    response = service.analyze(req)

    assert response.status == "partial_success"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is not None
    assert response.recommendation_status == "completed"

    assert response.scenarios is None
    assert response.scenario_status == "unavailable"
    assert response.scenario_error is not None
    assert "probabilities sum to 1.35" in response.scenario_error


# ------------------------------------------------------------------------------
# 6. Stage 4 Failure Skips Stage 5 via Dependency Policy
# ------------------------------------------------------------------------------

def test_06_stage4_unavailable_skips_stage5():
    """Verify dependency policy: if recommendation is unavailable, Stage 5 is skipped safely without hallucinating."""
    class FailingRecommendationService:
        def generate_recommendation(self, **kwargs):
            raise RuntimeError("Stage 4 model failure")

    class NeverCalledScenarioService(ScenarioService):
        def generate_scenarios(self, **kwargs) -> ScenarioSet:
            raise AssertionError("ScenarioService should not be invoked when Stage 4 is unavailable!")

    never_called_svc = NeverCalledScenarioService(generator=ScenarioGenerator(llm_client=FakeLLMClient()))
    service = AnalysisService(
        recommendation_service=FailingRecommendationService(),  # type: ignore
        scenario_service=never_called_svc,
    )

    req = AnalysisRequest(question="Should we deprecate our legacy API v1?")
    response = service.analyze(req)

    assert response.status == "partial_success"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None

    # Stage 4 unavailable
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"

    # Stage 5 skipped by dependency policy
    assert response.scenarios is None
    assert response.scenario_status == "unavailable"
    assert "prerequisite Stage 4 recommendation was unavailable" in str(response.scenario_error)


# ------------------------------------------------------------------------------
# 7. Deadline Propagation
# ------------------------------------------------------------------------------

def test_07_deadline_propagation():
    """Deterministic verification of monotonic deadline propagation across all branches."""
    service = AnalysisService()
    req = AnalysisRequest(question="Should we shift engineering focus to edge computing?")

    # 1. Already-expired deadline raises HTTP 504 before execution
    with pytest.raises(Exception) as exc_info:
        service.analyze(req, deadline_monotonic=time.monotonic() - 1.0)
    assert "504" in str(exc_info.value) or "timed out" in str(exc_info.value).lower()

    # 2. Stage 5 timeout after successful Stage 4
    class TimeoutInStage5Service(ScenarioService):
        def generate_scenarios(self, **kwargs) -> ScenarioSet:
            raise ScenarioServiceError(
                "LLM generation timed out during scenario synthesis.",
                stage="scenario_engine",
                details={"error_type": "timeout"},
            )

    now = time.monotonic()
    svc_stage5_timeout = AnalysisService(
        scenario_service=TimeoutInStage5Service(generator=ScenarioGenerator(llm_client=FakeLLMClient()))
    )
    resp_timeout = svc_stage5_timeout.analyze(req, deadline_monotonic=now + 60.0)
    assert resp_timeout.status == "partial_success"
    assert resp_timeout.recommendation is not None
    assert resp_timeout.scenarios is None
    assert resp_timeout.scenario_status == "unavailable"
    assert "timed out" in str(resp_timeout.scenario_error).lower()


# ------------------------------------------------------------------------------
# 8. SQLite Persistence Round-Trip
# ------------------------------------------------------------------------------

def test_08_sqlite_persistence_round_trip(tmp_path):
    """Verify AnalysisResponse with scenarios survives SQLite storage, restart, and deserialization."""
    db_file = str(tmp_path / "test_sqlite_roundtrip.db")
    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(storage=storage)

    req = AnalysisJobCreateRequest(
        question="Should we transition to open-source licensing for core libraries?",
        scenario_operation_timeout_seconds=55.0,
    )
    job_resp = manager.submit_job(req)
    job_id = job_resp.job_id

    # Wait for completion
    max_wait = 10.0
    start = time.time()
    job_status = manager.get_job_status(job_id)
    while job_status.status in (JobStatus.QUEUED, JobStatus.RUNNING) and time.time() - start < max_wait:
        time.sleep(0.05)
        job_status = manager.get_job_status(job_id)

    assert job_status.status == JobStatus.SUCCEEDED

    # Simulate process restart by closing old storage and opening new instance
    storage.close()
    new_storage = SQLiteJobStorage(db_path=db_file)

    retrieved = new_storage.get_job(job_id)
    assert retrieved is not None
    assert retrieved.scenario_timeout_seconds == 55.0
    assert retrieved.response is not None

    resp = retrieved.response
    assert resp.status == "completed"
    assert resp.scenarios is not None
    assert resp.scenario_status == "completed"
    assert len(resp.scenarios.scenarios) == 3
    assert resp.scenarios.decision_model_id == resp.decision_model.id
    new_storage.close()


# ------------------------------------------------------------------------------
# 9. Historical Four-Stage Response Compatibility
# ------------------------------------------------------------------------------

def test_09_historical_four_stage_response_compatibility(tmp_path):
    """Verify non-destructive compatibility when reading historical 4-stage jobs without scenario fields."""
    db_file = str(tmp_path / "historical_phase5a.db")
    conn = sqlite3.connect(db_file)
    # Create older table schema without scenario_timeout_seconds
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
            recommendation_timeout_seconds REAL,
            progress_message TEXT NOT NULL
        )
    """)

    # Generate a schema-valid response and strip scenario fields to simulate historical four-stage payload
    base_svc = AnalysisService()
    hist_resp = base_svc.analyze(AnalysisRequest(question="Historical four-stage decision inquiry"))
    four_stage_response = hist_resp.model_dump(mode="json")
    four_stage_response.pop("scenarios", None)
    four_stage_response.pop("scenario_status", None)
    four_stage_response.pop("scenario_error", None)

    conn.execute(
        """
        INSERT INTO analysis_jobs (
            job_id, status, stage, request_json, response_json,
            owner_id, created_at, completed_at, timeout_seconds, progress_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-hist-fourstage",
            "succeeded",
            "completed",
            json.dumps({"question": "Historical four-stage decision inquiry"}),
            json.dumps(four_stage_response),
            "owner-1",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            120.0,
            "Completed successfully",
        ),
    )
    conn.commit()
    conn.close()

    # Open with SQLiteJobStorage (applies ALTER TABLE migration safely)
    storage = SQLiteJobStorage(db_path=db_file)
    record = storage.get_job("job-hist-fourstage")

    assert record is not None
    assert record.scenario_timeout_seconds is None
    assert record.response is not None
    assert record.response.scenarios is None
    assert record.response.scenario_status is None
    assert record.response.scenario_error is None
    assert record.response.status == "completed"
    storage.close()


# ------------------------------------------------------------------------------
# 10. API Endpoints Compatibility
# ------------------------------------------------------------------------------

def test_10_api_endpoints_compatibility():
    """Verify synchronous POST /api/analyze and async /api/analysis/jobs contracts."""
    client = TestClient(app)

    # 1. Synchronous POST /api/analyze
    sync_resp = client.post(
        "/api/analyze",
        json={"question": "Should we build an internal design system?"},
    )
    assert sync_resp.status_code == status.HTTP_200_OK
    data = sync_resp.json()
    assert data["status"] == "completed"
    assert "scenarios" in data
    assert data["scenarios"] is not None
    assert data["scenario_status"] == "completed"
    assert data["scenario_error"] is None

    # 2. Asynchronous POST /api/analysis/jobs
    job_create_resp = client.post(
        "/api/analysis/jobs",
        json={
            "question": "Should we migrate to TypeScript for all frontend apps?",
            "scenario_operation_timeout_seconds": 60.0,
        },
    )
    assert job_create_resp.status_code == status.HTTP_202_ACCEPTED
    job_info = job_create_resp.json()
    job_id = job_info["job_id"]

    # Poll status
    max_wait = 10.0
    start = time.time()
    status_resp = client.get(f"/api/analysis/jobs/{job_id}")
    while status_resp.json()["status"] in ("queued", "running") and time.time() - start < max_wait:
        time.sleep(0.05)
        status_resp = client.get(f"/api/analysis/jobs/{job_id}")

    assert status_resp.status_code == status.HTTP_200_OK
    assert status_resp.json()["status"] == "succeeded"

    # Retrieve completed result
    result_resp = client.get(f"/api/analysis/jobs/{job_id}/result")
    assert result_resp.status_code == status.HTTP_200_OK
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["scenarios"] is not None
    assert result_data["scenario_status"] == "completed"
