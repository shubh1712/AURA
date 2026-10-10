"""AURA Asynchronous Analysis Job Manager.

Coordinates asynchronous job intake, bounded concurrent execution in a thread pool,
stage tracking, restart recovery, and safe result retrieval.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Callable, Optional
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
from app.services.jobs.storage import JobRecord, SQLiteJobStorage

logger = logging.getLogger(__name__)


class AnalysisJobManager:
    """Manages asynchronous job scheduling, bounded worker concurrency, and result access."""

    def __init__(
        self,
        storage: Optional[SQLiteJobStorage] = None,
        service_factory: Optional[Callable[[], AnalysisService]] = None,
        max_workers: Optional[int] = None,
        default_timeout_seconds: Optional[float] = None,
    ) -> None:
        """Initializes job manager with storage and thread pool.

        Args:
            storage: Persistent SQLiteJobStorage instance (defaults to configured path).
            service_factory: Callable returning an AnalysisService instance.
            max_workers: Maximum concurrent jobs executing in worker pool.
            default_timeout_seconds: Default parent timeout for submitted jobs.
        """
        db_path = getattr(settings, "AURA_JOBS_DB_PATH", "aura_jobs.db")
        self._owns_storage = storage is None
        self.storage = storage or SQLiteJobStorage(db_path=db_path)
        self.service_factory = service_factory or get_analysis_service
        self.max_workers = max_workers or getattr(settings, "AURA_MAX_JOB_WORKERS", 4)
        self.default_timeout_seconds = default_timeout_seconds or getattr(
            settings, "AURA_JOB_DEFAULT_TIMEOUT_SECONDS", 180.0
        )

        # Recover any orphaned jobs from prior process crash
        self.storage.recover_stale_jobs_on_startup()

        # Bounded worker concurrency pool
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="aura-job-worker",
        )

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

        # Dispatch execution to bounded worker thread pool
        self._executor.submit(self._execute_job, job.job_id)

        return self._record_to_response(job)

    def _execute_job(self, job_id: str) -> None:
        """Worker task executing the analysis pipeline in a background thread."""
        job = self.storage.get_job(job_id)
        if not job or job.status != JobStatus.QUEUED:
            return

        current_stage = PipelineStage.STAGE1_DECISION_FRAMER
        self.storage.update_running(
            job_id=job_id,
            stage=current_stage,
            message="Deconstructing decision problem (Decision Framer).",
        )

        # Construct AnalysisService for this job
        service = self.service_factory()
        if job.framer_timeout_seconds is not None:
            service.framer_operation_timeout_seconds = job.framer_timeout_seconds
        if job.boardroom_timeout_seconds is not None:
            service.boardroom_operation_timeout_seconds = job.boardroom_timeout_seconds

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
            else:
                msg = f"Executing stage: {stage_name}"
            logger.info(
                "Asynchronous analysis job %s transitioned to %s (elapsed=%.2fs)",
                job_id,
                current_stage.value,
                elapsed,
            )
            self.storage.update_stage(job_id, current_stage, msg)

        try:
            analysis_req = AnalysisRequest(
                question=job.request.question,
                context=job.request.context,
                constraints=job.request.constraints,
            )
            response = service.analyze(
                request=analysis_req,
                deadline_monotonic=deadline_monotonic,
                stage_callback=_stage_callback,
            )
            total_duration = time.monotonic() - t_start
            self.storage.complete_job(job_id, response)
            logger.info(
                "Asynchronous analysis job %s completed successfully in %.2fs.",
                job_id,
                total_duration,
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
                self.storage.timeout_job(
                    job_id,
                    error_message=str(he.detail),
                    stage=current_stage,
                )
            else:
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
        job = self.storage.get_job(job_id)
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
        job = self.storage.get_job(job_id)
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
        )

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
