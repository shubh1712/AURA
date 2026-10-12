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
from app.schemas.scenario import ScenarioSet
from app.schemas.resilience import ResilienceReport
from app.engines.resilience import evaluate_resilience
from app.services.scenario import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioPromptError,
    ScenarioService,
    ScenarioServiceError,
    ScenarioValidationError,
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
                ScenarioEvaluationError,
                ScenarioServiceError,
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
        scenario_service: Optional[ScenarioService] = None,
        llm_client: Optional[LLMClient] = None,
        search_provider: Optional[SearchProvider] = None,
        analysis_timeout_seconds: Optional[float] = None,
        framer_operation_timeout_seconds: Optional[float] = None,
        boardroom_operation_timeout_seconds: Optional[float] = None,
        boardroom_http_timeout_seconds: Optional[float] = None,
        boardroom_min_retry_headroom_seconds: Optional[float] = None,
        recommendation_operation_timeout_seconds: Optional[float] = None,
        scenario_operation_timeout_seconds: Optional[float] = None,
    ) -> None:
        """Initializes AnalysisService with engine, evidence_service, reasoning_service, recommendation_service, and scenario_service.

        Args:
            engine: Optional pre-configured QuestionUnderstandingEngine.
            evidence_service: Optional pre-configured EvidenceService.
            reasoning_service: Optional pre-configured ReasoningService.
            recommendation_service: Optional pre-configured RecommendationService.
            scenario_service: Optional pre-configured ScenarioService.
            llm_client: Optional pre-configured LLMClient.
            search_provider: Optional pre-configured SearchProvider.
            analysis_timeout_seconds: Optional overall wall-clock analysis deadline budget in seconds.
            framer_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 1 Decision Framer.
            boardroom_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 3 AI Boardroom perspectives.
            boardroom_http_timeout_seconds: Optional opt-in HTTP request timeout for Stage 3 AI Boardroom perspectives.
            boardroom_min_retry_headroom_seconds: Optional minimum retry headroom for Stage 3 AI Boardroom perspectives.
            recommendation_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 4 Recommendation Engine.
            scenario_operation_timeout_seconds: Optional opt-in operation ceiling for Stage 5 Scenario Generator.
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

        raw_boardroom_http_to = boardroom_http_timeout_seconds
        if raw_boardroom_http_to is None:
            raw_boardroom_http_to = getattr(settings, "AURA_BOARDROOM_HTTP_TIMEOUT_SECONDS", 90.0)
            if raw_boardroom_http_to is None:
                env_val = os.environ.get("AURA_BOARDROOM_HTTP_TIMEOUT_SECONDS")
                if env_val is not None:
                    try:
                        raw_boardroom_http_to = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_BOARDROOM_HTTP_TIMEOUT_SECONDS value: {env_val}") from ve

        if raw_boardroom_http_to is not None:
            if float(raw_boardroom_http_to) <= 0.0:
                raise ValueError("boardroom_http_timeout_seconds must be strictly greater than 0.0")
            self.boardroom_http_timeout_seconds: float = float(raw_boardroom_http_to)
        else:
            self.boardroom_http_timeout_seconds = 90.0

        raw_headroom = boardroom_min_retry_headroom_seconds
        if raw_headroom is None:
            raw_headroom = getattr(settings, "AURA_BOARDROOM_MIN_RETRY_HEADROOM_SECONDS", 30.0)
            if raw_headroom is None:
                env_val = os.environ.get("AURA_BOARDROOM_MIN_RETRY_HEADROOM_SECONDS")
                if env_val is not None:
                    try:
                        raw_headroom = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_BOARDROOM_MIN_RETRY_HEADROOM_SECONDS value: {env_val}") from ve

        if raw_headroom is not None:
            if float(raw_headroom) < 0.0:
                raise ValueError("boardroom_min_retry_headroom_seconds must be non-negative")
            self.boardroom_min_retry_headroom_seconds: float = float(raw_headroom)
        else:
            self.boardroom_min_retry_headroom_seconds = 30.0

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

        raw_scenario_to = scenario_operation_timeout_seconds
        if raw_scenario_to is None:
            raw_scenario_to = getattr(settings, "AURA_SCENARIO_OPERATION_TIMEOUT_SECONDS", None)
            if raw_scenario_to is None:
                env_val = os.environ.get("AURA_SCENARIO_OPERATION_TIMEOUT_SECONDS")
                if env_val is not None:
                    try:
                        raw_scenario_to = float(env_val.strip())
                    except ValueError as ve:
                        raise ValueError(f"Invalid AURA_SCENARIO_OPERATION_TIMEOUT_SECONDS value: {env_val}") from ve

        if raw_scenario_to is not None:
            if raw_scenario_to <= 0.0:
                raise ValueError("scenario_operation_timeout_seconds must be strictly greater than 0.0")
            self.scenario_operation_timeout_seconds: Optional[float] = float(raw_scenario_to)
        else:
            self.scenario_operation_timeout_seconds = None

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
                boardroom_http_timeout_seconds=self.boardroom_http_timeout_seconds,
                boardroom_min_retry_headroom_seconds=self.boardroom_min_retry_headroom_seconds,
            )

        if recommendation_service is not None and not isinstance(recommendation_service, DependsParam):
            self.recommendation_service = recommendation_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.recommendation_service = self._build_default_recommendation_service(
                llm_client=effective_llm,
                recommendation_operation_timeout_seconds=self.recommendation_operation_timeout_seconds,
            )

        if scenario_service is not None and not isinstance(scenario_service, DependsParam):
            self.scenario_service = scenario_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.scenario_service = self._build_default_scenario_service(
                llm_client=effective_llm,
                scenario_operation_timeout_seconds=self.scenario_operation_timeout_seconds,
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
        boardroom_http_timeout_seconds: Optional[float] = None,
        boardroom_min_retry_headroom_seconds: Optional[float] = None,
    ) -> ReasoningService:
        """Builds default ReasoningService wired with provided or default LLMClient."""
        client = llm_client or cls.get_default_client()
        return ReasoningService.create_default(
            llm_client=client,
            boardroom_operation_timeout_seconds=boardroom_operation_timeout_seconds,
            boardroom_http_timeout_seconds=boardroom_http_timeout_seconds,
            boardroom_min_retry_headroom_seconds=boardroom_min_retry_headroom_seconds,
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

    @classmethod
    def _build_default_scenario_service(
        cls,
        llm_client: Optional[LLMClient] = None,
        scenario_operation_timeout_seconds: Optional[float] = None,
    ) -> ScenarioService:
        """Builds default ScenarioService wired with provided or default LLMClient."""
        client = llm_client or cls.get_default_client()
        return ScenarioService.create_default(
            llm_client=client,
            scenario_operation_timeout_seconds=scenario_operation_timeout_seconds,
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
        stage_timings: Dict[str, float] = {}

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

            t_s1_start = time.monotonic()
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
            t_s1_end = time.monotonic()
            stage_timings["stage1_decision_framer"] = t_s1_end - t_s1_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage1_decision_framer, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage1_decision_framer"],
                max(0.0, effective_deadline - t_s1_end),
            )

            if time.monotonic() >= effective_deadline:
                raise AnalysisTimeoutError("Analysis operation exceeded end-to-end deadline before evidence gathering.")

            # 2. Gather, normalize, map, and gap-analyze evidence
            if stage_callback:
                stage_callback("stage2_evidence_engine")

            t_s2_start = time.monotonic()
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
            t_s2_end = time.monotonic()
            stage_timings["stage2_evidence_engine"] = t_s2_end - t_s2_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage2_evidence_engine, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage2_evidence_engine"],
                max(0.0, effective_deadline - t_s2_end),
            )

            if time.monotonic() >= effective_deadline:
                raise AnalysisTimeoutError("Analysis operation exceeded end-to-end deadline before boardroom deliberation.")

            # 3. Deliberate across canonical boardroom perspectives and synthesize board
            if stage_callback:
                stage_callback("stage3_ai_boardroom")

            boardroom_op_to = (
                self.boardroom_operation_timeout_seconds
                if self.boardroom_operation_timeout_seconds is not None
                else 120.0
            )
            effective_boardroom_http_to = min(self.boardroom_http_timeout_seconds, boardroom_op_to)

            perspective_config = LLMConfig(
                operation_timeout_seconds=boardroom_op_to,
                timeout_seconds=effective_boardroom_http_to,
                max_retries=1,
                min_retry_headroom_seconds=self.boardroom_min_retry_headroom_seconds,
                stage="stage3_ai_boardroom_perspectives",
            )

            boardroom_kwargs: Dict[str, Any] = {
                "decision_model": decision_model,
                "evidence_package": evidence_package,
                "deadline_monotonic": effective_deadline,
                "perspective_config": perspective_config,
                "boardroom_operation_timeout_seconds": boardroom_op_to,
                "boardroom_http_timeout_seconds": self.boardroom_http_timeout_seconds,
                "boardroom_min_retry_headroom_seconds": self.boardroom_min_retry_headroom_seconds,
            }

            t_s3_start = time.monotonic()
            try:
                reasoning_board = self.reasoning_service.build_reasoning_board(**boardroom_kwargs)
            except TypeError:
                try:
                    reasoning_board = self.reasoning_service.build_reasoning_board(
                        decision_model=decision_model,
                        evidence_package=evidence_package,
                        deadline_monotonic=effective_deadline,
                    )
                except TypeError:
                    reasoning_board = self.reasoning_service.build_reasoning_board(
                        decision_model=decision_model,
                        evidence_package=evidence_package,
                    )
            t_s3_end = time.monotonic()
            stage_timings["stage3_ai_boardroom"] = t_s3_end - t_s3_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage3_ai_boardroom, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage3_ai_boardroom"],
                max(0.0, effective_deadline - t_s3_end),
            )

            # 4. Generate grounded recommendation & action plan (Recommendation Engine)
            if stage_callback:
                stage_callback("stage4_recommendation")

            recommendation: Optional[DecisionRecommendation] = None
            recommendation_status: Optional[str] = None
            recommendation_error: Optional[str] = None

            t_s4_start = time.monotonic()
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
            t_s4_end = time.monotonic()
            stage_timings["stage4_recommendation"] = t_s4_end - t_s4_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage4_recommendation, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage4_recommendation"],
                max(0.0, effective_deadline - t_s4_end),
            )

            # 5. Generate future scenarios & milestones (Scenario Engine)
            if stage_callback:
                stage_callback("stage5_scenarios")

            scenarios: Optional[ScenarioSet] = None
            scenario_status: Optional[str] = None
            scenario_error: Optional[str] = None

            t_s5_start = time.monotonic()
            # Enforce dependency policy: Stage 5 requires authoritative recommendation from Stage 4
            if recommendation is None:
                logger.warning(
                    "Analysis %s Stage 5 scenario generation skipped: prerequisite Stage 4 recommendation was unavailable.",
                    analysis_id,
                )
                scenario_status = "unavailable"
                scenario_error = "Stage 5 scenario generation skipped: prerequisite Stage 4 recommendation was unavailable."
            elif time.monotonic() >= effective_deadline:
                logger.warning(
                    "Analysis %s exceeded end-to-end deadline before Stage 5 scenario generation.",
                    analysis_id,
                )
                scenario_status = "unavailable"
                scenario_error = "Stage 5 scenario generation skipped: global analysis deadline expired."
            else:
                scenario_config = None
                if self.scenario_operation_timeout_seconds is not None:
                    scenario_config = LLMConfig(
                        operation_timeout_seconds=self.scenario_operation_timeout_seconds,
                        timeout_seconds=min(45.0, self.scenario_operation_timeout_seconds),
                    )

                scen_kwargs: Dict[str, Any] = {
                    "decision_model": decision_model,
                    "evidence_package": evidence_package,
                    "reasoning_board": reasoning_board,
                    "recommendation": recommendation,
                    "deadline_monotonic": effective_deadline,
                }
                if scenario_config is not None:
                    scen_kwargs["scenario_config"] = scenario_config

                try:
                    try:
                        scenarios = self.scenario_service.generate_scenarios(**scen_kwargs)
                    except TypeError as te:
                        if "unexpected keyword argument 'scenario_config'" in str(te):
                            scen_kwargs.pop("scenario_config", None)
                            scenarios = self.scenario_service.generate_scenarios(**scen_kwargs)
                        else:
                            raise
                    scenario_status = "completed"
                except Exception as exc:
                    # Explicit Product Failure Policy:
                    # If Stages 1-4 succeed but Stage 5 fails, preserve completed upstream artifacts
                    # and expose scenarios as unavailable.
                    logger.warning(
                        "Analysis %s Stage 5 scenario generation failed; preserving upstream outputs. Error: %s: %s",
                        analysis_id,
                        type(exc).__name__,
                        str(exc),
                    )
                    scenario_status = "unavailable"
                    if _is_timeout_error(exc):
                        scenario_error = f"Scenario generation timed out: {getattr(exc, 'message', str(exc))}"
                    else:
                        scenario_error = f"Scenario generation unavailable: {getattr(exc, 'message', str(exc))}"
            t_s5_end = time.monotonic()
            stage_timings["stage5_scenarios"] = t_s5_end - t_s5_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage5_scenarios, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage5_scenarios"],
                max(0.0, effective_deadline - t_s5_end),
            )

            # 6. Evaluate decision resilience (Deterministic Resilience Engine)
            if stage_callback:
                stage_callback("stage6_resilience")

            resilience: Optional[ResilienceReport] = None
            resilience_status: Optional[str] = None
            resilience_error: Optional[str] = None

            t_s6_start = time.monotonic()
            # Enforce dependency policy: Stage 6 requires authoritative ScenarioSet and all inputs
            if scenarios is None or recommendation is None:
                logger.warning(
                    "Analysis %s Stage 6 resilience evaluation skipped: prerequisite upstream artifacts unavailable (scenarios=%s, recommendation=%s).",
                    analysis_id,
                    scenarios is not None,
                    recommendation is not None,
                )
                resilience_status = "unavailable"
                if scenarios is None and recommendation is not None:
                    resilience_error = "Stage 6 resilience evaluation skipped: prerequisite Stage 5 scenarios were unavailable."
                elif recommendation is None:
                    resilience_error = "Stage 6 resilience evaluation skipped: prerequisite Stage 4 recommendation was unavailable."
                else:
                    resilience_error = "Stage 6 resilience evaluation skipped: prerequisite upstream artifacts were unavailable."
            elif time.monotonic() >= effective_deadline:
                logger.warning(
                    "Analysis %s exceeded end-to-end deadline before Stage 6 resilience evaluation.",
                    analysis_id,
                )
                resilience_status = "unavailable"
                resilience_error = "Stage 6 resilience evaluation skipped: global analysis deadline expired."
            else:
                try:
                    resilience = evaluate_resilience(
                        decision_model=decision_model,
                        scenario_set=scenarios,
                        recommendation=recommendation,
                        evidence_package=evidence_package,
                        reasoning_board=reasoning_board,
                    )
                    resilience_status = "completed"
                except Exception as exc:
                    # Explicit Product Failure Policy:
                    # If Stages 1-5 succeed but Stage 6 fails, preserve completed upstream artifacts
                    # and expose resilience as unavailable with partial_success.
                    logger.warning(
                        "Analysis %s Stage 6 resilience evaluation failed; preserving upstream outputs. Error: %s: %s",
                        analysis_id,
                        type(exc).__name__,
                        str(exc),
                    )
                    resilience_status = "unavailable"
                    resilience_error = f"Resilience evaluation unavailable: {str(exc)}"
            t_s6_end = time.monotonic()
            stage_timings["stage6_resilience"] = t_s6_end - t_s6_start
            logger.info(
                "AURA Stage Metrics [%s]: stage=stage6_resilience, duration=%.3fs, remaining_parent_budget=%.3fs",
                analysis_id,
                stage_timings["stage6_resilience"],
                max(0.0, effective_deadline - t_s6_end),
            )

            # 7. Assemble validated response
            is_full_success = (
                recommendation is not None
                and scenarios is not None
                and resilience is not None
            )
            overall_status = "completed" if is_full_success else "partial_success"
            if is_full_success:
                message_text = "Decision deconstruction, evidence gathering, boardroom deliberation, recommendation, and scenario simulation completed successfully. Decision resilience evaluation completed successfully."
            elif scenarios is not None and resilience is None:
                message_text = f"Decision analysis completed with scenarios; resilience stage unavailable ({resilience_error})."
            elif recommendation is not None and scenarios is None:
                message_text = f"Decision analysis completed with recommendation; scenario stage unavailable ({scenario_error})."
            elif reasoning_board is not None:
                message_text = f"Decision analysis completed with Boardroom deliberation; recommendation stage unavailable ({recommendation_error})."
            else:
                message_text = "Decision analysis completed with partial success."

            total_analysis_duration = time.monotonic() - start_time
            self.last_stage_timings = dict(stage_timings)
            self.last_total_duration = total_analysis_duration
            logger.info(
                "AURA Pipeline Execution Summary [%s]: total=%.3fs, status=%s, "
                "s1_framer=%.3fs, s2_evidence=%.3fs, s3_boardroom=%.3fs, s4_rec=%.3fs, s5_scenarios=%.3fs, s6_resilience=%.3fs, "
                "remaining_parent_budget=%.3fs",
                analysis_id,
                total_analysis_duration,
                overall_status,
                stage_timings.get("stage1_decision_framer", 0.0),
                stage_timings.get("stage2_evidence_engine", 0.0),
                stage_timings.get("stage3_ai_boardroom", 0.0),
                stage_timings.get("stage4_recommendation", 0.0),
                stage_timings.get("stage5_scenarios", 0.0),
                stage_timings.get("stage6_resilience", 0.0),
                max(0.0, effective_deadline - time.monotonic()),
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
                scenarios=scenarios,
                scenario_status=scenario_status,
                scenario_error=scenario_error,
                resilience=resilience,
                resilience_status=resilience_status,
                resilience_error=resilience_error,
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


def get_scenario_service(
    llm_client: LLMClient = Depends(get_llm_client),
) -> ScenarioService:
    """FastAPI dependency provider for ScenarioService."""
    client = None if isinstance(llm_client, DependsParam) else llm_client
    return ScenarioService.create_default(
        llm_client=client or get_llm_client(),
    )


def get_analysis_service(
    engine: QuestionUnderstandingEngine = Depends(get_question_understanding_engine),
    evidence_service: EvidenceService = Depends(get_evidence_service),
    reasoning_service: ReasoningService = Depends(get_reasoning_service),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> AnalysisService:
    """FastAPI dependency provider for AnalysisService."""
    if (
        not isinstance(engine, DependsParam)
        and not isinstance(evidence_service, DependsParam)
        and not isinstance(reasoning_service, DependsParam)
        and not isinstance(recommendation_service, DependsParam)
        and not isinstance(scenario_service, DependsParam)
    ):
        return AnalysisService(
            engine=engine,
            evidence_service=evidence_service,
            reasoning_service=reasoning_service,
            recommendation_service=recommendation_service,
            scenario_service=scenario_service,
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
        scenario_service=None if isinstance(scenario_service, DependsParam) else scenario_service,
    )

