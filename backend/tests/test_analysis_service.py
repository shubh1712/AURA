"""Unit and integration tests for AnalysisService and error handling."""

import uuid
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.engines.question_understanding import QuestionUnderstandingEngine
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.mock_data import get_default_decision_model


def test_analysis_service_analyze_direct() -> None:
    """Unit test: Verify AnalysisService.analyze processes request and outputs expected contract."""
    service = AnalysisService()
    request = AnalysisRequest(
        question="Should we adopt Rust for core performance modules?",
        context={"team_size": 10, "current_language": "Python"},
        constraints=["Preserve existing APIs", "Deliver within 3 months"],
    )

    response = service.analyze(request)

    assert isinstance(response, AnalysisResponse)
    assert response.question == "Should we adopt Rust for core performance modules?"
    assert response.status == "completed"
    assert response.decision_model is not None
    assert isinstance(response.decision_model, DecisionModel)
    assert "completed successfully" in response.message

    # Verify that analysis_id is a valid UUID4
    parsed_uuid = uuid.UUID(response.analysis_id, version=4)
    assert str(parsed_uuid) == response.analysis_id


def test_analysis_service_generates_unique_ids() -> None:
    """Unit test: Ensure consecutive invocations generate unique analysis UUIDs."""
    service = AnalysisService()
    req = AnalysisRequest(question="Test question for unique ID validation")

    res1 = service.analyze(req)
    res2 = service.analyze(req)

    assert res1.analysis_id != res2.analysis_id


def test_get_analysis_service_provider() -> None:
    """Unit test: Verify dependency injection provider returns AnalysisService instance."""
    provider_instance = get_analysis_service()
    assert isinstance(provider_instance, AnalysisService)


def test_analysis_service_llm_auth_error_raises_503() -> None:
    """Verifies that an LLMAuthenticationError raises 503 Service Unavailable."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMAuthenticationError("Secret API key invalid: AIzaSyD-fake-key"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we hire more engineers?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 503
    # Critical security rule: never leak the key in the detail
    assert "AIzaSyD-fake-key" not in exc_info.value.detail
    assert "authentication failed or credentials not configured" in exc_info.value.detail


def test_analysis_service_rate_limit_raises_429() -> None:
    """Verifies that an LLMRateLimitError raises 429 Too Many Requests."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMRateLimitError("Quota exceeded for quota metric"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we launch today?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 429
    assert "rate limit or quota exceeded" in exc_info.value.detail


def test_analysis_service_timeout_raises_504() -> None:
    """Verifies that an LLMTimeoutError raises 504 Gateway Timeout."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMTimeoutError("Request timed out after 30s"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we refactor the monolith?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail


def test_analysis_service_response_validation_error_raises_502() -> None:
    """Verifies that an LLMResponseValidationError raises 502 Bad Gateway."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMResponseValidationError("Missing required objectives"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we cut pricing?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 502
    assert "unparseable response structure" in exc_info.value.detail


def test_analysis_service_unexpected_error_raises_500() -> None:
    """Verifies that an unhandled general exception raises 500 Internal Server Error."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(RuntimeError("Unexpected memory corruption"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we launch?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 500
    assert "unexpected internal error" in exc_info.value.detail


def test_route_integration_error_handling(client: TestClient) -> None:
    """Integration test: Verify route returns proper HTTP status codes for service failures."""
    class FailingAnalysisService(AnalysisService):
        def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
            raise HTTPException(
                status_code=503,
                detail="Decision intelligence service unavailable: AI provider authentication failed or credentials not configured.",
            )

    app.dependency_overrides[get_analysis_service] = lambda: FailingAnalysisService()
    try:
        response = client.post("/api/analyze", json={"question": "Test question failing with 503"})
        assert response.status_code == 503
        data = response.json()
        assert "authentication failed" in data["detail"]
    finally:
        app.dependency_overrides.clear()
