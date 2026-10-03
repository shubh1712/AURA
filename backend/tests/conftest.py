"""Pytest configuration, fixtures, and fail-closed safety mechanisms for AURA test suite."""

import socket
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.analysis_service import (
    AnalysisService,
    get_analysis_service,
    get_llm_client,
)
from app.services.llm.client import FakeLLMClient
from app.services.llm.gemini import GeminiLLMClient

# ------------------------------------------------------------------------------
# 1. Test-Layer Safety State
# ------------------------------------------------------------------------------

_LIVE_CALLS_ALLOWED: bool = False


def set_live_calls_allowed(allowed: bool) -> None:
    """Controls whether live external Gemini API calls are permitted during tests."""
    global _LIVE_CALLS_ALLOWED
    _LIVE_CALLS_ALLOWED = allowed


def is_live_calls_allowed() -> bool:
    """Returns True if live external Gemini API calls are permitted during tests."""
    return _LIVE_CALLS_ALLOWED


# ------------------------------------------------------------------------------
# 2. Fail-Closed Network & LLM Safety Mechanisms (Active ONLY during pytest)
# ------------------------------------------------------------------------------

_orig_socket_connect = socket.socket.connect


def _guarded_socket_connect(self: socket.socket, address: object) -> None:
    """Intersects outbound socket connections to fail closed if external network is contacted."""
    host = address[0] if isinstance(address, tuple) and len(address) > 0 else str(address)
    # Permitted local endpoints
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "testclient"):
        return _orig_socket_connect(self, address)

    if is_live_calls_allowed():
        return _orig_socket_connect(self, address)

    raise RuntimeError(
        f"Fail-closed network safety violation: Outbound network connection to {address} "
        f"attempted during normal automated test execution! "
        f"Normal automated tests must never contact external APIs."
    )


socket.socket.connect = _guarded_socket_connect


_orig_generate_structured = GeminiLLMClient.generate_structured


def _guarded_generate_structured(self: GeminiLLMClient, *args: object, **kwargs: object) -> object:
    """Guards GeminiLLMClient.generate_structured during automated tests.

    Fails closed if an unmocked Gemini call is attempted during normal tests.
    Permits calls if live calls are explicitly allowed (@pytest.mark.live_llm)
    or if a mock http_client transport was supplied.
    """
    if not is_live_calls_allowed() and self._http_client is None:
        # Check credentials first so missing API key tests raise LLMAuthenticationError
        self._get_api_key()
        raise RuntimeError(
            "Fail-closed safety violation: External Gemini API call attempted during normal test execution. "
            "Normal automated tests must use FakeLLMClient / MockLLMClient or mocked http_client transport. "
            "To execute live API tests, mark with @pytest.mark.live_llm and run 'pytest -m live_llm'."
        )
    return _orig_generate_structured(self, *args, **kwargs)


GeminiLLMClient.generate_structured = _guarded_generate_structured


# ------------------------------------------------------------------------------
# 3. Dependency Injection & Safety Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def configure_test_llm_client(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Ensures every normal automated test uses FakeLLMClient and forbids external calls.

    Opt-in tests marked with @pytest.mark.live_llm are permitted live external calls.
    """
    is_live = bool(request.node.get_closest_marker("live_llm"))
    set_live_calls_allowed(is_live)

    if is_live:
        yield
        set_live_calls_allowed(False)
        return

    # Normal test suite: inject deterministic FakeLLMClient
    fake_client = FakeLLMClient()
    AnalysisService.set_client_factory(lambda: fake_client)
    app.dependency_overrides[get_llm_client] = lambda: fake_client
    app.dependency_overrides[get_analysis_service] = lambda: AnalysisService(llm_client=fake_client)

    yield

    AnalysisService.set_client_factory(None)
    app.dependency_overrides.clear()
    set_live_calls_allowed(False)


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Fixture providing a synchronous FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
