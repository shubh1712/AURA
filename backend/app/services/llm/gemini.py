"""AURA Gemini LLM Client Implementation.

Provides a concrete implementation of LLMClient communicating with Google's
Gemini models on Google Cloud Vertex AI using the google-genai Python SDK
and the Interactions API.
All Gemini SDK dependencies remain strictly encapsulated within
this service module.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    """Production client for invoking Gemini models on Google Cloud Vertex AI with structured Pydantic validation."""

    def __init__(
        self,
        project: Optional[str] = None,
        location: Optional[str] = None,
        credentials: Optional[Any] = None,
        default_model: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        initial_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 2.0,
        backoff_multiplier: float = 2.0,
        **kwargs: Any,
    ) -> None:
        """Initializes the Gemini client on Google Cloud Vertex AI.

        Args:
            project: Optional Google Cloud project ID. Defaults to settings.GOOGLE_CLOUD_PROJECT or env GOOGLE_CLOUD_PROJECT.
            location: Optional Google Cloud location. Defaults to settings.GOOGLE_CLOUD_LOCATION or env GOOGLE_CLOUD_LOCATION or 'us-central1'.
            credentials: Optional Google Cloud Credentials (defaults to ADC in production).
            default_model: Optional default model name.
            http_client: Optional pre-configured httpx.Client (used for mocking and pooling).
            sleep_fn: Optional callable for backoff delays (defaults to time.sleep).
            initial_backoff_seconds: Initial backoff interval in seconds.
            max_backoff_seconds: Maximum backoff interval in seconds.
            backoff_multiplier: Multiplier factor for successive retries.
        """
        self.project = project or getattr(settings, "GOOGLE_CLOUD_PROJECT", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = (
            location
            or getattr(settings, "GOOGLE_CLOUD_LOCATION", None)
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or "global"
        )
        self.credentials = credentials
        self.default_model = default_model or settings.GEMINI_MODEL or "gemini-3.8-flash"
        self._http_client = http_client
        self._sleep_fn = sleep_fn or time.sleep
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self._genai_client: Optional[genai.Client] = None
        self._thread_local = threading.local()
        self._diagnostic_lock = threading.Lock()
        self._client_init_lock = threading.Lock()
        self._latest_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def last_diagnostic(self) -> Optional[Dict[str, Any]]:
        """Thread-safe access to the most recent diagnostic metadata."""
        thread_diag = getattr(self._thread_local, "diagnostic", None)
        if thread_diag is not None:
            return thread_diag
        with self._diagnostic_lock:
            return self._latest_diagnostic

    @last_diagnostic.setter
    def last_diagnostic(self, value: Optional[Dict[str, Any]]) -> None:
        """Thread-safe recording of diagnostic metadata."""
        self._thread_local.diagnostic = value
        with self._diagnostic_lock:
            self._latest_diagnostic = value

    def _get_project(self) -> str:
        """Retrieves and verifies the Google Cloud project ID prior to making a call."""
        if self.project is not None and not str(self.project).strip():
            raise LLMAuthenticationError(
                "Google Cloud project is not configured. Set GOOGLE_CLOUD_PROJECT in your environment or .env file."
            )
        project = self.project
        if not project or not str(project).strip():
            project = getattr(settings, "GOOGLE_CLOUD_PROJECT", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project or not str(project).strip():
            if self._http_client is not None:
                return "aura-test-project"
            raise LLMAuthenticationError(
                "Google Cloud project is not configured. Set GOOGLE_CLOUD_PROJECT in your environment or .env file."
            )
        return str(project).strip()

    def _get_location(self) -> str:
        """Retrieves the Google Cloud location prior to making a call."""
        location = self.location
        if not location or not str(location).strip():
            location = getattr(settings, "GOOGLE_CLOUD_LOCATION", None) or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        return str(location).strip()

    def _get_genai_client(self) -> genai.Client:
        """Returns the shared genai.Client instance for this GeminiLLMClient, initializing lazily with thread safety."""
        if self._genai_client is None:
            with self._client_init_lock:
                if self._genai_client is None:
                    project = self._get_project()
                    location = self._get_location()
                    # Disable SDK-level retries using supported public API (HttpOptions / HttpRetryOptions).
                    # attempts=1 and http_status_codes=[0] deterministically produces exactly 1 SDK attempt.
                    http_options = HttpOptions(
                        httpx_client=self._http_client,
                        retry_options=HttpRetryOptions(attempts=1, http_status_codes=[0]),
                    )
                    client_kwargs: Dict[str, Any] = {
                        "enterprise": True,
                        "project": project,
                        "location": location,
                        "http_options": http_options,
                    }
                    if self.credentials is not None:
                        client_kwargs["credentials"] = self.credentials
                    elif self._http_client is not None:
                        # When a custom http_client is supplied (mock transport in tests),
                        # provide an offline credentials dummy so tests do not make real OAuth2 network calls.
                        try:
                            import google.auth.credentials

                            class _OfflineTestCredentials(google.auth.credentials.Credentials):
                                def __init__(self) -> None:
                                    super().__init__()
                                    self.token = "aura-offline-test-token"

                                @property
                                def quota_project_id(self) -> str:
                                    return project or "aura-offline-test"

                                def refresh(self, request: Any) -> None:
                                    self.token = "aura-offline-test-token"

                                @property
                                def valid(self) -> bool:
                                    return True

                            client_kwargs["credentials"] = _OfflineTestCredentials()
                        except Exception:
                            pass

                    self._genai_client = genai.Client(**client_kwargs)
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

    @staticmethod
    def _clean_schema_for_transport(schema: Any) -> Any:
        """Removes purely informational metadata (e.g., title) from JSON schema for wire transport."""
        if isinstance(schema, dict):
            return {
                k: GeminiLLMClient._clean_schema_for_transport(v)
                for k, v in schema.items()
                if k != "title"
            }
        if isinstance(schema, list):
            return [GeminiLLMClient._clean_schema_for_transport(item) for item in schema]
        return schema

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
        # Enforce overall wall-clock operation deadline using monotonic clock
        start_time = time.monotonic()
        cfg = config or DEFAULT_LLM_CONFIG
        model_name = cfg.model_name or self.default_model

        genai_client = self._get_genai_client()

        diagnostics_enabled = os.environ.get("AURA_LLM_DIAGNOSTICS") == "1"
        t0_schema = time.monotonic() if diagnostics_enabled else 0.0
        raw_schema = response_schema.model_json_schema()
        schema_dict = self._clean_schema_for_transport(raw_schema)
        t_schema = (time.monotonic() - t0_schema) if diagnostics_enabled else 0.0
        schema_chars = len(json.dumps(schema_dict)) if diagnostics_enabled else 0
        sys_prompt_chars = len(system_instruction) if system_instruction else 0
        user_prompt_chars = len(prompt)

        response_format = {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema_dict,
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
            per_request_timeout = cfg.timeout_seconds if cfg.timeout_seconds else 45.0
            effective_http_timeout = min(per_request_timeout, remaining)
            create_kwargs["timeout"] = effective_http_timeout

            t0_call = time.monotonic() if diagnostics_enabled else 0.0
            try:
                interaction = genai_client.interactions.create(**create_kwargs)
                t_call = (time.monotonic() - t0_call) if diagnostics_enabled else 0.0
            except timeout_error_classes as e:
                t_call = (time.monotonic() - t0_call) if diagnostics_enabled else 0.0
                if diagnostics_enabled:
                    t_total = time.monotonic() - start_time
                    self.last_diagnostic = {
                        "schema_build_seconds": t_schema,
                        "schema_chars": schema_chars,
                        "system_prompt_chars": sys_prompt_chars,
                        "user_prompt_chars": user_prompt_chars,
                        "call_duration_seconds": t_call,
                        "parse_duration_seconds": 0.0,
                        "total_duration_seconds": t_total,
                        "model": model_name,
                        "location": self.location,
                        "attempt": attempts,
                        "status": "timeout",
                    }
                    logger.info(
                        "AURA LLM Diagnostic [timeout]: attempt=%d, schema_build=%.4fs, schema_len=%d, sys_len=%d, user_len=%d, "
                        "call_duration=%.3fs, total_duration=%.3fs, model=%s, location=%s",
                        attempts, t_schema, schema_chars, sys_prompt_chars, user_prompt_chars,
                        t_call, t_total, model_name, self.location,
                    )
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
            t0_parse = time.monotonic() if diagnostics_enabled else 0.0
            try:
                validated_result = parse_and_validate_structured_output(
                    raw_text=raw_text,
                    response_schema=response_schema,
                    raw_user_prompt=prompt,
                )
                t_parse = (time.monotonic() - t0_parse) if diagnostics_enabled else 0.0
                if diagnostics_enabled:
                    t_total = time.monotonic() - start_time
                    self.last_diagnostic = {
                        "schema_build_seconds": t_schema,
                        "schema_chars": schema_chars,
                        "system_prompt_chars": sys_prompt_chars,
                        "user_prompt_chars": user_prompt_chars,
                        "call_duration_seconds": t_call,
                        "parse_duration_seconds": t_parse,
                        "total_duration_seconds": t_total,
                        "model": model_name,
                        "location": self.location,
                        "attempt": attempts,
                        "status": "success",
                    }
                    logger.info(
                        "AURA LLM Diagnostic [success]: schema_build=%.4fs, schema_len=%d, sys_len=%d, user_len=%d, "
                        "call_duration=%.3fs, parse_duration=%.4fs, total_duration=%.3fs, model=%s, location=%s, attempt=%d",
                        t_schema, schema_chars, sys_prompt_chars, user_prompt_chars,
                        t_call, t_parse, t_total, model_name, self.location, attempts,
                    )
                return validated_result
            except LLMResponseValidationError:
                if attempts < max_attempts and (deadline - time.monotonic()) > 0:
                    _do_backoff(attempt_idx=attempts, retry_after=None)
                    continue
                raise

        raise LLMResponseValidationError("Gemini structured output generation failed all retry attempts.")
