"""AURA Decision Recommendation & Action Planning Generator.

Produces an authoritative DecisionRecommendation reconciling empirical evidence,
DecisionModel constraints, and AI Boardroom deliberations.

Guarantees:
- Consumes authoritative DecisionModel, EvidencePackage, and ReasoningBoard.
- Exactly one LLMClient.generate_structured(...) call requesting CandidateDecisionRecommendation.
- Strict candidate validation: all candidate evidence, assumption, gap, and disagreement IDs
  must resolve to authoritative collections; unknown IDs fail closed.
- Action-plan graph validation: acyclic dependencies, unique IDs, structured gates.
- Epistemic integrity: permits explicit 'insufficient_evidence' status; forbids false certainty.
- Content-derived deterministic recommendation ID (rec_<sha256[:32]>).
- Strict deadline propagation and timeout handling.
"""

from datetime import datetime
import time
from typing import Callable, Optional

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import (
    CandidateDecisionRecommendation,
    DecisionRecommendation,
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
from app.services.recommendation.prompt_builder import (
    build_recommendation_prompt,
    build_recommendation_system_instruction,
)
from app.services.recommendation.validator import (
    RecommendationError,
    RecommendationEvaluationError,
    RecommendationPromptError,
    RecommendationValidationError,
    validate_candidate_recommendation,
    validate_recommendation_inputs,
    validate_recommendation_references,
)


class RecommendationGenerator:
    """Injectable generator for decision recommendation and action planning."""

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
        deadline_monotonic: Optional[float] = None,
        clock: Optional[Callable[[], datetime]] = None,
        config: Optional[LLMConfig] = None,
    ) -> DecisionRecommendation:
        """Executes grounded recommendation generation.

        Flow:
        1. Validate authoritative input prerequisites
        2. Deadline pre-check
        3. Build deterministic, bounded prompts
        4. Structured LLM generation requesting CandidateDecisionRecommendation
        5. Pure Python candidate validation & authoritative reconciliation
        6. Defense-in-depth referential integrity check
        7. Return authoritative DecisionRecommendation

        Args:
            decision_model: Authoritative decision problem definition.
            evidence_package: Authoritative empirical evidence package.
            reasoning_board: Authoritative AI Boardroom deliberation artifact.
            deadline_monotonic: Optional monotonic clock deadline.
            clock: Optional clock callable for deterministic testing.
            config: Optional runtime LLMConfig override.

        Returns:
            Authoritative DecisionRecommendation object.

        Raises:
            RecommendationValidationError: If inputs or candidate references are invalid.
            RecommendationPromptError: If prompt construction exceeds bounded limits.
            RecommendationEvaluationError: If deadline expired or LLM generation fails.
        """
        # 1. Authoritative input validation
        validate_recommendation_inputs(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
        )

        # 2. Monotonic deadline pre-check
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise RecommendationEvaluationError(
                "Deadline exceeded prior to recommendation LLM generation."
            )

        # 3. Build bounded, deterministic prompts
        system_instruction = build_recommendation_system_instruction()
        user_prompt = build_recommendation_prompt(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
        )

        effective_config = config or self.config

        # 4. LLM structured generation
        try:
            candidate = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_schema=CandidateDecisionRecommendation,
                system_instruction=system_instruction,
                config=effective_config,
                deadline_monotonic=deadline_monotonic,
            )
        except LLMTimeoutError as exc:
            raise RecommendationEvaluationError(
                f"Recommendation generation timed out: {exc.message}",
                details={**getattr(exc, "details", {}), "error_type": "timeout"},
            ) from exc
        except LLMResponseValidationError as exc:
            raise RecommendationEvaluationError(
                f"Recommendation LLM output validation failed: {exc.message}",
                details={**getattr(exc, "details", {}), "error_type": "invalid_output"},
            ) from exc
        except LLMRateLimitError as exc:
            raise RecommendationEvaluationError(
                f"Recommendation LLM rate limit exceeded: {exc.message}",
                details={**getattr(exc, "details", {}), "error_type": "rate_limit"},
            ) from exc
        except LLMAuthenticationError as exc:
            raise RecommendationEvaluationError(
                f"Recommendation LLM authentication failed: {exc.message}",
                details={**getattr(exc, "details", {}), "error_type": "auth_error"},
            ) from exc
        except LLMError as exc:
            exc_details = getattr(exc, "details", {})
            status_code = exc_details.get("status_code")
            if status_code == 400 or exc_details.get("gemini_status") == "INVALID_ARGUMENT":
                raise RecommendationEvaluationError(
                    f"Recommendation LLM invalid request ({status_code or 400}): {exc.message}",
                    details={**exc_details, "error_type": "client_error"},
                ) from exc
            raise RecommendationEvaluationError(
                f"Recommendation LLM generation failed: {exc.message}",
                details={**exc_details, "error_type": "llm_error"},
            ) from exc
        except (RecommendationError, RecommendationEvaluationError, RecommendationValidationError):
            raise
        except Exception as exc:
            raise RecommendationEvaluationError(
                f"Recommendation LLM generation failed: {exc.__class__.__name__}: {str(exc)}"
            ) from exc

        # 5. Candidate validation & authoritative reconciliation
        recommendation = validate_candidate_recommendation(
            candidate=candidate,
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            clock=clock,
        )

        # 6. Defense-in-depth referential check
        validate_recommendation_references(
            recommendation=recommendation,
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
        )

        return recommendation
