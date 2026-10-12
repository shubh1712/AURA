"""AURA Action Intelligence API Endpoints (Day 8B).

Provides REST endpoints for Action Intelligence:
- GET /api/analysis/{analysis_id}/action-plan
  Retrieves the saved action plan for a completed analysis with zero LLM calls.
  Returns HTTP 404 if no action plan has been generated yet.
- GET /api/analysis/{analysis_id}/action-plan/status
  Polls current action plan status ('ready', 'cached', 'running', 'failed', 'not_generated')
  without triggering generation.
- POST /api/analysis/{analysis_id}/action-plan/generate
  Validates analysis completion and source recommendation fingerprint.
  Returns cached action plan if valid and not forcing regeneration.
  Executes grounded structured generation via Google Cloud Vertex AI / Gemini.
  Protects against concurrent duplicate generation via durable SQLite claims.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.schemas.action_intelligence import IntelligentActionPlan
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.analysis_service import get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.llm.client import LLMClient

router = APIRouter(prefix="/analysis", tags=["Action Intelligence"])


def get_action_intelligence_service(
    manager: AnalysisJobManager = Depends(get_job_manager),
) -> ActionIntelligenceService:
    """Dependency provider for read-only ActionIntelligenceService."""
    return ActionIntelligenceService(manager=manager, llm_client=None)


def get_action_intelligence_generation_service(
    manager: AnalysisJobManager = Depends(get_job_manager),
    llm_client: LLMClient = Depends(get_llm_client),
) -> ActionIntelligenceService:
    """Dependency provider for generation-capable ActionIntelligenceService."""
    return ActionIntelligenceService(manager=manager, llm_client=llm_client)


class ActionPlanResponse(BaseModel):
    """API response envelope for an Intelligent Action Plan."""
    analysis_id: str
    status: str = Field(description="Plan availability status ('ready', 'cached', 'running', 'failed', 'not_generated').")
    cached: bool = Field(default=False, description="True if retrieved from persistence without regeneration.")
    plan: Optional[IntelligentActionPlan] = Field(default=None, description="The authoritative action plan.")
    error_message: Optional[str] = Field(default=None, description="Error detail if generation failed.")


class ActionPlanGenerateRequest(BaseModel):
    """Request payload for triggering action plan generation."""
    force_regenerate: bool = Field(
        default=False,
        description="If true, bypasses existing cached plan matching the source fingerprint.",
    )


@router.get(
    "/{analysis_id}/action-plan",
    response_model=ActionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve saved Intelligent Action Plan for a completed analysis",
)
async def get_action_plan(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ActionIntelligenceService = Depends(get_action_intelligence_service),
) -> ActionPlanResponse:
    """Retrieves the persisted Intelligent Action Plan for an analysis.

    Zero LLM calls are executed.
    Returns 404 if the action plan has not been generated yet.
    """
    effective_owner = owner_id or x_owner_id
    plan = service.get_action_plan(analysis_id=analysis_id, owner_id=effective_owner)

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action plan has not been generated for analysis '{analysis_id}'.",
        )

    return ActionPlanResponse(
        analysis_id=analysis_id,
        status="ready",
        cached=True,
        plan=plan,
    )


@router.get(
    "/{analysis_id}/action-plan/status",
    response_model=ActionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll status of Intelligent Action Plan without triggering generation",
)
async def get_action_plan_status(
    analysis_id: str,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ActionIntelligenceService = Depends(get_action_intelligence_service),
) -> ActionPlanResponse:
    """Polls current generation status for an analysis without calling Gemini."""
    effective_owner = owner_id or x_owner_id
    status_info = service.get_action_plan_status(analysis_id=analysis_id, owner_id=effective_owner)

    return ActionPlanResponse(
        analysis_id=analysis_id,
        status=status_info["status"],
        cached=status_info.get("cached", False),
        plan=status_info.get("plan"),
        error_message=status_info.get("error_message"),
    )


@router.post(
    "/{analysis_id}/action-plan/generate",
    response_model=ActionPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or retrieve cached Intelligent Action Plan",
)
async def generate_action_plan(
    analysis_id: str,
    request: Optional[ActionPlanGenerateRequest] = None,
    owner_id: Optional[str] = Query(None, description="Optional owner identity for scoping"),
    x_owner_id: Optional[str] = Header(None, alias="X-Owner-Id"),
    service: ActionIntelligenceService = Depends(get_action_intelligence_generation_service),
) -> ActionPlanResponse:
    """Generates an Intelligent Action Plan grounded in Stage 4 recommendation using Google Gemini.

    Workflow:
    1. Verifies analysis is complete and Stage 4 recommendation is present.
    2. Returns valid cached plan if fingerprint matches and force_regenerate is False.
    3. Acquires durable SQLite claim to protect against concurrent duplicate execution.
    4. Calls Gemini structured output generation with CandidateActionPlan schema.
    5. Runs deterministic validation and rejects fabricated actions or unsupported claims.
    6. Persists validated plan and updates claim status.
    """
    effective_owner = owner_id or x_owner_id
    req = request or ActionPlanGenerateRequest()

    plan, cached = service.generate_action_plan(
        analysis_id=analysis_id,
        owner_id=effective_owner,
        force_regenerate=req.force_regenerate,
    )

    return ActionPlanResponse(
        analysis_id=analysis_id,
        status="cached" if cached else "ready",
        cached=cached,
        plan=plan,
    )
