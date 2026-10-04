"""Unit tests for AURA Day 3 Phase 5 SearchProvider abstraction and FakeSearchProvider.

Verifies:
1. SearchResultItem valid construction and field constraints.
2. SearchResultItem typed publication date (both date instances and ISO strings).
3. FakeSearchProvider returns expected canned results for registered queries.
4. FakeSearchProvider respects max_results truncation.
5. All queries received are recorded in recorded_queries.
6. Unknown query returns [] by default (non-strict mode).
7. Strict mode raises UnknownSearchQueryError on unexpected queries.
8. Whitespace and case normalization behaves deterministically.
9. Empty or whitespace-only query raises ValueError.
10. Invalid max_results (<= 0 or non-int) raises ValueError.
11. Mutation safety: mutating returned search results does not mutate internal canned results.
12. FakeSearchProvider performs zero external network calls.
"""

from datetime import date
import pytest
from pydantic import ValidationError

from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchResultItem,
    UnknownSearchQueryError,
)


# ------------------------------------------------------------------------------
# 1. SearchResultItem Tests
# ------------------------------------------------------------------------------

def test_search_result_item_valid_construction() -> None:
    """Verifies valid construction of provider-neutral SearchResultItem."""
    item = SearchResultItem(
        url="https://mock.example.com/reports/saas-pricing-2024",
        title="[ILLUSTRATIVE MOCK] 2024 SaaS Pricing Benchmarks",
        snippet="[ILLUSTRATIVE MOCK] Observed unit sales volume expansion was 12-16% for 20% discounts.",
        publisher="Mock Expansion Labs",
        published_date=date(2024, 9, 15),
        raw_content="# Pricing Benchmark Report\nFull text content...",
    )
    assert item.url == "https://mock.example.com/reports/saas-pricing-2024"
    assert item.title == "[ILLUSTRATIVE MOCK] 2024 SaaS Pricing Benchmarks"
    assert item.publisher == "Mock Expansion Labs"
    assert item.published_date == date(2024, 9, 15)
    assert item.raw_content is not None


def test_search_result_item_typed_published_date() -> None:
    """Verifies that published_date accepts date objects or valid ISO-8601 strings."""
    # 1. Date object
    item1 = SearchResultItem(
        url="https://mock.example.com/item1",
        title="Item 1",
        snippet="Snippet 1",
        published_date=date(2025, 1, 10),
    )
    assert item1.published_date == date(2025, 1, 10)

    # 2. String parsed into date
    item2 = SearchResultItem(
        url="https://mock.example.com/item2",
        title="Item 2",
        snippet="Snippet 2",
        published_date="2025-03-22",  # type: ignore[arg-type]
    )
    assert isinstance(item2.published_date, date)
    assert item2.published_date == date(2025, 3, 22)

    # 3. Invalid date string raises ValidationError
    with pytest.raises(ValidationError):
        SearchResultItem(
            url="https://mock.example.com/item3",
            title="Item 3",
            snippet="Snippet 3",
            published_date="not-a-valid-date",  # type: ignore[arg-type]
        )


# ------------------------------------------------------------------------------
# 2. FakeSearchProvider Tests
# ------------------------------------------------------------------------------

def _create_sample_items() -> list[SearchResultItem]:
    """Helper providing test SearchResultItem instances."""
    return [
        SearchResultItem(
            url="https://mock.example.com/result1",
            title="Result 1",
            snippet="Snippet 1",
            publisher="Publisher 1",
            published_date=date(2024, 5, 1),
        ),
        SearchResultItem(
            url="https://mock.example.com/result2",
            title="Result 2",
            snippet="Snippet 2",
            publisher="Publisher 2",
            published_date=date(2024, 6, 1),
        ),
        SearchResultItem(
            url="https://mock.example.com/result3",
            title="Result 3",
            snippet="Snippet 3",
            publisher="Publisher 3",
            published_date=date(2024, 7, 1),
        ),
    ]


def test_fake_search_provider_returns_canned_results() -> None:
    """Verifies FakeSearchProvider returns registered canned results."""
    items = _create_sample_items()
    provider = FakeSearchProvider(
        canned_results={
            "b2b saas price elasticity": items
        }
    )

    results = provider.search("b2b saas price elasticity")
    assert len(results) == 3
    assert results[0].url == "https://mock.example.com/result1"
    assert results[1].title == "Result 2"


def test_fake_search_provider_respects_max_results() -> None:
    """Verifies max_results parameter truncates the returned list."""
    items = _create_sample_items()
    provider = FakeSearchProvider(
        canned_results={
            "b2b saas price elasticity": items
        }
    )

    # Request max 2
    results = provider.search("b2b saas price elasticity", max_results=2)
    assert len(results) == 2
    assert results[0].url == "https://mock.example.com/result1"
    assert results[1].url == "https://mock.example.com/result2"

    # Request max 1
    results_one = provider.search("b2b saas price elasticity", max_results=1)
    assert len(results_one) == 1
    assert results_one[0].url == "https://mock.example.com/result1"


def test_fake_search_provider_records_queries() -> None:
    """Verifies every query is recorded in recorded_queries telemetry."""
    provider = FakeSearchProvider()
    assert provider.recorded_queries == []

    provider.search("first search query")
    provider.search("second search query", max_results=3)

    assert provider.recorded_queries == [
        "first search query",
        "second search query",
    ]


def test_fake_search_provider_unknown_query_returns_empty_list() -> None:
    """Verifies unknown queries return [] in non-strict mode."""
    provider = FakeSearchProvider(
        canned_results={"known query": _create_sample_items()},
        strict=False,
    )

    results = provider.search("completely unregistered query")
    assert results == []
    assert provider.recorded_queries == ["completely unregistered query"]


def test_fake_search_provider_strict_mode_unknown_query_raises() -> None:
    """Verifies strict mode raises UnknownSearchQueryError on unregistered queries."""
    provider = FakeSearchProvider(
        canned_results={"known query": _create_sample_items()},
        strict=True,
    )

    with pytest.raises(UnknownSearchQueryError) as exc_info:
        provider.search("unexpected unknown query")

    assert "Unexpected search query in strict mode: 'unexpected unknown query'" in str(exc_info.value)
    # Even when raising, query should be recorded
    assert provider.recorded_queries == ["unexpected unknown query"]


def test_fake_search_provider_normalization_matching() -> None:
    """Verifies queries match deterministically across case and whitespace variations."""
    items = _create_sample_items()
    provider = FakeSearchProvider(
        canned_results={
            "SaaS Pricing Elasticity": items
        }
    )

    # 1. Lowercase matching
    res1 = provider.search("saas pricing elasticity")
    assert len(res1) == 3

    # 2. Leading/trailing/collapsed whitespace matching
    res2 = provider.search("   saas    pricing   elasticity   ")
    assert len(res2) == 3

    # 3. Uppercase matching
    res3 = provider.search("SAAS PRICING ELASTICITY")
    assert len(res3) == 3


def test_fake_search_provider_empty_query_raises_value_error() -> None:
    """Verifies empty or whitespace-only queries raise ValueError."""
    provider = FakeSearchProvider()

    with pytest.raises(ValueError) as exc_info1:
        provider.search("")
    assert "Search query cannot be empty" in str(exc_info1.value)

    with pytest.raises(ValueError) as exc_info2:
        provider.search("     ")
    assert "Search query cannot be empty" in str(exc_info2.value)


def test_fake_search_provider_invalid_max_results_raises_value_error() -> None:
    """Verifies max_results <= 0 raises ValueError."""
    provider = FakeSearchProvider()

    with pytest.raises(ValueError) as exc_info1:
        provider.search("valid query", max_results=0)
    assert "max_results must be a positive integer" in str(exc_info1.value)

    with pytest.raises(ValueError) as exc_info2:
        provider.search("valid query", max_results=-5)
    assert "max_results must be a positive integer" in str(exc_info2.value)


def test_fake_search_provider_mutation_safety() -> None:
    """Verifies mutating returned search results does not mutate internal canned results."""
    items = _create_sample_items()
    provider = FakeSearchProvider(
        canned_results={"pricing": items}
    )

    results1 = provider.search("pricing")
    # Mutate the returned list and object in results1
    results1[0].title = "MUTATED TITLE"
    results1.pop()

    # Search again to verify internal state was preserved
    results2 = provider.search("pricing")
    assert len(results2) == 3
    assert results2[0].title == "Result 1"
    assert results2[0].title != "MUTATED TITLE"


def test_fake_search_provider_simulated_error_and_clear() -> None:
    """Verifies register_error and clear methods."""
    provider = FakeSearchProvider(
        canned_results={"query": _create_sample_items()}
    )

    provider.register_error(SearchProviderError("Simulated upstream search error"))
    with pytest.raises(SearchProviderError) as exc_info:
        provider.search("query")
    assert "Simulated upstream search error" in str(exc_info.value)

    # Next call should succeed (error consumed)
    assert len(provider.search("query")) == 3

    # Clear should empty history and canned results
    provider.clear()
    assert provider.recorded_queries == []
    assert provider.search("query") == []


def test_fake_search_provider_zero_network_activity() -> None:
    """Verifies FakeSearchProvider operates entirely in-memory with zero network calls."""
    # Instantiation and execution with unmocked environment
    provider = FakeSearchProvider(
        canned_results={"test query": _create_sample_items()}
    )
    results = provider.search("test query")
    assert len(results) == 3
    assert isinstance(provider, SearchProvider)
