"""Unit and integration tests for AnalysisService and error handling."""

import uuid
from fastapi import HTTPException
from fastapi.params import Depends as DependsParam
from fastapi.testclient import TestClient
import pytest

from app.engines.question_understanding import QuestionUnderstandingEngine
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.services.evidence import EvidenceService
from app.services.reasoning import ReasoningService
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
    """Unit test: Verify dependency injection provider returns AnalysisService instance with real subcomponents."""
    provider_instance = get_analysis_service()
    assert isinstance(provider_instance, AnalysisService)
    assert not isinstance(provider_instance.engine, DependsParam)
    assert isinstance(provider_instance.engine, QuestionUnderstandingEngine)
    assert not isinstance(provider_instance.evidence_service, DependsParam)
    assert isinstance(provider_instance.evidence_service, EvidenceService)
    assert not isinstance(provider_instance.reasoning_service, DependsParam)
    assert isinstance(provider_instance.reasoning_service, ReasoningService)


def test_analysis_service_llm_auth_error_raises_503(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an LLMAuthenticationError raises 503 Service Unavailable and never leaks credentials in detail or logs."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMAuthenticationError("Secret API key invalid: AIzaSyD-fake-key"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we hire more engineers?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 503
    # Critical security rule: never leak the key in the detail or logs
    assert "AIzaSyD-fake-key" not in exc_info.value.detail
    assert "AIzaSyD-fake-key" not in caplog.text
    assert "authentication failed or credentials not configured" in exc_info.value.detail


def test_analysis_service_rate_limit_raises_429(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an LLMRateLimitError raises 429 Too Many Requests."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMRateLimitError("Quota exceeded for quota metric: SECRET_QUOTA_123"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we launch today?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 429
    assert "rate limit or quota exceeded" in exc_info.value.detail
    assert "SECRET_QUOTA_123" not in exc_info.value.detail
    assert "SECRET_QUOTA_123" not in caplog.text


def test_analysis_service_timeout_raises_504(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an LLMTimeoutError raises 504 Gateway Timeout."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMTimeoutError("Request timed out after 30s: SECRET_TIMEOUT_INFO"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we refactor the monolith?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail
    assert "SECRET_TIMEOUT_INFO" not in exc_info.value.detail
    assert "SECRET_TIMEOUT_INFO" not in caplog.text


def test_analysis_service_response_validation_error_raises_502(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an LLMResponseValidationError raises 502 Bad Gateway."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMResponseValidationError("Missing required objectives: SECRET_VALIDATION_TRACE"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we cut pricing?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 502
    assert "unparseable response structure" in exc_info.value.detail
    assert "SECRET_VALIDATION_TRACE" not in exc_info.value.detail
    assert "SECRET_VALIDATION_TRACE" not in caplog.text


def test_analysis_service_unexpected_error_raises_500(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an unhandled general exception raises 500 Internal Server Error."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(RuntimeError("Unexpected memory corruption: SECRET_INTERNAL_DUMP"))
    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    service = AnalysisService(engine=engine)

    req = AnalysisRequest(question="Should we launch?")
    with pytest.raises(HTTPException) as exc_info:
        service.analyze(req)

    assert exc_info.value.status_code == 500
    assert "unexpected internal error" in exc_info.value.detail
    assert "SECRET_INTERNAL_DUMP" not in exc_info.value.detail
    assert "SECRET_INTERNAL_DUMP" not in caplog.text


# ------------------------------------------------------------------------------
# Security Tests: Secret Marker Redaction in Logs and HTTP Detail
# ------------------------------------------------------------------------------

SECRET_MARKER = "SUPER_SECRET_PROVIDER_MARKER_123"


def test_security_llm_provider_error_redaction(caplog: pytest.LogCaptureFixture) -> None:
    """Proves SUPER_SECRET_PROVIDER_MARKER_123 in LLMProviderError never appears in logs or HTTP detail."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(LLMProviderError(f"503 Service Unavailable: upstream payload {SECRET_MARKER}"))
    service = AnalysisService(engine=QuestionUnderstandingEngine(llm_client=mock_llm))

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we expand?"))

    assert exc_info.value.status_code == 502
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_info.value.detail


def test_security_search_errors_redaction(caplog: pytest.LogCaptureFixture) -> None:
    """Proves SUPER_SECRET_PROVIDER_MARKER_123 in SearchProvider errors never appears in logs or HTTP detail."""
    from app.services.evidence import (
        EvidenceService,
        EvidenceServiceError,
        SearchAuthenticationError,
        SearchRateLimitError,
        SearchTimeoutError,
        SearchNetworkError,
        SearchProviderError,
    )
    from app.services.evidence.search_provider import FakeSearchProvider
    from app.services.llm.client import FakeLLMClient

    # 1. Search Auth -> 503
    class SecretAuthSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> list:
            raise SearchAuthenticationError(f"Bad key: {SECRET_MARKER}")

    fake_llm = FakeLLMClient()
    svc_auth = AnalysisService(
        llm_client=fake_llm,
        evidence_service=EvidenceService.create_default(fake_llm, SecretAuthSearchProvider()),
    )
    with pytest.raises(HTTPException) as exc_auth:
        svc_auth.analyze(AnalysisRequest(question="Test question?"))
    assert exc_auth.value.status_code == 503
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_auth.value.detail

    caplog.clear()

    # 2. Search Rate Limit -> 429
    class SecretRateLimitSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> list:
            raise SearchRateLimitError(f"Rate limited: {SECRET_MARKER}")

    svc_rate = AnalysisService(
        llm_client=fake_llm,
        evidence_service=EvidenceService.create_default(fake_llm, SecretRateLimitSearchProvider()),
    )
    with pytest.raises(HTTPException) as exc_rate:
        svc_rate.analyze(AnalysisRequest(question="Test question?"))
    assert exc_rate.value.status_code == 429
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_rate.value.detail

    caplog.clear()

    # 3. Search Timeout -> 504
    class SecretTimeoutSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> list:
            raise SearchTimeoutError(f"Timed out: {SECRET_MARKER}")

    svc_timeout = AnalysisService(
        llm_client=fake_llm,
        evidence_service=EvidenceService.create_default(fake_llm, SecretTimeoutSearchProvider()),
    )
    with pytest.raises(HTTPException) as exc_timeout:
        svc_timeout.analyze(AnalysisRequest(question="Test question?"))
    assert exc_timeout.value.status_code == 504
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_timeout.value.detail

    caplog.clear()

    # 4. Search Network / Response / Provider -> 502
    class SecretNetworkSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> list:
            raise SearchNetworkError(f"Connection failed: {SECRET_MARKER}")

    svc_net = AnalysisService(
        llm_client=fake_llm,
        evidence_service=EvidenceService.create_default(fake_llm, SecretNetworkSearchProvider()),
    )
    with pytest.raises(HTTPException) as exc_net:
        svc_net.analyze(AnalysisRequest(question="Test question?"))
    assert exc_net.value.status_code == 502
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_net.value.detail

    caplog.clear()

    # 5. Wrapped EvidenceServiceError -> 502
    class SecretGenericEvidenceService(EvidenceService):
        def build_evidence_package(self, decision_model: DecisionModel) -> EvidencePackage:
            raise EvidenceServiceError(f"Internal crash with sensitive dump: {SECRET_MARKER}")

    svc_ev = AnalysisService(
        llm_client=fake_llm,
        evidence_service=SecretGenericEvidenceService(None, None, None, None, None),  # type: ignore
    )
    with pytest.raises(HTTPException) as exc_ev:
        svc_ev.analyze(AnalysisRequest(question="Test question?"))
    assert exc_ev.value.status_code == 502
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_ev.value.detail


def test_security_generic_unexpected_error_redaction(caplog: pytest.LogCaptureFixture) -> None:
    """Proves SUPER_SECRET_PROVIDER_MARKER_123 in unexpected general exceptions never appears in logs or detail."""
    mock_llm = MockLLMClient()
    mock_llm.register_error(RuntimeError(f"Unexpected low-level failure: {SECRET_MARKER}"))
    service = AnalysisService(engine=QuestionUnderstandingEngine(llm_client=mock_llm))

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Test question?"))

    assert exc_info.value.status_code == 500
    assert SECRET_MARKER not in caplog.text
    assert SECRET_MARKER not in exc_info.value.detail


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


def test_analysis_service_evidence_timeout_structured_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that an EvidenceServiceError wrapping LLMTimeoutError logs structured substage, attempts, and budget diagnostics."""
    from unittest.mock import MagicMock
    import logging
    from app.services.evidence import EvidenceServiceError

    mock_engine = MagicMock()
    mock_model = MagicMock()
    mock_engine.deconstruct.return_value = mock_model

    mock_evidence = MagicMock()
    llm_err = LLMTimeoutError(
        "Gemini API request timed out after 60.0s.",
        details={"timeout_source": "operation", "attempt": 2, "timeout": 60.0},
    )
    mock_evidence.build_evidence_package.side_effect = EvidenceServiceError(
        "Evidence orchestration failed at stage 'mapping': Gemini API request timed out",
        stage="mapping",
    )
    mock_evidence.build_evidence_package.side_effect.__cause__ = llm_err

    service = AnalysisService(
        engine=mock_engine,
        evidence_service=mock_evidence,
        analysis_timeout_seconds=180.0,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            service.analyze(AnalysisRequest(question="Should we reduce pricing?"))

    assert exc_info.value.status_code == 504
    assert "Decision analysis timed out" in exc_info.value.detail
    log_text = caplog.text
    assert "evidence stage timed out" in log_text
    assert "substage=mapping" in log_text
    assert "timeout_type=LLMTimeoutError" in log_text
    assert "timeout_source=operation" in log_text
    assert "attempts=2" in log_text
    assert "elapsed=" in log_text
    assert "remaining_budget=" in log_text


def test_analysis_service_direct_timeout_structured_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that direct LLMTimeoutError logs structured timeout_type, timeout_source, and budget diagnostics."""
    from unittest.mock import MagicMock
    import logging

    mock_engine = MagicMock()
    mock_engine.deconstruct.side_effect = LLMTimeoutError(
        "Gemini API request timed out after 60.0s.",
        details={"timeout_source": "operation", "attempt": 1, "timeout": 60.0},
    )

    service = AnalysisService(
        engine=mock_engine,
        analysis_timeout_seconds=120.0,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            service.analyze(AnalysisRequest(question="Should we reduce pricing?"))

    assert exc_info.value.status_code == 504
    log_text = caplog.text
    assert "timed out during evaluation" in log_text
    assert "timeout_type=LLMTimeoutError" in log_text
    assert "timeout_source=operation" in log_text
    assert "attempts=1" in log_text
    assert "elapsed=" in log_text
    assert "remaining_budget=" in log_text


def test_evidence_service_substage_failure_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that EvidenceService logs substage failures with elapsed time and exception type."""
    from unittest.mock import MagicMock
    import logging
    from app.services.evidence.service import EvidenceService, EvidenceServiceError

    mock_req_engine = MagicMock()
    mock_retriever = MagicMock()
    mock_normalizer = MagicMock()
    mock_mapper = MagicMock()
    mock_gap_detector = MagicMock()

    mock_req_engine.generate_requirements.side_effect = LLMTimeoutError(
        "Gemini API request timed out after 60.0s.",
        details={"timeout_source": "operation", "attempt": 2},
    )

    ev_service = EvidenceService(
        requirement_engine=mock_req_engine,
        retriever=mock_retriever,
        normalizer=mock_normalizer,
        mapper=mock_mapper,
        gap_detector=mock_gap_detector,
    )

    mock_model = MagicMock()
    mock_model.id = "mod_test_substage"

    with caplog.at_level(logging.WARNING):
        with pytest.raises(EvidenceServiceError) as exc_info:
            ev_service.build_evidence_package(decision_model=mock_model)

    assert exc_info.value.stage == "requirement_generation"
    assert "requirement_generation" in caplog.text
    assert "LLMTimeoutError" in caplog.text
    assert "failed after" in caplog.text
