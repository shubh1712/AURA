"""AURA Analysis Service.

Coordinates decision analysis intake, deconstruction, evidence retrieval,
and deterministic evaluation. All cognitive processing, language model interaction,
search retrieval, and provenance verification are orchestrated here, keeping API
controllers thin and free of model dependencies.
"""

import logging
import os
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from fastapi import Depends, HTTPException, status
from fastapi.params import Depends as DependsParam

from app.config import settings
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation, DecisionStatus
from app.services.evidence import (
    EvidenceService,
    EvidenceServiceError,
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProvider,
    SearchProviderError,
    SearchRateLimitError,
    SearchResponseError,
    SearchTimeoutError,
)
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.reasoning import (
    ReasoningError,
    ReasoningEvaluationError,
    ReasoningOrchestrationError,
    ReasoningPromptError,
    ReasoningService,
    ReasoningServiceError,
    ReasoningValidationError,
)
from app.services.recommendation import (
    RecommendationError,
    RecommendationEvaluationError,
    RecommendationService,
    RecommendationServiceError,
    RecommendationValidationError,
)

logger = logging.getLogger(__name__)


class AnalysisTimeoutError(Exception):
    """Raised when an end-to-end decision analysis exceeds its shared wall-clock deadline."""
    pass


def _find_cause_instance(
    exc: BaseException,
    target_type: Union[type, Tuple[type, ...]],
) -> Optional[BaseException]:
    """Traverses __cause__ and __context__ to find an instance of target_type."""
    current: Optional[BaseException] = exc
    visited = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, target_type):
            return current
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _is_timeout_error(exc: BaseException) -> bool:
    """Traverses __cause__ and __context__ to determine if the error represents a timeout."""
    current: Optional[BaseException] = exc
    visited = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, (LLMTimeoutError, SearchTimeoutError, AnalysisTimeoutError)):
            return True
        if isinstance(
            current,
            (
                ReasoningEvaluationError,
                ReasoningOrchestrationError,
                ReasoningServiceError,
                RecommendationEvaluationError,
                RecommendationServiceError,
            ),
        ):
            details = getattr(current, "details", {})
            if isinstance(details, dict) and details.get("error_type") == "timeout":
                return True
            msg = str(current).lower()
            clean_msg = msg.replace("timed out or failed", "")
            if ("timed out" in clean_msg or "timeout" in clean_msg or "deadline" in clean_msg) and "invalid request" not in clean_msg and "validation failed" not in clean_msg:
                return True
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _sanitize_reasoning_validation_diagnostic(
    err: ReasoningValidationError,
    stage: str,
) -> str:
    """Builds safe, privacy-preserving structured diagnostic text for ReasoningValidationError.

    Guarantees:
    - Never logs secrets, credentials, bearer tokens, private prompts, or raw unbounded user inputs.
    - Reports exception type, stage, location, field paths, and sanitized details.
    """
    exc_type = type(err).__name__
    raw_details = getattr(err, "details", {}) or {}

    location = raw_details.get("location") or "reasoning_validator"
    field = raw_details.get("field") or raw_details.get("field_paths") or "unknown_field"
    rule = raw_details.get("rule") or "validation_failure"

    safe_details: Dict[str, Any] = {}
    for k, v in raw_details.items():
        if k in ("location", "field", "field_paths", "rule"):
            continue
        if isinstance(v, (int, float, bool)):
            safe_details[k] = v
        elif isinstance(v, str):
            if len(v) <= 80 and not any(s in v.upper() for s in ("SECRET", "KEY", "TOKEN", "BEARER", "AIZA")):
                safe_details[k] = v
            else:
                safe_details[k] = "[REDACTED]"
        elif isinstance(v, (list, tuple)):
            safe_list = []
            for item in v:
                if isinstance(item, str) and len(item) <= 80 and not any(s in item.upper() for s in ("SECRET", "KEY", "TOKEN", "BEARER", "AIZA")):
                    safe_list.append(item)
                elif isinstance(item, (int, float, bool)):
                    safe_list.append(item)
                else:
                    safe_list.append("[REDACTED]")
            safe_details[k] = safe_list

    return (
        f"type={exc_type} stage={stage} location={location} field={field} rule={rule} details={safe_details}"
    )


class AnalysisService:
    """Orchestrates decision analysis workflows and error translation."""

    _client_factory: Optional[Callable[[], LLMClient]] = None

    @classmethod
    def set_client_factory(cls, factory: Optional[Callable[[], LLMClient]]) -> None:
        """Sets custom factory for providing LLMClient instances (e.g. in tests)."""
        cls._client_factory = factory

    @classmethod
    def get_default_client(cls) -> LLMClient:
        """Returns the default LLMClient instance."""
        if cls._client_factory is not None:
            return cls._client_factory()
        from app.services.llm.gemini import GeminiLLMClient

        return GeminiLLMClient()

    def __init__(
        self,
        engine: Optional[QuestionUnderstandingEngine] = None,
        evidence_service: Optional[EvidenceService] = None,
        reasoning_service: Optional[ReasoningService] = None,
        recommendation_service: Optional[RecommendationService] = None,
        llm_client: Optional[LLMClient] = None,
        search_provider: Optional[SearchProvider] = None,
        analysis_timeout_seconds: Optional[float] = None,
        framer_operation_timeout_seconds: Optional[float] = None,
        boardroom_operation_timeout_seconds: Optional[float] = None,
        recommendation_operation_timeout_seconds: Optional[float] = None,
    ) -> None:
        """Initializes AnalysisService with engine, evidence_service, reasoning_service, and recommendation_service.

        Args:
            engine: Optional pre-configured QuestionUnderstandingEngine.
            evidence_service: Optional pre-configured EvidenceService.
            reasoning_service: Optional pre-configured ReasoningService.
            recommendation_service: Optional pre-configured RecommendationService.
            llm_client: Optional pre-configured LLMClient.
            search_provider: Optional pre-configured SearchProvider.
            analysis_timeout_seconds: Optional overall wall-clock analysis deadline budget in seconds.
            framer_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 1 Decision Framer.
            boardroom_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 3 AI Boardroom perspectives.
            recommendation_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 4 Recommendation Engine.
        """
        self.analysis_timeout_seconds: float = (
            analysis_timeout_seconds
            if analysis_timeout_seconds is not None
            else getattr(settings, "ANALYSIS_TIMEOUT_SECONDS", 120.0)
        )

        raw_framer_to = framer_operation_timeout_seconds
        if raw_framer_to is None:
            raw_framer_to = getattr(settings, "AURA_FRAMER_OPERATION_TIMEOUT_SECONDS", None)
            if raw_framer_to is None:
                env_val = os.environ.get("AURA_FRAMER_OPERATION_TIMEOUT_SECONDS")
                if env_val is not None:
                    try:
                        raw_framer_to = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_FRAMER_OPERATION_TIMEOUT_SECONDS value: {env_val}") from ve

        if raw_framer_to is not None:
            if raw_framer_to <= 0.0:
                raise ValueError("framer_operation_timeout_seconds must be strictly greater than 0.0")
            self.framer_operation_timeout_seconds: Optional[float] = float(raw_framer_to)
        else:
            self.framer_operation_timeout_seconds = None

        raw_boardroom_to = boardroom_operation_timeout_seconds
        if raw_boardroom_to is None:
            raw_boardroom_to = getattr(settings, "AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS", None)
            if raw_boardroom_to is None:
                env_val = os.environ.get("AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS")
                if env_val is not None:
                    try:
                        raw_boardroom_to = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_BOARDROOM_OPERATION_TIMEOUT_SECONDS value: {env_val}") from ve

        if raw_boardroom_to is not None:
            if raw_boardroom_to <= 0.0:
                raise ValueError("boardroom_operation_timeout_seconds must be strictly greater than 0.0")
            self.boardroom_operation_timeout_seconds: Optional[float] = float(raw_boardroom_to)
        else:
            self.boardroom_operation_timeout_seconds = None

        raw_recommendation_to = recommendation_operation_timeout_seconds
        if raw_recommendation_to is None:
            raw_recommendation_to = getattr(settings, "AURA_RECOMMENDATION_OPERATION_TIMEOUT_SECONDS", None)
            if raw_recommendation_to is None:
                env_val = os.environ.get("AURA_RECOMMENDATION_OPERATION_TIMEOUT_SECONDS")
                if env_val is not None:
                    try:
                        raw_recommendation_to = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_RECOMMENDATION_OPERATION_TIMEOUT_SECONDS value: {env_val}") from ve

        if raw_recommendation_to is not None:
            if raw_recommendation_to <= 0.0:
                raise ValueError("recommendation_operation_timeout_seconds must be strictly greater than 0.0")
            self.recommendation_operation_timeout_seconds: Optional[float] = float(raw_recommendation_to)
        else:
            self.recommendation_operation_timeout_seconds = None

        if engine is not None and not isinstance(engine, DependsParam):
            self.engine = engine
        elif llm_client is not None:
            self.engine = QuestionUnderstandingEngine(llm_client=llm_client)
        else:
            self.engine = self._build_default_engine()

        if evidence_service is not None and not isinstance(evidence_service, DependsParam):
            self.evidence_service = evidence_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.evidence_service = self._build_default_evidence_service(
                llm_client=effective_llm,
                search_provider=search_provider,
            )

        if reasoning_service is not None and not isinstance(reasoning_service, DependsParam):
            self.reasoning_service = reasoning_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.reasoning_service = self._build_default_reasoning_service(
                llm_client=effective_llm,
                boardroom_operation_timeout_seconds=self.boardroom_operation_timeout_seconds,
            )

        if recommendation_service is not None and not isinstance(recommendation_service, DependsParam):
            self.recommendation_service = recommendation_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.recommendation_service = self._build_default_recommendation_service(
                llm_client=effective_llm,
                recommendation_operation_timeout_seconds=self.recommendation_operation_timeout_seconds,
            )

    @classmethod
    def _build_default_engine(cls) -> QuestionUnderstandingEngine:
        """Builds default QuestionUnderstandingEngine with configured LLMClient."""
        client = cls.get_default_client()
        return QuestionUnderstandingEngine(llm_client=client)

    @classmethod
    def _build_default_evidence_service(
        cls,
        llm_client: Optional[LLMClient] = None,
        search_provider: Optional[SearchProvider] = None,
    ) -> EvidenceService:
        """Builds default EvidenceService wired with provided or default providers."""
        client = llm_client or cls.get_default_client()
        provider = search_provider or get_search_provider()
        return EvidenceService.create_default(
            llm_client=client,
            search_provider=provider,
        )

    @classmethod
    def _build_default_reasoning_service(
        cls,
        llm_client: Optional[LLMClient] = None,
        boardroom_operation_timeout_seconds: Optional[float] = None,
    ) -> ReasoningService:
        """Builds default ReasoningService wired with provided or default LLMClient."""
        client = llm_client or cls.get_default_client()
        return ReasoningService.create_default(
            llm_client=client,
            boardroom_operation_timeout_seconds=boardroom_operation_timeout_seconds,
        )

    @classmethod
    def _build_default_recommendation_service(
        cls,
        llm_client: Optional[LLMClient] = None,
        recommendation_operation_timeout_seconds: Optional[float] = None,
    ) -> RecommendationService:
        """Builds default RecommendationService wired with provided or default LLMClient."""
        client = llm_client or cls.get_default_client()
        return RecommendationService.create_default(
            llm_client=client,
            recommendation_operation_timeout_seconds=recommendation_operation_timeout_seconds,
        )

    def analyze(
        self,
        request: AnalysisRequest,
        deadline_monotonic: Optional[float] = None,
        stage_callback: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResponse:
        """Executes decision deconstruction, evidence gathering, provenance auditing, and boardroom deliberation.

        Args:
            request: Validated AnalysisRequest payload.
            deadline_monotonic: Optional absolute monotonic deadline for the entire analysis.
            stage_callback: Optional callback receiving current pipeline stage name.

        Returns:
            AnalysisResponse containing generated analysis_id, status="completed",
            decision_model, evidence_package, and reasoning_board.

        Raises:
            HTTPException: With domain-specific status codes for LLM, Search, Timeout, or unexpected failures.
        """
        analysis_id = str(uuid.uuid4())
        start_time = time.monotonic()
        effective_deadline = (
            deadline_monotonic
            if deadline_monotonic is not None
            else start_time + self.analysis_timeout_seconds
        )

        try:
            if time.monotonic() >= effective_deadline:
                raise AnalysisTimeoutError("Analysis operation exceeded end-to-end deadline before deconstruction.")

            # 1. Deconstruct inquiry into canonical DecisionModel
            if stage_callback:
                stage_callback("stage1_decision_framer")

            framer_config = None
            if self.framer_operation_timeout_seconds is not None:
                framer_config = LLMConfig(operation_timeout_seconds=self.framer_operation_timeout_seconds)

            deconstruct_kwargs: Dict[str, Any] = {
                "question": request.question,
                "context": request.context,
                "constraints": request.constraints,
                "deadline_monotonic": effective_deadline,
            }
            if framer_config is not None:
                deconstruct_kwargs["config"] = framer_config

            try:
                try:
                    decision_model = self.engine.deconstruct(**deconstruct_kwargs)
                except TypeError as te:
                    if "unexpected keyword argument 'config'" in str(te):
                        deconstruct_kwargs.pop("config", None)
                        decision_model = self.engine.deconstruct(**deconstruct_kwargs)
                    else:
                        raise
            except TypeError as te:
                if "unexpected keyword argument 'deadline_monotonic'" in str(te):
                    decision_model = self.engine.deconstruct(
                        question=request.question,
                        context=request.context,
                        constraints=request.constraints,
                    )
                else:
                    raise

            if time.monotonic() >= effective_deadline:
                raise AnalysisTimeoutError("Analysis operation exceeded end-to-end deadline before evidence gathering.")

            # 2. Gather, normalize, map, and gap-analyze evidence
            if stage_callback:
                stage_callback("stage2_evidence_engine")

            try:
                evidence_package = self.evidence_service.build_evidence_package(
                    decision_model=decision_model,
                    deadline_monotonic=effective_deadline,
                )
            except TypeError as te:
                if "unexpected keyword argument 'deadline_monotonic'" in str(te):
                    evidence_package = self.evidence_service.build_evidence_package(
                        decision_model=decision_model,
                    )
                else:
                    raise

            if time.monotonic() >= effective_deadline:
                raise AnalysisTimeoutError("Analysis operation exceeded end-to-end deadline before boardroom deliberation.")

            # 3. Deliberate across canonical boardroom perspectives and synthesize board
            if stage_callback:
                stage_callback("stage3_ai_boardroom")

            perspective_config = None
            if self.boardroom_operation_timeout_seconds is not None:
                perspective_config = LLMConfig(
                    operation_timeout_seconds=self.boardroom_operation_timeout_seconds,
                    timeout_seconds=min(45.0, self.boardroom_operation_timeout_seconds),
                )

            boardroom_kwargs: Dict[str, Any] = {
                "decision_model": decision_model,
                "evidence_package": evidence_package,
                "deadline_monotonic": effective_deadline,
            }
            if perspective_config is not None:
                boardroom_kwargs["perspective_config"] = perspective_config

            try:
                try:
                    reasoning_board = self.reasoning_service.build_reasoning_board(**boardroom_kwargs)
                except TypeError as te:
                    if "unexpected keyword argument 'perspective_config'" in str(te):
                        boardroom_kwargs.pop("perspective_config", None)
                        reasoning_board = self.reasoning_service.build_reasoning_board(**boardroom_kwargs)
                    else:
                        raise
            except TypeError as te:
                if "unexpected keyword argument 'deadline_monotonic'" in str(te):
                    reasoning_board = self.reasoning_service.build_reasoning_board(
                        decision_model=decision_model,
                        evidence_package=evidence_package,
                    )
                else:
                    raise

            # 4. Generate grounded recommendation & action plan (Recommendation Engine)
            if stage_callback:
                stage_callback("stage4_recommendation")

            recommendation: Optional[DecisionRecommendation] = None
            recommendation_status: Optional[str] = None
            recommendation_error: Optional[str] = None

            if time.monotonic() >= effective_deadline:
                logger.warning(
                    "Analysis %s exceeded end-to-end deadline before Stage 4 recommendation generation.",
                    analysis_id,
                )
                recommendation_status = "unavailable"
                recommendation_error = "Stage 4 recommendation generation skipped: global analysis deadline expired."
            else:
                recommendation_config = None
                if self.recommendation_operation_timeout_seconds is not None:
                    recommendation_config = LLMConfig(
                        operation_timeout_seconds=self.recommendation_operation_timeout_seconds,
                        timeout_seconds=min(45.0, self.recommendation_operation_timeout_seconds),
                    )

                rec_kwargs: Dict[str, Any] = {
                    "decision_model": decision_model,
                    "evidence_package": evidence_package,
                    "reasoning_board": reasoning_board,
                    "deadline_monotonic": effective_deadline,
                }
                if recommendation_config is not None:
                    rec_kwargs["recommendation_config"] = recommendation_config

                try:
                    try:
                        recommendation = self.recommendation_service.generate_recommendation(**rec_kwargs)
                    except TypeError as te:
                        if "unexpected keyword argument 'recommendation_config'" in str(te):
                            rec_kwargs.pop("recommendation_config", None)
                            recommendation = self.recommendation_service.generate_recommendation(**rec_kwargs)
                        else:
                            raise
                    recommendation_status = "completed"
                except Exception as exc:
                    # Explicit Product Failure Policy:
                    # If Stages 1-3 succeed but Stage 4 fails, preserve completed Boardroom result
                    # and expose recommendation as unavailable.
                    logger.warning(
                        "Analysis %s Stage 4 recommendation generation failed; preserving Boardroom output. Error: %s: %s",
                        analysis_id,
                        type(exc).__name__,
                        str(exc),
                    )
                    recommendation_status = "unavailable"
                    if _is_timeout_error(exc):
                        recommendation_error = f"Recommendation generation timed out: {getattr(exc, 'message', str(exc))}"
                    else:
                        recommendation_error = f"Recommendation generation unavailable: {getattr(exc, 'message', str(exc))}"

            # 5. Assemble validated response
            is_full_success = recommendation is not None
            overall_status = "completed" if is_full_success else "partial_success"
            message_text = (
                "Decision deconstruction, evidence gathering, boardroom deliberation, and recommendation completed successfully."
                if is_full_success
                else f"Decision analysis completed with Boardroom deliberation; recommendation stage unavailable ({recommendation_error})."
            )

            return AnalysisResponse(
                analysis_id=analysis_id,
                status=overall_status,
                decision_model=decision_model,
                evidence_package=evidence_package,
                reasoning_board=reasoning_board,
                recommendation=recommendation,
                recommendation_status=recommendation_status,
                recommendation_error=recommendation_error,
                question=request.question,
                message=message_text,
            )

        except (LLMTimeoutError, SearchTimeoutError, AnalysisTimeoutError) as e:
            elapsed = time.monotonic() - start_time
            remaining = max(0.0, effective_deadline - time.monotonic())
            details = getattr(e, "details", None) or {}
            timeout_src = details.get("timeout_source", "unknown")
            attempts = details.get("attempt")
            logger.error(
                "Analysis %s timed out during evaluation: timeout_type=%s, timeout_source=%s, attempts=%s, elapsed=%.2fs, remaining_budget=%.2fs",
                analysis_id,
                type(e).__name__,
                timeout_src,
                attempts,
                elapsed,
                remaining,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Decision analysis timed out while evaluating the inquiry.",
            ) from e

        except LLMAuthenticationError as e:
            logger.error("Analysis %s failed with LLM authentication error", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Decision intelligence service unavailable: AI provider authentication failed or credentials not configured.",
            ) from e

        except LLMRateLimitError as e:
            logger.warning("Analysis %s rate limited by upstream LLM provider", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Decision intelligence request rate limit or quota exceeded. Please try again shortly.",
            ) from e

        except LLMResponseValidationError as e:
            logger.error("Analysis %s failed LLM response schema validation", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Decision intelligence engine returned an unparseable response structure.",
            ) from e

        except (LLMProviderError, LLMError) as e:
            logger.error("Analysis %s failed due to upstream LLM provider error", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream decision intelligence provider error encountered.",
            ) from e

        except (SearchProviderError, EvidenceServiceError) as e:
            # Check for timeout failures in causal chain first
            timeout_cause = _find_cause_instance(e, (SearchTimeoutError, LLMTimeoutError, AnalysisTimeoutError))
            if timeout_cause is not None:
                elapsed = time.monotonic() - start_time
                remaining = max(0.0, effective_deadline - time.monotonic())
                substage = getattr(e, "stage", None) or "evidence_engine"
                details = getattr(timeout_cause, "details", None) or {}
                timeout_src = details.get("timeout_source", "unknown")
                attempts = details.get("attempt")
                logger.error(
                    "Analysis %s evidence stage timed out: substage=%s, timeout_type=%s, timeout_source=%s, attempts=%s, elapsed=%.2fs, remaining_budget=%.2fs",
                    analysis_id,
                    substage,
                    type(timeout_cause).__name__,
                    timeout_src,
                    attempts,
                    elapsed,
                    remaining,
                )
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Decision analysis timed out while evaluating the inquiry.",
                ) from e

            # Check for SearchProvider failures in causal chain
            if _find_cause_instance(e, SearchAuthenticationError):
                logger.error("Analysis %s search provider authentication failure", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Decision intelligence search provider authentication failed or credentials not configured.",
                ) from e

            if _find_cause_instance(e, SearchRateLimitError):
                logger.warning("Analysis %s search provider rate limited", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Search provider request rate limit or quota exceeded. Please try again shortly.",
                ) from e

            if _find_cause_instance(e, (SearchNetworkError, SearchResponseError, SearchProviderError)):
                logger.error("Analysis %s search provider upstream error", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Upstream search provider error encountered during evidence retrieval.",
                ) from e

            # Check if an LLM failure occurred inside EvidenceService (e.g. mapping or requirements stage)
            if _find_cause_instance(e, LLMAuthenticationError):
                logger.error("Analysis %s evidence stage failed with LLM authentication error", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Decision intelligence service unavailable: AI provider authentication failed or credentials not configured.",
                ) from e

            if _find_cause_instance(e, LLMRateLimitError):
                logger.warning("Analysis %s evidence stage rate limited by LLM provider", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Decision intelligence request rate limit or quota exceeded. Please try again shortly.",
                ) from e

            val_cause = _find_cause_instance(e, LLMResponseValidationError)
            if val_cause is not None:
                v_details = getattr(val_cause, "details", {})
                v_cat = getattr(val_cause, "category", None) or (v_details.get("category") if isinstance(v_details, dict) else "validation_error")
                v_schema = v_details.get("schema", "unknown") if isinstance(v_details, dict) else "unknown"
                v_paths = v_details.get("field_paths", []) if isinstance(v_details, dict) else []
                logger.error(
                    "Analysis %s evidence stage validation failed: schema=%s, category=%s, field_paths=%s",
                    analysis_id,
                    v_schema,
                    v_cat,
                    v_paths,
                )
            else:
                logger.error("Analysis %s evidence orchestration pipeline failure", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Evidence orchestration pipeline failure encountered during analysis.",
            ) from e

        except ReasoningError as e:
            # 1. Check for timeout in cause chain or reasoning-level timeout
            timeout_cause = _find_cause_instance(e, (LLMTimeoutError, AnalysisTimeoutError)) or (e if _is_timeout_error(e) else None)
            if timeout_cause is not None:
                elapsed = time.monotonic() - start_time
                remaining = max(0.0, effective_deadline - time.monotonic())
                substage = getattr(e, "stage", None) or "boardroom"
                details = getattr(timeout_cause, "details", None) or {}
                timeout_src = details.get("timeout_source", "unknown")
                attempts = details.get("attempt")
                logger.error(
                    "Analysis %s reasoning stage timed out: substage=%s, timeout_type=%s, timeout_source=%s, attempts=%s, elapsed=%.2fs, remaining_budget=%.2fs",
                    analysis_id,
                    substage,
                    type(timeout_cause).__name__,
                    timeout_src,
                    attempts,
                    elapsed,
                    remaining,
                )
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Decision analysis timed out while evaluating the inquiry.",
                ) from e

            # 2. Check for LLM authentication failure in cause chain
            if _find_cause_instance(e, LLMAuthenticationError):
                logger.error("Analysis %s reasoning stage failed with LLM authentication error", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Decision intelligence service unavailable: AI provider authentication failed or credentials not configured.",
                ) from e

            # 3. Check for LLM rate limit in cause chain
            if _find_cause_instance(e, LLMRateLimitError):
                logger.warning("Analysis %s reasoning stage rate limited by LLM provider", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Decision intelligence request rate limit or quota exceeded. Please try again shortly.",
                ) from e

            # 4. Check for LLM response schema validation failure in cause chain
            val_cause = _find_cause_instance(e, LLMResponseValidationError)
            if val_cause:
                val_details = getattr(val_cause, "details", {})
                v_schema = val_details.get("schema", "unknown") if isinstance(val_details, dict) else "unknown"
                v_cat = val_details.get("category", "unknown") if isinstance(val_details, dict) else "unknown"
                v_paths = val_details.get("field_paths", []) if isinstance(val_details, dict) else []
                v_types = val_details.get("error_types", []) if isinstance(val_details, dict) else []
                logger.error(
                    "Analysis %s reasoning stage failed LLM response schema validation: schema=%s, category=%s, error_types=%s, field_paths=%s",
                    analysis_id,
                    v_schema,
                    v_cat,
                    v_types,
                    v_paths,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Decision intelligence engine returned an unparseable response structure.",
                ) from e

            # 5. Check for upstream LLM provider error or generic LLM error in cause chain
            if _find_cause_instance(e, (LLMProviderError, LLMError)):
                logger.error("Analysis %s reasoning stage failed due to upstream LLM provider error", analysis_id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Upstream decision intelligence provider error encountered.",
                ) from e

            # 6. Specific reasoning errors: validation or prompt construction
            val_err = _find_cause_instance(e, ReasoningValidationError)
            if val_err:
                stage = getattr(e, "stage", None) or "reasoning"
                diag = _sanitize_reasoning_validation_diagnostic(val_err, stage)
                logger.error("Analysis %s reasoning validation failed: %s", analysis_id, diag)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Reasoning validation failed during boardroom deliberation.",
                ) from e

            prompt_err = _find_cause_instance(e, ReasoningPromptError)
            if prompt_err:
                stage = getattr(e, "stage", None) or "reasoning"
                prompt_loc = getattr(prompt_err, "details", {}).get("location", "prompt_builder")
                logger.error(
                    "Analysis %s reasoning prompt construction failed: type=ReasoningPromptError stage=%s location=%s",
                    analysis_id,
                    stage,
                    prompt_loc,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Reasoning prompt construction failed during boardroom deliberation.",
                ) from e

            # 7. Generic ReasoningServiceError or unclassified reasoning failure
            logger.error("Analysis %s reasoning deliberation pipeline failure: %s", analysis_id, type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Decision reasoning pipeline failure encountered during analysis.",
            ) from e

        except HTTPException:
            # Re-raise already formed HTTPExceptions
            raise

        except Exception as e:
            tb_str = "".join(traceback.format_tb(e.__traceback__)) if e.__traceback__ else ""
            logger.error(
                "Analysis %s encountered unexpected failure of type %s:\n%s",
                analysis_id,
                type(e).__name__,
                tb_str,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred during decision analysis.",
            ) from e


def get_llm_client() -> LLMClient:
    """FastAPI dependency provider for LLMClient."""
    return AnalysisService.get_default_client()


def get_question_understanding_engine(
    llm_client: LLMClient = Depends(get_llm_client),
) -> QuestionUnderstandingEngine:
    """FastAPI dependency provider for QuestionUnderstandingEngine."""
    client = None if isinstance(llm_client, DependsParam) else llm_client
    return QuestionUnderstandingEngine(llm_client=client or get_llm_client())


def get_search_provider() -> SearchProvider:
    """FastAPI dependency provider for SearchProvider (Brave in production)."""
    from app.main import app

    if get_search_provider in app.dependency_overrides:
        return app.dependency_overrides[get_search_provider]()
    return BraveSearchProvider(api_key=settings.BRAVE_SEARCH_API_KEY)


def get_evidence_service(
    llm_client: LLMClient = Depends(get_llm_client),
    search_provider: SearchProvider = Depends(get_search_provider),
) -> EvidenceService:
    """FastAPI dependency provider for EvidenceService."""
    client = None if isinstance(llm_client, DependsParam) else llm_client
    provider = None if isinstance(search_provider, DependsParam) else search_provider
    return EvidenceService.create_default(
        llm_client=client or get_llm_client(),
        search_provider=provider or get_search_provider(),
    )


def get_reasoning_service(
    llm_client: LLMClient = Depends(get_llm_client),
) -> ReasoningService:
    """FastAPI dependency provider for ReasoningService."""
    client = None if isinstance(llm_client, DependsParam) else llm_client
    return ReasoningService.create_default(
        llm_client=client or get_llm_client(),
    )


def get_recommendation_service(
    llm_client: LLMClient = Depends(get_llm_client),
) -> RecommendationService:
    """FastAPI dependency provider for RecommendationService."""
    client = None if isinstance(llm_client, DependsParam) else llm_client
    return RecommendationService.create_default(
        llm_client=client or get_llm_client(),
    )


def get_analysis_service(
    engine: QuestionUnderstandingEngine = Depends(get_question_understanding_engine),
    evidence_service: EvidenceService = Depends(get_evidence_service),
    reasoning_service: ReasoningService = Depends(get_reasoning_service),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> AnalysisService:
    """FastAPI dependency provider for AnalysisService."""
    if (
        not isinstance(engine, DependsParam)
        and not isinstance(evidence_service, DependsParam)
        and not isinstance(reasoning_service, DependsParam)
        and not isinstance(recommendation_service, DependsParam)
    ):
        return AnalysisService(
            engine=engine,
            evidence_service=evidence_service,
            reasoning_service=reasoning_service,
            recommendation_service=recommendation_service,
        )

    # When called directly outside FastAPI (e.g. background job worker)
    try:
        from app.main import app

        if get_analysis_service in app.dependency_overrides:
            override = app.dependency_overrides[get_analysis_service]
            return override() if callable(override) else override
    except Exception:
        pass

    return AnalysisService(
        engine=None if isinstance(engine, DependsParam) else engine,
        evidence_service=None if isinstance(evidence_service, DependsParam) else evidence_service,
        reasoning_service=None if isinstance(reasoning_service, DependsParam) else reasoning_service,
        recommendation_service=None if isinstance(recommendation_service, DependsParam) else recommendation_service,
    )

