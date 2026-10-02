"""AURA Gemini LLM Client Implementation.

Provides a concrete implementation of LLMClient communicating with Google's
Gemini API using the google-genai Python SDK and the Interactions API.
All Gemini SDK dependencies remain strictly encapsulated within
this service module.
"""

import os
from typing import Any, Dict, List, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

from google import genai
from google.genai import errors
from google.genai.types import HttpOptions

try:
    from google.genai._gaos.lib import compat_errors
except ImportError:
    compat_errors = None

from app.config import settings
from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.parser import parse_and_validate_structured_output

T = TypeVar("T", bound=BaseModel)


class GeminiLLMClient(LLMClient):
    """Production client for invoking Gemini models with structured Pydantic validation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        """Initializes the Gemini client.

        Args:
            api_key: Optional API key. Defaults to settings.GEMINI_API_KEY or env GEMINI_API_KEY.
            default_model: Optional default model name.
            http_client: Optional pre-configured httpx.Client (used for mocking and pooling).
        """
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model or settings.GEMINI_MODEL or "gemini-3.8-flash"
        self._http_client = http_client

    def _get_api_key(self) -> str:
        """Retrieves and verifies the API key prior to making a call."""
        key = self.api_key
        if key is None:
            key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if not key or not key.strip():
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your environment or .env file."
            )
        return key.strip()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
    ) -> T:
        """Generates and validates a structured response matching response_schema via Gemini.

        Args:
            prompt: User/decision prompt.
            response_schema: Target Pydantic model class.
            system_instruction: Optional system instruction.
            config: Optional runtime configuration.

        Returns:
            Validated instance of response_schema (T).

        Raises:
            LLMTimeoutError: If the request exceeds timeout_seconds.
            LLMAuthenticationError: If API credentials are missing or invalid.
            LLMRateLimitError: If rate limit or quota is exceeded.
            LLMProviderError: If Gemini encounters internal 5xx errors.
            LLMResponseValidationError: If output parsing or Pydantic validation fails.
            LLMError: For other network or request failures.
        """
        cfg = config or DEFAULT_LLM_CONFIG
        api_key = self._get_api_key()
        model_name = cfg.model_name or self.default_model

        # Configure google-genai client
        http_options = HttpOptions(httpx_client=self._http_client) if self._http_client is not None else None
        genai_client = genai.Client(api_key=api_key, http_options=http_options)

        response_format = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_schema.model_json_schema(),
        }

        create_kwargs: Dict[str, Any] = {
            "model": model_name,
            "input": prompt,
            "response_format": response_format,
        }
        if system_instruction:
            create_kwargs["system_instruction"] = system_instruction
        if cfg.timeout_seconds:
            create_kwargs["timeout"] = cfg.timeout_seconds

        timeout_error_classes = (httpx.TimeoutException,)
        if compat_errors and hasattr(compat_errors, "APITimeoutError"):
            timeout_error_classes = (httpx.TimeoutException, compat_errors.APITimeoutError)

        try:
            interaction = genai_client.interactions.create(**create_kwargs)
        except timeout_error_classes as e:
            raise LLMTimeoutError(
                f"Gemini API request timed out after {cfg.timeout_seconds}s.",
                details={"model": model_name, "timeout": cfg.timeout_seconds, "error": str(e)},
            ) from e
        except Exception as e:
            status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
            err_text = str(e)

            is_auth_error = (
                status_code in (401, 403)
                or (compat_errors and isinstance(e, (compat_errors.AuthenticationError, compat_errors.PermissionDeniedError)))
            )
            is_rate_limit = (
                status_code == 429
                or (compat_errors and isinstance(e, compat_errors.RateLimitError))
            )
            is_provider_error = (
                (status_code and status_code >= 500)
                or isinstance(e, errors.ServerError)
                or (compat_errors and isinstance(e, compat_errors.InternalServerError))
            )
            is_client_error = (
                (status_code and status_code >= 400)
                or isinstance(e, errors.ClientError)
                or (compat_errors and isinstance(e, (compat_errors.BadRequestError, compat_errors.ClientError)))
            )

            if is_auth_error:
                raise LLMAuthenticationError(
                    f"Gemini authentication failed ({status_code}): {err_text}",
                    details={"status_code": status_code, "body": err_text},
                ) from e
            elif is_rate_limit:
                raise LLMRateLimitError(
                    f"Gemini rate limit or quota exceeded ({status_code}): {err_text}",
                    details={"status_code": status_code, "body": err_text},
                ) from e
            elif is_provider_error:
                raise LLMProviderError(
                    f"Gemini upstream server error ({status_code}): {err_text}",
                    details={"status_code": status_code, "body": err_text},
                ) from e
            elif is_client_error:
                raise LLMError(
                    f"Gemini API client error ({status_code}): {err_text}",
                    details={"status_code": status_code, "body": err_text},
                ) from e
            elif isinstance(e, httpx.RequestError):
                raise LLMError(
                    f"Network transport error calling Gemini API: {e}",
                    details={"model": model_name, "error": str(e)},
                ) from e
            raise LLMError(
                f"Unexpected error communicating with Gemini API: {e}",
                details={"model": model_name, "error": str(e)},
            ) from e

        # Extract output text using convenience property or fallback inspection
        raw_text = getattr(interaction, "output_text", None)
        if not raw_text and isinstance(interaction, dict):
            raw_text = interaction.get("output_text")
            if not raw_text and "steps" in interaction:
                for step in reversed(interaction["steps"]):
                    if step.get("type") == "model_output":
                        for part in step.get("content", []):
                            if part.get("type") == "text":
                                raw_text = part.get("text")
                                break
                    if raw_text:
                        break
            elif not raw_text and "candidates" in interaction:
                candidates = interaction.get("candidates") or []
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and parts[0].get("text"):
                        raw_text = parts[0]["text"]

        if not raw_text or not str(raw_text).strip():
            raise LLMResponseValidationError(
                "Gemini candidate returned empty text parts.",
                details={"interaction": str(interaction)},
            )

        # Delegate parsing, normalization, and Pydantic validation to StructuredOutputParser
        return parse_and_validate_structured_output(
            raw_text=raw_text,
            response_schema=response_schema,
            raw_user_prompt=prompt,
        )
