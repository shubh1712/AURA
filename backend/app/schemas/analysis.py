from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalysisRequest(BaseModel):
    """Initial API contract for submitting a decision for analysis.

    Validates core input fields for Day 1: question, optional context dictionary,
    and a list of constraints.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "question": "Should we migrate from a monolithic database to a distributed architecture?",
                "context": {
                    "current_db": "PostgreSQL",
                    "scale": "100k daily active users",
                    "budget_usd": 25000,
                },
                "constraints": [
                    "Zero downtime migration",
                    "Must complete in Q4",
                ],
            }
        },
    )

    question: str = Field(
        ...,
        description="The core decision question or problem statement to evaluate.",
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional dictionary providing operational context, background metrics, or parameters.",
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="List of boundaries, constraints, or non-negotiable criteria.",
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Question cannot be empty or contain only whitespace.")
        return trimmed


class AnalysisResponse(BaseModel):
    """Initial API response contract for a staged decision analysis."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "analysis_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
                "status": "pending",
                "question": "Should we migrate from a monolithic database to a distributed architecture?",
                "message": "Decision analysis request received and queued for processing.",
            }
        },
    )

    analysis_id: str = Field(
        ...,
        description="Unique identifier assigned to the analysis request.",
    )
    status: str = Field(
        ...,
        description="Current lifecycle status of the analysis (e.g. 'pending', 'staged').",
    )
    question: str = Field(
        ...,
        description="The validated decision question submitted for analysis.",
    )
    message: str = Field(
        ...,
        description="Human-readable informational message regarding the processing state.",
    )
