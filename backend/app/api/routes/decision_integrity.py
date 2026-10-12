"""AURA Decision Integrity API Endpoints (Day 8G-A & Day 8G-B).

Provides REST endpoints for retrieving deterministic decision integrity reports:
- GET /api/analysis/{analysis_id}/integrity
  Evaluates mathematical calculations, cross-stage consistency, alternative option comparisons,
  evidence quality classifications, and operational decision readiness.
  Executes ZERO LLM calls. Fully cached by artifact fingerprint.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.schemas.decision_integrity import DecisionIntegrityReport
from app.services.integrity.service import DecisionIntegrityService
from app.services.jobs.manager import AnalysisJobManager, get_job_manager

router = APIRouter(prefix="/analysis", tags=["Decision Integrity"])


def get_decision_integrity_service(
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> DecisionIntegrityService:
    """Dependency provider for DecisionIntegrityService."""
    return DecisionIntegrityService(manager=manager)


@router.get(
    "/{analysis_id}/integrity",
    response_model=DecisionIntegrityReport,
    status_code=status.HTTP_200_OK,
    summary="Retrieve deterministic decision integrity report for an analysis",
)
async def get_analysis_integrity(
    analysis_id: str,
    force_refresh: bool = Query(False, description="If true, re-evaluates rules without cache"),
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: DecisionIntegrityService = Depends(get_decision_integrity_service),
) -> DecisionIntegrityReport:
    """Retrieves authoritative Decision Integrity Report for an analysis.

    Zero LLM calls are executed.
    Evaluates:
    - Deterministic precision calculations (net savings, annualized costs, ceilings)
    - 15 cross-stage consistency rules
    - Viable alternatives comparison matrix
    - Source quality classification and duplicate citation tracking
    - Uncertainty calibration and decision-impact ranked evidence gaps
    - Operational decision readiness status
    """
    effective_owner = owner_id or x_owner_id
    try:
        report = service.get_integrity_report(
            analysis_id=analysis_id,
            owner_id=effective_owner,
            force_refresh=force_refresh,
        )
        return report
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate decision integrity for '{analysis_id}': {str(exc)}",
        )
