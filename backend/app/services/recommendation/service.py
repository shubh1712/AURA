"""AURA Recommendation Service & Action Planning Orchestration.

Coordinates generation and validation of authoritative DecisionRecommendation artifacts:
1. Validates upstream DecisionModel, EvidencePackage, and ReasoningBoard bindings.
2. Checks parent monotonic deadlines.
3. Invokes RecommendationGenerator with structured response schemas.
4. Validates referential integrity against empirical evidence and boardroom deliberations.
5. Emits authoritative, grounded DecisionRecommendation with deterministic ID.
"""

from datetime import datetime, timezone
import time
from typing import Callable, Optional

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.services.llm.client import LLMClient, LLMConfig, LLMTimeoutError
from app.services.recommendation.generator import RecommendationGenerator
from app.services.recommendation.validator import (
    RecommendationError,
    RecommendationEvaluationError,
    RecommendationServiceError,
    RecommendationValidationError,
    validate_recommendation_inputs,
)


class RecommendationService:
    """Service facade coordinating decision recommendation generation and validation."""

    def __init__(
        self,
        generator: RecommendationGenerator,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.generator = generator
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def create_default(
        cls,
        llm_client: LLMClient,
        config: Optional[LLMConfig] = None,
        clock: Optional[Callable[[], datetime]] = None,
        recommendation_operation_timeout_seconds: Optional[float] = None,
    ) -> "RecommendationService":
        """Factory creating RecommendationService with an injected LLMClient."""
        cfg = config
        if cfg is None and recommendation_operation_timeout_seconds is not None:
            cfg = LLMConfig(
                operation_timeout_seconds=recommendation_operation_timeout_seconds,
                timeout_seconds=min(45.0, recommendation_operation_timeout_seconds),
            )
        generator = RecommendationGenerator(llm_client=llm_client, config=cfg)
        return cls(generator=generator, clock=clock)

    def generate_recommendation(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        reasoning_board: ReasoningBoard,
        deadline_monotonic: Optional[float] = None,
        recommendation_config: Optional[LLMConfig] = None,
    ) -> DecisionRecommendation:
        """Executes grounded decision recommendation generation.

        Args:
            decision_model: Authoritative decision problem definition.
            evidence_package: Authoritative empirical evidence portfolio.
            reasoning_board: Authoritative AI Boardroom deliberation artifact.
            deadline_monotonic: Single authoritative parent monotonic deadline.
            recommendation_config: Optional operation LLMConfig override.

        Returns:
            DecisionRecommendation: Authoritative, fully grounded recommendation artifact.

        Raises:
            RecommendationServiceError: If generation times out or unhandled error occurs.
            RecommendationValidationError: If input or output referential integrity fails.
            RecommendationEvaluationError: If LLM generation fails or deadline expired.
        """
        # 1. Upstream validation
        validate_recommendation_inputs(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
        )

        # 2. Deadline pre-check
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Recommendation deadline expired prior to execution.")
            raise RecommendationServiceError(
                "Recommendation service timed out: deadline expired before generation.",
                stage="recommendation",
            ) from timeout_err

        # 3. Execution via RecommendationGenerator
        try:
            return self.generator.generate(
                decision_model=decision_model,
                evidence_package=evidence_package,
                reasoning_board=reasoning_board,
                deadline_monotonic=deadline_monotonic,
                clock=self.clock,
                config=recommendation_config,
            )
        except RecommendationValidationError:
            raise
        except LLMTimeoutError as exc:
            raise RecommendationServiceError(
                f"Recommendation generation timed out: {str(exc)}",
                stage="recommendation",
                details={**getattr(exc, "details", {}), "error_type": "timeout"},
            ) from exc
        except RecommendationEvaluationError as exc:
            exc_details = getattr(exc, "details", {})
            err_type = exc_details.get("error_type")
            if err_type == "timeout" or ("timed out" in str(exc).lower() and "failed" not in str(exc).lower()):
                msg = f"Recommendation generation timed out: {str(exc)}"
            elif err_type == "client_error":
                msg = f"Recommendation generation invalid request: {str(exc)}"
            elif err_type == "invalid_output":
                msg = f"Recommendation generation output validation failed: {str(exc)}"
            else:
                msg = f"Recommendation generation failed: {str(exc)}"
            raise RecommendationServiceError(
                msg,
                stage="recommendation",
                details=exc_details,
            ) from exc
        except RecommendationServiceError:
            raise
        except Exception as exc:
            raise RecommendationServiceError(
                f"Recommendation generation stage failed: {exc.__class__.__name__}: {str(exc)}",
                stage="recommendation",
            ) from exc
