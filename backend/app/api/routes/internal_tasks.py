"""AURA Internal Cloud Tasks Worker Route.

Receives authenticated HTTP task deliveries from Google Cloud Tasks, validates Google OIDC
signatures, and executes analysis jobs synchronously within the HTTP request lifecycle.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.routes.analysis_jobs import get_job_manager
from app.services.jobs.manager import AnalysisJobManager
from app.services.tasks.auth import verify_cloud_tasks_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/tasks", tags=["Internal Tasks"])


class ProcessJobTaskPayload(BaseModel):
    """Payload delivered by Cloud Tasks to invoke job execution."""
    job_id: str = Field(..., description="Unique analysis job identifier.")
    attempt_id: Optional[str] = Field(None, description="Unique attempt UUID for idempotency.")


class ProcessJobTaskResponse(BaseModel):
    """Execution status returned to Cloud Tasks."""
    status: str
    terminal: bool
    job_id: str
    message: Optional[str] = None
    fencing_token: Optional[int] = None


@router.post(
    "/process-job",
    response_model=ProcessJobTaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an analysis job from Cloud Tasks",
    description="Authenticated worker endpoint invoked by Cloud Tasks to process an analysis job.",
)
async def process_job_task(
    payload: ProcessJobTaskPayload,
    request: Request,
    auth_claims: Dict[str, Any] = Depends(verify_cloud_tasks_auth),
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> ProcessJobTaskResponse:
    """Executes an analysis job within the HTTP request lifetime.

    Returns HTTP 200 when execution reaches a terminal state (COMPLETED, FAILED, TIMED_OUT)
    or when duplicate tasks are safely deduplicated, ensuring Cloud Tasks acknowledges delivery.
    """
    task_name_header = request.headers.get("X-CloudTasks-TaskName")
    if task_name_header:
        expected_token = f"aura-job-{payload.job_id}"
        if not (task_name_header.endswith(expected_token) or payload.job_id in task_name_header):
            logger.warning(
                "Task name header mismatch: header '%s' does not match payload job_id '%s'",
                task_name_header,
                payload.job_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"X-CloudTasks-TaskName header does not match job_id '{payload.job_id}'.",
            )

    logger.info(
        "Received authenticated Cloud Tasks execution request for job %s (attempt_id=%s, caller=%s)",
        payload.job_id,
        payload.attempt_id,
        auth_claims.get("email", "unknown"),
    )

    try:
        result = await run_in_threadpool(
            manager.execute_job_task,
            job_id=payload.job_id,
            attempt_id=payload.attempt_id,
        )
        return ProcessJobTaskResponse(
            status=result["status"],
            terminal=result.get("terminal", True),
            job_id=payload.job_id,
            message=result.get("message"),
            fencing_token=result.get("fencing_token"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in Cloud Tasks worker endpoint for job %s: %s", payload.job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Worker execution failed unexpectedly: {exc}",
        ) from exc
