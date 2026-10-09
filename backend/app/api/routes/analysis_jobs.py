"""AURA Asynchronous Analysis Jobs API Router.

Provides endpoints for asynchronous decision analysis job submission,
polling status and stage transitions, and retrieving complete validated results.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, status

from app.schemas.analysis import AnalysisResponse
from app.schemas.job import (
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
)
from app.services.jobs.manager import AnalysisJobManager, get_job_manager

router = APIRouter(tags=["Analysis Jobs"])


@router.post(
    "/analysis/jobs",
    response_model=AnalysisJobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an asynchronous decision analysis job",
)
@router.post(
    "/jobs",
    response_model=AnalysisJobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def create_analysis_job(
    request: AnalysisJobCreateRequest,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
) -> AnalysisJobStatusResponse:
    """Submits a decision inquiry as an asynchronous job.

    Returns immediately with job_id and initial QUEUED status.
    Processing continues in the background within the bounded worker pool.
    """
    if x_owner_id and not request.owner_id:
        request.owner_id = x_owner_id
    return manager.submit_job(request)


@router.get(
    "/analysis/jobs/{job_id}",
    response_model=AnalysisJobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll status and stage of an asynchronous analysis job",
)
@router.get(
    "/jobs/{job_id}",
    response_model=AnalysisJobStatusResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_analysis_job_status(
    job_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for access control"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> AnalysisJobStatusResponse:
    """Retrieves current execution status, stage, and timestamps for an analysis job."""
    effective_owner = owner_id or x_owner_id
    return manager.get_job_status(job_id=job_id, owner_id=effective_owner)


@router.get(
    "/analysis/jobs/{job_id}/result",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve completed AnalysisResponse for an asynchronous job",
)
@router.get(
    "/jobs/{job_id}/result",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_analysis_job_result(
    job_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for access control"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> AnalysisResponse:
    """Retrieves the full, validated AnalysisResponse payload once the job has succeeded.

    Returns 409 Conflict if the job is still queued or running.
    Returns 504 Gateway Timeout if the job exceeded its deadline.
    Returns 500/502/503 if the job terminated with an error.
    """
    effective_owner = owner_id or x_owner_id
    return manager.get_job_result(job_id=job_id, owner_id=effective_owner)
