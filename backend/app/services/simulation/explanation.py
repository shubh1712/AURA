"""AURA What-if Simulation AI Explanation Service.

Provides an offline-first, grounded qualitative explanation service for what-if simulations:
- Verifies simulation existence, parent analysis association, and baseline fingerprint.
- Checks SQLite cache for valid existing explanations matching current prompt version.
- Invokes LLMClient with bounded prompts and strict CandidateSimulationExplanation schema.
- Enforces anti-hallucination rules and sanitizes outputs without touching deterministic metrics.
- Idempotently persists successful explanations in SQLite.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Optional
from fastapi import HTTPException, status

from app.schemas.job import JobStatus
from app.schemas.simulation import (
    CandidateSimulationExplanation,
    SimulationExplanationResponse,
    SimulationResult,
    compute_baseline_fingerprint,
)
from app.services.jobs.manager import AnalysisJobManager
from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.simulation.prompt_builder import (
    CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION,
    build_simulation_explanation_prompt,
    build_simulation_explanation_system_instruction,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    """Returns the current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class SimulationExplanationService:
    """Orchestrates grounded narrative explanations for deterministic simulation runs."""

    def __init__(
        self,
        manager: AnalysisJobManager,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.manager = manager
        self.llm_client = llm_client

    def explain_simulation(
        self,
        analysis_id: str,
        simulation_id: str,
        owner_id: Optional[str] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> SimulationExplanationResponse:
        """Generates or retrieves a cached qualitative explanation for a completed simulation.

        Raises HTTPException on:
        - 404: Analysis or Simulation not found.
        - 403: Ownership mismatch.
        - 409: Running analysis or baseline fingerprint mismatch.
        - 422: Analysis missing required artifacts.
        - 504: LLM timeout.
        - 502 / 503: LLM generation or validation error.
        """
        job = self.manager.storage.get_job_by_any_id(analysis_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )

        # Owner validation if configured
        if job.owner_id and owner_id and job.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: owner mismatch for analysis.",
            )

        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analysis is currently running; explanation is available once analysis completes.",
            )

        if job.status in (JobStatus.FAILED, JobStatus.TIMED_OUT) or job.response is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Analysis terminated with status '{job.status.value}'; cannot generate explanation.",
            )

        resp = job.response
        if resp.decision_model is None or resp.scenarios is None or resp.recommendation is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Analysis is missing required stages for simulation explanation (Stages 1, 4, and 5 are required).",
            )

        sim_row = self.manager.storage.get_simulation(
            simulation_id=simulation_id,
            job_id_or_analysis_id=job.job_id,
        )
        if sim_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Simulation '{simulation_id}' not found for analysis '{analysis_id}'.",
            )

        # Baseline fingerprint verification
        current_fp = compute_baseline_fingerprint(
            decision_model=resp.decision_model,
            scenario_set=resp.scenarios,
            recommendation=resp.recommendation,
            resilience_report=resp.resilience,
        )

        sim_fp = sim_row.get("baseline_fingerprint", "")
        if sim_fp and sim_fp != current_fp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Baseline fingerprint mismatch. Simulation was executed against baseline '{sim_fp}', "
                    f"but active analysis baseline fingerprint is '{current_fp}'."
                ),
            )

        # Check SQLite explanation cache
        cached_exp = self.manager.storage.get_simulation_explanation(simulation_id)
        if cached_exp is not None:
            cached_fp = cached_exp.get("baseline_fingerprint")
            cached_version = cached_exp.get("prompt_version")
            if cached_fp == current_fp and cached_version == CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION:
                try:
                    loaded = SimulationExplanationResponse.model_validate_json(cached_exp["explanation_json"])
                    # Return with status="cached"
                    return loaded.model_copy(update={"generation_status": "cached"})
                except Exception as ex:
                    logger.warning(f"Failed to parse cached explanation for {simulation_id}: {ex}")

        # Construct prompt
        sim_result = SimulationResult.model_validate_json(sim_row["result_json"])

        sys_inst = build_simulation_explanation_system_instruction()
        user_prompt = build_simulation_explanation_prompt(
            decision_model=resp.decision_model,
            recommendation=resp.recommendation,
            scenario_set=resp.scenarios,
            resilience_report=resp.resilience,
            simulation_result=sim_result,
        )

        llm_config = LLMConfig(
            model_name="gemini-3.8-flash",
            temperature=0.2,
            timeout_seconds=30.0,
            operation_timeout_seconds=60.0,
            stage="simulation_explanation",
        )

        # Invoke LLM Client
        try:
            candidate = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_schema=CandidateSimulationExplanation,
                system_instruction=sys_inst,
                config=llm_config,
                deadline_monotonic=deadline_monotonic,
            )
        except LLMTimeoutError as te:
            logger.error(f"LLM timeout explaining simulation {simulation_id}: {te}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI explanation generation exceeded allowed processing time.",
            ) from te
        except LLMAuthenticationError as ae:
            logger.error(f"LLM authentication error explaining simulation {simulation_id}: {ae}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI explanation service credentials are not configured or invalid.",
            ) from ae
        except LLMRateLimitError as rle:
            logger.error(f"LLM rate limit explaining simulation {simulation_id}: {rle}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI explanation rate limit exceeded. Please retry shortly.",
            ) from rle
        except LLMResponseValidationError as rve:
            logger.error(f"LLM response schema validation failure explaining simulation {simulation_id}: {rve}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI explanation output failed schema validation.",
            ) from rve
        except LLMError as le:
            logger.error(f"LLM error explaining simulation {simulation_id}: {le}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI explanation generation failed: {le.message}",
            ) from le
        except Exception as e:
            logger.exception(f"Unexpected error explaining simulation {simulation_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred during explanation generation.",
            ) from e

        model_name = getattr(self.llm_client, "model_name", "gemini-3.8-flash")
        created_at = _utc_now_iso()

        response = SimulationExplanationResponse(
            simulation_id=simulation_id,
            baseline_fingerprint=current_fp,
            summary=candidate.summary,
            what_changed=candidate.what_changed,
            constraint_implications=candidate.constraint_implications,
            resilience_interpretation=candidate.resilience_interpretation,
            limitations=candidate.limitations,
            suggested_validation_steps=candidate.suggested_validation_steps,
            evidence_or_artifact_references=candidate.evidence_or_artifact_references,
            generation_status="generated",
            model_name=model_name,
            prompt_version=CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION,
            created_at=created_at,
        )

        # Idempotently persist explanation in SQLite
        try:
            self.manager.storage.save_simulation_explanation(
                simulation_id=simulation_id,
                analysis_id=resp.analysis_id,
                baseline_fingerprint=current_fp,
                prompt_version=CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION,
                model_name=model_name,
                explanation_json=response.model_dump_json(),
                created_at=created_at,
            )
        except Exception as pe:
            logger.warning(f"Failed to persist simulation explanation to database: {pe}")
        return response

    def get_cached_explanation(
        self,
        analysis_id: str,
        simulation_id: str,
        owner_id: Optional[str] = None,
    ) -> SimulationExplanationResponse:
        """Retrieves a previously cached AI explanation for a simulation run without invoking LLM.

        Validates ownership, simulation existence, baseline fingerprint, and prompt version.
        Raises HTTP 404 if no valid cached explanation exists.
        """
        job = self.manager.storage.get_job_by_any_id(analysis_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )

        if job.owner_id and owner_id and job.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: owner mismatch for analysis.",
            )

        resp = job.response
        if resp is None or resp.decision_model is None or resp.scenarios is None or resp.recommendation is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Analysis is missing required stages.",
            )

        sim_row = self.manager.storage.get_simulation(
            simulation_id=simulation_id,
            job_id_or_analysis_id=job.job_id,
        )
        if sim_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Simulation '{simulation_id}' not found for analysis '{analysis_id}'.",
            )

        current_fp = compute_baseline_fingerprint(
            decision_model=resp.decision_model,
            scenario_set=resp.scenarios,
            recommendation=resp.recommendation,
            resilience_report=resp.resilience,
        )

        sim_fp = sim_row.get("baseline_fingerprint", "")
        if sim_fp and sim_fp != current_fp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Baseline fingerprint mismatch. Simulation was executed against baseline '{sim_fp}', "
                    f"but active analysis baseline fingerprint is '{current_fp}'."
                ),
            )

        cached_exp = self.manager.storage.get_simulation_explanation(simulation_id)
        if cached_exp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No cached AI explanation found for simulation '{simulation_id}'.",
            )

        cached_fp = cached_exp.get("baseline_fingerprint")
        cached_version = cached_exp.get("prompt_version")
        if cached_fp != current_fp or cached_version != CURRENT_SIMULATION_EXPLANATION_PROMPT_VERSION:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cached AI explanation for simulation '{simulation_id}' is stale or invalid.",
            )

        try:
            loaded = SimulationExplanationResponse.model_validate_json(cached_exp["explanation_json"])
            return loaded.model_copy(update={"generation_status": "cached"})
        except Exception as ex:
            logger.warning(f"Failed to parse cached explanation for {simulation_id}: {ex}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cached AI explanation for simulation '{simulation_id}' is corrupted.",
            )
