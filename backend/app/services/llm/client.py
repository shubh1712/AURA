"""AURA LLM Client Abstraction.

Provides a decoupled, provider-agnostic interface for invoking language models
with structured Pydantic output schemas, strict timeouts, model configuration,
and typed error handling.

This layer has ZERO knowledge of:
- FastAPI routes / HTTP requests
- Frontend components
- Database / Firestore persistence
- Downstream recommendation logic
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel, ConfigDict, Field, ValidationError

T = TypeVar("T", bound=BaseModel)


# ------------------------------------------------------------------------------
# 1. Typed Exceptions
# ------------------------------------------------------------------------------

class LLMError(Exception):
    """Base exception for all LLM client failures."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class LLMTimeoutError(LLMError):
    """Raised when an LLM operation exceeds the configured timeout."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when authentication credentials (e.g. API key) are missing or invalid."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when API rate limits or quota boundaries are encountered."""
    pass


class LLMResponseValidationError(LLMError):
    """Raised when the LLM output fails to conform to the requested Pydantic schema."""
    pass


class LLMProviderError(LLMError):
    """Raised when the upstream LLM service encounters an unhandled 5xx failure."""
    pass


# ------------------------------------------------------------------------------
# 2. Configuration Model
# ------------------------------------------------------------------------------

class LLMConfig(BaseModel):
    """Runtime configuration for an LLM generation call."""
    model_config = ConfigDict(frozen=True)

    model_name: str = Field(
        default="gemini-3.8-flash",
        description="Target model identifier.",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature. Lower values produce more deterministic structured outputs.",
    )
    top_p: Optional[float] = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability threshold.",
    )
    max_output_tokens: Optional[int] = Field(
        default=4096,
        gt=0,
        description="Maximum tokens allowed in generation.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Maximum duration in seconds before terminating the request.",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Number of retry attempts on transient network or rate-limit failures.",
    )


DEFAULT_LLM_CONFIG = LLMConfig()


# ------------------------------------------------------------------------------
# 3. LLM Client Protocol / Interface
# ------------------------------------------------------------------------------

class LLMClient(ABC):
    """Abstract interface defining AURA's interaction with language models."""

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
    ) -> T:
        """Generates and validates a structured response matching response_schema.

        Args:
            prompt: User/context prompt describing the task.
            response_schema: Pydantic model class defining the expected output.
            system_instruction: Optional high-level system framing.
            config: Optional runtime overrides (temperature, timeout, etc.).

        Returns:
            An instantiated, validated instance of response_schema (T).

        Raises:
            LLMTimeoutError: If the request exceeds timeout_seconds.
            LLMResponseValidationError: If output cannot be validated into response_schema.
            LLMRateLimitError: If provider quota/rate limits are exceeded.
            LLMAuthenticationError: If API credentials are not configured.
            LLMError: For other upstream or parsing failures.
        """
        pass


# ------------------------------------------------------------------------------
# 4. In-Memory Mock Client for Testing & Simulation
# ------------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Deterministic in-memory mock client for unit testing and local development.

    Allows test suites to register pre-determined Pydantic responses or simulate
    specific error conditions (timeouts, rate limits, schema mismatches).
    """

    def __init__(self) -> None:
        self._canned_responses: Dict[Type[BaseModel], BaseModel] = {}
        self._canned_error: Optional[Exception] = None
        self.call_history: List[Dict[str, Any]] = []

    def register_response(self, schema_cls: Type[T], response_instance: T) -> None:
        """Registers a fixed response to return when schema_cls is requested."""
        if not isinstance(response_instance, schema_cls):
            raise ValueError(f"Instance must match registered schema {schema_cls.__name__}")
        self._canned_responses[schema_cls] = response_instance

    def register_error(self, error: Exception) -> None:
        """Forces the next call to raise the specified exception."""
        self._canned_error = error

    def clear(self) -> None:
        """Clears canned responses, errors, and history."""
        self._canned_responses.clear()
        self._canned_error = None
        self.call_history.clear()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
    ) -> T:
        cfg = config or DEFAULT_LLM_CONFIG

        # Record call telemetry
        self.call_history.append({
            "prompt": prompt,
            "response_schema": response_schema,
            "system_instruction": system_instruction,
            "config": cfg,
        })

        # Simulate programmed errors
        if self._canned_error:
            err = self._canned_error
            self._canned_error = None
            raise err

        # Return registered schema instance
        if response_schema in self._canned_responses:
            instance = self._canned_responses[response_schema]
            return instance  # type: ignore

        # If schema can be instantiated with defaults, return fallback
        try:
            return response_schema.model_validate({})
        except ValidationError as e:
            raise LLMResponseValidationError(
                f"Mock client has no registered response for {response_schema.__name__} "
                f"and model cannot be constructed with empty defaults: {e}",
                details={"errors": e.errors()},
            ) from e
