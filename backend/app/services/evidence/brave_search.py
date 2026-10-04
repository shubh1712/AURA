"""AURA Brave Web Search Provider Implementation.

Integrates with the Brave Web Search API (https://api.search.brave.com/res/v1/web/search)
to retrieve external factual evidence for AURA decision analysis.

Guarantees:
- Strictly implements SearchProvider abstraction returning SearchResultItem domain DTOs.
- Real HTTP communication encapsulated behind injected or configured httpx.Client.
- Comprehensive typed error mapping (SearchAuthenticationError, SearchRateLimitError, SearchTimeoutError, SearchNetworkError, SearchResponseError).
- Never leaks API keys in logs, repr, exception messages, test output, or API responses.
- Initial implementation maps url, title, and description (snippet); raw_content is None.
- No reliance on Brave LLM Context, Answers, or extra_snippets.
- Zero network socket calls during normal automated pytest runs (tested via mocked transport).
"""

from datetime import date
import json
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.services.evidence.search_provider import (
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProvider,
    SearchProviderError,
    SearchRateLimitError,
    SearchResponseError,
    SearchResultItem,
    SearchTimeoutError,
)

BRAVE_SEARCH_API_ENDPOINT: str = "https://api.search.brave.com/res/v1/web/search"


def _clean_html_tags(text: str) -> str:
    """Removes HTML highlighting tags (e.g. <strong>, </strong>) if present in Brave snippets."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return " ".join(clean.strip().split())


class BraveSearchProvider(SearchProvider):
    """Concrete SearchProvider implementation communicating with Brave Web Search API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        http_client: Optional[httpx.Client] = None,
        api_endpoint: str = BRAVE_SEARCH_API_ENDPOINT,
        search_lang: str = "en",
    ) -> None:
        """Initializes BraveSearchProvider.

        Args:
            api_key: Optional Brave Search API key. Defaults to BRAVE_SEARCH_API_KEY from settings/env.
            timeout: Request timeout in seconds (default 10.0s).
            http_client: Optional pre-configured httpx.Client (used for mocking transport and connection pooling).
            api_endpoint: Target Brave Web Search endpoint URL.
            search_lang: Search language filter (defaults to 'en').
        """
        if api_key is not None:
            self._api_key: Optional[str] = api_key.strip() if api_key.strip() else None
        else:
            env_key = settings.BRAVE_SEARCH_API_KEY or os.environ.get("BRAVE_SEARCH_API_KEY")
            self._api_key = env_key.strip() if env_key and env_key.strip() else None

        self.timeout = timeout
        self._http_client = http_client
        self.api_endpoint = api_endpoint
        self.search_lang = search_lang

    def __repr__(self) -> str:
        """Sanitized string representation that never exposes the API key."""
        return f"BraveSearchProvider(configured={self._api_key is not None}, endpoint='{self.api_endpoint}')"

    def __str__(self) -> str:
        return self.__repr__()

    def _get_api_key(self) -> str:
        """Retrieves and validates API key prior to search execution.

        Raises:
            SearchAuthenticationError: If API key is missing or empty.
        """
        if not self._api_key:
            raise SearchAuthenticationError(
                "Brave Search API key is not configured. Set BRAVE_SEARCH_API_KEY in your environment or .env file."
            )
        return self._api_key

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[SearchResultItem]:
        """Executes search query against Brave Web Search API.

        Args:
            query: Non-empty search query string.
            max_results: Maximum results to return (1..20 supported by Brave Web Search).

        Returns:
            List of SearchResultItem instances (up to max_results). Returns [] on 0 results.

        Raises:
            ValueError: If query is empty or max_results <= 0.
            SearchAuthenticationError: On 401/403 or missing API credentials.
            SearchRateLimitError: On 429 rate limit exceeded.
            SearchTimeoutError: On request timeout.
            SearchNetworkError: On connection/network error.
            SearchResponseError: On 5xx, invalid JSON, or malformed response structure.
            SearchProviderError: On other provider failures.
        """
        # 1. Validate parameters
        cleaned_query = self._validate_search_params(query, max_results)

        # 2. Validate API key
        api_key = self._get_api_key()

        # 3. Construct headers and query parameters
        headers = {
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        # Brave API accepts count between 1 and 20
        brave_count = min(max(max_results, 1), 20)
        params: Dict[str, Any] = {
            "q": cleaned_query,
            "count": brave_count,
            "search_lang": self.search_lang,
        }

        # 4. Execute HTTP request
        try:
            if self._http_client is not None:
                response = self._http_client.get(
                    self.api_endpoint,
                    headers=headers,
                    params=params,
                    timeout=self.timeout,
                )
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(
                        self.api_endpoint,
                        headers=headers,
                        params=params,
                    )
        except httpx.TimeoutException as err:
            raise SearchTimeoutError(
                f"Brave Search request timed out for query '{cleaned_query}'."
            ) from err
        except httpx.NetworkError as err:
            raise SearchNetworkError(
                f"Brave Search network error: {type(err).__name__}."
            ) from err
        except Exception as err:
            raise SearchProviderError(
                f"Brave Search HTTP transport error: {type(err).__name__}."
            ) from err

        # 5. Handle HTTP status codes
        if response.status_code in (401, 403):
            raise SearchAuthenticationError(
                f"Brave Search authentication failed (HTTP {response.status_code}): Invalid or unauthorized API key."
            )
        elif response.status_code == 429:
            raise SearchRateLimitError(
                "Brave Search rate limit exceeded (HTTP 429): Quota or throughput limit reached."
            )
        elif response.status_code >= 500:
            raise SearchResponseError(
                f"Brave Search provider error (HTTP {response.status_code}): Upstream server error."
            )
        elif response.status_code != 200:
            raise SearchProviderError(
                f"Brave Search request failed with unexpected HTTP status {response.status_code}."
            )

        # 6. Parse JSON payload
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as err:
            raise SearchResponseError(
                "Brave Search returned malformed non-JSON response."
            ) from err

        if not isinstance(data, dict):
            raise SearchResponseError(
                f"Brave Search response must be a JSON object, got {type(data).__name__}."
            )

        # 7. Extract web results
        web = data.get("web")
        if web is None:
            # Successful response with zero web results
            return []

        if not isinstance(web, dict):
            raise SearchResponseError(
                f"Brave Search response 'web' field must be an object, got {type(web).__name__}."
            )

        raw_results = web.get("results")
        if raw_results is None:
            return []

        if not isinstance(raw_results, list):
            raise SearchResponseError(
                f"Brave Search response 'results' field must be a list, got {type(raw_results).__name__}."
            )

        # 8. Map to SearchResultItem domain DTOs
        results: List[SearchResultItem] = []
        for entry in raw_results:
            if not isinstance(entry, dict):
                raise SearchResponseError(
                    f"Brave Search result entry must be an object, got {type(entry).__name__}."
                )

            url = entry.get("url")
            raw_title = entry.get("title")
            raw_description = entry.get("description")

            if not url or not isinstance(url, str) or not url.strip():
                raise SearchResponseError("Brave Search result missing valid 'url' field.")
            if not raw_title or not isinstance(raw_title, str) or not raw_title.strip():
                raise SearchResponseError("Brave Search result missing valid 'title' field.")
            if not raw_description or not isinstance(raw_description, str) or not raw_description.strip():
                raise SearchResponseError("Brave Search result missing valid 'description' field.")

            clean_title = _clean_html_tags(raw_title)
            clean_snippet = _clean_html_tags(raw_description)

            if not clean_title:
                raise SearchResponseError("Brave Search result contains empty 'title' after stripping HTML tags.")
            if not clean_snippet:
                raise SearchResponseError("Brave Search result contains empty 'description' after stripping HTML tags.")

            # Map publisher without inference (from profile.name or profile.long_name if present)
            publisher: Optional[str] = None
            profile = entry.get("profile")
            if isinstance(profile, dict):
                name = profile.get("name") or profile.get("long_name")
                if isinstance(name, str) and name.strip():
                    publisher = name.strip()[:150]

            # Map published_date without inference (from page_age ISO date if present)
            published_date: Optional[date] = None
            page_age = entry.get("page_age")
            if isinstance(page_age, str) and len(page_age) >= 10:
                try:
                    published_date = date.fromisoformat(page_age[:10])
                except (ValueError, TypeError):
                    published_date = None

            try:
                item = SearchResultItem(
                    url=url.strip(),
                    title=clean_title[:300],
                    snippet=clean_snippet,
                    publisher=publisher,
                    published_date=published_date,
                    raw_content=None,
                )
            except Exception as exc:
                raise SearchResponseError(
                    f"Failed to map Brave Search result item: {type(exc).__name__}."
                ) from exc
            results.append(item)

            if len(results) >= max_results:
                break

        return results
