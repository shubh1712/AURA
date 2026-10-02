"""AURA Gemini LLM Client Implementation.

Provides a concrete implementation of LLMClient communicating with Google's
Gemini API using standard HTTP transport and native structured output modes.
All Gemini SDK or REST dependencies remain strictly encapsulated within
this service module.
"""

import os
from typing import Any, Dict, List, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

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

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


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
        self.default_model = default_model or settings.GEMINI_MODEL or "gemini-2.5-flash"
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

        # Build standard Gemini REST payload
        endpoint = f"{GEMINI_BASE_URL}/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

        generation_config: Dict[str, Any] = {
            "temperature": cfg.temperature,
            "responseMimeType": "application/json",
        }
        if cfg.top_p is not None:
            generation_config["topP"] = cfg.top_p
        if cfg.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = cfg.max_output_tokens

        body: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": generation_config,
        }

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}],
            }

        # Execute HTTP request with configured timeout
        client = self._http_client or httpx.Client(timeout=cfg.timeout_seconds)
        try:
            response = client.post(endpoint, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Gemini API request timed out after {cfg.timeout_seconds}s.",
                details={"model": model_name, "timeout": cfg.timeout_seconds},
            ) from e
        except httpx.RequestError as e:
            raise LLMError(
                f"Network transport error calling Gemini API: {e}",
                details={"model": model_name, "error": str(e)},
            ) from e
        finally:
            # If we created a temporary client, close it
            if self._http_client is None:
                client.close()

        # Handle HTTP status codes
        if response.status_code in (401, 403):
            raise LLMAuthenticationError(
                f"Gemini authentication failed ({response.status_code}): {response.text}",
                details={"status_code": response.status_code, "body": response.text},
            )
        elif response.status_code == 429:
            raise LLMRateLimitError(
                f"Gemini rate limit or quota exceeded ({response.status_code}): {response.text}",
                details={"status_code": response.status_code, "body": response.text},
            )
        elif response.status_code >= 500:
            raise LLMProviderError(
                f"Gemini upstream server error ({response.status_code}): {response.text}",
                details={"status_code": response.status_code, "body": response.text},
            )
        elif response.status_code >= 400:
            raise LLMError(
                f"Gemini API client error ({response.status_code}): {response.text}",
                details={"status_code": response.status_code, "body": response.text},
            )

        # Parse response body and extract content
        try:
            resp_json = response.json()
        except Exception as e:
            raise LLMResponseValidationError(
                f"Gemini returned non-JSON HTTP response body: {response.text[:200]}",
                details={"raw_body": response.text[:500]},
            ) from e

        candidates = resp_json.get("candidates") or []
        if not candidates:
            # Check for safety blocks or empty candidate list
            prompt_feedback = resp_json.get("promptFeedback", {})
            raise LLMResponseValidationError(
                f"Gemini returned no candidates. Prompt feedback: {prompt_feedback}",
                details={"response": resp_json},
            )

        candidate = candidates[0]
        content_parts = candidate.get("content", {}).get("parts", [])
        if not content_parts or not content_parts[0].get("text"):
            raise LLMResponseValidationError(
                "Gemini candidate returned empty text parts.",
                details={"candidate": candidate},
            )

        raw_text = content_parts[0]["text"]

        # Delegate parsing, normalization, and Pydantic validation to StructuredOutputParser
        return parse_and_validate_structured_output(
            raw_text=raw_text,
            response_schema=response_schema,
            raw_user_prompt=prompt,
        )
