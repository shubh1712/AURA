"""AURA Asynchronous Analysis Job Manager.

Coordinates asynchronous job intake, bounded concurrent execution in a thread pool,
stage tracking, restart recovery, and safe result retrieval.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional
import uuid
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import (
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    JobStatus,
    PipelineStage,
)
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.services.jobs.base import JobRecord, JobStorageInterface
from app.services.jobs.factory import get_job_storage
from app.services.tasks.dispatcher import CloudTasksDispatcher

logger = logging.getLogger(__name__)


class AnalysisJobManager:
    """Manages asynchronous job scheduling, bounded worker concurrency, and result access."""

    def __init__(
        self,
        storage: Optional[JobStorageInterface] = None,
        service_factory: Optional[Callable[[], AnalysisService]] = None,
        max_workers: Optional[int] = None,
        default_timeout_seconds: Optional[float] = None,
        execution_mode: Optional[str] = None,
        dispatcher: Optional[CloudTasksDispatcher] = None,
        lease_seconds: Optional[float] = None,
    ) -> None:
        """Initializes job manager with storage and execution configuration.

        Args:
            storage: Persistent JobStorageInterface instance (defaults to configured storage factory).
            service_factory: Callable returning an AnalysisService instance.
            max_workers: Maximum concurrent jobs executing in worker pool.
            default_timeout_seconds: Default parent timeout for submitted jobs.
            execution_mode: 'local' (thread pool) or 'cloud_tasks' (Google Cloud Tasks).
            dispatcher: Optional CloudTasksDispatcher instance for enqueuing tasks.
            lease_seconds: Duration of exclusive execution claim lease in seconds.
        """
        self._owns_storage = storage is None
        self.storage: JobStorageInterface = storage or get_job_storage()
        self.service_factory = service_factory or get_analysis_service
        self.max_workers = max_workers or getattr(settings, "AURA_MAX_JOB_WORKERS", 4)
        self.default_timeout_seconds = default_timeout_seconds or getattr(
            settings, "AURA_JOB_DEFAULT_TIMEOUT_SECONDS", 180.0
        )
        self.execution_mode = (
            execution_mode.strip().lower()
            if execution_mode
            else getattr(settings, "AURA_EXECUTION_MODE", "local").strip().lower()
        )
        self.lease_seconds = lease_seconds or getattr(settings, "AURA_JOB_LEASE_SECONDS", 300.0)
        self._dispatcher = dispatcher

        # Recover any orphaned jobs from prior process crash (applies to local/SQLite)
        self.storage.recover_stale_jobs_on_startup()

        # Bounded worker concurrency pool for local threaded execution
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="aura-job-worker",
        )

    @property
    def dispatcher(self) -> CloudTasksDispatcher:
        """Lazily initializes and returns CloudTasksDispatcher."""
        if self._dispatcher is None:
            self._dispatcher = CloudTasksDispatcher(storage=self.storage)
        return self._dispatcher

    def submit_job(self, request: AnalysisJobCreateRequest) -> AnalysisJobStatusResponse:
        """Enqueues an asynchronous analysis job for execution.

        Args:
            request: Validated job creation payload.

        Returns:
            AnalysisJobStatusResponse showing initial QUEUED state.
        """
        job = self.storage.create_job(
            request=request,
            default_timeout_seconds=self.default_timeout_seconds,
        )

        if self.execution_mode == "cloud_tasks":
            try:
                task_name = self.dispatcher.enqueue_analysis_job(job.job_id)
                logger.info(
                    "Job %s dispatched to Cloud Tasks: %s",
                    job.job_id,
                    task_name,
                )
            except Exception as exc:
                # Never silently fall back to background threads if cloud dispatch fails
                logger.error("Cloud Tasks dispatch failed for job %s: %s", job.job_id, exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to enqueue analysis job in Cloud Tasks: {exc}",
                ) from exc
        else:
            # Local threaded dispatch
            self.storage.record_dispatch_status(job.job_id, dispatch_status="local")
            self._executor.submit(self._execute_job, job.job_id)

        return self._record_to_response(job)

    def _execute_job(self, job_id: str) -> None:
        """Worker task executing the analysis pipeline in a local background thread."""
        job = self.storage.get_job(job_id)
        if not job or job.status != JobStatus.QUEUED:
            return

        current_stage = PipelineStage.STAGE1_DECISION_FRAMER
        self.storage.update_running(
            job_id=job_id,
            stage=current_stage,
            message="Deconstructing decision problem (Decision Framer).",
        )
        self._run_pipeline(job, attempt_id=job.attempt_id, fencing_token=job.fencing_token)

    def execute_job_task(
        self,
        job_id: str,
        attempt_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes an analysis job synchronously within an authenticated Cloud Tasks HTTP worker request.

        Enforces lease ownership, fencing tokens, idempotency, and terminal failure states to prevent
        duplicate or uncontrolled Gemini calls on at-least-once deliveries.
        """
        eff_attempt_id = attempt_id or str(uuid.uuid4())
        acquired, claim_status, record = self.storage.acquire_job_execution_claim(
            job_id=job_id,
            attempt_id=eff_attempt_id,
            lease_seconds=self.lease_seconds,
        )

        if not acquired:
            if claim_status == "not_found":
                logger.warning("Cloud Tasks worker received non-existent job_id: %s", job_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Analysis job '{job_id}' not found.",
                )
            if claim_status in ("already_completed", "already_terminal"):
                logger.info(
                    "Cloud Tasks duplicate acknowledged: job %s has already reached terminal status '%s'.",
                    job_id,
                    claim_status,
                )
                return {
                    "status": claim_status,
                    "terminal": True,
                    "job_id": job_id,
                    "message": "Job already reached terminal state; task acknowledged without re-execution.",
                }
            if claim_status == "ambiguous_failure":
                logger.error(
                    "Cloud Tasks worker attempt rejected for job %s: prior worker lease expired after provider execution started. "
                    "Job marked FAILED for manual recovery to prevent duplicate Gemini invocations.",
                    job_id,
                )
                return {
                    "status": "failed",
                    "terminal": True,
                    "job_id": job_id,
                    "message": "Prior worker lease expired after provider execution started; transitioned to failed for manual recovery.",
                }
            if claim_status == "concurrent_active":
                logger.warning(
                    "Cloud Tasks duplicate delivery ignored: job %s is active under another lease.",
                    job_id,
                )
                return {
                    "status": claim_status,
                    "terminal": False,
                    "job_id": job_id,
                    "message": "Job is actively running under an active lease.",
                }
            logger.warning("Execution claim rejected for job %s with status %s", job_id, claim_status)
            return {"status": claim_status, "terminal": False, "job_id": job_id}

        # Claim acquired: execute pipeline synchronously within this HTTP worker request
        logger.info(
            "Acquired execution claim for job %s (attempt_id=%s, fencing_token=%d)",
            job_id,
            eff_attempt_id,
            record.fencing_token,
        )
        self._run_pipeline(
            record,
            attempt_id=eff_attempt_id,
            fencing_token=record.fencing_token,
        )

        final_job = self.storage.get_job(job_id)
        final_status = final_job.status.value if final_job else "unknown"
        return {
            "status": final_status,
            "terminal": True,
            "job_id": job_id,
            "fencing_token": record.fencing_token,
        }

    def _run_pipeline(
        self,
        job: JobRecord,
        attempt_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> None:
        """Executes the six-stage reasoning pipeline and persists terminal outcomes."""
        job_id = job.job_id
        eff_attempt_id = attempt_id or job.attempt_id
        eff_fencing_token = fencing_token if fencing_token is not None else job.fencing_token
        current_stage = PipelineStage.STAGE1_DECISION_FRAMER
        service = self.service_factory()
        if job.framer_timeout_seconds is not None:
            service.framer_operation_timeout_seconds = job.framer_timeout_seconds
        if job.boardroom_timeout_seconds is not None:
            service.boardroom_operation_timeout_seconds = job.boardroom_timeout_seconds
        if getattr(job, "recommendation_timeout_seconds", None) is not None:
            service.recommendation_operation_timeout_seconds = job.recommendation_timeout_seconds
        if getattr(job, "scenario_timeout_seconds", None) is not None:
            service.scenario_operation_timeout_seconds = job.scenario_timeout_seconds

        t_start = time.monotonic()
        deadline_monotonic = t_start + job.timeout_seconds

        def _stage_callback(stage_name: str) -> None:
            nonlocal current_stage
            elapsed = time.monotonic() - t_start
            if stage_name == "stage1_decision_framer":
                current_stage = PipelineStage.STAGE1_DECISION_FRAMER
                msg = "Deconstructing decision problem (Decision Framer)."
            elif stage_name == "stage2_evidence_engine":
                current_stage = PipelineStage.STAGE2_EVIDENCE_ENGINE
                msg = "Gathering and mapping empirical evidence (Evidence Engine)."
            elif stage_name == "stage3_ai_boardroom":
                current_stage = PipelineStage.STAGE3_AI_BOARDROOM
                msg = "Conducting cross-perspective deliberation (AI Boardroom)."
            elif stage_name == "stage4_recommendation":
                current_stage = PipelineStage.STAGE4_RECOMMENDATION
                msg = "Developing recommendation and action plan (Recommendation Engine)."
            elif stage_name == "stage5_scenarios":
                current_stage = PipelineStage.STAGE5_SCENARIOS
                msg = "Generating future scenarios and milestones (Scenario Engine)."
            elif stage_name == "stage6_resilience":
                current_stage = PipelineStage.STAGE6_RESILIENCE
                msg = "Evaluating decision resilience (Deterministic Resilience Engine)."
            else:
                msg = f"Executing stage: {stage_name}"
            logger.info(
                "Asynchronous analysis job %s transitioned to %s (elapsed=%.2fs)",
                job_id,
                current_stage.value,
                elapsed,
            )
            try:
                self.storage.update_stage(job_id, current_stage, msg, fencing_token=eff_fencing_token)
            except TypeError:
                self.storage.update_stage(job_id, current_stage, msg)

        try:
            analysis_req = AnalysisRequest(
                question=job.request.question,
                context=job.request.context,
                constraints=job.request.constraints,
            )
            # Atomically verify active attempt, fencing token, RUNNING status, and lease before provider call
            marker_ok = False
            try:
                marker_res = self.storage.mark_provider_execution_started(
                    job_id,
                    attempt_id=eff_attempt_id,
                    fencing_token=eff_fencing_token,
                )
                marker_ok = (marker_res is True)
            except Exception as marker_exc:
                logger.error(
                    "mark_provider_execution_started failed with exception for job %s: %s",
                    job_id,
                    marker_exc,
                )
                marker_ok = False

            if not marker_ok:
                err_msg = (
                    f"Execution fence violation: claim for job {job_id} "
                    f"(attempt={eff_attempt_id}, fencing_token={eff_fencing_token}) is stale, superseded, lease expired, "
                    "or storage rejected provider boundary marker. "
                    "Aborting before invoking provider to prevent duplicate/unauthorized execution."
                )
                logger.error(err_msg)
                raise RuntimeError(err_msg)

            response = service.analyze(
                request=analysis_req,
                deadline_monotonic=deadline_monotonic,
                stage_callback=_stage_callback,
            )
            total_duration = time.monotonic() - t_start
            if response.status == "completed":
                completion_msg = "Analysis completed successfully."
            elif getattr(response, "resilience", None) is None and getattr(response, "scenarios", None) is not None:
                completion_msg = "Analysis completed with scenarios (resilience evaluation unavailable)."
            elif getattr(response, "scenarios", None) is None and getattr(response, "recommendation", None) is not None:
                completion_msg = "Analysis completed with recommendation (scenario generation unavailable)."
            elif getattr(response, "recommendation", None) is None:
                completion_msg = "Analysis completed with Boardroom deliberation (recommendation stage unavailable)."
            else:
                completion_msg = "Analysis completed with partial success."
            try:
                self.storage.complete_job(
                    job_id,
                    response,
                    message=completion_msg,
                    fencing_token=eff_fencing_token,
                )
            except TypeError:
                self.storage.complete_job(
                    job_id,
                    response,
                    message=completion_msg,
                )
            logger.info(
                "Asynchronous analysis job %s completed in %.2fs (status: %s).",
                job_id,
                total_duration,
                response.status,
            )

        except HTTPException as he:
            elapsed = time.monotonic() - t_start
            remaining = max(0.0, deadline_monotonic - time.monotonic())
            logger.warning(
                "Asynchronous analysis job %s failed with HTTP %d at stage %s (elapsed=%.2fs, remaining_budget=%.2fs): %s",
                job_id,
                he.status_code,
                current_stage.value,
                elapsed,
                remaining,
                he.detail,
            )
            if he.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
                try:
                    self.storage.timeout_job(
                        job_id,
                        error_message=str(he.detail),
                        stage=current_stage,
                        fencing_token=eff_fencing_token,
                    )
                except TypeError:
                    self.storage.timeout_job(
                        job_id,
                        error_message=str(he.detail),
                        stage=current_stage,
                    )
            else:
                try:
                    self.storage.fail_job(
                        job_id,
                        error_message=str(he.detail),
                        error_status_code=he.status_code,
                        stage=current_stage,
                        fencing_token=eff_fencing_token,
                    )
                except TypeError:
                    self.storage.fail_job(
                        job_id,
                        error_message=str(he.detail),
                        error_status_code=he.status_code,
                        stage=current_stage,
                    )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            remaining = max(0.0, deadline_monotonic - time.monotonic())
            logger.exception(
                "Unexpected error executing analysis job %s at stage %s (elapsed=%.2fs, remaining_budget=%.2fs): %s",
                job_id,
                current_stage.value,
                elapsed,
                remaining,
                exc,
            )
            # If the failure was a fence violation from a stale worker, avoid overwriting storage
            if "Execution fence violation" in str(exc):
                logger.warning("Aborted execution without terminal write for superseded job %s", job_id)
                return

            try:
                self.storage.fail_job(
                    job_id,
                    error_message="Internal analysis execution failure.",
                    error_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    stage=current_stage,
                    fencing_token=eff_fencing_token,
                )
            except TypeError:
                self.storage.fail_job(
                    job_id,
                    error_message="Internal analysis execution failure.",
                    error_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    stage=current_stage,
                )

    def get_job_status(
        self,
        job_id: str,
        owner_id: Optional[str] = None,
    ) -> AnalysisJobStatusResponse:
        """Retrieves current job status and stage.

        Raises:
            HTTPException 404: If job does not exist.
            HTTPException 403: If owner_id does not match job owner.
        """
        job = self.storage.get_job_by_any_id(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis job '{job_id}' not found.",
            )

        self._check_ownership(job, owner_id)
        return self._record_to_response(job)

    def get_job_result(
        self,
        job_id: str,
        owner_id: Optional[str] = None,
    ) -> AnalysisResponse:
        """Retrieves the full validated AnalysisResponse for a completed job.

        Raises:
            HTTPException 404: If job does not exist.
            HTTPException 403: If owner_id does not match job owner.
            HTTPException 409: If job is still QUEUED or RUNNING.
            HTTPException 504: If job timed out.
            HTTPException 500/502/503: If job failed.
        """
        job = self.storage.get_job_by_any_id(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis job '{job_id}' not found.",
            )

        self._check_ownership(job, owner_id)

        if job.status == JobStatus.QUEUED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analysis job is queued and has not yet started.",
            )

        if job.status == JobStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Analysis job is currently running (stage: {job.stage.value}).",
            )

        if job.status == JobStatus.TIMED_OUT:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=job.error_message or "Decision analysis timed out while evaluating the inquiry.",
            )

        if job.status == JobStatus.FAILED:
            status_code = job.error_status_code or status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(
                status_code=status_code,
                detail=job.error_message or "Analysis job execution failed.",
            )

        if job.status == JobStatus.SUCCEEDED and job.response is not None:
            return job.response

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis job completed without a valid response payload.",
        )

    def _check_ownership(self, job: JobRecord, caller_owner_id: Optional[str]) -> None:
        """Verifies caller identity matches job owner if ownership was specified."""
        if job.owner_id is not None and caller_owner_id is not None:
            if job.owner_id != caller_owner_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: you do not have permission to view this job.",
                )

    def _record_to_response(self, job: JobRecord) -> AnalysisJobStatusResponse:
        """Maps an internal JobRecord to an external AnalysisJobStatusResponse schema."""
        analysis_id = job.response.analysis_id if job.response is not None else None
        return AnalysisJobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            stage=job.stage,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            progress_message=job.progress_message,
            error=job.error_message,
            error_status_code=job.error_status_code,
            owner_id=job.owner_id,
            analysis_id=analysis_id,
        )

    def reconcile_job_dispatch(
        self,
        job_id: str,
        re_enqueue: bool = True,
    ) -> Dict[str, Any]:
        """Reconciles uncertain or pending Cloud Tasks dispatch for an analysis job.

        Inspects Cloud Tasks using deterministic task naming. If the task exists in Cloud Tasks,
        updates dispatch_status="enqueued". If absent and job is still QUEUED, safely re-enqueues
        (if re_enqueue=True) or marks enqueue_failed.
        """
        job = self.storage.get_job(job_id)
        if not job:
            return {"status": "not_found", "job_id": job_id}

        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT):
            return {
                "status": "already_terminal",
                "job_id": job_id,
                "job_status": job.status.value,
            }

        if job.status == JobStatus.RUNNING:
            return {
                "status": "already_running",
                "job_id": job_id,
                "job_status": job.status.value,
            }

        try:
            task = self.dispatcher.get_task(job_id)
            if task is not None:
                self.storage.record_dispatch_status(job_id, dispatch_status="enqueued")
                return {
                    "status": "reconciled_enqueued",
                    "job_id": job_id,
                    "message": "Task confirmed existing in Cloud Tasks.",
                }
        except Exception as exc:
            logger.warning("Reconciliation lookup failed for job %s: %s", job_id, exc)
            return {
                "status": "still_uncertain",
                "job_id": job_id,
                "error": str(exc),
            }

        # Task definitely not in queue
        if re_enqueue:
            try:
                task_name = self.dispatcher.enqueue_analysis_job(job_id)
                return {
                    "status": "reconciled_re_enqueued",
                    "job_id": job_id,
                    "task_name": task_name,
                }
            except Exception as exc:
                return {
                    "status": "re_enqueue_failed",
                    "job_id": job_id,
                    "error": str(exc),
                }
        else:
            self.storage.record_dispatch_status(
                job_id,
                dispatch_status="enqueue_failed",
                error_message="Reconciliation confirmed task was not created.",
            )
            return {
                "status": "reconciled_failed",
                "job_id": job_id,
                "message": "Task confirmed absent and job marked failed.",
            }

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully shuts down worker thread pool and closes storage if owned."""
        self._executor.shutdown(wait=wait)
        if self._owns_storage:
            self.storage.close()


# Module-level singleton
_default_job_manager: Optional[AnalysisJobManager] = None
_manager_lock = threading.Lock()


def get_job_manager() -> AnalysisJobManager:
    """Dependency provider returning singleton AnalysisJobManager."""
    global _default_job_manager
    if _default_job_manager is None:
        with _manager_lock:
            if _default_job_manager is None:
                _default_job_manager = AnalysisJobManager()
    return _default_job_manager
