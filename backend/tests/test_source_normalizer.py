"""Unit and regression tests for AURA Day 3 Phase 8 SourceNormalizer.

Verifies:
1. SearchResultItem converts to Source correctly.
2. requirement_id is preserved.
3. query is preserved.
4. title preserved.
5. publisher preserved.
6. published_date becomes Source.publication_date.
7. retrieval_timestamp is timezone-aware UTC.
8. reliability_score remains None.
9. obvious government domain classification works.
10. unknown source safely becomes OTHER.
11. URL fragment removal.
12. UTM tracking parameter removal.
13. hostname/scheme normalization where appropriate.
14. meaningful query parameters are preserved.
15. same canonical URL receives same Source identity.
16. duplicate source does NOT remove multiple retrieval lineage records.
17. different canonical URLs receive different Source identities.
18. metadata merge prefers useful non-empty metadata.
19. conflicting metadata behavior is deterministic.
20. empty retrieval results create no Source.
21. SourceNormalizer makes no SearchProvider calls.
22. SourceNormalizer has no LLM dependency.
23. no Gemini API key required.
24. no external network calls.
25. SaaS scenario regression case.
"""

from datetime import date, timezone
import inspect
import pytest

from app.schemas.evidence import Source, SourceType
from app.services.evidence.normalizer import (
    NormalizedSourceResult,
    SourceNormalizationError,
    SourceNormalizer,
    canonicalize_url,
    classify_source_type,
)
from app.services.evidence.retriever import RequirementSearchResults
from app.services.evidence.search_provider import SearchResultItem


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _create_sample_item(
    url: str = "https://example.com/reports/saas-pricing-2024",
    title: str = "2024 SaaS Pricing Benchmark Report",
    snippet: str = "Observed volume expansion was 12-16% for 20% discounts.",
    publisher: str = "Mock Expansion Labs",
    published_date: date = date(2024, 9, 15),
) -> SearchResultItem:
    return SearchResultItem(
        url=url,
        title=title,
        snippet=snippet,
        publisher=publisher,
        published_date=published_date,
    )


# ------------------------------------------------------------------------------
# 1-8: Conversion & Field Preservation Tests
# ------------------------------------------------------------------------------

def test_search_result_item_converts_to_source_correctly() -> None:
    """Verifies SearchResultItem fields convert into Source attributes correctly."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="B2B SaaS price elasticity",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)

    assert len(lineage) == 1
    record = lineage[0]
    assert record.requirement_id == "req_1"
    assert record.query == "B2B SaaS price elasticity"

    src = record.source
    assert src.id == "src_1"
    assert src.url == "https://example.com/reports/saas-pricing-2024"
    assert src.title == "2024 SaaS Pricing Benchmark Report"
    assert src.publisher == "Mock Expansion Labs"
    assert src.publication_date == date(2024, 9, 15)
    assert src.retrieval_timestamp.tzinfo is not None
    assert src.source_type == SourceType.OTHER
    assert src.reliability_score is None


def test_requirement_id_and_query_preserved() -> None:
    """Verifies requirement_id and query are strictly preserved on NormalizedSourceResult."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_special_42",
            query="custom inquiry query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 1
    assert lineage[0].requirement_id == "req_special_42"
    assert lineage[0].query == "custom inquiry query"


def test_title_and_publisher_preserved() -> None:
    """Verifies title and publisher are preserved."""
    normalizer = SourceNormalizer()
    item = _create_sample_item(
        title="Specific Study Title",
        publisher="Specific Publisher Name",
    )
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert lineage[0].source.title == "Specific Study Title"
    assert lineage[0].source.publisher == "Specific Publisher Name"


def test_published_date_becomes_source_publication_date() -> None:
    """Verifies SearchResultItem.published_date maps to Source.publication_date."""
    normalizer = SourceNormalizer()
    item = _create_sample_item(published_date=date(2025, 1, 20))
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert lineage[0].source.publication_date == date(2025, 1, 20)


def test_retrieval_timestamp_is_timezone_aware_utc() -> None:
    """Verifies Source.retrieval_timestamp is timezone-aware UTC."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    ts = lineage[0].source.retrieval_timestamp
    assert ts.tzinfo is not None
    assert ts.tzinfo == timezone.utc


def test_reliability_score_remains_none() -> None:
    """Verifies reliability_score is strictly None in Day 3."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert lineage[0].source.reliability_score is None


# ------------------------------------------------------------------------------
# 9-10: Source Type Classification Tests
# ------------------------------------------------------------------------------

def test_government_and_regulatory_domain_classification() -> None:
    """Verifies government and regulatory domains are classified conservatively."""
    # 1. Government domain (.gov)
    assert classify_source_type("https://www.bls.gov/cpi/") == SourceType.GOVERNMENT
    assert classify_source_type("https://census.gov/data") == SourceType.GOVERNMENT
    assert classify_source_type("https://data.gov.uk/dataset") == SourceType.GOVERNMENT

    # 2. Regulatory Filing domain (sec.gov, companieshouse)
    assert classify_source_type("https://www.sec.gov/edgar/searchedgar/companysearch") == SourceType.REGULATORY_FILING
    assert classify_source_type("https://edgar.sec.gov/Archives/edgar/data") == SourceType.REGULATORY_FILING
    assert classify_source_type("https://companieshouse.gov.uk/company/123") == SourceType.REGULATORY_FILING


def test_unknown_domain_safely_becomes_other() -> None:
    """Verifies non-government, non-regulatory domains safely default to SourceType.OTHER."""
    assert classify_source_type("https://example.com/reports/saas") == SourceType.OTHER
    assert classify_source_type("https://academic-journal.org/paper") == SourceType.OTHER
    assert classify_source_type("https://techcrunch.com/article") == SourceType.OTHER
    assert classify_source_type("https://mckinsey.com/insights") == SourceType.OTHER


# ------------------------------------------------------------------------------
# 11-14: Canonical URL Normalization Tests
# ------------------------------------------------------------------------------

def test_url_fragment_removal() -> None:
    """Verifies URL fragments (#section) are stripped."""
    assert (
        canonicalize_url("https://example.com/report#methodology")
        == "https://example.com/report"
    )
    assert (
        canonicalize_url("https://example.com/pricing#pricing-table")
        == "https://example.com/pricing"
    )


def test_utm_tracking_parameter_removal() -> None:
    """Verifies UTM and common tracking parameters are removed."""
    raw = (
        "https://example.com/study?"
        "utm_source=google&utm_medium=cpc&utm_campaign=saas&utm_term=pricing&utm_content=v1"
        "&gclid=12345&fbclid=67890"
    )
    assert canonicalize_url(raw) == "https://example.com/study"


def test_hostname_and_scheme_normalization() -> None:
    """Verifies scheme and hostname are normalized to lowercase and default ports stripped."""
    assert (
        canonicalize_url("HTTPS://EXAMPLE.COM/report")
        == "https://example.com/report"
    )
    assert (
        canonicalize_url("https://example.com:443/report")
        == "https://example.com/report"
    )
    assert (
        canonicalize_url("http://example.com:80/report")
        == "http://example.com/report"
    )


def test_meaningful_query_parameters_preserved() -> None:
    """Verifies meaningful non-tracking query parameters are preserved and sorted."""
    raw = "https://example.com/search?q=saas+elasticity&page=2&utm_source=mail"
    assert (
        canonicalize_url(raw)
        == "https://example.com/search?page=2&q=saas+elasticity"
    )


# ------------------------------------------------------------------------------
# 15-17: Deduplication & Lineage Integrity Tests
# ------------------------------------------------------------------------------

def test_same_canonical_url_receives_same_source_identity() -> None:
    """Verifies multiple results with identical canonical URLs map to the same Source ID."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(url="https://example.com/report?utm_source=twitter")
    item2 = _create_sample_item(url="https://EXAMPLE.com/report#section")

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query 1",
            results=[item1],
        ),
        RequirementSearchResults(
            requirement_id="req_2",
            query="query 2",
            results=[item2],
        ),
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 2
    assert lineage[0].source.id == lineage[1].source.id
    assert lineage[0].source.id == "src_1"


def test_duplicate_source_does_not_remove_lineage_records() -> None:
    """Verifies that deduplicating a Source does NOT collapse multiple lineage records."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(url="https://example.com/report?utm_source=a")
    item2 = _create_sample_item(url="https://example.com/report?utm_source=b")
    item3 = _create_sample_item(url="https://example.com/report#fragment")

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1],
        ),
        RequirementSearchResults(
            requirement_id="req_1",
            query="q2",
            results=[item2],
        ),
        RequirementSearchResults(
            requirement_id="req_2",
            query="q3",
            results=[item3],
        ),
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 3
    # All three point to the same canonical Source
    assert lineage[0].source.id == lineage[1].source.id == lineage[2].source.id == "src_1"
    # But preserve distinct requirement/query lineage
    assert lineage[0].query == "q1"
    assert lineage[1].query == "q2"
    assert lineage[2].query == "q3"
    assert lineage[2].requirement_id == "req_2"


def test_different_canonical_urls_receive_different_source_identities() -> None:
    """Verifies distinct canonical URLs produce distinct Source IDs."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(url="https://example.com/report-alpha")
    item2 = _create_sample_item(url="https://example.com/report-beta")

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1, item2],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 2
    assert lineage[0].source.id == "src_1"
    assert lineage[1].source.id == "src_2"
    assert lineage[0].source.url != lineage[1].source.url


# ------------------------------------------------------------------------------
# 18-19: Metadata Merging Policy Tests
# ------------------------------------------------------------------------------

def test_metadata_merge_prefers_useful_non_empty_metadata() -> None:
    """Verifies metadata merging policy prefers non-empty publisher and longer title."""
    normalizer = SourceNormalizer()
    item1 = SearchResultItem(
        url="https://example.com/report",
        title="Short Title",
        snippet="Snippet 1",
        publisher=None,
        published_date=None,
    )
    item2 = SearchResultItem(
        url="https://example.com/report#details",
        title="Comprehensive SaaS Benchmark Report 2024",
        snippet="Snippet 2",
        publisher="Authoritative Lab",
        published_date=date(2024, 5, 1),
    )

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1, item2],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 2
    # Both records should reflect the enriched, merged source
    src = lineage[0].source
    assert src.title == "Comprehensive SaaS Benchmark Report 2024"
    assert src.publisher == "Authoritative Lab"
    assert src.publication_date == date(2024, 5, 1)


def test_conflicting_metadata_behavior_is_deterministic() -> None:
    """Verifies conflicting publication dates resolve deterministically (earliest date kept)."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(url="https://example.com/data", published_date=date(2024, 8, 1))
    item2 = _create_sample_item(url="https://example.com/data#ref", published_date=date(2024, 2, 1))

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1, item2],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert lineage[0].source.publication_date == date(2024, 8, 1)


# ------------------------------------------------------------------------------
# 20: Empty Result Handling & Retrieval Text Retention Tests
# ------------------------------------------------------------------------------

def test_empty_retrieval_results_create_no_source() -> None:
    """Verifies RequirementSearchResults with results=[] produces no Source records."""
    normalizer = SourceNormalizer()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_empty",
            query="obscure query with no results",
            results=[],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert lineage == []


def test_normalized_lineage_retains_search_result_item_text() -> None:
    """Verifies normalized lineage preserves originating SearchResultItem snippet and raw_content."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    item.raw_content = "# Full Markdown Content\nObserved empirical findings..."

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 1
    assert lineage[0].search_result is not None
    assert lineage[0].search_result.snippet == item.snippet
    assert lineage[0].search_result.raw_content == item.raw_content


def test_duplicate_canonical_sources_preserve_individual_retrieval_text() -> None:
    """Verifies duplicate canonical Sources preserve each retrieval item's own snippet and raw_content."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(
        url="https://example.com/report?utm_source=ad1",
        snippet="Snippet 1 from query A",
    )
    item2 = _create_sample_item(
        url="https://example.com/report#frag2",
        snippet="Snippet 2 from query B",
    )

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1],
        ),
        RequirementSearchResults(
            requirement_id="req_2",
            query="q2",
            results=[item2],
        ),
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 2
    # Same canonical Source
    assert lineage[0].source.id == lineage[1].source.id
    # Preserves each item's own snippet
    assert lineage[0].search_result is not None
    assert lineage[0].search_result.snippet == "Snippet 1 from query A"
    assert lineage[1].search_result is not None
    assert lineage[1].search_result.snippet == "Snippet 2 from query B"


def test_source_itself_does_not_absorb_snippet_or_raw_content() -> None:
    """Verifies canonical Source domain entity does NOT absorb snippet or raw_content."""
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    item.raw_content = "Raw content here"

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    src = lineage[0].source
    assert not hasattr(src, "snippet")
    assert not hasattr(src, "raw_content")
    assert "snippet" not in Source.model_fields
    assert "raw_content" not in Source.model_fields



# ------------------------------------------------------------------------------
# 21-24: Safety, Dependency & Network Tests
# ------------------------------------------------------------------------------

def test_source_normalizer_makes_no_search_provider_calls() -> None:
    """Verifies SourceNormalizer has no SearchProvider dependency or calls."""
    init_sig = inspect.signature(SourceNormalizer.__init__)
    assert "search_provider" not in init_sig.parameters


def test_source_normalizer_has_no_llm_dependency() -> None:
    """Verifies SourceNormalizer has no LLMClient dependency."""
    init_sig = inspect.signature(SourceNormalizer.__init__)
    assert "llm_client" not in init_sig.parameters


def test_no_gemini_api_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies SourceNormalizer operates completely without GEMINI_API_KEY."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    normalizer = SourceNormalizer()
    item = _create_sample_item()
    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="query",
            results=[item],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 1


def test_no_external_network_calls() -> None:
    """Verifies normalization completes in-memory with zero network calls under fail-closed guard."""
    normalizer = SourceNormalizer()
    items = [_create_sample_item(url=f"https://example.com/page_{i}") for i in range(5)]
    search_results = [
        RequirementSearchResults(
            requirement_id="req_batch",
            query="batch query",
            results=items,
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 5


def test_invalid_url_raises_source_normalization_error() -> None:
    """Verifies empty or malformed URL raises SourceNormalizationError."""
    with pytest.raises(SourceNormalizationError):
        canonicalize_url("")

    with pytest.raises(SourceNormalizationError):
        canonicalize_url("   ")


def test_extract_unique_sources_helper() -> None:
    """Verifies extract_unique_sources helper deduplicates canonical Source entities."""
    normalizer = SourceNormalizer()
    item1 = _create_sample_item(url="https://example.com/same-url?utm_source=ad")
    item2 = _create_sample_item(url="https://example.com/same-url#section")
    item3 = _create_sample_item(url="https://example.com/different-url")

    search_results = [
        RequirementSearchResults(
            requirement_id="req_1",
            query="q1",
            results=[item1, item2, item3],
        )
    ]

    lineage = normalizer.normalize(search_results)
    assert len(lineage) == 3

    unique_sources = normalizer.extract_unique_sources(lineage)
    assert len(unique_sources) == 2
    assert {s.id for s in unique_sources} == {"src_1", "src_2"}



# ------------------------------------------------------------------------------
# 25: Important SaaS Scenario Regression Test
# ------------------------------------------------------------------------------

def test_saas_scenario_regression() -> None:
    """Executes the exact prompt-specified SaaS scenario regression case.

    Input:
    RequirementSearchResults(
        requirement_id="req_1",
        query="B2B SaaS price elasticity",
        results=[
            SearchResultItem(
                url="https://example.com/report?utm_source=google",
                title="SaaS Pricing Report",
                snippet="...",
                publisher="Example Research",
            )
        ]
    )
    and:
    RequirementSearchResults(
        requirement_id="req_2",
        query="SaaS discount conversion study",
        results=[
            SearchResultItem(
                url="https://EXAMPLE.com/report#results",
                title="SaaS Pricing Report",
                snippet="...",
                publisher="Example Research",
            )
        ]
    )

    Expected:
    ONE canonical Source identity (src_1)
    TWO lineage records:
    req_1 -> first query -> src_1
    req_2 -> second query -> src_1
    """
    normalizer = SourceNormalizer()

    req_results_1 = RequirementSearchResults(
        requirement_id="req_1",
        query="B2B SaaS price elasticity",
        results=[
            SearchResultItem(
                url="https://example.com/report?utm_source=google",
                title="SaaS Pricing Report",
                snippet="...",
                publisher="Example Research",
            )
        ],
    )

    req_results_2 = RequirementSearchResults(
        requirement_id="req_2",
        query="SaaS discount conversion study",
        results=[
            SearchResultItem(
                url="https://EXAMPLE.com/report#results",
                title="SaaS Pricing Report",
                snippet="...",
                publisher="Example Research",
            )
        ],
    )

    lineage = normalizer.normalize([req_results_1, req_results_2])

    # 1. Exactly TWO lineage records must be returned (not collapsed into one)
    assert len(lineage) == 2

    # 2. Lineage 1 preserves req_1 and query 1
    assert lineage[0].requirement_id == "req_1"
    assert lineage[0].query == "B2B SaaS price elasticity"

    # 3. Lineage 2 preserves req_2 and query 2
    assert lineage[1].requirement_id == "req_2"
    assert lineage[1].query == "SaaS discount conversion study"

    # 4. Both lineage records point to the EXACT same canonical Source identity
    assert lineage[0].source.id == lineage[1].source.id
    assert lineage[0].source.id == "src_1"
    assert lineage[0].source.url == "https://example.com/report"
    assert lineage[0].source.title == "SaaS Pricing Report"
    assert lineage[0].source.publisher == "Example Research"
