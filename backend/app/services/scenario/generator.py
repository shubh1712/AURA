"""AURA Scenario Generator (Phase 5A).

Produces authoritative ScenarioSet reconciling empirical evidence,
DecisionModel constraints, AI Boardroom deliberations, and DecisionRecommendation.

Guarantees:
- Consumes authoritative DecisionModel, EvidencePackage, ReasoningBoard, and DecisionRecommendation.
- Invokes LLMClient.generate_structured(...) requesting CandidateScenarioSet.
- Strict candidate validation: exact 3 canonical scenario types (optimistic, base_case, pessimistic).
- Strict probability invariant validation: finite probabilities summing to 1.0 within 0.01 tolerance.
- Fails closed on fabricated evidence, assumption, constraint, or gap references.
- Content-derived deterministic scenario IDs (scen_<sha256[:16]>) and scenario set ID (scenset_<sha256[:32]>).
- Strict deadline propagation and timeout handling.
"""

from datetime import datetime
import time
from typing import Callable, Optional

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import CandidateScenarioSet, ScenarioSet
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.scenario.prompt_builder import (
    build_scenario_prompt,
    build_scenario_system_instruction,
)
from app.services.scenario.validator import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioPromptError,
    ScenarioValidationError,
    validate_candidate_scenario_set,
    validate_scenario_inputs,
)


class ScenarioGenerator:
    """Injectable generator for decision future scenario simulation."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: Optional[LLMConfig] = None,
    ) -> None:
        self.llm_client = llm_client
        self.config = config

    def generate(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        reasoning_board: ReasoningBoard,
        recommendation: DecisionRecommendation,
        deadline_monotonic: Optional[float] = None,
        clock: Optional[Callable[[], datetime]] = None,
        config: Optional[LLMConfig] = None,
    ) -> ScenarioSet:
        """Executes grounded scenario generation.

        Flow:
        1. Validate authoritative input prerequisites
        2. Deadline pre-check
        3. Build deterministic, bounded prompts
        4. Structured LLM generation requesting CandidateScenarioSet
        5. Pure Python candidate validation & authoritative reconciliation
        6. Return authoritative ScenarioSet

        Args:
            decision_model: Authoritative decision problem definition.
            evidence_package: Authoritative empirical evidence portfolio.
            reasoning_board: Authoritative AI Boardroom deliberation artifact.
            recommendation: Authoritative decision recommendation and action plan.
            deadline_monotonic: Optional monotonic clock deadline.
            clock: Optional clock callable for deterministic testing.
            config: Optional runtime LLMConfig override.

        Returns:
            Authoritative ScenarioSet object.

        Raises:
            ScenarioValidationError: If inputs or candidate scenarios fail validation.
            ScenarioPromptError: If prompt construction exceeds bounded limits.
            ScenarioEvaluationError: If deadline expired or LLM generation fails.
        """
        # 1. Authoritative input validation
        validate_scenario_inputs(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            recommendation=recommendation,
        )

        # 2. Deadline pre-check
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Scenario generation deadline expired prior to execution.")
            raise ScenarioEvaluationError(
                "Scenario generation timed out: deadline expired before generation.",
                details={"error_type": "timeout", "timeout_source": "deadline_pre_check"},
            ) from timeout_err

        # 3. Build bounded prompt
        prompt = build_scenario_prompt(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            recommendation=recommendation,
        )
        system_instruction = build_scenario_system_instruction()

        # 4. Invoke structured generation via LLMClient
        effective_config = config or self.config
        gen_kwargs = {
            "prompt": prompt,
            "response_schema": CandidateScenarioSet,
            "system_instruction": system_instruction,
            "deadline_monotonic": deadline_monotonic,
        }
        if effective_config is not None:
            gen_kwargs["config"] = effective_config

        try:
            try:
                candidate = self.llm_client.generate_structured(**gen_kwargs)
            except TypeError as te:
                if "unexpected keyword argument" in str(te):
                    gen_kwargs.pop("config", None)
                    candidate = self.llm_client.generate_structured(**gen_kwargs)
                else:
                    raise
        except LLMTimeoutError as exc:
            raise ScenarioEvaluationError(
                f"Scenario generation timed out against provider: {str(exc)}",
                details={**getattr(exc, "details", {}), "error_type": "timeout"},
            ) from exc
        except LLMResponseValidationError as exc:
            raise ScenarioEvaluationError(
                f"Scenario generation structured response validation failed: {str(exc)}",
                details={**getattr(exc, "details", {}), "error_type": "invalid_output"},
            ) from exc
        except LLMAuthenticationError as exc:
            raise ScenarioEvaluationError(
                f"Scenario generation provider authentication failed: {str(exc)}",
                details={"error_type": "auth_error"},
            ) from exc
        except LLMRateLimitError as exc:
            raise ScenarioEvaluationError(
                f"Scenario generation rate limit exceeded: {str(exc)}",
                details={"error_type": "rate_limit"},
            ) from exc
        except LLMError as exc:
            raise ScenarioEvaluationError(
                f"Scenario generation provider error: {str(exc)}",
                details={"error_type": "provider_error"},
            ) from exc

        # 5. Pure Python validation and authoritative reconciliation
        return validate_candidate_scenario_set(
            candidate=candidate,
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            recommendation=recommendation,
            clock=clock,
        )
