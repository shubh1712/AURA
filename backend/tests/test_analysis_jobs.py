"""Unit and integration tests for Phase 4.38: Asynchronous Analysis Execution.

Verifies:
1. Job creation and status transitions (QUEUED -> RUNNING -> SUCCEEDED).
2. Complete validated result retrieval (AnalysisResponse).
3. No partial result exposure (409 Conflict while queued/running).
4. Failure and timeout handling (TIMED_OUT on 504, FAILED on 502/500).
5. Duplicate polling idempotency.
6. Concurrent jobs bounded execution.
7. Ownership isolation (403 on mismatched owner).
8. Worker interruption and restart recovery.
9. Deadline enforcement.
10. Existing synchronous API compatibility (POST /api/analyze).
"""

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any, Dict, Optional
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
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.services.evidence import FakeSearchProvider, SearchResultItem
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient


# ------------------------------------------------------------------------------
# Test Fixtures & In-Memory Helpers
# ------------------------------------------------------------------------------

def _create_mock_analysis_service(
    fail_with_status: Optional[int] = None,
    delay_seconds: float = 0.0,
) -> AnalysisService:
    """Builds an offline AnalysisService using FakeLLMClient and FakeSearchProvider."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(
        default_results=[
            SearchResultItem(
                url="https://example.com/report",
                title="SaaS Benchmark Report",
                snippet="Pricing reduction lifted customer acquisition by 14%.",
            )
        ]
    )
    svc = AnalysisService(
        llm_client=fake_llm,
        search_provider=fake_search,
        analysis_timeout_seconds=120.0,
    )

    if fail_with_status or delay_seconds > 0:
        orig_analyze = svc.analyze
        def patched_analyze(request: AnalysisRequest, *args: Any, **kwargs: Any) -> AnalysisResponse:
            stage_cb = kwargs.get("stage_callback")
            if stage_cb:
                stage_cb("stage1_decision_framer")
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            if fail_with_status:
                if fail_with_status == 504:
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail="Decision analysis timed out while evaluating the inquiry.",
                    )
                raise HTTPException(
                    status_code=fail_with_status,
                    detail=f"Simulated failure with HTTP {fail_with_status}",
                )
            if stage_cb:
                stage_cb("stage2_evidence_engine")
                stage_cb("stage3_ai_boardroom")
            return orig_analyze(request, *args, **kwargs)
        svc.analyze = patched_analyze

    return svc


@pytest.fixture
def test_storage() -> SQLiteJobStorage:
    """Creates a fresh in-memory SQLiteJobStorage for isolation."""
    storage = SQLiteJobStorage(db_path=":memory:")
    yield storage
    storage.close()


@pytest.fixture
def test_manager(test_storage: SQLiteJobStorage) -> AnalysisJobManager:
    """Creates an AnalysisJobManager wired with in-memory storage and mock service."""
    svc = _create_mock_analysis_service()
    manager = AnalysisJobManager(
        storage=test_storage,
        service_factory=lambda: svc,
        max_workers=2,
        default_timeout_seconds=60.0,
    )
    yield manager
    manager.shutdown(wait=True)


# ------------------------------------------------------------------------------
# 1. Job Creation and Status Transitions
# ------------------------------------------------------------------------------

def test_1_job_creation_and_status_transitions(test_manager: AnalysisJobManager) -> None:
    """Test job lifecycle moves from QUEUED to RUNNING to SUCCEEDED with valid output."""
    req = AnalysisJobCreateRequest(
        question="Should we expand into European enterprise markets?",
        context={"market": "EU"},
        constraints=["GDPR compliance required"],
    )

    resp = test_manager.submit_job(req)
    assert resp.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    assert resp.job_id is not None
    assert len(resp.job_id) > 0

    # Wait for completion in background pool
    t0 = time.monotonic()
    final_status = None
    while time.monotonic() - t0 < 5.0:
        status_resp = test_manager.get_job_status(resp.job_id)
        if status_resp.status == JobStatus.SUCCEEDED:
            final_status = status_resp
            break
        time.sleep(0.05)

    assert final_status is not None
    assert final_status.status == JobStatus.SUCCEEDED
    assert final_status.stage == PipelineStage.COMPLETED
    assert final_status.started_at is not None
    assert final_status.completed_at is not None


# ------------------------------------------------------------------------------
# 2. Complete Validated Result Retrieval
# ------------------------------------------------------------------------------

def test_2_complete_validated_result_retrieval(test_manager: AnalysisJobManager) -> None:
    """Retrieving /result returns full validated AnalysisResponse matching canonical contract."""
    req = AnalysisJobCreateRequest(question="Should we expand pricing?")
    created = test_manager.submit_job(req)

    # Wait for completion
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0:
        s = test_manager.get_job_status(created.job_id)
        if s.status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    result = test_manager.get_job_result(created.job_id)
    assert isinstance(result, AnalysisResponse)
    assert result.status == "completed"
    assert result.decision_model is not None
    assert result.evidence_package is not None
    assert result.reasoning_board is not None
    assert len(result.reasoning_board.perspectives) == 4
    assert result.question == "Should we expand pricing?"


# ------------------------------------------------------------------------------
# 3. No Partial Result Exposure While Running
# ------------------------------------------------------------------------------

def test_3_no_partial_result_exposure(test_storage: SQLiteJobStorage) -> None:
    """While job is QUEUED or RUNNING, get_job_result raises 409 Conflict, leaking zero partial data."""
    # Build service with controlled sleep
    svc = _create_mock_analysis_service(delay_seconds=0.5)
    manager = AnalysisJobManager(
        storage=test_storage,
        service_factory=lambda: svc,
        max_workers=1,
    )
    try:
        req = AnalysisJobCreateRequest(question="Should we delay launch?")
        job = manager.submit_job(req)

        # Immediately query result while job is running or queued
        with pytest.raises(HTTPException) as exc_info:
            manager.get_job_result(job.job_id)

        assert exc_info.value.status_code == 409
        assert "not yet completed" in exc_info.value.detail or "running" in exc_info.value.detail
    finally:
        manager.shutdown(wait=True)


# ------------------------------------------------------------------------------
# 4. Failure and Timeout Handling
# ------------------------------------------------------------------------------

def test_4_failure_and_timeout_handling(test_storage: SQLiteJobStorage) -> None:
    """Verifies TIMED_OUT (504) and FAILED (502) states with safe error descriptions."""
    # Case A: Timeout (504)
    svc_timeout = _create_mock_analysis_service(fail_with_status=504)
    mgr_timeout = AnalysisJobManager(storage=test_storage, service_factory=lambda: svc_timeout)
    try:
        job_t = mgr_timeout.submit_job(AnalysisJobCreateRequest(question="Will this time out?"))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            s = mgr_timeout.get_job_status(job_t.job_id)
            if s.status == JobStatus.TIMED_OUT:
                break
            time.sleep(0.05)

        s = mgr_timeout.get_job_status(job_t.job_id)
        assert s.status == JobStatus.TIMED_OUT
        assert s.error_status_code == 504
        assert "timed out" in s.error.lower()

        with pytest.raises(HTTPException) as exc_info:
            mgr_timeout.get_job_result(job_t.job_id)
        assert exc_info.value.status_code == 504
    finally:
        mgr_timeout.shutdown(wait=True)

    # Case B: Provider Failure (502)
    svc_fail = _create_mock_analysis_service(fail_with_status=502)
    mgr_fail = AnalysisJobManager(storage=test_storage, service_factory=lambda: svc_fail)
    try:
        job_f = mgr_fail.submit_job(AnalysisJobCreateRequest(question="Will this fail?"))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            s = mgr_fail.get_job_status(job_f.job_id)
            if s.status == JobStatus.FAILED:
                break
            time.sleep(0.05)

        s = mgr_fail.get_job_status(job_f.job_id)
        assert s.status == JobStatus.FAILED
        assert s.error_status_code == 502

        with pytest.raises(HTTPException) as exc_info:
            mgr_fail.get_job_result(job_f.job_id)
        assert exc_info.value.status_code == 502
    finally:
        mgr_fail.shutdown(wait=True)


# ------------------------------------------------------------------------------
# 5. Duplicate Polling Idempotency
# ------------------------------------------------------------------------------

def test_5_duplicate_polling_idempotency(test_manager: AnalysisJobManager) -> None:
    """Repeated calls to get_job_status return identical, stable state."""
    job = test_manager.submit_job(AnalysisJobCreateRequest(question="Polling question?"))

    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0:
        if test_manager.get_job_status(job.job_id).status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    poll_1 = test_manager.get_job_status(job.job_id)
    poll_2 = test_manager.get_job_status(job.job_id)
    poll_3 = test_manager.get_job_status(job.job_id)

    assert poll_1.model_dump() == poll_2.model_dump() == poll_3.model_dump()


# ------------------------------------------------------------------------------
# 6. Concurrent Jobs Bounded Execution
# ------------------------------------------------------------------------------

def test_6_concurrent_jobs_bounded_execution(test_storage: SQLiteJobStorage) -> None:
    """Multiple concurrent jobs execute safely and all complete."""
    svc = _create_mock_analysis_service()
    manager = AnalysisJobManager(storage=test_storage, service_factory=lambda: svc, max_workers=3)
    try:
        job_ids = []
        for i in range(5):
            j = manager.submit_job(AnalysisJobCreateRequest(question=f"Concurrent question #{i}?"))
            job_ids.append(j.job_id)

        # Wait for all to finish
        t0 = time.monotonic()
        while time.monotonic() - t0 < 10.0:
            all_done = all(
                manager.get_job_status(jid).status == JobStatus.SUCCEEDED
                for jid in job_ids
            )
            if all_done:
                break
            time.sleep(0.05)

        for jid in job_ids:
            st = manager.get_job_status(jid)
            assert st.status == JobStatus.SUCCEEDED
            res = manager.get_job_result(jid)
            assert isinstance(res, AnalysisResponse)
    finally:
        manager.shutdown(wait=True)


# ------------------------------------------------------------------------------
# 7. Ownership Isolation
# ------------------------------------------------------------------------------

def test_7_ownership_isolation(test_manager: AnalysisJobManager) -> None:
    """A job submitted with owner_id rejects requests with a different owner_id."""
    req = AnalysisJobCreateRequest(
        question="Confidential decision inquiry?",
        owner_id="team-alpha",
    )
    job = test_manager.submit_job(req)

    # Allowed with matching owner
    status_alpha = test_manager.get_job_status(job.job_id, owner_id="team-alpha")
    assert status_alpha.job_id == job.job_id

    # Forbidden with mismatched owner
    with pytest.raises(HTTPException) as exc_info:
        test_manager.get_job_status(job.job_id, owner_id="team-beta")
    assert exc_info.value.status_code == 403
    assert "forbidden" in exc_info.value.detail.lower()

    # Wait for completion
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0:
        if test_manager.get_job_status(job.job_id).status == JobStatus.SUCCEEDED:
            break
        time.sleep(0.05)

    # Result retrieval also enforces ownership
    with pytest.raises(HTTPException) as exc_info:
        test_manager.get_job_result(job.job_id, owner_id="team-beta")
    assert exc_info.value.status_code == 403

    res = test_manager.get_job_result(job.job_id, owner_id="team-alpha")
    assert res.status == "completed"


# ------------------------------------------------------------------------------
# 8. Worker Interruption and Restart Recovery
# ------------------------------------------------------------------------------

def test_8_worker_interruption_and_restart_recovery(tmp_path) -> None:
    """Verifies jobs left in QUEUED/RUNNING on crash are marked FAILED on startup."""
    db_file = str(tmp_path / "crash_test.db")

    # Instance 1: Create a job and leave it in RUNNING state (simulate crash)
    storage1 = SQLiteJobStorage(db_path=db_file)
    req = AnalysisJobCreateRequest(question="Interrupted task?")
    rec = storage1.create_job(req)
    storage1.update_running(rec.job_id, PipelineStage.STAGE2_EVIDENCE_ENGINE, "Running when crash happened.")
    storage1.close()

    # Instance 2: Manager starts up with same database (simulating restart)
    storage2 = SQLiteJobStorage(db_path=db_file)
    recovered_count = storage2.recover_stale_jobs_on_startup()
    assert recovered_count == 1

    rec_after = storage2.get_job(rec.job_id)
    assert rec_after is not None
    assert rec_after.status == JobStatus.FAILED
    assert rec_after.stage == PipelineStage.FAILED
    assert "restart" in rec_after.error_message.lower()
    storage2.close()


# ------------------------------------------------------------------------------
# 9. Deadline Enforcement
# ------------------------------------------------------------------------------

def test_9_deadline_enforcement(test_storage: SQLiteJobStorage) -> None:
    """Verifies that an expired deadline triggers 504 TIMED_OUT."""
    # Service that enforces deadline check
    class DeadlineCheckingService(AnalysisService):
        def analyze(self, request, deadline_monotonic=None, stage_callback=None):
            time.sleep(0.03)
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                raise HTTPException(status_code=504, detail="Decision analysis timed out.")
            return super().analyze(request, deadline_monotonic=deadline_monotonic, stage_callback=stage_callback)

    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(default_results=[])
    svc = DeadlineCheckingService(
        llm_client=fake_llm,
        search_provider=fake_search,
        analysis_timeout_seconds=0.01,
    )

    manager = AnalysisJobManager(
        storage=test_storage,
        service_factory=lambda: svc,
        default_timeout_seconds=0.01,
    )
    try:
        # Give tiny timeout so it expires immediately
        req = AnalysisJobCreateRequest(
            question="Quick expiring question?",
            timeout_seconds=0.01,
        )
        time.sleep(0.02)
        job = manager.submit_job(req)

        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            s = manager.get_job_status(job.job_id)
            if s.status in (JobStatus.TIMED_OUT, JobStatus.FAILED):
                break
            time.sleep(0.05)

        s = manager.get_job_status(job.job_id)
        assert s.status == JobStatus.TIMED_OUT
        assert s.error_status_code == 504
    finally:
        manager.shutdown(wait=True)


# ------------------------------------------------------------------------------
# 10. Existing Synchronous API Compatibility & FastAPI HTTP Integration
# ------------------------------------------------------------------------------

def test_10_api_routes_and_sync_compatibility() -> None:
    """Verifies FastAPI TestClient works for both synchronous and asynchronous endpoints."""
    # Override get_analysis_service dependency with mock
    mock_svc = _create_mock_analysis_service()
    app.dependency_overrides[get_analysis_service] = lambda: mock_svc

    # Override get_job_manager dependency with isolated manager
    test_storage = SQLiteJobStorage(db_path=":memory:")
    test_mgr = AnalysisJobManager(
        storage=test_storage,
        service_factory=lambda: mock_svc,
        max_workers=2,
    )
    app.dependency_overrides[get_job_manager] = lambda: test_mgr

    try:
        client = TestClient(app)

        # 1. Existing synchronous API POST /api/analyze remains 100% operational
        sync_resp = client.post(
            "/api/analyze",
            json={"question": "Synchronous compatibility check?"},
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["status"] == "completed"
        assert "decision_model" in sync_data

        # 2. Async API POST /api/analysis/jobs
        async_post = client.post(
            "/api/analysis/jobs",
            json={"question": "Asynchronous compatibility check?", "owner_id": "test-user"},
        )
        assert async_post.status_code == 202
        job_data = async_post.json()
        job_id = job_data["job_id"]
        assert job_data["status"] in ("queued", "running")

        # 3. Async API GET /api/analysis/jobs/{job_id}
        poll_resp = client.get(f"/api/analysis/jobs/{job_id}")
        assert poll_resp.status_code == 200
        assert poll_resp.json()["job_id"] == job_id

        # Wait for job to finish
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            check = client.get(f"/api/analysis/jobs/{job_id}").json()
            if check["status"] == "succeeded":
                break
            time.sleep(0.05)

        # 4. Async API GET /api/analysis/jobs/{job_id}/result
        result_resp = client.get(f"/api/analysis/jobs/{job_id}/result")
        assert result_resp.status_code == 200
        res_data = result_resp.json()
        assert res_data["status"] == "completed"
        assert "decision_model" in res_data
        assert "evidence_package" in res_data
        assert "reasoning_board" in res_data

        # 5. Also check un-prefixed routing /analysis/jobs
        unprefixed_post = client.post(
            "/analysis/jobs",
            json={"question": "Un-prefixed route check?"},
        )
        assert unprefixed_post.status_code == 202
        unpref_id = unprefixed_post.json()["job_id"]
        assert unpref_id is not None

    finally:
        app.dependency_overrides.clear()
        test_mgr.shutdown(wait=True)


def test_async_job_default_service_factory_regression() -> None:
    """Regression test: AnalysisJobManager with default service_factory (get_analysis_service)

    Verifies that calling get_analysis_service directly outside FastAPI request dependency
    injection does not pass FastAPI Depends objects into AnalysisService, preventing
    AttributeError: 'Depends' object has no attribute 'deconstruct'.
    """
    saved_analysis_svc_override = app.dependency_overrides.pop(get_analysis_service, None)
    test_storage = SQLiteJobStorage(db_path=":memory:")
    # Initialize manager WITHOUT explicit service_factory so it defaults to get_analysis_service
    manager = AnalysisJobManager(
        storage=test_storage,
        max_workers=1,
    )
    try:
        req = AnalysisJobCreateRequest(
            question="Should we expand into enterprise sales in Q3?",
        )
        status_resp = manager.submit_job(req)
        assert status_resp.status == JobStatus.QUEUED

        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            job = manager.get_job_status(status_resp.job_id)
            if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT):
                break
            time.sleep(0.05)

        final_job = manager.get_job_status(status_resp.job_id)
        assert final_job.status == JobStatus.SUCCEEDED, (
            f"Job failed with status_code={final_job.error_status_code}, error={final_job.error}"
        )
        assert final_job.error is None
        result = manager.get_job_result(status_resp.job_id)
        assert result.status == "completed"
        assert result.decision_model is not None
        assert result.decision_model.decision.raw_prompt == "Should we expand into enterprise sales in Q3?"
    finally:
        manager.shutdown(wait=True)
        if saved_analysis_svc_override is not None:
            app.dependency_overrides[get_analysis_service] = saved_analysis_svc_override


def test_async_job_manager_timeout_structured_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that AnalysisJobManager logs structured elapsed time and remaining budget when a job times out."""
    import logging
    from unittest.mock import MagicMock

    test_storage = SQLiteJobStorage(db_path=":memory:")
    mock_svc = MagicMock()
    mock_svc.analyze.side_effect = HTTPException(
        status_code=504,
        detail="Decision analysis timed out while evaluating the inquiry.",
    )

    manager = AnalysisJobManager(
        storage=test_storage,
        service_factory=lambda: mock_svc,
        max_workers=1,
        default_timeout_seconds=180.0,
    )

    try:
        with caplog.at_level(logging.WARNING):
            req = AnalysisJobCreateRequest(
                question="Should we reduce prices?",
                timeout_seconds=180.0,
            )
            created = manager.submit_job(req)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 5.0:
                job = manager.get_job_status(created.job_id)
                if job.status == JobStatus.TIMED_OUT:
                    break
                time.sleep(0.05)

            job = manager.get_job_status(created.job_id)
            assert job.status == JobStatus.TIMED_OUT
            assert "failed with HTTP 504" in caplog.text
            assert "elapsed=" in caplog.text
            assert "remaining_budget=" in caplog.text
    finally:
        manager.shutdown(wait=True)

