from fastapi import APIRouter, Depends, status
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis_service import AnalysisService, get_analysis_service

router = APIRouter(tags=["Analysis"])


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Stage a decision question for intelligence processing",
)
async def analyze_decision(
    request: AnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResponse:
    """Intake endpoint for decision questions.

    Delegates analysis orchestration to AnalysisService via dependency injection
    rather than directly constructing responses or housing business logic.
    """
    return service.analyze(request)
