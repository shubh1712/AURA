"""AURA Evidence Retriever.

Executes external-research queries through an injected SearchProvider abstraction.

Guarantees:
- Only EXTERNAL_RESEARCH requirements may invoke SearchProvider.
- INTERNAL_DATA, USER_CLARIFICATION, and DETERMINISTIC_CALCULATION never invoke SearchProvider.
- Executes only explicitly suggested queries; never invents queries or calls an LLM.
- Preserves requirement-to-query-to-results provenance in RequirementSearchResults.
- Deduplicates identical queries within the same requirement.
- Retains query execution records even when the search provider returns empty results ([]).
- Propagates search provider failures without converting errors to empty results.
- Zero LLM dependencies and zero external network calls.
"""

from typing import List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import EvidenceKind, EvidenceRequirement
from app.services.evidence.search_provider import (
    SearchProvider,
    SearchProviderError,
    SearchResultItem,
)


# ------------------------------------------------------------------------------
# 1. Typed Exceptions
# ------------------------------------------------------------------------------

class EvidenceRetrieverError(SearchProviderError):
    """Raised when an error occurs during evidence retrieval."""

    def __init__(
        self,
        message: str,
        requirement_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.requirement_id = requirement_id
        self.query = query


# ------------------------------------------------------------------------------
# 2. Retrieval Result Model
# ------------------------------------------------------------------------------

class RequirementSearchResults(BaseModel):
    """Associates search results with a specific EvidenceRequirement and query.

    Preserves exact provenance from requirement_id -> query -> SearchResultItem[].
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    requirement_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the parent EvidenceRequirement.",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="Exact search query executed.",
    )
    results: List[SearchResultItem] = Field(
        default_factory=list,
        description="Raw search results returned by provider for this query.",
    )


# ------------------------------------------------------------------------------
# 3. EvidenceRetriever Implementation
# ------------------------------------------------------------------------------

class EvidenceRetriever:
    """Executes external-research queries through an injected SearchProvider."""

    def __init__(
        self,
        search_provider: SearchProvider,
        max_results_per_query: int = 5,
    ) -> None:
        """Initializes EvidenceRetriever with an injected SearchProvider.

        Args:
            search_provider: Injected SearchProvider abstraction instance.
            max_results_per_query: Positive integer maximum results per query (defaults to 5).

        Raises:
            TypeError: If search_provider is not an instance of SearchProvider.
            ValueError: If max_results_per_query <= 0 or not an integer.
        """
        if not isinstance(search_provider, SearchProvider):
            raise TypeError(
                f"search_provider must implement SearchProvider abstraction, got {type(search_provider).__name__}."
            )
        if isinstance(max_results_per_query, bool) or not isinstance(max_results_per_query, int) or max_results_per_query <= 0:
            raise ValueError(
                f"max_results_per_query must be a positive integer greater than 0, got {max_results_per_query}."
            )

        self.search_provider = search_provider
        self.max_results_per_query = max_results_per_query

    def retrieve(
        self,
        requirements: List[EvidenceRequirement],
    ) -> List[RequirementSearchResults]:
        """Executes search queries for all EXTERNAL_RESEARCH requirements.

        Args:
            requirements: List of EvidenceRequirement objects to evaluate.

        Returns:
            List of RequirementSearchResults preserving requirement_id, query, and results.

        Raises:
            EvidenceRetrieverError: If SearchProvider fails during retrieval.
        """
        retrieval_records: List[RequirementSearchResults] = []

        for req in requirements:
            # Routing Policy: ONLY EXTERNAL_RESEARCH may invoke search
            if req.kind != EvidenceKind.EXTERNAL_RESEARCH:
                continue

            # Query Policy: If suggested_queries is empty, do NOT search, do NOT invent queries
            if not req.suggested_queries:
                continue

            # Deduplication Strategy:
            # Avoid executing the exact same normalized query more than once for the SAME requirement.
            seen_norm_queries: Set[str] = set()

            for raw_query in req.suggested_queries:
                if not raw_query or not raw_query.strip():
                    continue

                norm_key = " ".join(raw_query.strip().lower().split())
                if norm_key in seen_norm_queries:
                    continue
                seen_norm_queries.add(norm_key)

                # Clean query for search provider execution
                clean_query = " ".join(raw_query.strip().split())

                try:
                    search_results = self.search_provider.search(
                        query=clean_query,
                        max_results=self.max_results_per_query,
                    )
                except SearchProviderError as err:
                    raise EvidenceRetrieverError(
                        f"Search provider failure for requirement '{req.id}' and query '{clean_query}': {err}",
                        requirement_id=req.id,
                        query=clean_query,
                    ) from err

                # Result Provenance & Empty Results:
                # Preserve the record even if search_results is []
                record = RequirementSearchResults(
                    requirement_id=req.id,
                    query=clean_query,
                    results=search_results,
                )
                retrieval_records.append(record)

        return retrieval_records
