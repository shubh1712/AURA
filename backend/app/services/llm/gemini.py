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
import re
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


def _sanitize_diagnostic_text(text: Optional[str]) -> str:
    """Sanitizes text for diagnostic logs and errors, redacting credentials and truncating length."""
    if not text:
        return ""
    s = str(text).strip()
    s = re.sub(r'AIza[0-9A-Za-z_\-]{20,}', '[REDACTED_API_KEY]', s)
    s = re.sub(r'ya29\.[0-9A-Za-z_\-]+', '[REDACTED_TOKEN]', s)
    s = re.sub(r'(?i)\b(?:bearer|key|token|api_key|secret|password)\s*[:=]\s*[^\s,;]+', '[REDACTED_CREDENTIAL]', s)
    s = re.sub(r'(?i)\bbearer\s+[^\s,;]+', '[REDACTED_TOKEN]', s)
    if len(s) > 500:
        s = s[:497] + "..."
    return s


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

    @classmethod
    def _clean_schema_for_transport(
        cls,
        schema: Any,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        """Removes purely informational metadata (e.g., title) from JSON schema for wire transport.

        When response_schema is DecisionModel, applies narrow safe description compaction
        to reduce wire payload without altering field semantics, types, or validation contracts.
        Preserves schema properties named 'title' inside 'properties' dictionaries.
        """
        def _strip_titles(s: Any, parent_key: Optional[str] = None) -> Any:
            if isinstance(s, dict):
                return {
                    k: _strip_titles(v, parent_key=k)
                    for k, v in s.items()
                    if not (k == "title" and parent_key != "properties" and isinstance(v, str))
                }
            if isinstance(s, list):
                return [_strip_titles(item, parent_key=parent_key) for item in s]
            return s

        cleaned = _strip_titles(schema)

        if response_schema is not None:
            try:
                from app.schemas.decision_model import DecisionModel
                if isinstance(response_schema, type) and issubclass(response_schema, DecisionModel):
                    from app.services.llm.transport_schema import compact_decision_model_schema_for_transport
                    return compact_decision_model_schema_for_transport(cleaned)
            except Exception:
                pass

        return cleaned

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
        schema_dict = self._clean_schema_for_transport(raw_schema, response_schema=response_schema)
        t_schema = (time.monotonic() - t0_schema) if diagnostics_enabled else 0.0

        stage = getattr(cfg, "stage", None) if cfg else None
        if not stage and response_schema is not None:
            schema_name = getattr(response_schema, "__name__", "")
            if "Recommendation" in schema_name:
                stage = "recommendation"
            elif "Synthesis" in schema_name:
                stage = "synthesis"
            elif "Perspective" in schema_name:
                stage = "perspective_evaluation"
            elif "Requirements" in schema_name:
                stage = "evidence_requirements"
            elif "Evidence" in schema_name:
                stage = "evidence_mapping"
            elif "DecisionModel" in schema_name:
                stage = "framing"
            else:
                stage = schema_name or "unknown"
        elif not stage:
            stage = "unknown"

        schema_chars = len(json.dumps(schema_dict))
        sys_prompt_chars = len(system_instruction) if system_instruction else 0
        user_prompt_chars = len(prompt)
        total_payload_chars = user_prompt_chars + sys_prompt_chars + schema_chars

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
        attempt_records: List[Dict[str, Any]] = []

        def _determine_timeout_source(now: float) -> str:
            if (deadline - now) <= 0:
                if deadline_monotonic is not None and deadline_monotonic <= local_deadline:
                    return "parent"
                return "operation"
            return "request"

        def _record_attempt(
            status: str,
            error_category: Optional[str],
            t_start: float,
            t_end: float,
            effective_timeout: float,
            backoff_seconds: float = 0.0,
        ) -> Optional[Dict[str, Any]]:
            if not diagnostics_enabled:
                return None
            dur = t_end - t_start
            rem_op = max(0.0, local_deadline - t_end)
            rem_par = max(0.0, deadline_monotonic - t_end) if deadline_monotonic is not None else None
            record: Dict[str, Any] = {
                "attempt_index": attempts,
                "start_monotonic": t_start,
                "end_monotonic": t_end,
                "duration_seconds": dur,
                "status": status,
                "error_category": error_category,
                "backoff_seconds": backoff_seconds,
                "remaining_operation_seconds": rem_op,
                "remaining_parent_seconds": rem_par,
                "effective_http_timeout_seconds": effective_timeout,
            }
            attempt_records.append(record)
            return record

        def _update_diagnostic(
            status: str,
            final_call_duration: float,
            final_parse_duration: float = 0.0,
            final_timeout_source: Optional[str] = None,
            final_validation_category: Optional[str] = None,
            final_validation_field_paths: Optional[List[str]] = None,
            final_validation_error_types: Optional[List[str]] = None,
            final_validation_constraints: Optional[List[Dict[str, Any]]] = None,
        ) -> None:
            if not diagnostics_enabled:
                return
            t_total = time.monotonic() - start_time
            diag_dict: Dict[str, Any] = {
                "schema_build_seconds": t_schema,
                "schema_chars": schema_chars,
                "system_prompt_chars": sys_prompt_chars,
                "user_prompt_chars": user_prompt_chars,
                "call_duration_seconds": final_call_duration,
                "parse_duration_seconds": final_parse_duration,
                "total_duration_seconds": t_total,
                "model": model_name,
                "location": self.location,
                "attempt": attempts,
                "status": status,
                "final_timeout_source": final_timeout_source,
                "final_validation_category": final_validation_category,
                "final_validation_field_paths": final_validation_field_paths,
                "final_validation_error_types": final_validation_error_types,
                "final_validation_constraints": final_validation_constraints,
                "attempts": list(attempt_records),
            }
            self.last_diagnostic = diag_dict
            logger.info(
                "AURA LLM Diagnostic [%s]: attempt=%d, schema_build=%.4fs, schema_len=%d, sys_len=%d, user_len=%d, "
                "call_duration=%.3fs, parse_duration=%.4fs, total_duration=%.3fs, model=%s, location=%s, timeout_source=%s",
                status,
                attempts,
                t_schema,
                schema_chars,
                sys_prompt_chars,
                user_prompt_chars,
                final_call_duration,
                final_parse_duration,
                t_total,
                model_name,
                self.location,
                str(final_timeout_source),
            )

        def _do_backoff(attempt_idx: int, retry_after: Optional[float] = None) -> float:
            calc_delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_idx - 1))
            if retry_after is not None and retry_after > 0:
                calc_delay = max(calc_delay, retry_after)
            capped_delay = min(calc_delay, self.max_backoff_seconds)

            now = time.monotonic()
            rem_time = deadline - now
            if rem_time <= 0:
                timeout_source = _determine_timeout_source(now)
                _update_diagnostic(
                    status="timeout",
                    final_call_duration=0.0,
                    final_timeout_source=timeout_source,
                )
                raise LLMTimeoutError(
                    f"Gemini API request timed out after {operation_timeout:.1f}s.",
                    details={
                        "model": model_name,
                        "timeout": operation_timeout,
                        "timeout_source": timeout_source,
                        "attempt": attempt_idx,
                    },
                )
            actual_sleep = min(capped_delay, rem_time)
            self._sleep_fn(actual_sleep)
            return actual_sleep

        while attempts < max_attempts:
            attempts += 1

            # Check remaining deadline before each attempt
            now_before = time.monotonic()
            remaining = deadline - now_before
            if remaining <= 0:
                timeout_source = _determine_timeout_source(now_before)
                _update_diagnostic(
                    status="timeout",
                    final_call_duration=0.0,
                    final_timeout_source=timeout_source,
                )
                raise LLMTimeoutError(
                    f"Gemini API request timed out after {operation_timeout:.1f}s.",
                    details={
                        "model": model_name,
                        "timeout": operation_timeout,
                        "timeout_source": timeout_source,
                        "attempt": attempts,
                    },
                )

            # Effective per-request timeout cannot exceed remaining operation budget
            per_request_timeout = cfg.timeout_seconds if cfg.timeout_seconds else 30.0
            effective_http_timeout = min(per_request_timeout, remaining)
            create_kwargs["timeout"] = effective_http_timeout

            t0_call = time.monotonic() if diagnostics_enabled else 0.0
            try:
                interaction = genai_client.interactions.create(**create_kwargs)
                t1_call = time.monotonic() if diagnostics_enabled else 0.0
                t_call = (t1_call - t0_call) if diagnostics_enabled else 0.0
            except timeout_error_classes as e:
                t1_call = time.monotonic() if diagnostics_enabled else 0.0
                t_call = (t1_call - t0_call) if diagnostics_enabled else 0.0
                now = t1_call if diagnostics_enabled else time.monotonic()
                is_exhausted = (attempts >= max_attempts) or ((deadline - now) <= 0)
                timeout_source = _determine_timeout_source(now) if is_exhausted else None

                att_rec = _record_attempt(
                    status="timeout",
                    error_category="timeout",
                    t_start=t0_call,
                    t_end=t1_call,
                    effective_timeout=effective_http_timeout,
                )
                _update_diagnostic(
                    status="timeout",
                    final_call_duration=t_call,
                    final_timeout_source=timeout_source,
                )
                if is_exhausted:
                    raise LLMTimeoutError(
                        f"Gemini API request timed out after {operation_timeout:.1f}s.",
                        details={
                            "model": model_name,
                            "timeout": operation_timeout,
                            "timeout_source": timeout_source,
                            "attempt": attempts,
                        },
                    ) from e
                sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=None)
                if att_rec is not None:
                    att_rec["backoff_seconds"] = sleep_dur
                continue
            except Exception as e:
                t1_call = time.monotonic() if diagnostics_enabled else 0.0
                t_call = (t1_call - t0_call) if diagnostics_enabled else 0.0
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
                    _record_attempt(
                        status="auth_error",
                        error_category="auth_error",
                        t_start=t0_call,
                        t_end=t1_call,
                        effective_timeout=effective_http_timeout,
                    )
                    _update_diagnostic(
                        status="auth_error",
                        final_call_duration=t_call,
                    )
                    raise LLMAuthenticationError(
                        f"Gemini authentication failed ({status_code}).",
                        details={"status_code": status_code, "model": model_name},
                    ) from e

                # Non-retryable: Deterministic client error
                if is_client_error:
                    gemini_status = None
                    gemini_message = None

                    err_body = getattr(e, "body", None)
                    if isinstance(err_body, dict):
                        err_obj = err_body.get("error", {})
                        if isinstance(err_obj, dict):
                            gemini_status = err_obj.get("status")
                            gemini_message = err_obj.get("message")
                        elif isinstance(err_obj, str):
                            gemini_message = err_obj
                    elif isinstance(err_body, str):
                        try:
                            parsed_body = json.loads(err_body)
                            if isinstance(parsed_body, dict):
                                err_obj = parsed_body.get("error", {})
                                if isinstance(err_obj, dict):
                                    gemini_status = err_obj.get("status")
                                    gemini_message = err_obj.get("message")
                        except Exception:
                            gemini_message = err_body

                    resp = getattr(e, "response", None)
                    if resp is not None and not gemini_message:
                        try:
                            resp_json = resp.json()
                            if isinstance(resp_json, dict):
                                err_obj = resp_json.get("error", {})
                                if isinstance(err_obj, dict):
                                    gemini_status = gemini_status or err_obj.get("status")
                                    gemini_message = err_obj.get("message")
                        except Exception:
                            pass

                    if not gemini_status:
                        gemini_status = getattr(e, "status", None)
                    if not gemini_message:
                        gemini_message = getattr(e, "message", None) or str(e)

                    sanitized_status = _sanitize_diagnostic_text(gemini_status) or "INVALID_ARGUMENT"
                    sanitized_message = _sanitize_diagnostic_text(gemini_message)

                    err_details: Dict[str, Any] = {
                        "status_code": status_code or 400,
                        "gemini_status": sanitized_status,
                        "gemini_message": sanitized_message,
                        "model": model_name,
                        "stage": stage,
                        "is_structured": True,
                        "schema_name": getattr(response_schema, "__name__", "unknown"),
                        "payload_size_chars": total_payload_chars,
                        "generation_config": {
                            "temperature": cfg.temperature,
                            "top_p": cfg.top_p,
                            "max_output_tokens": cfg.max_output_tokens,
                        },
                    }

                    _record_attempt(
                        status="client_error",
                        error_category="client_error",
                        t_start=t0_call,
                        t_end=t1_call,
                        effective_timeout=effective_http_timeout,
                    )
                    _update_diagnostic(
                        status="client_error",
                        final_call_duration=t_call,
                    )

                    if diagnostics_enabled:
                        logger.warning(
                            "Gemini client error (HTTP %s): status=%s, model=%s, stage=%s, structured=True, payload_chars=%d, message=%s",
                            status_code or 400,
                            sanitized_status,
                            model_name,
                            stage,
                            total_payload_chars,
                            sanitized_message,
                        )

                    error_suffix = f": {sanitized_message}" if sanitized_message else "."
                    raise LLMError(
                        f"Gemini API client error ({status_code or 400}){error_suffix}",
                        details=err_details,
                    ) from e

                # Retryable: Rate limit
                if is_rate_limit:
                    att_rec = _record_attempt(
                        status="rate_limit",
                        error_category="rate_limit",
                        t_start=t0_call,
                        t_end=t1_call,
                        effective_timeout=effective_http_timeout,
                    )
                    _update_diagnostic(
                        status="rate_limit",
                        final_call_duration=t_call,
                    )
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMRateLimitError(
                            f"Gemini rate limit or quota exceeded ({status_code}).",
                            details={"status_code": status_code, "model": model_name},
                        ) from e
                    retry_after = self._extract_retry_after(e)
                    sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=retry_after)
                    if att_rec is not None:
                        att_rec["backoff_seconds"] = sleep_dur
                    continue

                # Retryable: Provider transient 5xx error
                if is_provider_error:
                    att_rec = _record_attempt(
                        status="server_error",
                        error_category="server_error",
                        t_start=t0_call,
                        t_end=t1_call,
                        effective_timeout=effective_http_timeout,
                    )
                    _update_diagnostic(
                        status="server_error",
                        final_call_duration=t_call,
                    )
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMProviderError(
                            f"Gemini upstream server error ({status_code}).",
                            details={"status_code": status_code, "model": model_name},
                        ) from e
                    retry_after = self._extract_retry_after(e)
                    sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=retry_after)
                    if att_rec is not None:
                        att_rec["backoff_seconds"] = sleep_dur
                    continue

                # Retryable: Network transport failure
                if is_transport_error:
                    att_rec = _record_attempt(
                        status="transport_error",
                        error_category="transport_error",
                        t_start=t0_call,
                        t_end=t1_call,
                        effective_timeout=effective_http_timeout,
                    )
                    _update_diagnostic(
                        status="transport_error",
                        final_call_duration=t_call,
                    )
                    if attempts >= max_attempts or (deadline - time.monotonic()) <= 0:
                        raise LLMError(
                            "Network transport error calling Gemini API.",
                            details={"model": model_name},
                        ) from e
                    sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=None)
                    if att_rec is not None:
                        att_rec["backoff_seconds"] = sleep_dur
                    continue

                # Non-retryable: Unexpected other exception
                _record_attempt(
                    status="unexpected_error",
                    error_category="unexpected_error",
                    t_start=t0_call,
                    t_end=t1_call,
                    effective_timeout=effective_http_timeout,
                )
                _update_diagnostic(
                    status="unexpected_error",
                    final_call_duration=t_call,
                )
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
                att_rec = _record_attempt(
                    status="empty_response",
                    error_category="empty_response",
                    t_start=t0_call,
                    t_end=t1_call,
                    effective_timeout=effective_http_timeout,
                )
                if attempts < max_attempts and (deadline - time.monotonic()) > 0:
                    sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=None)
                    if att_rec is not None:
                        att_rec["backoff_seconds"] = sleep_dur
                    continue
                _update_diagnostic(
                    status="empty_response",
                    final_call_duration=t_call,
                )
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
                t1_parse = time.monotonic() if diagnostics_enabled else 0.0
                t_parse = (t1_parse - t0_parse) if diagnostics_enabled else 0.0

                _record_attempt(
                    status="success",
                    error_category=None,
                    t_start=t0_call,
                    t_end=t1_parse,
                    effective_timeout=effective_http_timeout,
                )
                _update_diagnostic(
                    status="success",
                    final_call_duration=t_call,
                    final_parse_duration=t_parse,
                )
                return validated_result
            except LLMResponseValidationError as val_err:
                t1_parse = time.monotonic() if diagnostics_enabled else 0.0
                val_cat = getattr(val_err, "category", None) or "validation_error"
                val_details = getattr(val_err, "details", {})
                att_rec = _record_attempt(
                    status="validation_error",
                    error_category=val_cat,
                    t_start=t0_call,
                    t_end=t1_parse,
                    effective_timeout=effective_http_timeout,
                )
                field_paths_list = val_details.get("field_paths", []) if isinstance(val_details, dict) else []
                error_types_list = val_details.get("error_types", []) if isinstance(val_details, dict) else []
                constraints_list = val_details.get("constraints", []) if isinstance(val_details, dict) else []
                if att_rec is not None and isinstance(val_details, dict):
                    att_rec["validation_category"] = val_cat
                    att_rec["validation_field_paths"] = field_paths_list
                    att_rec["validation_schema"] = val_details.get("schema", response_schema.__name__)
                    att_rec["validation_categories"] = val_details.get("categories", [val_cat])
                    att_rec["validation_error_types"] = error_types_list
                    att_rec["validation_constraints"] = constraints_list
                schema_str = val_details.get("schema", getattr(response_schema, "__name__", "unknown")) if isinstance(val_details, dict) else getattr(response_schema, "__name__", "unknown")
                logger.warning(
                    "Gemini structured response validation failed (attempt %d/%d): schema=%s, category=%s, error_types=%s, field_paths=%s, constraints=%s",
                    attempts,
                    max_attempts,
                    schema_str,
                    val_cat,
                    error_types_list,
                    field_paths_list,
                    constraints_list,
                )

                if attempts < max_attempts and (deadline - time.monotonic()) > 0:
                    sleep_dur = _do_backoff(attempt_idx=attempts, retry_after=None)
                    if att_rec is not None:
                        att_rec["backoff_seconds"] = sleep_dur
                    continue
                _update_diagnostic(
                    status="validation_error",
                    final_call_duration=t_call,
                    final_parse_duration=(t1_parse - t0_parse) if diagnostics_enabled else 0.0,
                    final_validation_category=val_cat,
                    final_validation_field_paths=field_paths_list,
                    final_validation_error_types=error_types_list,
                    final_validation_constraints=constraints_list,
                )
                logger.error(
                    "Gemini structured response validation exhausted all %d attempts: schema=%s, category=%s, error_types=%s, field_paths=%s, constraints=%s",
                    max_attempts,
                    schema_str,
                    val_cat,
                    error_types_list,
                    field_paths_list,
                    constraints_list,
                )
                raise

        raise LLMResponseValidationError("Gemini structured output generation failed all retry attempts.")
