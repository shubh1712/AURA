"""Deterministic offline test suite for AURA's Vertex AI Gemini provider migration.

Validates:
1. Vertex/enterprise mode (enterprise=True) is selected.
2. Configured project is passed correctly to genai.Client.
3. Configured location is passed correctly to genai.Client.
4. API key is NEVER passed to the Vertex client.
5. Existing HttpOptions and SDK-level retry disabling (attempts=1, status_codes=[0]) are preserved.
6. AURA retry count semantics (AURA owns retries, bounded by max_retries) are preserved.
7. Existing operation deadline (operation_timeout_seconds) is preserved.
8. Existing parent analysis deadline (deadline_monotonic) propagation is preserved.
9. FastAPI dependency injection shares exactly one GeminiLLMClient across
   QuestionUnderstandingEngine, EvidenceRequirementEngine, and EvidenceMapper.
10. Fail-closed safety prevents real external Vertex AI or socket calls during normal test runs.
"""

import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings, settings
from app.services.analysis_service import (
    AnalysisService,
    get_analysis_service,
    get_evidence_service,
    get_llm_client,
    get_question_understanding_engine,
)
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMConfig,
    LLMProviderError,
    LLMTimeoutError,
)
from app.services.llm.gemini import GeminiLLMClient


class SampleStructuredOutput(BaseModel):
    summary: str
    confidence: float


# ------------------------------------------------------------------------------
# 1. Vertex Client Initialization & Parameter Routing
# ------------------------------------------------------------------------------

def test_vertex_enterprise_mode_and_config_parameters() -> None:
    """Proves that genai.Client is initialized with enterprise=True, project, location, and no api_key."""
    captured_kwargs: Dict[str, Any] = {}

    def mock_genai_init(*args: Any, **kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        mock_instance = MagicMock()
        mock_instance.interactions = MagicMock()
        return mock_instance

    with patch("google.genai.Client", side_effect=mock_genai_init):
        client = GeminiLLMClient(
            project="test-aura-project-101",
            location="asia-south1",
            api_key="legacy-key-that-must-be-ignored",
        )
        genai_client = client._get_genai_client()

    assert genai_client is not None
    # 1. enterprise=True is passed
    assert captured_kwargs.get("enterprise") is True
    # 2. project is passed correctly
    assert captured_kwargs.get("project") == "test-aura-project-101"
    # 3. location is passed correctly
    assert captured_kwargs.get("location") == "asia-south1"
    # 4. api_key is NOT passed to genai.Client
    assert "api_key" not in captured_kwargs or captured_kwargs.get("api_key") is None
    # 5. legacy vertexai flag is not passed (enterprise is preferred in 2.28+)
    assert "vertexai" not in captured_kwargs or captured_kwargs.get("vertexai") is None


def test_vertex_client_reads_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that GeminiLLMClient reads project and location from settings when omitted in init."""
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_PROJECT", "settings-project-999")
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_LOCATION", "europe-west1")

    captured_kwargs: Dict[str, Any] = {}

    def mock_genai_init(*args: Any, **kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        mock_instance = MagicMock()
        return mock_instance

    with patch("google.genai.Client", side_effect=mock_genai_init):
        client = GeminiLLMClient()
        client._get_genai_client()

    assert captured_kwargs.get("enterprise") is True
    assert captured_kwargs.get("project") == "settings-project-999"
    assert captured_kwargs.get("location") == "europe-west1"
    assert "api_key" not in captured_kwargs or captured_kwargs.get("api_key") is None


def test_vertex_client_defaults_location_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that GOOGLE_CLOUD_LOCATION defaults to global if unspecified."""
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_PROJECT", "settings-project-default")
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_LOCATION", "")
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    captured_kwargs: Dict[str, Any] = {}

    def mock_genai_init(*args: Any, **kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch("google.genai.Client", side_effect=mock_genai_init):
        client = GeminiLLMClient(location=None)
        client._get_genai_client()

    assert captured_kwargs.get("location") == "global"


def test_missing_project_raises_llm_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that invoking generate_structured without a configured project raises LLMAuthenticationError."""
    monkeypatch.setattr(settings, "GOOGLE_CLOUD_PROJECT", None)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)

    client = GeminiLLMClient(project="")

    with pytest.raises(LLMAuthenticationError) as exc_info:
        client._get_project()

    assert "Google Cloud project is not configured" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 2. Phase 14A Reliability & HttpOptions Preservation
# ------------------------------------------------------------------------------

def test_existing_http_options_retry_disabling_preserved() -> None:
    """Proves that HttpOptions disables SDK retries (attempts=1, status_codes=[0]) and injects http_client."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    custom_http_client = httpx.Client(transport=mock_transport)

    captured_kwargs: Dict[str, Any] = {}

    def mock_genai_init(*args: Any, **kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch("google.genai.Client", side_effect=mock_genai_init):
        client = GeminiLLMClient(
            project="test-proj",
            location="us-central1",
            http_client=custom_http_client,
        )
        client._get_genai_client()

    http_options = captured_kwargs.get("http_options")
    assert http_options is not None
    assert http_options.httpx_client is custom_http_client
    assert http_options.retry_options is not None
    assert http_options.retry_options.attempts == 1
    assert http_options.retry_options.http_status_codes == [0]


def test_aura_owns_retries_with_bounded_backoff() -> None:
    """Proves that AURA's retry loop owns retries (max_retries=2 -> 3 attempts total) on 503."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, json={"error": {"code": 503, "message": "Service Unavailable"}})

    mock_transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=mock_transport)
    sleeps = []

    client = GeminiLLMClient(
        project="test-proj",
        location="us-central1",
        http_client=http_client,
        sleep_fn=sleeps.append,
    )

    with pytest.raises(LLMProviderError):
        client.generate_structured(
            prompt="Analyze scenario",
            response_schema=SampleStructuredOutput,
            config=LLMConfig(max_retries=2, timeout_seconds=10.0, operation_timeout_seconds=30.0),
        )

    # 1 initial + 2 retries = 3 attempts
    assert call_count == 3
    # 2 backoff sleep delays
    assert len(sleeps) == 2


def test_operation_deadline_enforced_strictly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that operation_timeout_seconds is enforced across retries."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"output_text": '{"summary":"ok","confidence":1.0}'})

    mock_transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(
        project="test-proj",
        location="us-central1",
        http_client=http_client,
    )

    # Simulate elapsed time beyond operation timeout (60s)
    simulated_times = [100.0, 165.0]
    monkeypatch.setattr(time, "monotonic", lambda: simulated_times.pop(0) if simulated_times else 200.0)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Analyze scenario",
            response_schema=SampleStructuredOutput,
            config=LLMConfig(operation_timeout_seconds=60.0),
        )

    assert call_count == 0  # Aborted before sending request
    assert "Gemini API request timed out" in str(exc_info.value)


def test_remaining_budget_below_30s_clamps_http_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that a remaining operation budget below 30s clamps the per-request HTTP timeout.

    When remaining budget is below configured 30s (e.g. 28s remaining):
    timeout = min(30.0, 28.0) -> 28.0s.
    When remaining budget is above 30s (e.g. 58s remaining):
    timeout = min(30.0, 58.0) -> 30.0s.
    """
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": '{"summary":"ok","confidence":1.0}'}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(
        project="test-proj",
        location="global",
        http_client=http_client,
    )

    observed_timeouts: List[float] = []
    orig_genai = client._get_genai_client()

    def mock_create(**kwargs: Any) -> Any:
        observed_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = '{"summary":"ok","confidence":1.0}'
        return mock_resp

    monkeypatch.setattr(orig_genai.interactions, "create", mock_create)

    # Case 1: Remaining budget is 28.0s (below 30s) -> clamped to 28.0s
    # start_time = 100.0, deadline = 160.0 (operation_timeout_seconds=60.0)
    # when remaining is evaluated, current time = 132.0 -> remaining = 160.0 - 132.0 = 28.0s
    times_case1 = [100.0, 132.0, 133.0]
    monkeypatch.setattr(time, "monotonic", lambda: times_case1.pop(0) if times_case1 else 135.0)

    client.generate_structured(
        prompt="Test prompt",
        response_schema=SampleStructuredOutput,
    )
    assert len(observed_timeouts) == 1
    assert observed_timeouts[0] == pytest.approx(28.0, abs=0.01)

    # Case 2: Remaining budget is 58.0s (above 30s) -> capped at configured 30.0s
    # start_time = 200.0, deadline = 260.0
    # when remaining is evaluated, current time = 202.0 -> remaining = 260.0 - 202.0 = 58.0s
    times_case2 = [200.0, 202.0, 203.0]
    monkeypatch.setattr(time, "monotonic", lambda: times_case2.pop(0) if times_case2 else 205.0)

    client.generate_structured(
        prompt="Test prompt",
        response_schema=SampleStructuredOutput,
    )
    assert len(observed_timeouts) == 2
    assert observed_timeouts[1] == pytest.approx(30.0, abs=0.01)


def test_60s_operation_deadline_is_unchanged() -> None:
    """Proves that operation_timeout_seconds remains strictly 60.0s in DEFAULT_LLM_CONFIG."""
    from app.services.llm.client import DEFAULT_LLM_CONFIG
    assert DEFAULT_LLM_CONFIG.timeout_seconds == 30.0
    assert DEFAULT_LLM_CONFIG.operation_timeout_seconds == 60.0


def test_request_timeout_produces_llm_timeout_error_correctly() -> None:
    """Proves that request-level timeouts produce LLMTimeoutError correctly."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(
        project="test-proj",
        location="global",
        http_client=http_client,
    )

    mock_genai = client._get_genai_client()
    mock_genai.interactions.create = MagicMock(side_effect=httpx.TimeoutException("Client timeout"))

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Test prompt",
            response_schema=SampleStructuredOutput,
            config=LLMConfig(max_retries=0, timeout_seconds=45.0, operation_timeout_seconds=60.0),
        )

    assert "timed out" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 3. Phase 14C Deadline Propagation Preservation
# ------------------------------------------------------------------------------

def test_parent_analysis_deadline_propagation() -> None:
    """Proves that deadline_monotonic propagates and bounds the effective Gemini deadline."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": '{"summary":"ok","confidence":1.0}'}))
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(
        project="test-proj",
        location="us-central1",
        http_client=http_client,
    )

    # Expired deadline passed from parent analysis
    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Analyze scenario",
            response_schema=SampleStructuredOutput,
            deadline_monotonic=expired_deadline,
        )

    assert "timed out" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 4. FastAPI Dependency Injection: Exactly One Shared GeminiLLMClient
# ------------------------------------------------------------------------------

def test_fastapi_di_shares_single_gemini_client_per_analysis_request() -> None:
    """Proves that within a single request, exactly one GeminiLLMClient is shared across engines."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()

    observed_clients: Dict[str, Any] = {}

    @test_app.get("/test-di")
    def di_endpoint(
        service: AnalysisService = pytest.importorskip("fastapi").Depends(get_analysis_service),
    ) -> Dict[str, bool]:
        que_client = service.engine.llm_client
        req_client = service.evidence_service.requirement_engine.llm_client
        map_client = service.evidence_service.mapper.llm_client

        observed_clients["que_client"] = que_client
        observed_clients["req_client"] = req_client
        observed_clients["map_client"] = map_client

        return {
            "all_same": (que_client is req_client and req_client is map_client),
            "is_gemini": isinstance(que_client, GeminiLLMClient),
        }

    # Clean dependency overrides to test natural production wiring
    test_app.dependency_overrides.clear()
    with patch.object(AnalysisService, "_client_factory", None):
        client = TestClient(test_app)
        res = client.get("/test-di")
        assert res.status_code == 200
        data = res.json()
        assert data["all_same"] is True
        assert data["is_gemini"] is True

    # Assert object identity
    assert observed_clients["que_client"] is observed_clients["req_client"]
    assert observed_clients["req_client"] is observed_clients["map_client"]


# ------------------------------------------------------------------------------
# 5. Normal Automated Tests Safety: Fail-Closed Protection
# ------------------------------------------------------------------------------

def test_unmocked_gemini_call_fails_closed_in_normal_tests() -> None:
    """Proves that unmocked GeminiLLMClient cannot contact Vertex AI during normal tests."""
    client = GeminiLLMClient(project="test-proj", location="us-central1")
    # No http_client mock supplied, not marked @pytest.mark.live_llm
    with pytest.raises(RuntimeError) as exc_info:
        client.generate_structured(
            prompt="Analyze question",
            response_schema=SampleStructuredOutput,
        )

    assert "Fail-closed safety violation" in str(exc_info.value)
