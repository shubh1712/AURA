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
    """Live test calling real Gemini API with structured output validation.

    Skips safely if GEMINI_API_KEY is not configured.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        pytest.skip("GEMINI_API_KEY is not configured; skipping live LLM test.")

    client = GeminiLLMClient(api_key=api_key.strip())
    prompt = build_decomposition_prompt(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )

    result = client.generate_structured(
        prompt=prompt,
        response_schema=DecisionModel,
        system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
        config=LLMConfig(timeout_seconds=30.0),
    )

    assert isinstance(result, DecisionModel)
    assert len(result.objectives) >= 1
    assert len(result.variables) >= 1
