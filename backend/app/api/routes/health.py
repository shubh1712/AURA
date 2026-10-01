from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def get_health() -> HealthResponse:
    """Return runtime service health, release version, and current UTC timestamp."""
    return HealthResponse(
        status="ok",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        timestamp=datetime.now(timezone.utc),
    )
