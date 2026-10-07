"""Opt-in live integration tests communicating with Google Gemini API.

Excluded by default from normal test runs. To run explicitly:
    pytest -m live_llm
"""

import os
import pytest
from app.config import settings
from app.schemas.decision_model import DecisionModel
from app.services.llm.client import LLMConfig
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.prompts import DECOMPOSITION_SYSTEM_PROMPT, build_decomposition_prompt


@pytest.mark.live_llm
def test_live_gemini_structured_generation() -> None:
    """Live test calling real Gemini on Google Cloud Vertex AI with structured output validation.

    Skips safely if Google Cloud project is not configured.
    """
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or settings.GOOGLE_CLOUD_PROJECT
        or os.environ.get("GCP_PROJECT")
    )
    if not project or not project.strip():
        pytest.skip("GOOGLE_CLOUD_PROJECT is not configured; skipping live Vertex LLM test.")

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or settings.GOOGLE_CLOUD_LOCATION
        or "global"
    )
    client = GeminiLLMClient(project=project.strip(), location=location.strip())
    prompt = build_decomposition_prompt(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )

    result = client.generate_structured(
        prompt=prompt,
        response_schema=DecisionModel,
        system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
        config=LLMConfig(timeout_seconds=45.0),
    )

    assert isinstance(result, DecisionModel)
    assert len(result.objectives) >= 1
    assert len(result.variables) >= 1
