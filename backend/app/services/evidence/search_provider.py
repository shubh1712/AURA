"""AURA Search Provider Abstraction.

Provides a decoupled, provider-agnostic interface for external evidence search
and retrieval, along with a deterministic in-memory fake for automated testing.

This layer has ZERO knowledge of:
- Specific search engine vendors (Google, Tavily, Bing, Serper)
- EvidenceItem or Source domain entities
- DecisionModel or QuestionUnderstandingEngine
- LLM generation or prompts
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------------------
# 1. Typed Exceptions
# ------------------------------------------------------------------------------

class SearchProviderError(Exception):
    """Base exception for search provider failures."""
    pass


class UnknownSearchQueryError(SearchProviderError):
    """Raised in strict mode when an unregistered query is passed to FakeSearchProvider."""
    pass


class SearchAuthenticationError(SearchProviderError):
    """Raised when search provider authentication fails (e.g. 401, 403, missing API key)."""
    pass


class SearchRateLimitError(SearchProviderError):
    """Raised when search provider rate limits or quotas are exceeded (e.g. 429)."""
    pass


class SearchTimeoutError(SearchProviderError):
    """Raised when search provider requests time out."""
    pass


class SearchNetworkError(SearchProviderError):
    """Raised when network, connection, or transport errors occur."""
    pass


class SearchResponseError(SearchProviderError):
    """Raised when provider returns server errors (5xx), invalid JSON, or malformed structures."""
    pass


# ------------------------------------------------------------------------------
# 2. Retrieval DTO: SearchResultItem
# ------------------------------------------------------------------------------

class SearchResultItem(BaseModel):
    """Provider-neutral raw search result item.

    Represents a raw retrieval artifact prior to normalization into canonical Source
    or EvidenceItem domain entities.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="URL of the retrieved document.",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Title or headline of the search result.",
    )
    snippet: str = Field(
        ...,
        min_length=1,
        description="Text snippet or abstract from the search result.",
    )
    publisher: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Publishing organization, publication name, or domain.",
    )
    published_date: Optional[date] = Field(
        default=None,
        description="Typed publication date if reported by the provider.",
    )
    raw_content: Optional[str] = Field(
        default=None,
        description="Optional full text or extracted page markdown if retrieved.",
    )


# ------------------------------------------------------------------------------
# 3. SearchProvider Interface
# ------------------------------------------------------------------------------

class SearchProvider(ABC):
    """Abstract interface for external evidence search and retrieval."""

    @staticmethod
    def _validate_search_params(query: str, max_results: int) -> str:
        """Validates query and max_results parameters.

        Raises:
            ValueError: If query is empty or max_results <= 0.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query cannot be empty or contain only whitespace.")
        if not isinstance(max_results, int) or max_results <= 0:
            raise ValueError(f"max_results must be a positive integer greater than 0, got {max_results}.")
        return " ".join(query.strip().split())

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[SearchResultItem]:
        """Executes a search query and returns structured SearchResultItem objects.

        Args:
            query: Non-empty search query string.
            max_results: Positive integer maximum number of results to return.

        Returns:
            List of SearchResultItem instances (up to max_results).

        Raises:
            ValueError: If query is empty or max_results <= 0.
            SearchProviderError: On provider communication failure.
        """
        pass


# ------------------------------------------------------------------------------
# 4. In-Memory Fake Search Provider for Testing
# ------------------------------------------------------------------------------

class FakeSearchProvider(SearchProvider):
    """Deterministic in-memory fake search provider for automated testing.

    Guarantees:
    - Zero external network or socket calls.
    - Deterministic query matching with normalized whitespace and casing.
    - Full telemetry recording of all queries in `recorded_queries`.
    - Returns empty list `[]` for unknown queries by default, or raises
      `UnknownSearchQueryError` when `strict=True`.
    - Returns deep copies of results to ensure mutation safety.
    """

    @staticmethod
    def _normalize_query_key(query: str) -> str:
        """Normalizes query key by stripping, lower-casing, and collapsing whitespace."""
        return " ".join(query.strip().lower().split())

    def __init__(
        self,
        canned_results: Optional[Dict[str, List[SearchResultItem]]] = None,
        default_results: Optional[List[SearchResultItem]] = None,
        strict: bool = False,
    ) -> None:
        """Initializes FakeSearchProvider.

        Args:
            canned_results: Optional dictionary mapping query strings to lists of SearchResultItem.
            default_results: Optional fallback list of SearchResultItem returned when query is not canned.
            strict: If True, unexpected queries raise UnknownSearchQueryError instead of returning default/empty.
        """
        self.strict = strict
        self.default_results = (
            [item.model_copy(deep=True) for item in default_results]
            if default_results is not None
            else None
        )
        self._canned_results: Dict[str, List[SearchResultItem]] = {}
        if canned_results:
            for k, v in canned_results.items():
                norm_k = self._normalize_query_key(k)
                self._canned_results[norm_k] = [item.model_copy(deep=True) for item in v]

        self._canned_error: Optional[Exception] = None
        self.recorded_queries: List[str] = []

    @property
    def queries_executed(self) -> List[str]:
        """Telemetry alias for recorded_queries."""
        return self.recorded_queries

    def register_canned_results(self, query: str, results: List[SearchResultItem]) -> None:
        """Registers canned search results for a specific query."""
        norm_k = self._normalize_query_key(query)
        self._canned_results[norm_k] = [item.model_copy(deep=True) for item in results]

    def register_error(self, error: Exception) -> None:
        """Forces the next search call to raise the specified exception."""
        self._canned_error = error

    def clear(self) -> None:
        """Clears canned results, errors, and recorded query history."""
        self._canned_results.clear()
        self._canned_error = None
        self.recorded_queries.clear()

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[SearchResultItem]:
        """Executes simulated search matching registered canned queries."""
        # 1. Validate parameters
        cleaned_query = self._validate_search_params(query, max_results)

        # 2. Record telemetry
        self.recorded_queries.append(cleaned_query)

        # 3. Simulate programmed error if present
        if self._canned_error is not None:
            err = self._canned_error
            self._canned_error = None
            raise err

        # 4. Lookup normalized query
        norm_key = self._normalize_query_key(cleaned_query)
        if norm_key in self._canned_results:
            results = self._canned_results[norm_key]
            # Enforce max_results and return deep copies for mutation safety
            sliced = results[:max_results]
            return [item.model_copy(deep=True) for item in sliced]

        # 5. Handle fallback default results if configured
        if self.default_results is not None:
            sliced = self.default_results[:max_results]
            return [item.model_copy(deep=True) for item in sliced]

        # 6. Handle unregistered queries
        if self.strict:
            raise UnknownSearchQueryError(
                f"Unexpected search query in strict mode: '{cleaned_query}'. "
                f"Registered queries: {list(self._canned_results.keys())}"
            )

        return []
