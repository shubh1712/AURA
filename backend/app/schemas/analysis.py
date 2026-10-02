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


from app.schemas.decision_model import DecisionModel


class AnalysisResponse(BaseModel):
    """API response contract for a completed decision analysis."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "analysis_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
                "status": "completed",
                "decision_model": {
                    "id": "dec_sample",
                    "decision": {
                        "raw_prompt": "Should we migrate to a distributed database?",
                        "summary": "Evaluate migrating to distributed architecture.",
                        "decision_type": "architecture_technology",
                        "time_horizon": "medium_term",
                    },
                    "complexity": {
                        "level": "medium",
                        "reasoning": "Data consistency and replication trade-offs.",
                        "reversibility": "partially_reversible",
                        "score": 45.0,
                    },
                    "objectives": [],
                    "variables": [],
                    "constraints": [],
                    "stakeholders": [],
                    "tradeoffs": [],
                    "assumptions": [],
                    "unknowns": [],
                    "key_questions": ["What is our latency budget?"],
                },
                "question": "Should we migrate from a monolithic database to a distributed architecture?",
                "message": "Decision deconstruction and provenance audit completed successfully.",
            }
        },
    )

    analysis_id: str = Field(
        ...,
        description="Unique identifier assigned to the analysis request.",
    )
    status: str = Field(
        default="completed",
        description="Current lifecycle status of the analysis ('completed', 'failed', 'staged').",
    )
    decision_model: Optional[DecisionModel] = Field(
        default=None,
        description="Canonical decomposed decision model with verified provenance and complexity.",
    )
    question: str = Field(
        default="",
        description="The validated decision question submitted for analysis.",
    )
    message: str = Field(
        default="Decision analysis completed successfully.",
        description="Human-readable informational message regarding the processing state.",
    )
