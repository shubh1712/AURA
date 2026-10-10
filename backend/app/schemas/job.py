"""AURA Asynchronous Analysis Job Schemas.

Defines schemas and enums for asynchronous decision analysis job lifecycle,
status transitions, and stage reporting.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisRequest


class JobStatus(str, Enum):
    """Lifecycle states for asynchronous analysis jobs."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class PipelineStage(str, Enum):
    """Granular execution stage within the analysis pipeline."""
    QUEUED = "queued"
    STAGE1_DECISION_FRAMER = "stage1_decision_framer"
    STAGE2_EVIDENCE_ENGINE = "stage2_evidence_engine"
    STAGE3_AI_BOARDROOM = "stage3_ai_boardroom"
    STAGE4_RECOMMENDATION = "stage4_recommendation"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class AnalysisJobCreateRequest(AnalysisRequest):
    """Request contract for submitting an asynchronous analysis job."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "question": "Should we migrate from a monolithic database to a distributed architecture?",
                "context": {
                    "current_db": "PostgreSQL",
                    "scale": "100k daily active users",
                },
                "constraints": ["Zero downtime migration"],
                "owner_id": "team-infra",
                "timeout_seconds": 180.0,
                "framer_operation_timeout_seconds": 75.0,
                "boardroom_operation_timeout_seconds": 75.0,
                "recommendation_operation_timeout_seconds": 60.0,
            }
        },
    )

    owner_id: Optional[str] = Field(
        default=None,
        description="Optional identity or team identifier for ownership validation.",
    )
    timeout_seconds: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Optional overall analysis deadline in seconds for this job.",
    )
    framer_operation_timeout_seconds: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Optional Decision Framer operation ceiling in seconds for this job.",
    )
    boardroom_operation_timeout_seconds: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Optional AI Boardroom perspective operation ceiling in seconds for this job.",
    )
    recommendation_operation_timeout_seconds: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Optional Recommendation & Action Planning operation ceiling in seconds for this job.",
    )


class AnalysisJobStatusResponse(BaseModel):
    """Response contract providing current job status, pipeline stage, and execution timestamps."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "7c9b83b3-f72b-4171-8bc4-9d568c078044",
                "status": "running",
                "stage": "stage2_evidence_engine",
                "created_at": "2026-10-09T14:00:00Z",
                "started_at": "2026-10-09T14:00:01Z",
                "completed_at": None,
                "progress_message": "Gathering and mapping empirical evidence.",
                "error": None,
                "error_status_code": None,
                "owner_id": "team-infra",
            }
        }
    )

    job_id: str = Field(
        ...,
        description="Stable unique identifier for the analysis job.",
    )
    status: JobStatus = Field(
        ...,
        description="Current high-level job lifecycle state.",
    )
    stage: PipelineStage = Field(
        ...,
        description="Current granular pipeline execution stage.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when job was submitted.",
    )
    started_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp when execution began.",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp when job terminated (succeeded, failed, or timed out).",
    )
    progress_message: str = Field(
        default="Job registered.",
        description="Human-readable informational message regarding the current progress.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Safe, sanitized error description if the job failed or timed out.",
    )
    error_status_code: Optional[int] = Field(
        default=None,
        description="Associated HTTP status code if the job terminated with an error.",
    )
    owner_id: Optional[str] = Field(
        default=None,
        description="Owner identity if specified at job submission.",
    )
