import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis_service import AnalysisService, get_analysis_service


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
    assert response.status == "pending"
    assert "Day 1 Stub" in response.message

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


def test_route_with_dependency_injection_override(client: TestClient) -> None:
    """Integration test: Verify FastAPI dependency injection allows clean service mocking."""
    class MockAnalysisService(AnalysisService):
        def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
            return AnalysisResponse(
                analysis_id="mocked-test-id-0000",
                status="mocked",
                question=request.question,
                message="Mocked service response for DI verification.",
            )

    # Apply dependency override
    app.dependency_overrides[get_analysis_service] = lambda: MockAnalysisService()

    try:
        response = client.post(
            "/api/analyze",
            json={"question": "Test question with mocked service dependency"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_id"] == "mocked-test-id-0000"
        assert data["status"] == "mocked"
        assert data["message"] == "Mocked service response for DI verification."
    finally:
        # Clean up dependency override
        app.dependency_overrides.clear()
