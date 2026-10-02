"""Unit tests for AURA LLM abstraction and prompt builders."""

import pytest
from pydantic import BaseModel, Field

from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    LLMAuthenticationError,
    LLMConfig,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
    build_decomposition_prompt,
)


class DummyStructuredOutput(BaseModel):
    summary: str = Field(..., description="Summary")
    confidence: float = Field(default=0.9, description="Confidence score")


# ------------------------------------------------------------------------------
# 1. LLMConfig Tests
# ------------------------------------------------------------------------------

def test_llm_config_defaults() -> None:
    """Verifies default LLM configuration parameters."""
    cfg = LLMConfig()
    assert cfg.model_name == "gemini-3.8-flash"
    assert cfg.temperature == 0.2
    assert cfg.timeout_seconds == 30.0
    assert cfg.max_retries == 2


def test_llm_config_custom_overrides() -> None:
    """Verifies custom overrides on LLMConfig."""
    cfg = LLMConfig(
        model_name="gemini-2.5-pro",
        temperature=0.0,
        timeout_seconds=45.0,
    )
    assert cfg.model_name == "gemini-2.5-pro"
    assert cfg.temperature == 0.0
    assert cfg.timeout_seconds == 45.0


# ------------------------------------------------------------------------------
# 2. MockLLMClient Tests
# ------------------------------------------------------------------------------

def test_mock_llm_client_generate_structured() -> None:
    """Verifies that MockLLMClient returns registered structured schema instances."""
    client = MockLLMClient()
    expected_output = DummyStructuredOutput(summary="Test Decision Summary", confidence=0.95)
    client.register_response(DummyStructuredOutput, expected_output)

    result = client.generate_structured(
        prompt="Analyze decision",
        response_schema=DummyStructuredOutput,
        system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
    )

    assert result.summary == "Test Decision Summary"
    assert result.confidence == 0.95
    assert len(client.call_history) == 1
    assert client.call_history[0]["prompt"] == "Analyze decision"
    assert client.call_history[0]["response_schema"] is DummyStructuredOutput


def test_mock_llm_client_timeout_simulation() -> None:
    """Verifies typed LLMTimeoutError handling."""
    client = MockLLMClient()
    client.register_error(LLMTimeoutError("Request exceeded 30s timeout"))

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Analyze decision",
            response_schema=DummyStructuredOutput,
        )
    assert "exceeded 30s timeout" in str(exc_info.value)


def test_mock_llm_client_rate_limit_simulation() -> None:
    """Verifies typed LLMRateLimitError handling."""
    client = MockLLMClient()
    client.register_error(LLMRateLimitError("Quota limit reached"))

    with pytest.raises(LLMRateLimitError) as exc_info:
        client.generate_structured(
            prompt="Analyze decision",
            response_schema=DummyStructuredOutput,
        )
    assert "Quota limit reached" in str(exc_info.value)


def test_mock_llm_client_unregistered_schema_without_defaults_raises() -> None:
    """Verifies that requesting an unregistered schema without defaults raises LLMResponseValidationError."""
    client = MockLLMClient()

    class StrictSchema(BaseModel):
        mandatory_field: str = Field(...)

    with pytest.raises(LLMResponseValidationError):
        client.generate_structured(
            prompt="Analyze decision",
            response_schema=StrictSchema,
        )


# ------------------------------------------------------------------------------
# 3. Prompt Builder Tests
# ------------------------------------------------------------------------------

def test_build_decomposition_prompt_minimal() -> None:
    """Verifies prompt construction with only a question."""
    prompt = build_decomposition_prompt(
        question="Should we migrate to a distributed database?"
    )
    assert "Decision Question:\nShould we migrate to a distributed database?" in prompt
    assert "Operational Context:" not in prompt
    assert "Stated Constraints:" not in prompt


def test_build_decomposition_prompt_with_context_and_constraints() -> None:
    """Verifies prompt construction with context and constraints."""
    prompt = build_decomposition_prompt(
        question="Should we reduce pricing by 20%?",
        context={"current_users": 10000, "runway_months": 14},
        constraints=["Zero downtime", "Budget under $30,000"],
    )
    assert "Decision Question:\nShould we reduce pricing by 20%?" in prompt
    assert "Operational Context:\n- current_users: 10000\n- runway_months: 14" in prompt
    assert "Stated Constraints:\n- Zero downtime\n- Budget under $30,000" in prompt
    assert "Deconstruct this decision problem into its structured components" in prompt
