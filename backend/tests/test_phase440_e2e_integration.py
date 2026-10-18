"""Phase 4.40: End-to-End Integration, Security Boundaries, and Failure Journey Tests.

Deterministic verification covering:
1. Security boundaries (unauthenticated job access, no enumeration, no payload leakage).
2. Single-process worker safety (concurrency bounding, restart recovery, no duplicate execution).
3. Stage timeouts & failures (Framer timeout, Evidence timeout, Boardroom timeout, provider errors).
4. Full mocked analysis journey through FastAPI TestClient.
"""

import time
from typing import Any, Optional
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import (
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    JobStatus,
    PipelineStage,
)
from app.services.analysis_service import AnalysisService
from app.services.evidence import FakeSearchProvider, SearchResultItem
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient, LLMResponseValidationError


def create_scenario_analysis_service(
    fail_stage: Optional[str] = None,
    fail_with_status: int = 504,
) -> AnalysisService:
    """Builds a mock AnalysisService that can fail at specific pipeline stages."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(default_results=[])
    svc = AnalysisService(
        llm_client=fake_llm,
        search_provider=fake_search,
        analysis_timeout_seconds=60.0,
    )
    orig_analyze = svc.analyze

    def staged_analyze(request: AnalysisRequest, *args: Any, **kwargs: Any) -> AnalysisResponse:
        stage_cb = kwargs.get("stage_callback")

        if stage_cb:
            stage_cb("stage1_decision_framer")
        if fail_stage == "framer":
            raise HTTPException(status_code=fail_with_status, detail="Decision Framer operation deadline exceeded.")

        if stage_cb:
            stage_cb("stage2_evidence_engine")
        if fail_stage == "evidence":
            raise HTTPException(status_code=fail_with_status, detail="Evidence Engine operation deadline exceeded.")

        if stage_cb:
            stage_cb("stage3_ai_boardroom")
        if fail_stage == "boardroom":
            raise HTTPException(status_code=fail_with_status, detail="AI Boardroom synthesis operation deadline exceeded.")

        if fail_stage == "validation_error":
            raise HTTPException(status_code=502, detail="LLM response validation failed against canonical schema.")

        return orig_analyze(request, *args, **kwargs)

    svc.analyze = staged_analyze
    return svc


# ------------------------------------------------------------------------------
# 1. Security Boundaries Tests
# ------------------------------------------------------------------------------

def test_security_no_job_enumeration(tmp_path):
    """Verifies that job IDs cannot be enumerated (no list route exists on public API)."""
    client = TestClient(app)

    # Attempting to list jobs via GET /api/analysis/jobs or /api/jobs must return 405 Method Not Allowed (only POST is allowed)
    resp1 = client.get("/api/analysis/jobs")
    assert resp1.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    resp2 = client.get("/api/jobs")
    assert resp2.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # Non-existent UUID returns 404, not an enumeration list
    resp3 = client.get("/api/analysis/jobs/non-existent-uuid-12345")
    assert resp3.status_code == status.HTTP_404_NOT_FOUND


def test_security_error_does_not_leak_payload(tmp_path):
    """Verifies that job execution failure does not leak input prompt or private payloads."""
    db_file = str(tmp_path / "leak_test.db")
    storage = SQLiteJobStorage(db_path=db_file)
    svc = create_scenario_analysis_service(fail_stage="framer", fail_with_status=504)
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    try:
        req = AnalysisJobCreateRequest(
            question="SECRET_CONFIDENTIAL_INQUIRY: Acquisition of Target Corp for $500M",
            context={"internal_revenue": "$20M"},
        )
        job = manager.submit_job(req)

        # Wait for failure
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            st = manager.get_job_status(job.job_id)
            if st.status in (JobStatus.FAILED, JobStatus.TIMED_OUT):
                break
            time.sleep(0.05)

        status_resp = manager.get_job_status(job.job_id)
        assert status_resp.status == JobStatus.TIMED_OUT
        # Error text must describe timeout, not reveal confidential prompt
        assert "SECRET_CONFIDENTIAL_INQUIRY" not in (status_resp.error or "")
        assert "$500M" not in (status_resp.error or "")

        with pytest.raises(HTTPException) as exc_info:
            manager.get_job_result(job.job_id)
        assert "SECRET_CONFIDENTIAL_INQUIRY" not in str(exc_info.value.detail)
    finally:
        manager.shutdown(wait=True)
        storage.close()


def test_security_x_owner_id_is_unauthenticated(tmp_path):
    """Verifies that X-Owner-Id is purely a caller-supplied label without cryptographic proof."""
    db_file = str(tmp_path / "owner_test.db")
    storage = SQLiteJobStorage(db_path=db_file)
    svc = create_scenario_analysis_service()
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    try:
        # User A creates a job labeled with owner 'alice'
        req = AnalysisJobCreateRequest(question="Alice decision question", owner_id="alice")
        job = manager.submit_job(req)

        # Any caller claiming owner 'alice' via unverified header is granted access
        st_alice = manager.get_job_status(job.job_id, owner_id="alice")
        assert st_alice.job_id == job.job_id

        # Mismatched claimed owner 'bob' is rejected
        with pytest.raises(HTTPException) as exc_info:
            manager.get_job_status(job.job_id, owner_id="bob")
        assert exc_info.value.status_code == 403
    finally:
        manager.shutdown(wait=True)
        storage.close()


# ------------------------------------------------------------------------------
# 2. Single-Process Worker Safety Tests
# ------------------------------------------------------------------------------

def test_single_process_bounded_concurrency(tmp_path):
    """Verifies that bounded worker pool limits simultaneous active executions."""
    db_file = str(tmp_path / "concurrency_test.db")
    storage = SQLiteJobStorage(db_path=db_file)

    active_executions = 0
    max_observed_active = 0

    class SlowService(AnalysisService):
        def analyze(self, request, *args, **kwargs):
            nonlocal active_executions, max_observed_active
            active_executions += 1
            if active_executions > max_observed_active:
                max_observed_active = active_executions
            time.sleep(0.1)
            active_executions -= 1
            return super().analyze(request, *args, **kwargs)

    svc = SlowService(llm_client=FakeLLMClient(), search_provider=FakeSearchProvider(default_results=[]))
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc, max_workers=2)

    try:
        # Submit 4 jobs simultaneously
        jobs = [manager.submit_job(AnalysisJobCreateRequest(question=f"Job #{i}")) for i in range(4)]

        # Wait for all to complete
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            if all(manager.get_job_status(j.job_id).status == JobStatus.SUCCEEDED for j in jobs):
                break
            time.sleep(0.05)

        # Max concurrently active executions must never exceed max_workers (2)
        assert max_observed_active <= 2
    finally:
        manager.shutdown(wait=True)
        storage.close()


def test_process_restart_marks_active_jobs_failed(tmp_path):
    """Verifies that jobs running when process terminates are safely transitioned to FAILED on startup."""
    db_file = str(tmp_path / "restart_recovery.db")

    # Process 1: Starts a job and simulates abrupt shutdown
    storage1 = SQLiteJobStorage(db_path=db_file)
    rec = storage1.create_job(AnalysisJobCreateRequest(question="Interrupted task"))
    storage1.update_running(rec.job_id, PipelineStage.STAGE1_DECISION_FRAMER, "Framing decision...")
    storage1.close()

    # Process 2: Clean restart initializes manager
    storage2 = SQLiteJobStorage(db_path=db_file)
    manager2 = AnalysisJobManager(storage=storage2, service_factory=lambda: create_scenario_analysis_service())

    try:
        # Job must be marked FAILED with restart explanation
        st = manager2.get_job_status(rec.job_id)
        assert st.status == JobStatus.FAILED
        assert st.stage == PipelineStage.FAILED
        assert "restart" in (st.error or "").lower()
    finally:
        manager2.shutdown(wait=True)
        storage2.close()


# ------------------------------------------------------------------------------
# 3. Failure Journey Tests (Stage-specific timeouts & provider errors)
# ------------------------------------------------------------------------------

@pytest.mark.parametrize("fail_stage, expected_stage", [
    ("framer", PipelineStage.STAGE1_DECISION_FRAMER),
    ("evidence", PipelineStage.STAGE2_EVIDENCE_ENGINE),
    ("boardroom", PipelineStage.STAGE3_AI_BOARDROOM),
])
def test_stage_specific_timeouts(tmp_path, fail_stage, expected_stage):
    """Verifies that timeouts at Stage 1, Stage 2, or Stage 3 are caught and stored cleanly."""
    db_file = str(tmp_path / f"timeout_{fail_stage}.db")
    storage = SQLiteJobStorage(db_path=db_file)
    svc = create_scenario_analysis_service(fail_stage=fail_stage, fail_with_status=504)
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    try:
        job = manager.submit_job(AnalysisJobCreateRequest(question=f"Timeout test for {fail_stage}"))

        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            st = manager.get_job_status(job.job_id)
            if st.status == JobStatus.TIMED_OUT:
                break
            time.sleep(0.05)

        final_st = manager.get_job_status(job.job_id)
        assert final_st.status == JobStatus.TIMED_OUT
        assert final_st.error_status_code == 504
        assert "deadline exceeded" in (final_st.error or "").lower()

        # No partial result exposed
        with pytest.raises(HTTPException) as exc_info:
            manager.get_job_result(job.job_id)
        assert exc_info.value.status_code == 504
    finally:
        manager.shutdown(wait=True)
        storage.close()


def test_provider_validation_failure(tmp_path):
    """Verifies that an unrecoverable schema validation error results in FAILED with HTTP 502."""
    db_file = str(tmp_path / "validation_fail.db")
    storage = SQLiteJobStorage(db_path=db_file)
    svc = create_scenario_analysis_service(fail_stage="validation_error", fail_with_status=502)
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    try:
        job = manager.submit_job(AnalysisJobCreateRequest(question="Schema validation failure test"))

        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            st = manager.get_job_status(job.job_id)
            if st.status == JobStatus.FAILED:
                break
            time.sleep(0.05)

        final_st = manager.get_job_status(job.job_id)
        assert final_st.status == JobStatus.FAILED
        assert final_st.error_status_code == 502

        with pytest.raises(HTTPException) as exc_info:
            manager.get_job_result(job.job_id)
        assert exc_info.value.status_code == 502
    finally:
        manager.shutdown(wait=True)
        storage.close()


# ------------------------------------------------------------------------------
# 4. Full Mocked Analysis Journey
# ------------------------------------------------------------------------------

def test_full_mocked_analysis_journey(tmp_path):
    """Runs a complete end-to-end journey from submission to validated 4-perspective result."""
    db_file = str(tmp_path / "journey_e2e.db")
    storage = SQLiteJobStorage(db_path=db_file)
    svc = create_scenario_analysis_service()
    manager = AnalysisJobManager(storage=storage, service_factory=lambda: svc)

    # Override app dependency
    app.dependency_overrides[get_job_manager] = lambda: manager
    client = TestClient(app)

    try:
        # Step 1: Submit job via POST /api/analysis/jobs
        submit_resp = client.post(
            "/api/analysis/jobs",
            json={
                "question": "Should we migrate from PostgreSQL to a distributed cluster?",
                "context": {"current_qps": "20,000"},
                "constraints": ["Budget under $40k/month"],
            },
        )
        assert submit_resp.status_code == status.HTTP_202_ACCEPTED
        job_data = submit_resp.json()
        job_id = job_data["job_id"]
        assert job_data["status"] == "queued"

        # Step 2: Poll status until succeeded
        t0 = time.monotonic()
        final_status_data = None
        while time.monotonic() - t0 < 5.0:
            poll_resp = client.get(f"/api/analysis/jobs/{job_id}")
            assert poll_resp.status_code == status.HTTP_200_OK
            st_json = poll_resp.json()
            if st_json["status"] == "succeeded":
                final_status_data = st_json
                break
            time.sleep(0.05)

        assert final_status_data is not None
        assert final_status_data["status"] == "succeeded"
        assert final_status_data["stage"] == "completed"

        # Step 3: Retrieve result via GET /api/analysis/jobs/{job_id}/result
        result_resp = client.get(f"/api/analysis/jobs/{job_id}/result")
        assert result_resp.status_code == status.HTTP_200_OK
        result_data = result_resp.json()

        # Validate canonical ReasoningBoard contents
        assert "reasoning_board" in result_data
        board = result_data["reasoning_board"]
        assert board is not None
        assert len(board["perspectives"]) == 4

        perspectives = {p["perspective_type"]: p for p in board["perspectives"]}
        assert "growth" in perspectives
        assert "finance" in perspectives
        assert "customer" in perspectives
        assert "risk" in perspectives

        # Validate synthesis
        assert "synthesis" in board
        synthesis = board["synthesis"]
        assert len(synthesis["summary"]) > 0
        assert len(synthesis["areas_of_agreement"]) > 0

        # Validate disagreements
        assert "disagreements" in board
        assert isinstance(board["disagreements"], list)

    finally:
        app.dependency_overrides.clear()
        manager.shutdown(wait=True)
        storage.close()
