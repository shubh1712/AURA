"""AURA Report and PDF Export API Endpoints (Day 8G-C).

Provides REST and binary download endpoints for normalized reports:
- GET /api/analysis/{analysis_id}/report
  Returns full normalized SharedReportModel JSON for web viewing.
- GET /api/analysis/{analysis_id}/report/summary/pdf
  Generates and streams 2-4 page executive summary vector PDF.
- GET /api/analysis/{analysis_id}/report/detailed/pdf
  Generates and streams comprehensive multi-page audit vector PDF.
Executes ZERO Gemini calls. Pure deterministic assembly and rendering.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.schemas.report import SharedReportModel
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.report.pdf_generator import AuraPDFGenerator
from app.services.report.service import ReportService

router = APIRouter(prefix="/analysis", tags=["Report and PDF Exports"])


def get_report_service(
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> ReportService:
    """Dependency provider for ReportService."""
    return ReportService(manager=manager)


def get_pdf_generator() -> AuraPDFGenerator:
    """Dependency provider for AuraPDFGenerator."""
    return AuraPDFGenerator()


@router.get(
    "/{analysis_id}/report",
    response_model=SharedReportModel,
    status_code=status.HTTP_200_OK,
    summary="Retrieve normalized SharedReportModel JSON",
)
async def get_report_json(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ReportService = Depends(get_report_service),
) -> SharedReportModel:
    """Retrieves normalized SharedReportModel JSON representation."""
    effective_owner = owner_id or x_owner_id
    try:
        return service.get_shared_report(analysis_id=analysis_id, owner_id=effective_owner, mode="shared")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report data for '{analysis_id}': {str(exc)}",
        )


@router.get(
    "/{analysis_id}/report/summary",
    response_model=SharedReportModel,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Executive Summary Report JSON",
)
async def get_summary_report_json(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ReportService = Depends(get_report_service),
) -> SharedReportModel:
    """Retrieves executive summary report JSON representation."""
    effective_owner = owner_id or x_owner_id
    try:
        return service.get_shared_report(analysis_id=analysis_id, owner_id=effective_owner, mode="summary")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary report data for '{analysis_id}': {str(exc)}",
        )


@router.get(
    "/{analysis_id}/report/detailed",
    response_model=SharedReportModel,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Detailed Audit Report JSON",
)
async def get_detailed_report_json(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ReportService = Depends(get_report_service),
) -> SharedReportModel:
    """Retrieves detailed audit report JSON representation."""
    effective_owner = owner_id or x_owner_id
    try:
        return service.get_shared_report(analysis_id=analysis_id, owner_id=effective_owner, mode="detailed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate detailed report data for '{analysis_id}': {str(exc)}",
        )


@router.get(
    "/{analysis_id}/report/summary/pdf",
    status_code=status.HTTP_200_OK,
    summary="Download Executive Summary PDF (2-4 pages)",
)
async def download_summary_pdf(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ReportService = Depends(get_report_service),
    pdf_gen: AuraPDFGenerator = Depends(get_pdf_generator),
) -> Response:
    """Streams executive summary PDF."""
    effective_owner = owner_id or x_owner_id
    try:
        report = service.get_shared_report(analysis_id=analysis_id, owner_id=effective_owner)
        pdf_bytes = pdf_gen.generate_summary_pdf(report)

        filename = f"AURA_Summary_{analysis_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary PDF for '{analysis_id}': {str(exc)}",
        )


@router.get(
    "/{analysis_id}/report/detailed/pdf",
    status_code=status.HTTP_200_OK,
    summary="Download Comprehensive Detailed Audit PDF",
)
async def download_detailed_pdf(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ReportService = Depends(get_report_service),
    pdf_gen: AuraPDFGenerator = Depends(get_pdf_generator),
) -> Response:
    """Streams comprehensive detailed audit PDF."""
    effective_owner = owner_id or x_owner_id
    try:
        report = service.get_shared_report(analysis_id=analysis_id, owner_id=effective_owner)
        pdf_bytes = pdf_gen.generate_detailed_pdf(report)

        filename = f"AURA_Detailed_Audit_{analysis_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate detailed audit PDF for '{analysis_id}': {str(exc)}",
        )
