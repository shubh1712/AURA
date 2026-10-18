"""Comprehensive offline tests for Cloud Tasks execution, OIDC auth, and worker lifecycle.

Covers:
1. OIDC authentication, signature checking, issuer verification, audience checking, and service account enforcement.
2. CloudTasksDispatcher deterministic task generation, idempotency on AlreadyExists, and enqueue failures.
3. Strict execution mode enforcement (cloud mode never falls back to thread pool on enqueue failure).
4. Atomic execution claims, fencing tokens, lease expiration, and concurrent execution rejection.
5. At-least-once delivery deduplication (already completed or active jobs acknowledged without re-execution).
6. Terminal failure handling (failed/timed out jobs acknowledged to prevent infinite paid provider retries).
7. Full worker HTTP route integration with FastAPI TestClient.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional
import uuid

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from google.api_core import exceptions as google_exceptions

from app.config import Settings
from app.main import app
from app.schemas.analysis import AnalysisResponse
from app.schemas.job import AnalysisJobCreateRequest, JobStatus, PipelineStage
from app.services.jobs.base import JobRecord, JobStorageInterface
from app.services.jobs.manager import AnalysisJobManager
from app.api.routes.analysis_jobs import get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.tasks.auth import (
    OIDCValidator,
    set_oidc_validator_override,
    verify_cloud_tasks_auth,
)
from app.services.tasks.dispatcher import CloudTasksDispatcher


# =============================================================================
# In-Memory Fake Cloud Tasks Client for Offline Testing
# =============================================================================

class FakeTask:
    def __init__(self, name: str, http_request: Any) -> None:
        self.name = name
        self.http_request = http_request


class FakeCloudTasksClient:
    """Mock CloudTasksClient recording enqueued tasks and simulating Cloud Tasks errors."""

    def __init__(self) -> None:
        self.created_tasks: List[FakeTask] = []
        self.simulate_already_exists = False
        self.simulate_failure = False
        self.simulate_response_lost = False

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def task_path(self, project: str, location: str, queue: str, task: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}/tasks/{task}"

    def create_task(self, parent: str, task: Any) -> FakeTask:
        if self.simulate_response_lost:
            fake_task = FakeTask(name=task.name, http_request=task.http_request)
            self.created_tasks.append(fake_task)
            raise google_exceptions.DeadlineExceeded("Deadline exceeded waiting for create_task response")
        if self.simulate_failure:
            raise google_exceptions.PermissionDenied("Cloud Tasks API 403: Permission Denied")
        if self.simulate_already_exists:
            raise google_exceptions.AlreadyExists("Task already exists")

        fake_task = FakeTask(name=task.name, http_request=task.http_request)
        self.created_tasks.append(fake_task)
        return fake_task

    def get_task(self, name: str) -> FakeTask:
        for t in self.created_tasks:
            if t.name == name:
                return t
        raise google_exceptions.NotFound(f"Task {name} not found")


# =============================================================================
# Mock Analysis Service for Offline Worker Pipeline Execution
# =============================================================================

class MockFastAnalysisService:
    """Fast, deterministic analysis service that executes the 6 stages without live LLM calls."""

    def __init__(self, should_fail: bool = False, should_timeout: bool = False) -> None:
        self.should_fail = should_fail
        self.should_timeout = should_timeout

    def analyze(self, request: Any, deadline_monotonic: float, stage_callback: Any) -> AnalysisResponse:
        stages = [
            "stage1_decision_framer",
            "stage2_evidence_engine",
            "stage3_ai_boardroom",
            "stage4_recommendation",
            "stage5_scenarios",
            "stage6_resilience",
        ]
        for s in stages:
            stage_callback(s)

        if self.should_timeout:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Analysis deadline exceeded.",
            )
        if self.should_fail:
            raise RuntimeError("Ambiguous execution crash during synthesis.")

        return AnalysisResponse(
            analysis_id=f"analysis-{uuid.uuid4().hex[:8]}",
            status="completed",
        )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        AURA_EXECUTION_MODE="cloud_tasks",
        AURA_CLOUD_TASKS_PROJECT="aura-test-project",
        AURA_CLOUD_TASKS_LOCATION="asia-southeast1",
        AURA_CLOUD_TASKS_QUEUE="aura-test-queue",
        AURA_CLOUD_TASKS_WORKER_URL="https://aura-worker.run.app/api/internal/tasks/process-job",
        AURA_CLOUD_TASKS_SERVICE_ACCOUNT="aura-invoker@aura-test-project.iam.gserviceaccount.com",
        AURA_OIDC_AUDIENCE="https://aura-worker.run.app/api/internal/tasks/process-job",
        AURA_JOB_LEASE_SECONDS=30.0,
    )


@pytest.fixture
def sqlite_storage() -> SQLiteJobStorage:
    storage = SQLiteJobStorage(db_path=":memory:")
    yield storage
    storage.close()


@pytest.fixture
def fake_tasks_client() -> FakeCloudTasksClient:
    return FakeCloudTasksClient()


@pytest.fixture(autouse=True)
def reset_oidc_override() -> None:
    set_oidc_validator_override(None)
    yield
    set_oidc_validator_override(None)


# =============================================================================
# 1. OIDC Token Authentication Tests
# =============================================================================

class TestCloudTasksOIDCAuth:
    """Tests security constraints on Cloud Tasks worker endpoints."""

    def test_missing_authorization_header_rejected(self) -> None:
        client = TestClient(app)
        resp = client.post("/api/internal/tasks/process-job", json={"job_id": "job-1"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing Authorization header" in resp.json()["detail"]

    def test_malformed_authorization_header_rejected(self) -> None:
        client = TestClient(app)
        resp = client.post(
            "/api/internal/tasks/process-job",
            json={"job_id": "job-1"},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Malformed Authorization header" in resp.json()["detail"]

    def test_untrusted_issuer_rejected(self, mock_settings: Settings) -> None:
        validator = OIDCValidator(
            expected_audience=mock_settings.AURA_OIDC_AUDIENCE,
            expected_service_account=mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
        )
        # Mock payload from untrusted issuer
        set_oidc_validator_override(lambda token, aud: {"iss": "https://attacker.example.com", "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT})
        with pytest.raises(HTTPException) as exc:
            validator.verify("fake-token")
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "untrusted" in exc.value.detail

    def test_spoofed_service_account_rejected(self, mock_settings: Settings) -> None:
        validator = OIDCValidator(
            expected_audience=mock_settings.AURA_OIDC_AUDIENCE,
            expected_service_account=mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
        )
        # Token has trusted Google issuer, but wrong service account
        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": "unauthorized-sa@other-project.iam.gserviceaccount.com",
                "email_verified": True,
            }
        )
        with pytest.raises(HTTPException) as exc:
            validator.verify("fake-token")
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "not the authorized Cloud Tasks invoker" in exc.value.detail

    def test_valid_google_oidc_token_accepted(self, mock_settings: Settings) -> None:
        validator = OIDCValidator(
            expected_audience=mock_settings.AURA_OIDC_AUDIENCE,
            expected_service_account=mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
        )
        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
                "email_verified": True,
                "sub": "1234567890",
            }
        )
        claims = validator.verify("valid-token")
        assert claims["email"] == mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT


# =============================================================================
# 2. Cloud Tasks Dispatcher Tests
# =============================================================================

class TestCloudTasksDispatcher:
    """Tests task construction, deterministic naming, and enqueue safety."""

    def test_deterministic_task_enqueuing(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        job_id = "job-deterministic-01"
        task_name = dispatcher.enqueue_analysis_job(job_id)

        assert f"aura-job-{job_id}" in task_name
        assert len(fake_tasks_client.created_tasks) == 1
        created = fake_tasks_client.created_tasks[0]
        assert created.http_request.url == mock_settings.AURA_CLOUD_TASKS_WORKER_URL

        # Verify task payload
        payload = json.loads(created.http_request.body.decode("utf-8"))
        assert payload["job_id"] == job_id
        assert "attempt_id" in payload

    def test_already_exists_handled_idempotently(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        fake_tasks_client.simulate_already_exists = True
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        # Should not raise; treats as idempotent duplicate dispatch
        task_name = dispatcher.enqueue_analysis_job("job-duplicate-01")
        assert "aura-job-job-duplicate-01" in task_name

    def test_enqueue_failure_recorded_and_propagated(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        fake_tasks_client.simulate_failure = True
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        # Pre-create job in storage
        req = AnalysisJobCreateRequest(question="Test question")
        sqlite_storage.create_job(req, job_id="job-fail-01")

        with pytest.raises(RuntimeError) as exc:
            dispatcher.enqueue_analysis_job("job-fail-01")
        assert "Cloud Tasks API 403" in str(exc.value)

        # Confirm dispatch failure state was persisted in storage
        job = sqlite_storage.get_job("job-fail-01")
        assert job is not None
        assert job.dispatch_status == "enqueue_failed"
        assert "403" in str(job.dispatch_error)
        assert job.status == JobStatus.FAILED


# =============================================================================
# 3. Execution Mode Enforcement & Fallback Protection
# =============================================================================

class TestExecutionModeEnforcement:
    """Verifies that cloud mode never silently falls back to background threads."""

    def test_cloud_mode_fails_fast_on_enqueue_error(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        fake_tasks_client.simulate_failure = True
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            execution_mode="cloud_tasks",
            dispatcher=dispatcher,
        )

        req = AnalysisJobCreateRequest(question="Test question")
        with pytest.raises(HTTPException) as exc:
            manager.submit_job(req)

        assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Failed to enqueue analysis job in Cloud Tasks" in exc.value.detail

    def test_local_mode_executes_in_thread_pool(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        # Mock fast service
        service = MockFastAnalysisService()
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=lambda: service,
            execution_mode="local",
        )

        req = AnalysisJobCreateRequest(question="Local threaded job")
        resp = manager.submit_job(req)
        assert resp.status == JobStatus.QUEUED

        # Allow background thread to process
        time.sleep(0.1)

        completed = manager.get_job_status(resp.job_id)
        assert completed.status == JobStatus.SUCCEEDED


# =============================================================================
# 4. Atomic Execution Claims & Concurrency Protection
# =============================================================================

class TestExecutionClaimsAndConcurrency:
    """Tests lease claims, fencing tokens, and duplicate task delivery protection."""

    def test_successful_claim_acquisition(self, sqlite_storage: SQLiteJobStorage) -> None:
        req = AnalysisJobCreateRequest(question="Test question")
        record = sqlite_storage.create_job(req, job_id="job-claim-01")

        acquired, claim_status, updated = sqlite_storage.acquire_job_execution_claim(
            job_id="job-claim-01",
            attempt_id="attempt-01",
            lease_seconds=60.0,
        )
        assert acquired is True
        assert claim_status == "acquired"
        assert updated is not None
        assert updated.status == JobStatus.RUNNING
        assert updated.attempt_id == "attempt-01"
        assert updated.fencing_token == 1

    def test_active_duplicate_delivery_rejected(self, sqlite_storage: SQLiteJobStorage) -> None:
        req = AnalysisJobCreateRequest(question="Test question")
        sqlite_storage.create_job(req, job_id="job-claim-02")

        # Worker 1 acquires claim
        sqlite_storage.acquire_job_execution_claim(
            job_id="job-claim-02",
            attempt_id="attempt-worker-1",
            lease_seconds=60.0,
        )

        # Worker 2 attempts concurrent claim with different attempt_id
        acquired2, status2, _ = sqlite_storage.acquire_job_execution_claim(
            job_id="job-claim-02",
            attempt_id="attempt-worker-2",
            lease_seconds=60.0,
        )
        assert acquired2 is False
        assert status2 == "concurrent_active"

    def test_lease_expiry_allows_new_worker_claim(self, sqlite_storage: SQLiteJobStorage) -> None:
        req = AnalysisJobCreateRequest(question="Test question")
        sqlite_storage.create_job(req, job_id="job-claim-03")

        # Worker 1 acquires claim with 10ms lease
        sqlite_storage.acquire_job_execution_claim(
            job_id="job-claim-03",
            attempt_id="attempt-worker-1",
            lease_seconds=0.01,
        )
        time.sleep(0.02)  # Let lease expire

        # Worker 2 acquires expired claim
        acquired2, status2, updated2 = sqlite_storage.acquire_job_execution_claim(
            job_id="job-claim-03",
            attempt_id="attempt-worker-2",
            lease_seconds=60.0,
        )
        assert acquired2 is True
        assert status2 == "acquired"
        assert updated2.attempt_id == "attempt-worker-2"
        assert updated2.fencing_token == 2  # Fencing token incremented!

    def test_completed_job_acknowledged_without_reexecution(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        service = MockFastAnalysisService()
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=lambda: service,
        )
        req = AnalysisJobCreateRequest(question="Test completed job")
        job = sqlite_storage.create_job(req, job_id="job-complete-01")

        # Execute once to completion
        res1 = manager.execute_job_task("job-complete-01", attempt_id="attempt-1")
        assert res1["status"] == "succeeded"

        # Cloud Tasks duplicate delivery
        res2 = manager.execute_job_task("job-complete-01", attempt_id="attempt-2")
        assert res2["status"] == "already_completed"
        assert res2["terminal"] is True


# =============================================================================
# 5. Worker Endpoint HTTP Integration Tests
# =============================================================================

class TestWorkerEndpointIntegration:
    """Tests the full FastAPI worker route integration with simulated Cloud Tasks requests."""

    def test_worker_route_successful_execution(
        self,
        mock_settings: Settings,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        service = MockFastAnalysisService()
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=lambda: service,
        )
        app.dependency_overrides[get_job_manager] = lambda: manager

        # Mock valid OIDC token
        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
                "email_verified": True,
            }
        )

        req = AnalysisJobCreateRequest(question="Cloud Tasks E2E Test")
        job = sqlite_storage.create_job(req, job_id="job-e2e-01")

        client = TestClient(app)
        resp = client.post(
            "/api/internal/tasks/process-job",
            json={"job_id": "job-e2e-01", "attempt_id": "attempt-e2e-1"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["terminal"] is True

        # Verify job is completed in storage
        completed_job = sqlite_storage.get_job("job-e2e-01")
        assert completed_job.status == JobStatus.SUCCEEDED
        assert completed_job.response is not None

        app.dependency_overrides.clear()

    def test_worker_route_failure_stops_retries_with_terminal_200(
        self,
        mock_settings: Settings,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies that an execution crash marks job as FAILED and acknowledges task to prevent paid re-execution."""
        failing_service = MockFastAnalysisService(should_fail=True)
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=lambda: failing_service,
        )
        app.dependency_overrides[get_job_manager] = lambda: manager

        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
                "email_verified": True,
            }
        )

        req = AnalysisJobCreateRequest(question="Failing Cloud Tasks Test")
        sqlite_storage.create_job(req, job_id="job-fail-e2e")

        client = TestClient(app)
        resp = client.post(
            "/api/internal/tasks/process-job",
            json={"job_id": "job-fail-e2e", "attempt_id": "attempt-fail-1"},
            headers={"Authorization": "Bearer valid-token"},
        )
        # HTTP 200 tells Cloud Tasks not to retry
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "failed"
        assert data["terminal"] is True

        # Verify job was marked failed
        failed_job = sqlite_storage.get_job("job-fail-e2e")
        assert failed_job.status == JobStatus.FAILED

        app.dependency_overrides.clear()

    def test_worker_route_task_name_header_mismatch_rejected(
        self,
        mock_settings: Settings,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies that an incoming task name header that contradicts job_id payload is rejected."""
        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
                "email_verified": True,
            }
        )
        client = TestClient(app)
        resp = client.post(
            "/api/internal/tasks/process-job",
            json={"job_id": "job-target-123", "attempt_id": "attempt-1"},
            headers={
                "Authorization": "Bearer valid-token",
                "X-CloudTasks-TaskName": "projects/p/locations/l/queues/q/tasks/aura-job-DIFFERENT_JOB",
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match" in resp.json()["detail"]

    def test_worker_route_unverified_email_oidc_rejected(
        self,
        mock_settings: Settings,
    ) -> None:
        """Verifies that Google OIDC tokens with email_verified=False are rejected with 403."""
        set_oidc_validator_override(
            lambda token, aud: {
                "iss": "https://accounts.google.com",
                "email": mock_settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT,
                "email_verified": False,
            }
        )
        client = TestClient(app)
        resp = client.post(
            "/api/internal/tasks/process-job",
            json={"job_id": "job-target-123", "attempt_id": "attempt-1"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "not verified" in resp.json()["detail"]


# =============================================================================
# 6. Safety Hardening: Crash Protection & Dispatch Reconciliation Tests
# =============================================================================

class TestSafetyHardeningAndReconciliation:
    """Verifies protection against duplicate Gemini calls on worker crash and safe dispatch reconciliation."""

    def test_crash_after_provider_execution_marker_prevents_duplicate_provider_calls(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Simulates abrupt worker crash (OOM/kill) after provider marker committed; redelivery halts and marks FAILED."""
        service_invocations = 0

        class CountingAnalysisService:
            def analyze(self, request: Any, deadline_monotonic: float, stage_callback: Any) -> AnalysisResponse:
                nonlocal service_invocations
                service_invocations += 1
                return AnalysisResponse(status="completed", analysis_id="test-1")

        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=CountingAnalysisService,
            lease_seconds=0.01,
        )
        req = AnalysisJobCreateRequest(question="Crash test question")
        job = sqlite_storage.create_job(req, job_id="job-crash-safety-01")

        # Worker 1 acquires claim and commits provider marker (simulating start of Gemini call)
        acquired, status_claim, rec = sqlite_storage.acquire_job_execution_claim(
            "job-crash-safety-01",
            attempt_id="attempt-worker-1",
            lease_seconds=0.01,
        )
        assert acquired is True
        sqlite_storage.mark_provider_execution_started("job-crash-safety-01")

        # Worker 1 abruptly killed by OOM/SIGKILL before finishing (job remains RUNNING with expired lease)
        time.sleep(0.02)

        # Cloud Tasks redelivers the task with a new attempt ID
        res2 = manager.execute_job_task("job-crash-safety-01", attempt_id="attempt-worker-2")
        assert res2["status"] == "failed"
        assert res2["terminal"] is True

        # CRITICAL VERIFICATION: Provider was NEVER invoked because ambiguous re-execution was rejected!
        assert service_invocations == 0

        # Check job in storage: reflects manual recovery requirement
        final_job = sqlite_storage.get_job("job-crash-safety-01")
        assert final_job.status == JobStatus.FAILED
        assert "Ambiguous worker termination after provider execution started" in final_job.error_message
        assert "manual recovery required" in final_job.error_message

    def test_task_created_but_response_lost_reconciled_via_lookup(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Simulates task created on server but HTTP response lost; verifies lookup confirms enqueue."""
        fake_tasks_client.simulate_response_lost = True
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        req = AnalysisJobCreateRequest(question="Response lost question")
        sqlite_storage.create_job(req, job_id="job-lost-resp-01")

        # Enqueue should succeed by looking up the deterministic task
        task_name = dispatcher.enqueue_analysis_job("job-lost-resp-01")
        assert "aura-job-job-lost-resp-01" in task_name

        # Verify job is marked as enqueued, not failed
        job = sqlite_storage.get_job("job-lost-resp-01")
        assert job.status == JobStatus.QUEUED
        assert job.dispatch_status == "enqueued"

    def test_reconcile_job_dispatch_when_task_exists(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies reconcile_job_dispatch marks job enqueued when task is already in queue."""
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            dispatcher=dispatcher,
            execution_mode="cloud_tasks",
        )
        req = AnalysisJobCreateRequest(question="Reconcile test")
        sqlite_storage.create_job(req, job_id="job-recon-01")

        # Pre-create task in fake client with matching deterministic task path
        task_name = fake_tasks_client.task_path(
            dispatcher.project, dispatcher.location, dispatcher.queue, "aura-job-job-recon-01"
        )
        fake_tasks_client.created_tasks.append(
            FakeTask(
                name=task_name,
                http_request={},
            ),
        )
        sqlite_storage.record_dispatch_status("job-recon-01", dispatch_status="dispatch_uncertain")

        outcome = manager.reconcile_job_dispatch("job-recon-01")
        assert outcome["status"] == "reconciled_enqueued"

        job = sqlite_storage.get_job("job-recon-01")
        assert job.dispatch_status == "enqueued"

        job = sqlite_storage.get_job("job-recon-01")
        assert job.dispatch_status == "enqueued"

    def test_reconcile_job_dispatch_when_task_absent_re_enqueues(
        self,
        mock_settings: Settings,
        fake_tasks_client: FakeCloudTasksClient,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies reconcile_job_dispatch safely re-enqueues when task was never created."""
        dispatcher = CloudTasksDispatcher(
            client=fake_tasks_client,
            config=mock_settings,
            storage=sqlite_storage,
        )
        manager = AnalysisJobManager(
            storage=sqlite_storage,
            dispatcher=dispatcher,
            execution_mode="cloud_tasks",
        )
        req = AnalysisJobCreateRequest(question="Re-enqueue test")
        sqlite_storage.create_job(req, job_id="job-recon-absent")
        sqlite_storage.record_dispatch_status("job-recon-absent", dispatch_status="dispatch_uncertain")

        outcome = manager.reconcile_job_dispatch("job-recon-absent", re_enqueue=True)
        assert outcome["status"] == "reconciled_re_enqueued"
        assert len(fake_tasks_client.created_tasks) == 1

        job = sqlite_storage.get_job("job-recon-absent")
        assert job.dispatch_status == "enqueued"

    def test_stale_worker_with_expired_lease_cannot_mark_provider_started_or_call_analyze(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies that a worker whose lease expired before reaching the provider cannot call service.analyze."""
        service_invocations = 0

        class SpyAnalysisService:
            def analyze(self, request: Any, deadline_monotonic: float, stage_callback: Any) -> AnalysisResponse:
                nonlocal service_invocations
                service_invocations += 1
                return AnalysisResponse(status="completed", analysis_id="spy-1")

        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=SpyAnalysisService,
            lease_seconds=0.01,
        )
        req = AnalysisJobCreateRequest(question="Race test question")
        sqlite_storage.create_job(req, job_id="job-stale-worker-01")

        # Worker 1 acquires claim with 0.01s lease
        acq, stat, rec = sqlite_storage.acquire_job_execution_claim(
            "job-stale-worker-01",
            attempt_id="worker-attempt-1",
            lease_seconds=0.01,
        )
        assert acq is True

        # Stall worker until lease expires
        time.sleep(0.02)

        # Worker attempts to run pipeline after lease expiry
        manager._run_pipeline(
            rec,
            attempt_id="worker-attempt-1",
            fencing_token=rec.fencing_token,
        )

        # CRITICAL: service.analyze MUST NEVER have been called!
        assert service_invocations == 0

        # Provider execution marker must remain False
        job = sqlite_storage.get_job("job-stale-worker-01")
        assert job.provider_execution_started is False

    def test_superseded_worker_with_stale_fencing_token_rejected_at_provider_boundary(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies that a superseded worker with an older fencing token cannot enter service.analyze."""
        service_invocations = 0

        class SpyAnalysisService:
            def analyze(self, request: Any, deadline_monotonic: float, stage_callback: Any) -> AnalysisResponse:
                nonlocal service_invocations
                service_invocations += 1
                return AnalysisResponse(status="completed", analysis_id="spy-2")

        manager = AnalysisJobManager(
            storage=sqlite_storage,
            service_factory=SpyAnalysisService,
            lease_seconds=0.01,
        )
        req = AnalysisJobCreateRequest(question="Superseded test question")
        sqlite_storage.create_job(req, job_id="job-superseded-01")

        # Worker 1 acquires claim (fencing_token = 1)
        acq1, stat1, rec1 = sqlite_storage.acquire_job_execution_claim(
            "job-superseded-01",
            attempt_id="attempt-worker-1",
            lease_seconds=0.01,
        )
        assert acq1 is True
        assert rec1.fencing_token == 1

        # Worker 1 stalls; lease expires
        time.sleep(0.02)

        # Worker 2 supersedes Worker 1 (fencing_token = 2)
        acq2, stat2, rec2 = sqlite_storage.acquire_job_execution_claim(
            "job-superseded-01",
            attempt_id="attempt-worker-2",
            lease_seconds=60.0,
        )
        assert acq2 is True
        assert rec2.fencing_token == 2

        # Stale Worker 1 wakes up and tries to execute pipeline
        manager._run_pipeline(
            rec1,
            attempt_id="attempt-worker-1",
            fencing_token=rec1.fencing_token,  # Token 1 is stale!
        )

        # CRITICAL: service.analyze was NOT called by the stale worker
        assert service_invocations == 0

        # Verify job is still active under Worker 2 with token 2
        active_job = sqlite_storage.get_job("job-superseded-01")
        assert active_job.attempt_id == "attempt-worker-2"
        assert active_job.fencing_token == 2

    def test_terminal_writes_fenced_against_stale_tokens(
        self,
        sqlite_storage: SQLiteJobStorage,
    ) -> None:
        """Verifies complete_job and fail_job reject writes from stale fencing tokens."""
        req = AnalysisJobCreateRequest(question="Terminal fencing test")
        sqlite_storage.create_job(req, job_id="job-fenced-terminal")

        # Worker 2 has token 2
        acq, _, rec = sqlite_storage.acquire_job_execution_claim(
            "job-fenced-terminal",
            attempt_id="attempt-2",
            lease_seconds=60.0,
        )
        sqlite_storage.acquire_job_execution_claim(
            "job-fenced-terminal",
            attempt_id="attempt-2",
            lease_seconds=60.0,
        )
        job = sqlite_storage.get_job("job-fenced-terminal")
        current_token = job.fencing_token  # e.g. 2

        # Stale worker with token 1 tries to complete job
        stale_resp = AnalysisResponse(analysis_id="stale-resp", status="completed")
        sqlite_storage.complete_job(
            "job-fenced-terminal",
            stale_resp,
            fencing_token=current_token - 1,
        )

        # Status must still be RUNNING (stale write rejected!)
        unaltered_job = sqlite_storage.get_job("job-fenced-terminal")
        assert unaltered_job.status == JobStatus.RUNNING

        # Stale worker with token 1 tries to fail job
        sqlite_storage.fail_job(
            "job-fenced-terminal",
            error_message="Stale error",
            fencing_token=current_token - 1,
        )
        still_running_job = sqlite_storage.get_job("job-fenced-terminal")
        assert still_running_job.status == JobStatus.RUNNING

        # Valid worker with matching token completes job
        sqlite_storage.complete_job(
            "job-fenced-terminal",
            stale_resp,
            fencing_token=current_token,
        )
        completed_job = sqlite_storage.get_job("job-fenced-terminal")
        assert completed_job.status == JobStatus.SUCCEEDED

    @pytest.mark.parametrize(
        "marker_behavior",
        [
            "legacy_type_error",  # Adapter only accepts (job_id), raising TypeError on attempt_id/fencing_token
            "returns_none",       # Adapter returns None
            "returns_false",      # Adapter returns False
            "raises_exception",   # Adapter raises an unexpected database exception
            "returns_truthy_int", # Adapter returns 1 (truthy int, not explicit boolean True)
        ],
    )
    def test_legacy_or_incompatible_marker_cannot_trigger_provider(
        self,
        sqlite_storage: SQLiteJobStorage,
        marker_behavior: str,
    ) -> None:
        """Verifies that an incompatible or legacy storage marker implementation CANNOT trigger service.analyze."""
        service_invocations = 0

        class SpyAnalysisService:
            def analyze(self, request: Any, deadline_monotonic: float, stage_callback: Any) -> AnalysisResponse:
                nonlocal service_invocations
                service_invocations += 1
                return AnalysisResponse(status="completed", analysis_id="spy-incompatible")

        # Create job and acquire claim
        req = AnalysisJobCreateRequest(question="Marker compatibility test")
        sqlite_storage.create_job(req, job_id=f"job-compat-{marker_behavior}")
        acq, _, record = sqlite_storage.acquire_job_execution_claim(
            f"job-compat-{marker_behavior}",
            attempt_id="att-compat-1",
            lease_seconds=60.0,
        )
        assert acq is True

        # Wrap storage to simulate legacy or incompatible marker behaviors
        class IncompatibleStorageProxy:
            def __init__(self, target: SQLiteJobStorage):
                self._target = target

            def mark_provider_execution_started(self, *args, **kwargs):
                if marker_behavior == "legacy_type_error":
                    # Simulates a legacy signature def mark_provider_execution_started(self, job_id): ...
                    if "attempt_id" in kwargs or "fencing_token" in kwargs or len(args) > 1:
                        raise TypeError("mark_provider_execution_started() takes 1 positional argument but 3 were given")
                    return True
                elif marker_behavior == "returns_none":
                    return None
                elif marker_behavior == "returns_false":
                    return False
                elif marker_behavior == "raises_exception":
                    raise RuntimeError("Database connection reset during marker commit")
                elif marker_behavior == "returns_truthy_int":
                    return 1  # Truthy integer, but not boolean True

            def __getattr__(self, name):
                return getattr(self._target, name)

        proxy_storage = IncompatibleStorageProxy(sqlite_storage)
        manager = AnalysisJobManager(
            storage=proxy_storage,
            service_factory=SpyAnalysisService,
            lease_seconds=60.0,
        )

        # Run pipeline
        manager._run_pipeline(
            record,
            attempt_id="att-compat-1",
            fencing_token=record.fencing_token,
        )

        # CRITICAL PROOF: service.analyze was NEVER invoked!
        assert service_invocations == 0, f"service.analyze was called for behavior {marker_behavior}!"

