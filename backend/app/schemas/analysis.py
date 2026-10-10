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
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation


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
                "evidence_package": {
                    "id": "evpkg_dec_sample",
                    "decision_model_id": "dec_sample",
                    "requirements": [],
                    "sources": [],
                    "items": [],
                    "claim_links": [],
                    "gaps": [],
                    "summary": "0 evidence requirements.",
                },
                "reasoning_board": None,
                "recommendation": None,
                "recommendation_status": "completed",
                "recommendation_error": None,
                "question": "Should we migrate from a monolithic database to a distributed architecture?",
                "message": "Decision deconstruction, evidence gathering, boardroom deliberation, and recommendation completed successfully.",
            }
        },
    )

    analysis_id: str = Field(
        ...,
        description="Unique identifier assigned to the analysis request.",
    )
    status: str = Field(
        default="completed",
        description="Current lifecycle status of the analysis ('completed', 'partial_success', 'failed', 'staged').",
    )
    decision_model: Optional[DecisionModel] = Field(
        default=None,
        description="Canonical decomposed decision model with verified provenance and complexity.",
    )
    evidence_package: Optional[EvidencePackage] = Field(
        default=None,
        description="Empirical evidence package containing sources, findings, claim links, and gaps.",
    )
    reasoning_board: Optional[ReasoningBoard] = Field(
        default=None,
        description="Authoritative AI Boardroom reasoning evaluation across canonical perspectives.",
    )
    recommendation: Optional[DecisionRecommendation] = Field(
        default=None,
        description="Authoritative recommendation and action plan grounded in empirical evidence and deliberations.",
    )
    recommendation_status: Optional[str] = Field(
        default=None,
        description="Stage 4 execution status ('completed', 'unavailable', 'failed', 'timed_out').",
    )
    recommendation_error: Optional[str] = Field(
        default=None,
        description="Safe, sanitized error description if the recommendation stage was unavailable or failed.",
    )
    question: str = Field(
        default="",
        description="The validated decision question submitted for analysis.",
    )
    message: str = Field(
        default="Decision analysis completed successfully.",
        description="Human-readable informational message regarding the processing state.",
    )

