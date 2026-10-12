"""AURA Action Intelligence Service (Day 8B).

Orchestrates retrieval, caching, durable concurrency control, Gemini generation,
deterministic validation, and persistence of IntelligentActionPlan:
- Ensures Stage 4 recommendation and parent analysis are completed and authoritative.
- Enforces source recommendation fingerprint identity.
- Retrieves saved action plans from SQLite with zero LLM calls.
- Provides durable SQLite claim acquisition to coalesce or prevent concurrent generation runs.
- Executes Gemini structured generation via ActionIntelligenceGenerator.
- Validates structural, threshold, and grounding invariants deterministically.
- Rejects fabricated or invalid Stage 4 actions and unsupported numeric claims.
- Prevents partial plan persistence on generation or validation failure.
- Idempotently persists completed action plans into SQLite.
"""

from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
from fastapi import HTTPException, status

from app.config import settings

from app.schemas.action_intelligence import (
    ACTION_INTELLIGENCE_GENERATOR_VERSION,
    ACTION_INTELLIGENCE_SCHEMA_VERSION,
    IntelligentActionPlan,
    compute_source_recommendation_fingerprint,
)
from app.schemas.job import JobStatus
from app.services.action_intelligence.generator import ActionIntelligenceGenerator
from app.services.action_intelligence.prompt_builder import CURRENT_ACTION_INTELLIGENCE_PROMPT_VERSION
from app.services.action_intelligence.validator import (
    ActionPlanValidationError,
    validate_action_plan,
)
from app.services.jobs.manager import AnalysisJobManager
from app.services.llm.client import LLMClient

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionIntelligenceService:
    """Domain service managing Intelligent Action Plans."""

    def __init__(
        self,
        manager: AnalysisJobManager,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.manager = manager
        self.llm_client = llm_client

    def get_action_plan(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Optional[IntelligentActionPlan]:
        """Retrieves a persisted action plan for an analysis from SQLite.

        Raises:
            HTTPException: 404 if analysis not found, 403 on owner mismatch.
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

        row = self.manager.storage.get_action_plan(analysis_id=analysis_id, owner_id=owner_id)
        if not row:
            return None

        try:
            plan_data = json.loads(row["plan_json"])
            return IntelligentActionPlan.model_validate(plan_data)
        except Exception as exc:
            logger.error("Failed to deserialize persisted action plan: %s", exc)
            return None

    def get_action_plan_status(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Polls current generation status for an analysis without triggering generation."""
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

        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return {
                "analysis_id": analysis_id,
                "status": "queued_or_running",
                "cached": False,
                "plan": None,
                "message": "Analysis is currently running; action plan is available once analysis completes.",
            }

        if job.status in (JobStatus.FAILED, JobStatus.TIMED_OUT) or job.response is None:
            return {
                "analysis_id": analysis_id,
                "status": "invalid_analysis",
                "cached": False,
                "plan": None,
                "message": f"Analysis terminated with status '{job.status.value}'.",
            }

        # Check existing cached plan against current recommendation fingerprint
        rec_fp = compute_source_recommendation_fingerprint(
            recommendation=job.response.recommendation,
            decision_model=job.response.decision_model,
            scenario_set=job.response.scenarios,
            resilience_report=job.response.resilience,
        )
        cached_plan = self.get_action_plan(analysis_id=analysis_id, owner_id=owner_id)
        if cached_plan and cached_plan.source_recommendation_fingerprint == rec_fp:
            return {
                "analysis_id": analysis_id,
                "status": "ready",
                "cached": True,
                "plan": cached_plan,
            }

        # Check active durable claim
        claim = self.manager.storage.get_action_plan_claim(analysis_id=analysis_id)
        if claim:
            c_status = claim.get("status")
            c_expires = float(claim.get("expires_at", 0))
            if c_status == "running" and time.time() < c_expires:
                return {
                    "analysis_id": analysis_id,
                    "status": "running",
                    "cached": False,
                    "plan": None,
                }
            if c_status == "failed":
                return {
                    "analysis_id": analysis_id,
                    "status": "failed",
                    "cached": False,
                    "plan": None,
                    "error_message": claim.get("error_message"),
                }

        return {
            "analysis_id": analysis_id,
            "status": "not_generated",
            "cached": False,
            "plan": None,
        }

    def save_action_plan(
        self,
        plan: IntelligentActionPlan,
        owner_id: Optional[str] = None,
    ) -> IntelligentActionPlan:
        """Deterministically validates and saves an IntelligentActionPlan into SQLite."""
        # 1. Resolve analysis to obtain context artifacts for validation
        job = self.manager.storage.get_job_by_any_id(plan.analysis_id)
        decision_model = None
        evidence_package = None
        recommendation = None

        if job and job.response:
            decision_model = job.response.decision_model
            evidence_package = job.response.evidence_package
            recommendation = job.response.recommendation

        # 2. Execute deterministic validation
        validated_plan = validate_action_plan(
            plan=plan,
            decision_model=decision_model,
            evidence_package=evidence_package,
            recommendation=recommendation,
        )

        # 3. Persist into SQLite
        plan_json = json.dumps(validated_plan.model_dump(mode="json"))
        effective_owner = owner_id or (job.owner_id if job else None)

        self.manager.storage.save_action_plan(
            plan_id=validated_plan.plan_id,
            analysis_id=validated_plan.analysis_id,
            source_recommendation_fingerprint=validated_plan.source_recommendation_fingerprint,
            schema_version=validated_plan.schema_version,
            generator_version=validated_plan.generator_version,
            plan_json=plan_json,
            owner_id=effective_owner,
            created_at=validated_plan.created_at,
        )

        return validated_plan

    def verify_generation_prerequisites(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
    ) -> Tuple[Any, str, Optional[IntelligentActionPlan]]:
        """Verifies upstream prerequisites for action plan generation.

        Returns:
            Tuple of (JobRecord, source_recommendation_fingerprint, existing_cached_plan).

        Raises:
            HTTPException on missing analysis (404), owner mismatch (403),
            incomplete analysis (409), or missing Stage 4 recommendation (422).
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

        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analysis is currently in progress. Action Intelligence is available once analysis completes.",
            )

        if job.status in (JobStatus.FAILED, JobStatus.TIMED_OUT) or job.response is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Analysis terminated with status '{job.status.value}'. Cannot generate action plan.",
            )

        if not job.response.recommendation:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Analysis is missing Stage 4 DecisionRecommendation required for Action Intelligence.",
            )

        # Compute stable source fingerprint
        rec_fp = compute_source_recommendation_fingerprint(
            recommendation=job.response.recommendation,
            decision_model=job.response.decision_model,
            scenario_set=job.response.scenarios,
            resilience_report=job.response.resilience,
        )

        # Check existing cached plan
        cached_plan = self.get_action_plan(analysis_id=analysis_id, owner_id=owner_id)
        if cached_plan and cached_plan.source_recommendation_fingerprint == rec_fp:
            return job, rec_fp, cached_plan

        return job, rec_fp, None

    def generate_action_plan(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        force_regenerate: bool = False,
        timeout_seconds: Optional[float] = None,
        operation_timeout_seconds: Optional[float] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Tuple[IntelligentActionPlan, bool]:
        """Executes full Day 8B/8F Action Intelligence generation workflow.

        Returns:
            Tuple of (IntelligentActionPlan, cached: bool).

        Guarantees:
        - Returns existing valid plan when available without invoking Gemini.
        - Concurrency protection via durable SQLite claim; rejects concurrent generation with HTTP 409.
        - Grounded structured output parsed and validated deterministically.
        - Rejection of fabricated Stage 4 actions, invalid evidence, and unsupported claims.
        - On failure, claim is released as failed and no partial plan is saved.
        """
        eff_http_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS
        )
        eff_op_timeout = (
            operation_timeout_seconds
            if operation_timeout_seconds is not None
            else settings.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS
        )
        eff_claim_ttl = settings.AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS
        diagnostics_enabled = os.environ.get("AURA_LLM_DIAGNOSTICS") == "1"

        # 1. Verify prerequisites
        job, rec_fp, cached_plan = self.verify_generation_prerequisites(
            analysis_id=analysis_id,
            owner_id=owner_id,
        )

        # 2. Return cached plan if valid and not forcing regeneration
        if cached_plan is not None and not force_regenerate:
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Cache Diagnostic [hit]: analysis_id=%s, plan_id=%s",
                    analysis_id,
                    cached_plan.plan_id,
                )
            return cached_plan, True

        if diagnostics_enabled:
            logger.info(
                "AURA Action Intelligence Cache Diagnostic [miss]: analysis_id=%s, force_regenerate=%s",
                analysis_id,
                force_regenerate,
            )

        # 3. Durable concurrency claim in SQLite
        acquired, claim_status, claim_id = self.manager.storage.acquire_action_plan_claim(
            analysis_id=analysis_id,
            owner_id=owner_id,
            ttl_seconds=eff_claim_ttl,
        )
        if diagnostics_enabled:
            logger.info(
                "AURA Action Intelligence Claim Diagnostic [acquire]: analysis_id=%s, acquired=%s, claim_id=%s, ttl=%.1fs",
                analysis_id,
                acquired,
                claim_id,
                eff_claim_ttl,
            )
        if not acquired:
            logger.warning("Duplicate concurrent generation request rejected for %s", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Action plan generation is currently in progress for analysis '{analysis_id}'.",
            )

        # 4. Generate structured candidate via Gemini
        if not self.llm_client:
            self.manager.storage.release_action_plan_claim(
                analysis_id=analysis_id,
                claim_id=claim_id,
                success=False,
                error_message="LLM client is not configured.",
            )
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Claim Diagnostic [release_failed]: analysis_id=%s, claim_id=%s",
                    analysis_id,
                    claim_id,
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM client is not configured for Action Intelligence generation.",
            )

        generator = ActionIntelligenceGenerator(llm_client=self.llm_client)
        resp = job.response

        try:
            candidate = generator.generate(
                decision_model=resp.decision_model,
                recommendation=resp.recommendation,
                evidence_package=resp.evidence_package,
                reasoning_board=resp.reasoning_board,
                scenario_set=resp.scenarios,
                resilience_report=resp.resilience,
                timeout_seconds=eff_http_timeout,
                operation_timeout_seconds=eff_op_timeout,
                deadline_monotonic=deadline_monotonic,
            )

            # 5. Assemble and validate
            assembled_plan = generator.assemble_plan(
                candidate=candidate,
                analysis_id=analysis_id,
                source_recommendation_fingerprint=rec_fp,
            )

            # Ensure an expired, invalid, or superseded claim cannot overwrite a newer plan
            current_claim = self.manager.storage.get_action_plan_claim(analysis_id=analysis_id)
            now = time.time()
            is_expired = current_claim is not None and now > float(current_claim.get("expires_at", 0))
            if (
                not current_claim
                or current_claim.get("claim_id") != claim_id
                or current_claim.get("status") != "running"
                or is_expired
            ):
                logger.warning(
                    "Worker claim %s for analysis %s is invalid, expired, or superseded (current: %s, is_expired: %s); aborting save.",
                    claim_id,
                    analysis_id,
                    current_claim,
                    is_expired,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Action plan generation claim expired or was superseded by another operation.",
                )

            # Deterministic validation and persistence into SQLite
            saved_plan = self.save_action_plan(
                plan=assembled_plan,
                owner_id=owner_id,
            )

            # 6. Release claim with success
            self.manager.storage.release_action_plan_claim(
                analysis_id=analysis_id,
                claim_id=claim_id,
                success=True,
            )
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Claim Diagnostic [release_success]: analysis_id=%s, claim_id=%s",
                    analysis_id,
                    claim_id,
                )

            return saved_plan, False

        except ActionPlanValidationError as val_err:
            logger.error("Generated candidate failed validation for %s: %s", analysis_id, val_err)
            self.manager.storage.release_action_plan_claim(
                analysis_id=analysis_id,
                claim_id=claim_id,
                success=False,
                error_message=str(val_err),
            )
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Claim Diagnostic [release_failed]: analysis_id=%s, claim_id=%s",
                    analysis_id,
                    claim_id,
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Generated action plan failed deterministic validation: {val_err}",
            ) from val_err
        except HTTPException as http_exc:
            self.manager.storage.release_action_plan_claim(
                analysis_id=analysis_id,
                claim_id=claim_id,
                success=False,
                error_message=http_exc.detail,
            )
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Claim Diagnostic [release_failed]: analysis_id=%s, claim_id=%s",
                    analysis_id,
                    claim_id,
                )
            raise
        except Exception as exc:
            logger.exception("Unexpected error generating action plan for %s: %s", analysis_id, exc)
            self.manager.storage.release_action_plan_claim(
                analysis_id=analysis_id,
                claim_id=claim_id,
                success=False,
                error_message=str(exc),
            )
            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence Claim Diagnostic [release_failed]: analysis_id=%s, claim_id=%s",
                    analysis_id,
                    claim_id,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during action plan generation.",
            ) from exc
