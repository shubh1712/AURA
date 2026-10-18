"""AURA Scenario Service & Orchestration Facade (Phase 5A).

Coordinates generation and validation of authoritative ScenarioSet artifacts:
1. Validates upstream DecisionModel, EvidencePackage, ReasoningBoard, and DecisionRecommendation bindings.
2. Checks parent monotonic deadlines.
3. Invokes ScenarioGenerator with structured response schemas.
4. Validates referential integrity against empirical evidence and boardroom deliberations.
5. Emits authoritative, grounded ScenarioSet with deterministic IDs.
"""

from datetime import datetime, timezone
import time
from typing import Callable, Optional

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import ScenarioSet
from app.services.llm.client import LLMClient, LLMConfig, LLMTimeoutError
from app.services.scenario.generator import ScenarioGenerator
from app.services.scenario.validator import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioServiceError,
    ScenarioValidationError,
    validate_scenario_inputs,
)


class ScenarioService:
    """Service facade coordinating future scenario simulation and validation."""

    def __init__(
        self,
        generator: ScenarioGenerator,
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
        scenario_operation_timeout_seconds: Optional[float] = None,
    ) -> "ScenarioService":
        """Factory creating ScenarioService with an injected LLMClient."""
        cfg = config
        if cfg is None and scenario_operation_timeout_seconds is not None:
            cfg = LLMConfig(
                operation_timeout_seconds=scenario_operation_timeout_seconds,
                timeout_seconds=min(45.0, scenario_operation_timeout_seconds),
            )
        generator = ScenarioGenerator(llm_client=llm_client, config=cfg)
        return cls(generator=generator, clock=clock)

    def generate_scenarios(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        reasoning_board: ReasoningBoard,
        recommendation: DecisionRecommendation,
        deadline_monotonic: Optional[float] = None,
        scenario_config: Optional[LLMConfig] = None,
    ) -> ScenarioSet:
        """Executes grounded future scenario generation.

        Args:
            decision_model: Authoritative decision problem definition.
            evidence_package: Authoritative empirical evidence portfolio.
            reasoning_board: Authoritative AI Boardroom deliberation artifact.
            recommendation: Authoritative decision recommendation and action plan.
            deadline_monotonic: Single authoritative parent monotonic deadline.
            scenario_config: Optional operation LLMConfig override.

        Returns:
            ScenarioSet: Authoritative, fully grounded 3-scenario portfolio.

        Raises:
            ScenarioServiceError: If generation times out or unhandled error occurs.
            ScenarioValidationError: If input or output referential integrity fails.
            ScenarioEvaluationError: If LLM generation fails or deadline expired.
        """
        # 1. Upstream validation
        validate_scenario_inputs(
            decision_model=decision_model,
            evidence_package=evidence_package,
            reasoning_board=reasoning_board,
            recommendation=recommendation,
        )

        # 2. Deadline pre-check
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Scenario generation deadline expired prior to execution.")
            raise ScenarioServiceError(
                "Scenario service timed out: deadline expired before generation.",
                stage="scenario_engine",
            ) from timeout_err

        # 3. Execution via ScenarioGenerator
        try:
            return self.generator.generate(
                decision_model=decision_model,
                evidence_package=evidence_package,
                reasoning_board=reasoning_board,
                recommendation=recommendation,
                deadline_monotonic=deadline_monotonic,
                clock=self.clock,
                config=scenario_config,
            )
        except ScenarioValidationError:
            raise
        except LLMTimeoutError as exc:
            raise ScenarioServiceError(
                f"Scenario generation timed out: {str(exc)}",
                stage="scenario_engine",
                details={**getattr(exc, "details", {}), "error_type": "timeout"},
            ) from exc
        except ScenarioEvaluationError as exc:
            exc_details = getattr(exc, "details", {})
            err_type = exc_details.get("error_type")
            if err_type == "timeout" or ("timed out" in str(exc).lower() and "failed" not in str(exc).lower()):
                msg = f"Scenario generation timed out: {str(exc)}"
            elif err_type == "client_error":
                msg = f"Scenario generation invalid request: {str(exc)}"
            elif err_type == "invalid_output":
                msg = f"Scenario generation output validation failed: {str(exc)}"
            else:
                msg = f"Scenario generation failed: {str(exc)}"
            raise ScenarioServiceError(
                msg,
                stage="scenario_engine",
                details=exc_details,
            ) from exc
        except ScenarioServiceError:
            raise
        except Exception as exc:
            raise ScenarioServiceError(
                f"Scenario generation stage failed: {exc.__class__.__name__}: {str(exc)}",
                stage="scenario_engine",
            ) from exc
