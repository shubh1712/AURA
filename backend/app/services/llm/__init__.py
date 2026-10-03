"""AURA LLM Service Package.

Provides client abstractions, configuration models, prompt templates,
and typed error classes for language model operations.
"""

from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    FakeLLMClient,
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.parser import (
    StructuredOutputParser,
    parse_and_validate_structured_output,
)
from app.services.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
    build_decomposition_prompt,
)

__all__ = [
    "DEFAULT_LLM_CONFIG",
    "LLMClient",
    "LLMConfig",
    "MockLLMClient",
    "FakeLLMClient",
    "GeminiLLMClient",
    "StructuredOutputParser",
    "parse_and_validate_structured_output",
    "LLMError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMResponseValidationError",
    "LLMProviderError",
    "DECOMPOSITION_SYSTEM_PROMPT",
    "build_decomposition_prompt",
]
