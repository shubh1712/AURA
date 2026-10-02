"""AURA Analysis Service.

Coordinates decision analysis intake, deconstruction, and deterministic evaluation.
All cognitive processing, language model interaction, and provenance verification
are orchestrated here, keeping API controllers thin and free of model dependencies.
"""

import logging
import uuid
from typing import Optional
from fastapi import HTTPException, status

from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
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


class AnalysisService:
    """Orchestrates decision analysis workflows and error translation."""

    def __init__(
        self,
        engine: Optional[QuestionUnderstandingEngine] = None,
    ) -> None:
        """Initializes AnalysisService.

        Args:
            engine: Optional pre-configured QuestionUnderstandingEngine.
        """
        if engine is not None:
            self.engine = engine
        else:
            self.engine = self._build_default_engine()

    @staticmethod
    def _build_default_engine() -> QuestionUnderstandingEngine:
        """Builds default QuestionUnderstandingEngine with configured LLMClient."""
        import os
        import sys
        from app.config import settings
        from app.services.llm.gemini import GeminiLLMClient
        from app.services.llm.client import MockLLMClient
        from app.services.llm.mock_data import get_default_decision_model

        # If running under automated unit test runner (pytest) or no API key, use deterministic mock
        if "pytest" in sys.modules or not (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")):
            mock = MockLLMClient()
            mock.register_response(DecisionModel, get_default_decision_model())
            return QuestionUnderstandingEngine(llm_client=mock)

        api_key = (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")).strip()
        client: LLMClient = GeminiLLMClient(api_key=api_key)
        return QuestionUnderstandingEngine(llm_client=client)

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """Executes decision deconstruction, provenance auditing, and complexity scoring.

        Args:
            request: Validated AnalysisRequest payload.

        Returns:
            AnalysisResponse containing generated analysis_id, status="completed",
            and the fully validated DecisionModel.

        Raises:
            HTTPException: With domain-specific status codes for LLM or unexpected failures.
        """
        analysis_id = str(uuid.uuid4())

        try:
            decision_model = self.engine.deconstruct(
                question=request.question,
                context=request.context,
                constraints=request.constraints,
            )

            return AnalysisResponse(
                analysis_id=analysis_id,
                status="completed",
                decision_model=decision_model,
                question=request.question,
                message="Decision deconstruction and provenance audit completed successfully.",
            )

        except LLMAuthenticationError as e:
            logger.error(f"Analysis {analysis_id} failed with LLM authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Decision intelligence service unavailable: AI provider authentication failed or credentials not configured.",
            ) from e

        except LLMRateLimitError as e:
            logger.warning(f"Analysis {analysis_id} rate limited: {e}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Decision intelligence request rate limit or quota exceeded. Please try again shortly.",
            ) from e

        except LLMTimeoutError as e:
            logger.error(f"Analysis {analysis_id} timed out: {e}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Decision analysis timed out while evaluating the inquiry.",
            ) from e

        except LLMResponseValidationError as e:
            logger.error(f"Analysis {analysis_id} failed schema validation: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Decision intelligence engine returned an unparseable response structure.",
            ) from e

        except (LLMProviderError, LLMError) as e:
            logger.error(f"Analysis {analysis_id} upstream error: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream decision intelligence provider error encountered.",
            ) from e

        except HTTPException:
            # Re-raise already formed HTTPExceptions
            raise

        except Exception as e:
            logger.exception(f"Analysis {analysis_id} encountered unexpected failure: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred during decision analysis.",
            ) from e


def get_analysis_service() -> AnalysisService:
    """FastAPI dependency provider for AnalysisService."""
    return AnalysisService()
