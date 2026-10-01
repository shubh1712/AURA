from datetime import datetime
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Current health status of the service")
    service: str = Field(..., description="Service identifier")
    version: str = Field(..., description="Service release version")
    timestamp: datetime = Field(..., description="UTC timestamp of the health check")
