"""AURA Analysis Service.

Coordinates decision analysis intake, deconstruction, evidence retrieval,
and deterministic evaluation. All cognitive processing, language model interaction,
search retrieval, and provenance verification are orchestrated here, keeping API
controllers thin and free of model dependencies.
"""

import logging
import time
import uuid
from typing import Callable, Optional
from fastapi import Depends, HTTPException, status

from app.config import settings
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
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
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class AnalysisTimeoutError(Exception):
    """Raised when an end-to-end decision analysis exceeds its shared wall-clock deadline."""
    pass


def _find_cause_instance(exc: BaseException, target_type: type) -> Optional[BaseException]:
    """Traverses __cause__ and __context__ to find an instance of target_type."""
    current: Optional[BaseException] = exc
    visited = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, target_type):
            return current
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return None


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
        import os
        from app.services.llm.gemini import GeminiLLMClient

        api_key = (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")).strip()
        return GeminiLLMClient(api_key=api_key)

    def __init__(
        self,
        engine: Optional[QuestionUnderstandingEngine] = None,
        evidence_service: Optional[EvidenceService] = None,
        llm_client: Optional[LLMClient] = None,
        search_provider: Optional[SearchProvider] = None,
        analysis_timeout_seconds: Optional[float] = None,
    ) -> None:
        """Initializes AnalysisService with engine and evidence_service.

        Args:
            engine: Optional pre-configured QuestionUnderstandingEngine.
            evidence_service: Optional pre-configured EvidenceService.
            llm_client: Optional pre-configured LLMClient.
            search_provider: Optional pre-configured SearchProvider.
            analysis_timeout_seconds: Optional overall wall-clock analysis deadline budget in seconds.
        """
        if engine is not None:
            self.engine = engine
        elif llm_client is not None:
            self.engine = QuestionUnderstandingEngine(llm_client=llm_client)
        else:
            self.engine = self._build_default_engine()

        if evidence_service is not None:
            self.evidence_service = evidence_service
        else:
            effective_llm = llm_client or getattr(self.engine, "llm_client", None)
            self.evidence_service = self._build_default_evidence_service(
                llm_client=effective_llm,
                search_provider=search_provider,
            )

        self.analysis_timeout_seconds: float = (
            analysis_timeout_seconds
            if analysis_timeout_seconds is not None
            else getattr(settings, "ANALYSIS_TIMEOUT_SECONDS", 120.0)
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

    def analyze(
        self,
        request: AnalysisRequest,
        deadline_monotonic: Optional[float] = None,
    ) -> AnalysisResponse:
        """Executes decision deconstruction, evidence gathering, provenance auditing, and complexity scoring.

        Args:
            request: Validated AnalysisRequest payload.
            deadline_monotonic: Optional absolute monotonic deadline for the entire analysis.

        Returns:
            AnalysisResponse containing generated analysis_id, status="completed",
            decision_model, and evidence_package.

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
            try:
                decision_model = self.engine.deconstruct(
                    question=request.question,
                    context=request.context,
                    constraints=request.constraints,
                    deadline_monotonic=effective_deadline,
                )
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

            # 3. Assemble validated response
            return AnalysisResponse(
                analysis_id=analysis_id,
                status="completed",
                decision_model=decision_model,
                evidence_package=evidence_package,
                question=request.question,
                message="Decision deconstruction and evidence gathering completed successfully.",
            )

        except (LLMTimeoutError, SearchTimeoutError, AnalysisTimeoutError) as e:
            logger.error("Analysis %s timed out during evaluation", analysis_id)
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
            if _find_cause_instance(e, (SearchTimeoutError, LLMTimeoutError, AnalysisTimeoutError)):
                logger.error("Analysis %s evidence stage timed out", analysis_id)
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

            logger.error("Analysis %s evidence orchestration pipeline failure", analysis_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Evidence orchestration pipeline failure encountered during analysis.",
            ) from e

        except HTTPException:
            # Re-raise already formed HTTPExceptions
            raise

        except Exception as e:
            logger.error(
                "Analysis %s encountered unexpected failure of type %s",
                analysis_id,
                type(e).__name__,
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
    return QuestionUnderstandingEngine(llm_client=llm_client)


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
    return EvidenceService.create_default(
        llm_client=llm_client,
        search_provider=search_provider,
    )


def get_analysis_service(
    engine: QuestionUnderstandingEngine = Depends(get_question_understanding_engine),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> AnalysisService:
    """FastAPI dependency provider for AnalysisService."""
    return AnalysisService(
        engine=engine,
        evidence_service=evidence_service,
    )
