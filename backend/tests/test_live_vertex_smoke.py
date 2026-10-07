"""Opt-in live smoke test for single-request Vertex AI Gemini connectivity.

Excluded by default from normal test runs. To execute explicitly:
    RUN_LIVE_VERTEX_SMOKE=1 pytest tests/test_live_vertex_smoke.py -m live_vertex_smoke -v

Requirements:
    RUN_LIVE_VERTEX_SMOKE=1
    GOOGLE_CLOUD_PROJECT (configured via environment, .env, or ADC)

Properties:
- Uses the same GeminiLLMClient configuration and production initialization pathway.
- Makes exactly ONE minimal structured generation request (max_retries=0).
- Does NOT use Brave Search.
- Does NOT invoke the full analysis pipeline.
- Enforces a strict per-request and operation timeout.
- Never prints credentials, tokens, or authorization headers.
"""

import os
import time
import pytest
from pydantic import BaseModel, Field

from app.config import settings
from app.services.llm.client import LLMConfig
from app.services.llm.gemini import GeminiLLMClient


class MinimalSmokePayload(BaseModel):
    """Minimal Pydantic schema for single-call smoke verification."""
    status: str = Field(description="Operational status indicator, e.g. ok")
    message: str = Field(description="Brief confirmation message")


@pytest.mark.live_vertex_smoke
def test_live_vertex_single_request_smoke() -> None:
    """Executes a single, minimal live Vertex AI Gemini structured call.

    Distinguishes:
    A. Model/API incompatibility
    B. Vertex configuration/endpoint issue
    C. Authentication/permission issue
    D. Transient provider/network latency
    """
    run_flag = os.environ.get("RUN_LIVE_VERTEX_SMOKE", "").strip() == "1"
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or getattr(settings, "GOOGLE_CLOUD_PROJECT", None)
        or os.environ.get("GCP_PROJECT")
    )
    if not run_flag or not project or not str(project).strip():
        pytest.skip(
            "RUN_LIVE_VERTEX_SMOKE=1 and GOOGLE_CLOUD_PROJECT are required for the live Vertex smoke test."
        )

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or getattr(settings, "GOOGLE_CLOUD_LOCATION", None)
        or "global"
    )

    # Initialize production GeminiLLMClient with identical production config
    client = GeminiLLMClient(
        project=str(project).strip(),
        location=str(location).strip(),
    )

    # Strict configuration: exactly ONE attempt (max_retries=0) and short timeouts
    smoke_config = LLMConfig(
        timeout_seconds=20.0,
        operation_timeout_seconds=25.0,
        max_retries=0,
    )

    start_time = time.monotonic()
    result = client.generate_structured(
        prompt="Respond with status 'ok' and a brief message confirming receipt.",
        response_schema=MinimalSmokePayload,
        config=smoke_config,
    )
    duration = time.monotonic() - start_time

    assert isinstance(result, MinimalSmokePayload)
    assert result.status is not None and len(result.status.strip()) > 0
    assert result.message is not None and len(result.message.strip()) > 0
    assert duration < 25.0, f"Smoke call took {duration:.2f}s, exceeding strict limit"
