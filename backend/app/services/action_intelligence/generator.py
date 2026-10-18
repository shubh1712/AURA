"""AURA Action Intelligence Gemini Generator (Day 8B).

Generates grounded, sequenced IntelligentActionPlan candidate structures via Google Cloud Vertex AI / Gemini:
- Consumes authoritative Stage 1-6 analysis artifacts.
- Enforces single structured generation call with CandidateActionPlan response schema.
- Epistemic grounding in Stage 4 recommendation actions.
- Anti-hallucination guardrails and structured conversion into IntelligentActionPlan.
"""

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.action_intelligence import (
    ACTION_INTELLIGENCE_GENERATOR_VERSION,
    ACTION_INTELLIGENCE_SCHEMA_VERSION,
    ActionCriterion,
    CandidateActionPlan,
    IntelligentActionItem,
    IntelligentActionPlan,
    IntelligentDecisionGate,
    compute_plan_id,
)
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.resilience import ResilienceReport
from app.schemas.scenario import ScenarioSet
from app.services.action_intelligence.prompt_builder import (
    CURRENT_ACTION_INTELLIGENCE_PROMPT_VERSION,
    build_action_intelligence_system_instruction,
    build_action_intelligence_user_prompt,
)
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_model_name(llm_client: LLMClient) -> str:
    """Accurately discovers model name from client or settings."""
    return (
        getattr(llm_client, "default_model", None)
        or getattr(llm_client, "model_name", None)
        or getattr(settings, "GEMINI_MODEL", None)
        or "gemini-3.8-flash"
    )


class ActionIntelligenceGenerator:
    """Manages Gemini structured generation for Intelligent Action Plans."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        self.last_diagnostic: Optional[Dict[str, Any]] = None

    def generate(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
        evidence_package: Optional[EvidencePackage] = None,
        reasoning_board: Optional[ReasoningBoard] = None,
        scenario_set: Optional[ScenarioSet] = None,
        resilience_report: Optional[ResilienceReport] = None,
        timeout_seconds: Optional[float] = None,
        operation_timeout_seconds: Optional[float] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> CandidateActionPlan:
        """Invokes Gemini structured generation with CandidateActionPlan schema."""
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
        max_retries = settings.AURA_ACTION_INTELLIGENCE_MAX_RETRIES

        system_instruction = build_action_intelligence_system_instruction()
        user_prompt = build_action_intelligence_user_prompt(
            decision_model=decision_model,
            recommendation=recommendation,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            scenario_set=scenario_set,
            resilience_report=resilience_report,
        )

        model_name = _resolve_model_name(self.llm_client)
        config = LLMConfig(
            model_name=model_name,
            temperature=0.2,
            timeout_seconds=eff_http_timeout,
            operation_timeout_seconds=eff_op_timeout,
            max_retries=max_retries,
            stage="action_intelligence",
        )

        prompt_chars = len(user_prompt)
        sys_chars = len(system_instruction)
        est_tokens = (prompt_chars + sys_chars) // 4
        diagnostics_enabled = os.environ.get("AURA_LLM_DIAGNOSTICS") == "1"
        t_start = time.monotonic()

        try:
            candidate = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_schema=CandidateActionPlan,
                system_instruction=system_instruction,
                config=config,
                deadline_monotonic=deadline_monotonic,
            )
            elapsed = time.monotonic() - t_start

            self.last_diagnostic = {
                "status": "success",
                "model_name": model_name,
                "prompt_chars": prompt_chars,
                "system_chars": sys_chars,
                "total_prompt_chars": prompt_chars + sys_chars,
                "estimated_prompt_tokens": est_tokens,
                "elapsed_seconds": round(elapsed, 3),
                "operation_timeout_seconds": eff_op_timeout,
                "http_timeout_seconds": eff_http_timeout,
            }

            if diagnostics_enabled:
                logger.info(
                    "AURA Action Intelligence LLM Diagnostic [success]: model=%s, prompt_chars=%d, "
                    "est_prompt_tokens=%d, elapsed=%.3fs, op_timeout=%.1fs, http_timeout=%.1fs",
                    model_name,
                    prompt_chars + sys_chars,
                    est_tokens,
                    elapsed,
                    eff_op_timeout,
                    eff_http_timeout,
                )

            return candidate
        except LLMTimeoutError as exc:
            elapsed = time.monotonic() - t_start
            timeout_source = "operation"
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                timeout_source = "parent"
            elif elapsed < eff_op_timeout:
                timeout_source = "http_request"

            self.last_diagnostic = {
                "status": "timeout",
                "model_name": model_name,
                "prompt_chars": prompt_chars + sys_chars,
                "estimated_prompt_tokens": est_tokens,
                "elapsed_seconds": round(elapsed, 3),
                "timeout_source": timeout_source,
                "error": str(exc),
            }

            logger.error(
                "LLM timeout generating Action Intelligence: %s (elapsed=%.3fs, source=%s)",
                exc,
                elapsed,
                timeout_source,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Action Intelligence generation exceeded allowed processing time.",
            ) from exc
        except LLMAuthenticationError as exc:
            logger.error("LLM authentication failure generating Action Intelligence: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Action Intelligence credentials are not configured or invalid.",
            ) from exc
        except LLMRateLimitError as exc:
            logger.error("LLM rate limit exceeded generating Action Intelligence: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Action Intelligence rate limit exceeded. Please retry shortly.",
            ) from exc
        except LLMResponseValidationError as exc:
            elapsed = time.monotonic() - t_start
            self.last_diagnostic = {
                "status": "validation_error",
                "model_name": model_name,
                "elapsed_seconds": round(elapsed, 3),
                "error": str(exc.message),
            }
            logger.error("LLM output schema validation failure: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Action Intelligence output failed structured schema validation: {exc.message}",
            ) from exc
        except LLMError as exc:
            logger.error("LLM provider error generating Action Intelligence: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Action Intelligence generation failed: {exc.message}",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error generating Action Intelligence: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred during action plan generation.",
            ) from exc

    def assemble_plan(
        self,
        candidate: CandidateActionPlan,
        analysis_id: str,
        source_recommendation_fingerprint: str,
    ) -> IntelligentActionPlan:
        """Converts raw CandidateActionPlan output into strongly typed IntelligentActionPlan."""
        actions: List[IntelligentActionItem] = []
        for a_idx, c_act in enumerate(candidate.actions, start=1):
            criteria: List[ActionCriterion] = []
            for c_idx, c_crit in enumerate(c_act.success_criteria, start=1):
                crit_dict = c_crit.model_dump()
                if not crit_dict.get("criterion_id"):
                    crit_dict["criterion_id"] = f"crit_{c_act.action_id}_{c_idx}"
                criteria.append(ActionCriterion(**crit_dict))

            act_dict = c_act.model_dump()
            act_dict["success_criteria"] = criteria
            actions.append(IntelligentActionItem(**act_dict))

        gates: List[IntelligentDecisionGate] = []
        for g_idx, c_gate in enumerate(candidate.decision_gates, start=1):
            gate_criteria: List[ActionCriterion] = []
            for gc_idx, gc_crit in enumerate(c_gate.criteria, start=1):
                crit_dict = gc_crit.model_dump()
                if not crit_dict.get("criterion_id"):
                    crit_dict["criterion_id"] = f"crit_gate_{c_gate.gate_id}_{gc_idx}"
                gate_criteria.append(ActionCriterion(**crit_dict))

            gate_dict = c_gate.model_dump()
            gate_dict["criteria"] = gate_criteria
            gates.append(IntelligentDecisionGate(**gate_dict))

        plan_id = compute_plan_id(
            analysis_id=analysis_id,
            source_recommendation_fingerprint=source_recommendation_fingerprint,
            actions=actions,
        )

        model_name = _resolve_model_name(self.llm_client)
        created_at = _utc_now_iso()

        generation_metadata: Dict[str, Any] = {
            "model_name": model_name,
            "prompt_version": CURRENT_ACTION_INTELLIGENCE_PROMPT_VERSION,
            "generator_version": ACTION_INTELLIGENCE_GENERATOR_VERSION,
        }
        if self.last_diagnostic:
            generation_metadata.update({
                "prompt_chars": self.last_diagnostic.get("prompt_chars"),
                "estimated_prompt_tokens": self.last_diagnostic.get("estimated_prompt_tokens"),
                "elapsed_seconds": self.last_diagnostic.get("elapsed_seconds"),
            })

        return IntelligentActionPlan(
            plan_id=plan_id,
            analysis_id=analysis_id,
            source_recommendation_fingerprint=source_recommendation_fingerprint,
            schema_version=ACTION_INTELLIGENCE_SCHEMA_VERSION,
            generator_version=ACTION_INTELLIGENCE_GENERATOR_VERSION,
            created_at=created_at,
            strategy_summary=candidate.strategy_summary,
            actions=actions,
            decision_gates=gates,
            unresolved_questions=candidate.unresolved_questions,
            limitations=candidate.limitations,
            validation_warnings=[],
            generation_metadata=generation_metadata,
        )
