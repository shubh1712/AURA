"""AURA What-if Simulation API Router (Day 7 Phase 7B).

Provides endpoints for discovering adjustable variables, executing deterministic
what-if simulations against completed six-stage analyses, and retrieving persisted runs.
"""

import json
import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.engines.simulation import simulate_what_if
from app.schemas.job import JobStatus
from app.schemas.simulation import (
    SimulationExplanationResponse,
    SimulationListResponse,
    SimulationRequest,
    SimulationResult,
    SimulationSubmitRequest,
    SimulationVariableDiscoveryResponse,
    compute_baseline_fingerprint,
)
from app.services.analysis_service import get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.llm.client import LLMClient
from app.services.simulation.explanation import SimulationExplanationService
from app.services.simulation.variables import discover_simulation_variables

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Simulation"])


def _check_simulation_access(job: Any, x_owner_id: Optional[str]) -> None:
    """Verifies caller identity matches job owner if ownership was specified."""
    if job.owner_id and x_owner_id and job.owner_id != x_owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: owner mismatch for analysis.",
        )


@router.get(
    "/analysis/{analysis_id}/simulation-variables",
    response_model=SimulationVariableDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover supported adjustable variables for an analysis",
)
async def get_simulation_variables(
    analysis_id: str,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationVariableDiscoveryResponse:
    """Discovers authoritative numeric variables from completed analysis artifacts.

    Returns variable bounds, units, baseline values, and supported capabilities.
    Fails if the analysis is missing, pending, or failed.
    """
    job = manager.storage.get_job_by_any_id(analysis_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    _check_simulation_access(job, x_owner_id)

    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is currently running; simulation variables are available once analysis completes.",
        )

    if job.status in (JobStatus.FAILED, JobStatus.TIMED_OUT) or job.response is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Analysis terminated with status '{job.status.value}'; cannot discover simulation variables.",
        )

    if job.response.decision_model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Analysis does not contain a valid DecisionModel (Stage 1).",
        )

    try:
        discovered = discover_simulation_variables(
            decision_model=job.response.decision_model,
            scenario_set=job.response.scenarios,
            recommendation=job.response.recommendation,
        )
    except Exception as exc:
        logger.error(
            "Failed to discover simulation variables for analysis '%s': %s",
            analysis_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Variable discovery failed for analysis '{analysis_id}': {str(exc)}",
        )

    baseline_fp = compute_baseline_fingerprint(
        decision_model=job.response.decision_model,
        scenario_set=job.response.scenarios,
        recommendation=job.response.recommendation,
        resilience_report=job.response.resilience,
    )

    supported_count = sum(1 for v in discovered if v.simulation_supported)
    unsupported_count = len(discovered) - supported_count

    recalculation_capabilities = {
        "direct_substitution": True,
        "constraint_threshold_evaluation": True,
        "resilience_score_recalculation": False,
        "note": (
            "Business metric adjustments evaluate operational constraint threshold breaches. "
            "Scenario constraint relevance is preserved unchanged to respect scenario narrative integrity. "
            "Direct parameter-to-resilience score deltas are explicitly reported as unsupported rather than fabricated."
        ),
    }

    return SimulationVariableDiscoveryResponse(
        analysis_id=job.response.analysis_id,
        job_id=job.job_id,
        baseline_fingerprint=baseline_fp,
        variables=discovered,
        supported_count=supported_count,
        unsupported_count=unsupported_count,
        recalculation_capabilities=recalculation_capabilities,
    )


@router.post(
    "/analysis/{analysis_id}/simulate",
    response_model=SimulationResult,
    status_code=status.HTTP_200_OK,
    summary="Submit and evaluate what-if simulation adjustments",
)
async def run_simulation(
    analysis_id: str,
    payload: SimulationSubmitRequest,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationResult:
    """Executes a pure deterministic what-if simulation against completed analysis artifacts.

    Evaluates adjustments on deep copies, preserves original analysis artifacts unchanged,
    evaluates constraint threshold breaches, and atomically persists the result in SQLite.
    """
    job = manager.storage.get_job_by_any_id(analysis_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    _check_simulation_access(job, x_owner_id)

    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is currently running; what-if simulation requires completed analysis artifacts.",
        )

    if job.status in (JobStatus.FAILED, JobStatus.TIMED_OUT) or job.response is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Analysis terminated with status '{job.status.value}'; cannot execute simulation.",
        )

    # Verify required stages exist
    resp = job.response
    if resp.decision_model is None or resp.scenarios is None or resp.recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Analysis is missing required stages for what-if simulation (Stages 1, 4, and 5 are required).",
        )

    # Compute and verify baseline fingerprint
    current_fp = compute_baseline_fingerprint(
        decision_model=resp.decision_model,
        scenario_set=resp.scenarios,
        recommendation=resp.recommendation,
        resilience_report=resp.resilience,
    )

    if payload.baseline_fingerprint and payload.baseline_fingerprint != current_fp:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Baseline fingerprint mismatch. Client provided '{payload.baseline_fingerprint}', "
                f"but current baseline fingerprint is '{current_fp}'."
            ),
        )

    # Build internal SimulationRequest with authoritative IDs
    sim_request = SimulationRequest(
        decision_model_id=resp.decision_model.id,
        scenario_set_id=resp.scenarios.id,
        recommendation_id=resp.recommendation.id,
        adjustments=payload.adjustments,
    )

    try:
        result = simulate_what_if(
            request=sim_request,
            decision_model=resp.decision_model,
            scenario_set=resp.scenarios,
            recommendation=resp.recommendation,
            evidence_package=resp.evidence_package,
            reasoning_board=resp.reasoning_board,
            baseline_resilience_report=resp.resilience,
            baseline_fingerprint=current_fp,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(ve),
        )

    # Atomically and idempotently persist in SQLite
    manager.storage.save_simulation(
        simulation_id=result.id,
        job_id=job.job_id,
        analysis_id=resp.analysis_id,
        baseline_fingerprint=current_fp,
        request_json=payload.model_dump_json(),
        result_json=result.model_dump_json(),
    )

    return result


@router.get(
    "/analysis/{analysis_id}/simulations/{simulation_id}",
    response_model=SimulationResult,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a previously executed what-if simulation",
)
async def get_simulation_by_id(
    analysis_id: str,
    simulation_id: str,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationResult:
    """Retrieves a persisted simulation result associated with an analysis."""
    job = manager.storage.get_job_by_any_id(analysis_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    _check_simulation_access(job, x_owner_id)

    sim_row = manager.storage.get_simulation(
        simulation_id=simulation_id,
        job_id_or_analysis_id=job.job_id,
    )
    if sim_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation '{simulation_id}' not found for analysis '{analysis_id}'.",
        )

    return SimulationResult.model_validate_json(sim_row["result_json"])


@router.get(
    "/analysis/{analysis_id}/simulations",
    response_model=SimulationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all persisted what-if simulations for an analysis",
)
async def list_simulations_for_analysis(
    analysis_id: str,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationListResponse:
    """Lists all saved simulations for an analysis, sorted by creation date descending."""
    job = manager.storage.get_job_by_any_id(analysis_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )

    _check_simulation_access(job, x_owner_id)

    sim_rows = manager.storage.list_simulations(job_id_or_analysis_id=job.job_id)
    sims = [SimulationResult.model_validate_json(r["result_json"]) for r in sim_rows]

    canonical_analysis_id = job.response.analysis_id if job.response else analysis_id
    return SimulationListResponse(
        analysis_id=canonical_analysis_id,
        simulations=sims,
        total_count=len(sims),
    )


@router.get(
    "/analysis/{analysis_id}/simulations/{simulation_id}/explain",
    response_model=SimulationExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a cached grounded AI explanation for a what-if simulation run if available",
)
async def get_cached_simulation_explanation(
    analysis_id: str,
    simulation_id: str,
    manager: AnalysisJobManager = Depends(get_job_manager),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationExplanationResponse:
    """Retrieves a previously cached AI explanation for a simulation run.

    Purely read-only; does not invoke Gemini or alter simulation state.
    Returns HTTP 404 if no valid cached explanation exists.
    """
    service = SimulationExplanationService(manager=manager, llm_client=None)
    return service.get_cached_explanation(
        analysis_id=analysis_id,
        simulation_id=simulation_id,
        owner_id=x_owner_id,
    )


@router.post(
    "/analysis/{analysis_id}/simulations/{simulation_id}/explain",
    response_model=SimulationExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or retrieve a grounded AI explanation for a what-if simulation run",
)
async def explain_simulation_run(
    analysis_id: str,
    simulation_id: str,
    manager: AnalysisJobManager = Depends(get_job_manager),
    llm_client: LLMClient = Depends(get_llm_client),
    x_owner_id: Optional[str] = Header(default=None, alias="X-Owner-Id"),
) -> SimulationExplanationResponse:
    """Generates a grounded, non-hallucinated narrative explanation of a what-if simulation.

    Leverages Gemini to synthesize operational consequences, constraint boundaries, and
    methodological limitations. Does not alter deterministic engine calculations.
    Reuses valid cached explanations where prompt version and baseline fingerprint match.
    """
    service = SimulationExplanationService(manager=manager, llm_client=llm_client)
    return service.explain_simulation(
        analysis_id=analysis_id,
        simulation_id=simulation_id,
        owner_id=x_owner_id,
    )
