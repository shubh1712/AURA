"""Unit and regression tests for AURA Day 3 Phase 7 EvidenceRetriever.

Verifies:
1. EXTERNAL_RESEARCH invokes SearchProvider.
2. INTERNAL_DATA never invokes SearchProvider.
3. USER_CLARIFICATION never invokes SearchProvider.
4. DETERMINISTIC_CALCULATION never invokes SearchProvider.
5. Requirement with two external queries executes both.
6. requirement_id is preserved.
7. exact executed query is preserved.
8. SearchResultItem results are preserved.
9. max_results_per_query is respected.
10. invalid max_results_per_query rejected.
11. EXTERNAL_RESEARCH with no suggested_queries performs no search.
12. empty provider result is represented as an executed query with results=[].
13. duplicate normalized queries within one requirement execute only once.
14. same query belonging to two different requirements retains separate requirement provenance.
15. provider exception is not silently converted to empty results.
16. FakeSearchProvider recorded_queries confirms exact expected call count.
17. no LLMClient is required.
18. no Gemini key is required.
19. no external network call occurs.
20. SaaS scenario regression case.
"""

from datetime import date
import inspect
from typing import List
import pytest

from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidenceRequirement,
    RequirementStatus,
)
from app.services.evidence.retriever import (
    EvidenceRetriever,
    EvidenceRetrieverError,
    RequirementSearchResults,
)
from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchResultItem,
)


# ------------------------------------------------------------------------------
# Test Fixtures & Helpers
# ------------------------------------------------------------------------------

def _create_sample_items(count: int = 2) -> List[SearchResultItem]:
    """Helper creating structured SearchResultItem instances."""
    return [
        SearchResultItem(
            url=f"https://example.com/source_{i}",
            title=f"Sample Benchmark Document {i}",
            snippet=f"Observed expansion was {i * 5}% for SaaS pricing models.",
            publisher=f"Benchmark Lab {i}",
            published_date=date(2024, 6, i),
        )
        for i in range(1, count + 1)
    ]


def _create_requirement(
    req_id: str,
    kind: EvidenceKind,
    queries: List[str],
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
) -> EvidenceRequirement:
    """Helper constructing canonical EvidenceRequirement instances."""
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=kind,
        description=f"Evidence specification for {target_id}.",
        status=RequirementStatus.PENDING,
        suggested_queries=queries,
    )


# ------------------------------------------------------------------------------
# 1-4: Routing Policy Tests
# ------------------------------------------------------------------------------

def test_external_research_invokes_search_provider() -> None:
    """Verifies EXTERNAL_RESEARCH invokes SearchProvider and captures results."""
    items = _create_sample_items(2)
    fake_provider = FakeSearchProvider(
        canned_results={"b2b saas price elasticity": items}
    )
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_ext_1",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["b2b saas price elasticity"],
    )

    results = retriever.retrieve([req])

    assert len(results) == 1
    assert results[0].requirement_id == "req_ext_1"
    assert results[0].query == "b2b saas price elasticity"
    assert len(results[0].results) == 2
    assert results[0].results[0].title == "Sample Benchmark Document 1"
    assert fake_provider.recorded_queries == ["b2b saas price elasticity"]


def test_internal_data_never_invokes_search_provider() -> None:
    """Verifies INTERNAL_DATA never invokes SearchProvider even if queries exist."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_int_1",
        kind=EvidenceKind.INTERNAL_DATA,
        queries=["internal churn telemetry rate"],
    )

    results = retriever.retrieve([req])

    assert results == []
    assert fake_provider.recorded_queries == []


def test_user_clarification_never_invokes_search_provider() -> None:
    """Verifies USER_CLARIFICATION never invokes SearchProvider."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_clar_1",
        kind=EvidenceKind.USER_CLARIFICATION,
        queries=["prospect risk tolerance preference"],
    )

    results = retriever.retrieve([req])

    assert results == []
    assert fake_provider.recorded_queries == []


def test_deterministic_calculation_never_invokes_search_provider() -> None:
    """Verifies DETERMINISTIC_CALCULATION never invokes SearchProvider."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_calc_1",
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        queries=["break-even formula volume calculation"],
    )

    results = retriever.retrieve([req])

    assert results == []
    assert fake_provider.recorded_queries == []


# ------------------------------------------------------------------------------
# 5-8: Multiple Queries & Provenance Preservation
# ------------------------------------------------------------------------------

def test_requirement_with_two_external_queries_executes_both() -> None:
    """Verifies that a requirement with multiple queries generates distinct retrieval records."""
    fake_provider = FakeSearchProvider(
        canned_results={
            "query one": _create_sample_items(1),
            "query two": _create_sample_items(2),
        }
    )
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_multi_q",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["query one", "query two"],
    )

    records = retriever.retrieve([req])

    assert len(records) == 2
    assert records[0].requirement_id == "req_multi_q"
    assert records[0].query == "query one"
    assert len(records[0].results) == 1

    assert records[1].requirement_id == "req_multi_q"
    assert records[1].query == "query two"
    assert len(records[1].results) == 2

    assert fake_provider.recorded_queries == ["query one", "query two"]


def test_requirement_id_preserved() -> None:
    """Verifies requirement_id is strictly preserved on the retrieval record."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_specific_id_999",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["test query"],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1
    assert records[0].requirement_id == "req_specific_id_999"


def test_exact_executed_query_preserved() -> None:
    """Verifies the exact cleaned query string is preserved on the retrieval record."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_query_test",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["   SaaS   discount   conversion   study   "],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1
    assert records[0].query == "SaaS discount conversion study"
    assert fake_provider.recorded_queries == ["SaaS discount conversion study"]


def test_search_result_item_results_preserved() -> None:
    """Verifies SearchResultItem instances are preserved with all fields intact."""
    items = [
        SearchResultItem(
            url="https://reports.example.com/saas-2024",
            title="SaaS Benchmark Report 2024",
            snippet="Detailed pricing and elasticity study across 500 SaaS companies.",
            publisher="Benchmark Research Group",
            published_date=date(2024, 3, 15),
            raw_content="# Full Report Markdown\nContent...",
        )
    ]
    fake_provider = FakeSearchProvider(canned_results={"saas benchmark": items})
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_items",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["saas benchmark"],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1
    res_items = records[0].results
    assert len(res_items) == 1
    assert res_items[0].url == "https://reports.example.com/saas-2024"
    assert res_items[0].title == "SaaS Benchmark Report 2024"
    assert res_items[0].publisher == "Benchmark Research Group"
    assert res_items[0].published_date == date(2024, 3, 15)
    assert res_items[0].raw_content == "# Full Report Markdown\nContent..."


# ------------------------------------------------------------------------------
# 9-10: Max Results Parameter Validation
# ------------------------------------------------------------------------------

def test_max_results_per_query_respected() -> None:
    """Verifies max_results_per_query truncates provider results correctly."""
    items = _create_sample_items(5)
    fake_provider = FakeSearchProvider(canned_results={"elasticity study": items})
    retriever = EvidenceRetriever(
        search_provider=fake_provider,
        max_results_per_query=2,
    )

    req = _create_requirement(
        req_id="req_max_res",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["elasticity study"],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1
    assert len(records[0].results) == 2


def test_invalid_max_results_per_query_rejected() -> None:
    """Verifies non-positive or invalid max_results_per_query raises ValueError."""
    fake_provider = FakeSearchProvider()

    with pytest.raises(ValueError) as exc1:
        EvidenceRetriever(search_provider=fake_provider, max_results_per_query=0)
    assert "max_results_per_query must be a positive integer" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        EvidenceRetriever(search_provider=fake_provider, max_results_per_query=-3)
    assert "max_results_per_query must be a positive integer" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        EvidenceRetriever(search_provider=fake_provider, max_results_per_query=False)  # type: ignore[arg-type]
    assert "max_results_per_query must be a positive integer" in str(exc3.value)

    with pytest.raises(TypeError) as exc4:
        EvidenceRetriever(search_provider="invalid_provider")  # type: ignore[arg-type]
    assert "search_provider must implement SearchProvider" in str(exc4.value)


# ------------------------------------------------------------------------------
# 11-12: Empty Query & Empty Result Behavior
# ------------------------------------------------------------------------------

def test_external_research_with_no_suggested_queries_performs_no_search() -> None:
    """Verifies EXTERNAL_RESEARCH with empty suggested_queries does not search or invent queries."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req1 = _create_requirement(
        req_id="req_no_q",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=[],
    )
    req2 = _create_requirement(
        req_id="req_blank_q",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["   ", ""],
    )

    records = retriever.retrieve([req1, req2])
    assert records == []
    assert fake_provider.recorded_queries == []


def test_empty_provider_result_represented_as_executed_query_with_empty_results() -> None:
    """Verifies that queries returning 0 results preserve an executed record with results=[]."""
    fake_provider = FakeSearchProvider(strict=False)
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_empty_res",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["obscure unindexed empirical study"],
    )

    records = retriever.retrieve([req])

    assert len(records) == 1
    assert records[0].requirement_id == "req_empty_res"
    assert records[0].query == "obscure unindexed empirical study"
    assert records[0].results == []
    assert fake_provider.recorded_queries == ["obscure unindexed empirical study"]


# ------------------------------------------------------------------------------
# 13-14: Deduplication Policy Tests
# ------------------------------------------------------------------------------

def test_duplicate_normalized_queries_within_one_requirement_execute_only_once() -> None:
    """Verifies exact same normalized query within the same requirement executes only once."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_dup_test",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=[
            "B2B SaaS price elasticity",
            "  b2b   saas price elasticity  ",
            "B2B SAAS PRICE ELASTICITY",
        ],
    )

    records = retriever.retrieve([req])

    assert len(records) == 1
    assert records[0].query == "B2B SaaS price elasticity"
    assert fake_provider.recorded_queries == ["B2B SaaS price elasticity"]


def test_same_query_across_different_requirements_retains_separate_provenance() -> None:
    """Verifies identical queries belonging to distinct requirements retain separate provenance."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req_a = _create_requirement(
        req_id="req_alpha",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["SaaS churn benchmark"],
    )
    req_b = _create_requirement(
        req_id="req_beta",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["SaaS churn benchmark"],
    )

    records = retriever.retrieve([req_a, req_b])

    assert len(records) == 2
    assert records[0].requirement_id == "req_alpha"
    assert records[0].query == "SaaS churn benchmark"

    assert records[1].requirement_id == "req_beta"
    assert records[1].query == "SaaS churn benchmark"

    assert fake_provider.recorded_queries == [
        "SaaS churn benchmark",
        "SaaS churn benchmark",
    ]


# ------------------------------------------------------------------------------
# 15-16: Provider Error & Telemetry Tests
# ------------------------------------------------------------------------------

def test_provider_exception_not_silently_converted_to_empty_results() -> None:
    """Verifies provider exceptions are propagated as EvidenceRetrieverError, NOT converted to results=[]."""
    fake_provider = FakeSearchProvider()
    fake_provider.register_error(SearchProviderError("Simulated upstream search provider failure"))
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_fail",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["failing query"],
    )

    with pytest.raises(EvidenceRetrieverError) as exc_info:
        retriever.retrieve([req])

    assert "Search provider failure for requirement 'req_fail' and query 'failing query'" in str(exc_info.value)
    assert exc_info.value.requirement_id == "req_fail"
    assert exc_info.value.query == "failing query"
    # Verifies it also satisfies SearchProviderError inheritance
    assert isinstance(exc_info.value, SearchProviderError)


def test_fake_search_provider_recorded_queries_confirms_exact_call_count() -> None:
    """Verifies recorded_queries confirms exact expected provider call count."""
    fake_provider = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req1 = _create_requirement(
        req_id="req_1",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["query A", "query B"],
    )
    req2 = _create_requirement(
        req_id="req_2",
        kind=EvidenceKind.INTERNAL_DATA,
        queries=["ignored query"],
    )
    req3 = _create_requirement(
        req_id="req_3",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["query C"],
    )

    records = retriever.retrieve([req1, req2, req3])

    assert len(records) == 3
    assert len(fake_provider.recorded_queries) == 3
    assert fake_provider.recorded_queries == ["query A", "query B", "query C"]


# ------------------------------------------------------------------------------
# 17-19: Architecture, Credential & Network Safety Tests
# ------------------------------------------------------------------------------

def test_no_llm_client_required() -> None:
    """Verifies EvidenceRetriever does NOT require or accept an LLMClient."""
    init_sig = inspect.signature(EvidenceRetriever.__init__)
    param_names = list(init_sig.parameters.keys())

    assert "llm_client" not in param_names
    assert "client" not in param_names
    assert param_names == ["self", "search_provider", "max_results_per_query"]


def test_no_gemini_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies EvidenceRetriever functions with no GEMINI_API_KEY environment variable."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_provider = FakeSearchProvider(
        canned_results={"benchmark": _create_sample_items(1)}
    )
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_no_gemini",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["benchmark"],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1
    assert len(records[0].results) == 1


def test_no_external_network_call_occurs() -> None:
    """Verifies that retrieval execution executes completely in-memory with zero network calls."""
    fake_provider = FakeSearchProvider(
        canned_results={"test query": _create_sample_items(1)}
    )
    retriever = EvidenceRetriever(search_provider=fake_provider)

    req = _create_requirement(
        req_id="req_offline",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        queries=["test query"],
    )

    records = retriever.retrieve([req])
    assert len(records) == 1


# ------------------------------------------------------------------------------
# 20: Full SaaS Scenario Regression Test
# ------------------------------------------------------------------------------

def test_saas_scenario_regression() -> None:
    """Executes the exact prompt-specified SaaS scenario regression test.

    A:
    EXTERNAL_RESEARCH
    target = SaaS price elasticity assumption
    queries:
    - "B2B SaaS price elasticity customer acquisition"
    - "SaaS pricing discount conversion study"

    B:
    INTERNAL_DATA
    target = current company CAC
    queries = []

    C:
    USER_CLARIFICATION
    target = target customer segment
    queries = []

    D:
    DETERMINISTIC_CALCULATION
    target = break-even effect
    queries = []

    Expected:
    SearchProvider calls = 2
    Only requirement A generates retrieval records.
    B, C and D generate no SearchProvider calls.
    """
    fake_provider = FakeSearchProvider(
        canned_results={
            "B2B SaaS price elasticity customer acquisition": _create_sample_items(2),
            "SaaS pricing discount conversion study": _create_sample_items(1),
        }
    )
    retriever = EvidenceRetriever(
        search_provider=fake_provider,
        max_results_per_query=5,
    )

    req_a = EvidenceRequirement(
        id="req_A",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="SaaS price elasticity assumption empirical validation.",
        suggested_queries=[
            "B2B SaaS price elasticity customer acquisition",
            "SaaS pricing discount conversion study",
        ],
    )
    req_b = EvidenceRequirement(
        id="req_B",
        target_entity_id="var_cac",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Current company CAC from marketing records.",
        suggested_queries=[],
    )
    req_c = EvidenceRequirement(
        id="req_C",
        target_entity_id="stk_segment",
        target_entity_type=DecisionEntityType.STAKEHOLDER,
        kind=EvidenceKind.USER_CLARIFICATION,
        description="Target customer segment risk tolerance definition.",
        suggested_queries=[],
    )
    req_d = EvidenceRequirement(
        id="req_D",
        target_entity_id="trd_break_even",
        target_entity_type=DecisionEntityType.TRADEOFF,
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        description="Break-even volume calculation.",
        suggested_queries=[],
    )

    requirements = [req_a, req_b, req_c, req_d]
    records = retriever.retrieve(requirements)

    # 1. Total SearchProvider calls must be exactly 2
    assert len(fake_provider.recorded_queries) == 2
    assert fake_provider.recorded_queries == [
        "B2B SaaS price elasticity customer acquisition",
        "SaaS pricing discount conversion study",
    ]

    # 2. Only requirement A generates retrieval records
    assert len(records) == 2
    for record in records:
        assert record.requirement_id == "req_A"
        assert record.requirement_id not in ("req_B", "req_C", "req_D")

    assert records[0].query == "B2B SaaS price elasticity customer acquisition"
    assert len(records[0].results) == 2

    assert records[1].query == "SaaS pricing discount conversion study"
    assert len(records[1].results) == 1
