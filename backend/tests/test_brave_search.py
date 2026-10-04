"""Comprehensive mocked unit tests for BraveSearchProvider.

Verifies:
1. Successful Brave response maps to SearchResultItem[].
2. Correct URL mapping.
3. Correct title mapping (including HTML tag cleanup).
4. Description maps to snippet (including HTML tag cleanup).
5. Empty results in Brave response returns [].
6. Missing optional fields (publisher, page_age) map safely to None.
7. max_results parameter is respected.
8. HTTP 401 raises SearchAuthenticationError (and SearchProviderError).
9. HTTP 403 raises SearchAuthenticationError.
10. HTTP 429 raises SearchRateLimitError.
11. HTTP 5xx raises SearchResponseError.
12. Timeout raises SearchTimeoutError.
13. Malformed non-JSON response raises SearchResponseError.
14. Malformed response structure raises SearchResponseError.
15. API key never appears in repr, str, or exception messages.
16. FakeSearchProvider behavior remains completely unchanged.
17. Missing API key raises SearchAuthenticationError.
18. Integration with EvidenceRetriever.

Guarantees:
- Zero real network socket calls (mocked HTTP transport).
"""

from datetime import date
import json
from typing import Any, Dict, List
import httpx
import pytest

from app.schemas.evidence import DecisionEntityType, EvidenceKind, EvidenceRequirement
from app.services.evidence.brave_search import (
    BRAVE_SEARCH_API_ENDPOINT,
    BraveSearchProvider,
)
from app.services.evidence.retriever import EvidenceRetriever
from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProvider,
    SearchProviderError,
    SearchRateLimitError,
    SearchResponseError,
    SearchResultItem,
    SearchTimeoutError,
)

SAMPLE_API_KEY = "BSA_test_secret_token_123456789"

SAMPLE_BRAVE_RESPONSE: Dict[str, Any] = {
    "query": {
        "original": "B2B SaaS pricing research",
        "show_strict_warning": False,
        "is_navigational": False,
    },
    "web": {
        "total": 2,
        "results": [
            {
                "title": "SaaS Pricing <strong>Benchmarks</strong> 2024",
                "url": "https://example.com/reports/saas-pricing-2024",
                "description": "Comprehensive benchmark study on <strong>SaaS pricing</strong> elasticity across 240 companies.",
                "page_age": "2024-05-15T12:00:00Z",
                "profile": {
                    "name": "SaaS Insights Lab",
                    "long_name": "SaaS Insights Laboratory Institute",
                    "url": "https://example.com",
                },
            },
            {
                "title": "Competitor Discounting Dynamics",
                "url": "https://example.org/analysis/discounting",
                "description": "Analysis of customer churn and revenue retention when lowering prices.",
                "page_age": "2024-06-20",
                "profile": {
                    "name": "Economics Quarterly",
                },
            },
        ],
    },
}


def create_mock_client(handler: Any) -> httpx.Client:
    """Helper to build an httpx.Client with MockTransport."""
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


# ------------------------------------------------------------------------------
# 1-4: Successful Mapping Tests
# ------------------------------------------------------------------------------

def test_successful_brave_response_maps_to_search_result_items() -> None:
    """1. Successful Brave response returns valid SearchResultItem list."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Subscription-Token") == SAMPLE_API_KEY
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("B2B SaaS pricing research", max_results=5)

    assert isinstance(results, list)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, SearchResultItem)
        assert r.raw_content is None


def test_correct_url_mapping() -> None:
    """2. Validates accurate URL mapping."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("pricing research", max_results=2)

    assert results[0].url == "https://example.com/reports/saas-pricing-2024"
    assert results[1].url == "https://example.org/analysis/discounting"


def test_correct_title_mapping() -> None:
    """3. Validates title mapping with HTML tag stripping."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("pricing research", max_results=2)

    # HTML <strong> tags are cleaned
    assert results[0].title == "SaaS Pricing Benchmarks 2024"
    assert results[1].title == "Competitor Discounting Dynamics"


def test_description_to_snippet_mapping() -> None:
    """4. Validates description to snippet mapping with HTML tag stripping."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("pricing research", max_results=2)

    # HTML <strong> tags cleaned from snippet
    assert results[0].snippet == "Comprehensive benchmark study on SaaS pricing elasticity across 240 companies."
    assert results[1].snippet == "Analysis of customer churn and revenue retention when lowering prices."
    assert results[0].publisher == "SaaS Insights Lab"
    assert results[0].published_date == date(2024, 5, 15)
    assert results[1].published_date == date(2024, 6, 20)


# ------------------------------------------------------------------------------
# 5-7: Edge Cases, Optional Fields, Truncation
# ------------------------------------------------------------------------------

def test_empty_results_returns_empty_list() -> None:
    """5. Successful response with 0 results returns []."""
    payloads = [
        {"web": {"total": 0, "results": []}},
        {"web": {"results": []}},
        {"web": None},
        {},
    ]
    for p in payloads:
        def handler(request: httpx.Request, payload: Dict[str, Any] = p) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = create_mock_client(handler)
        provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
        assert provider.search("nonexistent query", max_results=5) == []


def test_missing_optional_fields() -> None:
    """6. Missing optional fields (profile, page_age) map safely to None."""
    payload: Dict[str, Any] = {
        "web": {
            "results": [
                {
                    "title": "Minimal Result",
                    "url": "https://minimal.example.com",
                    "description": "Minimal description without profile or age.",
                }
            ]
        }
    }
    client = create_mock_client(lambda req: httpx.Response(200, json=payload))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("minimal query", max_results=5)

    assert len(results) == 1
    assert results[0].url == "https://minimal.example.com"
    assert results[0].title == "Minimal Result"
    assert results[0].snippet == "Minimal description without profile or age."
    assert results[0].publisher is None
    assert results[0].published_date is None
    assert results[0].raw_content is None


def test_max_results_respected() -> None:
    """7. max_results limits the number of returned items and sets count parameter."""
    recorded_params: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_params
        recorded_params = dict(request.url.params)
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    results = provider.search("pricing research", max_results=1)

    assert len(results) == 1
    assert results[0].url == "https://example.com/reports/saas-pricing-2024"
    assert recorded_params.get("count") == "1"


# ------------------------------------------------------------------------------
# 8-14: Error Handling & Mapping
# ------------------------------------------------------------------------------

def test_401_raises_search_authentication_error() -> None:
    """8. HTTP 401 raises SearchAuthenticationError."""
    client = create_mock_client(lambda req: httpx.Response(401, json={"message": "Unauthorized"}))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchAuthenticationError) as exc_info:
        provider.search("query")
    assert "401" in str(exc_info.value)
    assert isinstance(exc_info.value, SearchProviderError)


def test_403_raises_search_authentication_error() -> None:
    """9. HTTP 403 raises SearchAuthenticationError."""
    client = create_mock_client(lambda req: httpx.Response(403, json={"message": "Forbidden"}))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchAuthenticationError) as exc_info:
        provider.search("query")
    assert "403" in str(exc_info.value)


def test_429_raises_search_rate_limit_error() -> None:
    """10. HTTP 429 raises SearchRateLimitError."""
    client = create_mock_client(lambda req: httpx.Response(429, json={"message": "Rate limit exceeded"}))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchRateLimitError) as exc_info:
        provider.search("query")
    assert "429" in str(exc_info.value)
    assert isinstance(exc_info.value, SearchProviderError)


def test_5xx_raises_search_response_error() -> None:
    """11. HTTP 5xx raises SearchResponseError."""
    client = create_mock_client(lambda req: httpx.Response(502, text="Bad Gateway"))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchResponseError) as exc_info:
        provider.search("query")
    assert "502" in str(exc_info.value)
    assert isinstance(exc_info.value, SearchProviderError)


def test_timeout_raises_search_timeout_error() -> None:
    """12. Request timeout raises SearchTimeoutError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out.")

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchTimeoutError) as exc_info:
        provider.search("query")
    assert "timed out" in str(exc_info.value).lower()
    assert isinstance(exc_info.value, SearchProviderError)


def test_network_error_raises_search_network_error() -> None:
    """Request network failure raises SearchNetworkError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to establish connection.")

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchNetworkError) as exc_info:
        provider.search("query")
    assert "network error" in str(exc_info.value).lower()
    assert isinstance(exc_info.value, SearchProviderError)


def test_malformed_json_raises_search_response_error() -> None:
    """13. Non-JSON response raises SearchResponseError."""
    client = create_mock_client(lambda req: httpx.Response(200, text="<html>502 Bad Gateway</html>"))
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)

    with pytest.raises(SearchResponseError) as exc_info:
        provider.search("query")
    assert "non-json" in str(exc_info.value).lower()


def test_malformed_response_structure_raises_search_response_error() -> None:
    """14. Unexpected response structures raise SearchResponseError."""
    malformed_cases = [
        # Response is a list, not a dict
        [{"some": "data"}],
        # web is a string
        {"web": "invalid_string"},
        # results is not a list
        {"web": {"results": "not_a_list"}},
        # result entry is not a dict
        {"web": {"results": ["string_item"]}},
        # missing url
        {"web": {"results": [{"title": "T", "description": "D"}]}},
        # missing title
        {"web": {"results": [{"url": "https://example.com", "description": "D"}]}},
        # missing description
        {"web": {"results": [{"url": "https://example.com", "title": "T"}]}},
        # empty title after stripping HTML tags
        {"web": {"results": [{"url": "https://example.com", "title": "<b>  </b>", "description": "D"}]}},
        # empty description after stripping HTML tags
        {"web": {"results": [{"url": "https://example.com", "title": "T", "description": "<i>  </i>"}]}},
    ]
    for case in malformed_cases:
        client = create_mock_client(lambda req, c=case: httpx.Response(200, json=c))
        provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
        with pytest.raises(SearchResponseError):
            provider.search("query")


# ------------------------------------------------------------------------------
# 15: Security & API Key Masking
# ------------------------------------------------------------------------------

def test_api_key_never_appears_in_repr_str_or_exception_messages() -> None:
    """15. API key must never appear in repr, str, or exception messages."""
    SECRET = "TOP_SECRET_BRAVE_KEY_XYZ_987654321"

    provider = BraveSearchProvider(api_key=SECRET)
    assert SECRET not in repr(provider)
    assert SECRET not in str(provider)
    assert "configured=True" in repr(provider)

    # 1. HTTP error statuses
    error_statuses = [401, 403, 429, 500, 502, 503]
    for status in error_statuses:
        client = create_mock_client(lambda req, s=status: httpx.Response(s, text=f"Error {s}"))
        p = BraveSearchProvider(api_key=SECRET, http_client=client)
        with pytest.raises(SearchProviderError) as exc_info:
            p.search("secret test")
        assert SECRET not in str(exc_info.value)
        assert SECRET not in repr(exc_info.value)

    # 2. Timeout error
    timeout_client = create_mock_client(lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("Timeout error")))
    p_timeout = BraveSearchProvider(api_key=SECRET, http_client=timeout_client)
    with pytest.raises(SearchProviderError) as exc_info:
        p_timeout.search("secret test")
    assert SECRET not in str(exc_info.value)
    assert SECRET not in repr(exc_info.value)

    # 3. Network connect error
    net_client = create_mock_client(lambda req: (_ for _ in ()).throw(httpx.ConnectError("Network connect error")))
    p_net = BraveSearchProvider(api_key=SECRET, http_client=net_client)
    with pytest.raises(SearchProviderError) as exc_info:
        p_net.search("secret test")
    assert SECRET not in str(exc_info.value)
    assert SECRET not in repr(exc_info.value)

    # 4. Malformed JSON error
    json_client = create_mock_client(lambda req: httpx.Response(200, text="<!DOCTYPE html>"))
    p_json = BraveSearchProvider(api_key=SECRET, http_client=json_client)
    with pytest.raises(SearchProviderError) as exc_info:
        p_json.search("secret test")
    assert SECRET not in str(exc_info.value)
    assert SECRET not in repr(exc_info.value)


# ------------------------------------------------------------------------------
# 16: FakeSearchProvider Unchanged Behavior
# ------------------------------------------------------------------------------

def test_fake_search_provider_behavior_remains_unchanged() -> None:
    """16. FakeSearchProvider semantics and contract remain completely identical."""
    fake = FakeSearchProvider()
    assert fake.search("unregistered query") == []

    fake.register_canned_results(
        "saas elasticity",
        [
            SearchResultItem(
                url="https://fake.example.com",
                title="Fake Elasticity",
                snippet="Fake snippet.",
            )
        ],
    )
    res = fake.search("saas elasticity")
    assert len(res) == 1
    assert res[0].title == "Fake Elasticity"
    assert "saas elasticity" in fake.recorded_queries


# ------------------------------------------------------------------------------
# 17-18: Configuration & Integration Tests
# ------------------------------------------------------------------------------

def test_missing_api_key_raises_search_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """17. Missing API key raises SearchAuthenticationError on search."""
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "BRAVE_SEARCH_API_KEY", None)

    provider = BraveSearchProvider(api_key=None)
    with pytest.raises(SearchAuthenticationError) as exc_info:
        provider.search("query")
    assert "api key is not configured" in str(exc_info.value).lower()


def test_brave_search_provider_integrates_with_evidence_retriever() -> None:
    """18. EvidenceRetriever seamlessly orchestrates with BraveSearchProvider."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_BRAVE_RESPONSE)

    client = create_mock_client(handler)
    provider = BraveSearchProvider(api_key=SAMPLE_API_KEY, http_client=client)
    retriever = EvidenceRetriever(search_provider=provider, max_results_per_query=2)

    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical elasticity studies.",
        suggested_queries=["B2B SaaS pricing research"],
    )
    records = retriever.retrieve([req])

    assert len(records) == 1
    assert records[0].requirement_id == "req_1"
    assert records[0].query == "B2B SaaS pricing research"
    assert len(records[0].results) == 2
    assert records[0].results[0].title == "SaaS Pricing Benchmarks 2024"
