"""AURA Gemini LLM Client Implementation.

Provides a concrete implementation of LLMClient communicating with Google's
Gemini API using the google-genai Python SDK and the Interactions API.
All Gemini SDK dependencies remain strictly encapsulated within
this service module.
"""

import os
import time
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

from google import genai
from google.genai import errors
from google.genai.types import HttpOptions, HttpRetryOptions

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
        sleep_fn: Optional[Callable[[float], None]] = None,
        initial_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 2.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        """Initializes the Gemini client.

        Args:
            api_key: Optional API key. Defaults to settings.GEMINI_API_KEY or env GEMINI_API_KEY.
            default_model: Optional default model name.
            http_client: Optional pre-configured httpx.Client (used for mocking and pooling).
            sleep_fn: Optional callable for backoff delays (defaults to time.sleep).
            initial_backoff_seconds: Initial backoff interval in seconds.
            max_backoff_seconds: Maximum backoff interval in seconds.
            backoff_multiplier: Multiplier factor for successive retries.
        """
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model or settings.GEMINI_MODEL or "gemini-3.8-flash"
        self._http_client = http_client
        self._sleep_fn = sleep_fn or time.sleep
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self._genai_client: Optional[genai.Client] = None

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

    def _get_genai_client(self) -> genai.Client:
        """Returns the shared genai.Client instance for this GeminiLLMClient, initializing lazily."""
        if self._genai_client is None:
            api_key = self._get_api_key()
            # Disable SDK-level retries using supported public API (HttpOptions / HttpRetryOptions).
            # attempts=1 and http_status_codes=[0] deterministically produces exactly 1 SDK attempt.
            http_options = HttpOptions(
                httpx_client=self._http_client,
                retry_options=HttpRetryOptions(attempts=1, http_status_codes=[0]),
            )
            self._genai_client = genai.Client(api_key=api_key, http_options=http_options)
        return self._genai_client

    def _extract_retry_after(self, exc: Exception) -> Optional[float]:
        """Extracts Retry-After header delay in seconds if present on the exception."""
        response = getattr(exc, "response", None)
        if response is not None and hasattr(response, "headers"):
            retry_after_str = response.headers.get("retry-after") or response.headers.get("Retry-After")
            if retry_after_str:
                try:
                    return float(retry_after_str.strip())
                except ValueError:
                    pass
        retry_after_attr = getattr(exc, "retry_after", None)
        if isinstance(retry_after_attr, (int, float)) and retry_after_attr > 0:
            return float(retry_after_attr)
        return None

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> T:
        """Generates and validates a structured response matching response_schema via Gemini.

        Args:
            prompt: User/decision prompt.
            response_schema: Target Pydantic model class.
            system_instruction: Optional system instruction.
            config: Optional runtime configuration.
            deadline_monotonic: Optional absolute monotonic deadline from a parent analysis.

        Returns:
            Validated instance of response_schema (T).

        Raises:
            LLMTimeoutError: If the operation exceeds operation_timeout_seconds or request times out.
            LLMAuthenticationError: If API credentials are missing or invalid.
            LLMRateLimitError: If rate limit or quota is exceeded.
            LLMProviderError: If Gemini encounters internal 5xx errors.
            LLMResponseValidationError: If output parsing or Pydantic validation fails.
            LLMError: For other network or request failures.
        """
        cfg = config or DEFAULT_LLM_CONFIG
        model_name = cfg.model_name or self.default_model

        genai_client = self._get_genai_client()

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

        timeout_error_classes = (httpx.TimeoutException,)
        if compat_errors and hasattr(compat_errors, "APITimeoutError"):
            timeout_error_classes = (httpx.TimeoutException, compat_errors.APITimeoutError)

        # Enforce overall wall-clock operation deadline using monotonic clock
        start_time = time.monotonic()
        operation_timeout = cfg.operation_timeout_seconds if cfg.operation_timeout_seconds else 60.0
        local_deadline = start_time + operation_timeout
        if deadline_monotonic is not None:
            deadline = min(local_deadline, deadline_monotonic)
        else:
            deadline = local_deadline

        attempts = 0
        max_attempts = max(1, 1 + (cfg.max_retries if cfg.max_retries is not None else 0))

        def _do_backoff(attempt_idx: int, retry_after: Optional[float] = None) -> None:
            calc_delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_idx - 1))
            if retry_after is not None and retry_after > 0:
                calc_delay = max(calc_delay, retry_after)
            capped_delay = min(calc_delay, self.max_backoff_seconds)

            rem_time = deadline - time.monotonic()
            if rem_time <= 0:
                raise LLMTimeoutError(
                    f"Gemini API request timed out after {operation_timeout:.1f}s.",
                    details={"model": model_name, "timeout": operation_timeout},
                )
            actual_sleep = min(capped_delay, rem_time)
            self._sleep_fn(actual_sleep)

        while attempts < max_attempts:
            attempts += 1

            # Check remaining deadline before each attempt
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMTimeoutError(
                    f"Gemini API request timed out after {operation_timeout:.1f}s.",
                    details={"model": model_name, "timeout": operation_timeout},
                )

            # Effective per-request timeout cannot exceed remaining operation budget
            per_request_timeout = cfg.timeout_seconds if cfg.timeout_seconds else 30.0
            effective_http_timeout = min(per_request_timeout, remaining)
            create_kwargs["timeout"] = effective_http_timeout

            try:
                interaction = genai_client.interactions.create(**create_kwargs)
            except timeout_error_classes as e:
                if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                    raise LLMTimeoutError(
                        f"Gemini API request timed out after {operation_timeout:.1f}s.",
                        details={"model": model_name, "timeout": operation_timeout},
                    ) from e
                _do_backoff(attempt_idx=attempts, retry_after=None)
                continue
            except Exception as e:
                status_code = getattr(e, "status_code", None) or getattr(e, "code", None)

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
                    (status_code and 400 <= status_code < 500 and status_code not in (401, 403, 429))
                    or isinstance(e, errors.ClientError)
                    or (compat_errors and isinstance(e, (compat_errors.BadRequestError, compat_errors.NotFoundError, compat_errors.ConflictError, compat_errors.UnprocessableEntityError)))
                )
                is_transport_error = (
                    isinstance(e, httpx.RequestError)
                    or (compat_errors and isinstance(e, compat_errors.APIConnectionError))
                )

                # Non-retryable: Authentication failure
                if is_auth_error:
                    raise LLMAuthenticationError(
                        f"Gemini authentication failed ({status_code}).",
                        details={"status_code": status_code, "model": model_name},
                    ) from e

                # Non-retryable: Deterministic client error
                if is_client_error:
                    raise LLMError(
                        f"Gemini API client error ({status_code}).",
                        details={"status_code": status_code, "model": model_name},
                    ) from e

                # Retryable: Rate limit
                if is_rate_limit:
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMRateLimitError(
                            f"Gemini rate limit or quota exceeded ({status_code}).",
                            details={"status_code": status_code, "model": model_name},
                        ) from e
                    retry_after = self._extract_retry_after(e)
                    _do_backoff(attempt_idx=attempts, retry_after=retry_after)
                    continue

                # Retryable: Provider transient 5xx error
                if is_provider_error:
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMProviderError(
                            f"Gemini upstream server error ({status_code}).",
                            details={"status_code": status_code, "model": model_name},
                        ) from e
                    retry_after = self._extract_retry_after(e)
                    _do_backoff(attempt_idx=attempts, retry_after=retry_after)
                    continue

                # Retryable: Network transport failure
                if is_transport_error:
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMError(
                            "Network transport error calling Gemini API.",
                            details={"model": model_name},
                        ) from e
                    _do_backoff(attempt_idx=attempts, retry_after=None)
                    continue

                # Non-retryable: Unexpected other exception
                raise LLMError(
                    "Unexpected error communicating with Gemini API.",
                    details={"model": model_name},
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
                if attempts < max_attempts and (deadline - time.monotonic()) > 0:
                    _do_backoff(attempt_idx=attempts, retry_after=None)
                    continue
                raise LLMResponseValidationError(
                    "Gemini candidate returned empty text parts.",
                    details={"model": model_name},
                )

            # Delegate parsing, normalization, and Pydantic validation to StructuredOutputParser
            try:
                return parse_and_validate_structured_output(
                    raw_text=raw_text,
                    response_schema=response_schema,
                    raw_user_prompt=prompt,
                )
            except LLMResponseValidationError:
                if attempts < max_attempts and (deadline - time.monotonic()) > 0:
                    _do_backoff(attempt_idx=attempts, retry_after=None)
                    continue
                raise

        raise LLMResponseValidationError("Gemini structured output generation failed all retry attempts.")
