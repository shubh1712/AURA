"""Unit and regression tests for AURA Day 4 Phase 4.13: Evidence Mapping Optimization.

Verifies:
1. Same URL retrieved for two different requirements preserves both requirement relationships.
2. Same URL retrieved twice for the same requirement deduplicates redundant mapping work.
3. Same URL with different snippets preserves distinct factual evidence.
4. Different URLs with similar content preserve distinct Source identities.
5. Different related entities sharing a source preserve distinct target links.
6. Stable ordering and deterministic sequential IDs (evi_1, evi_2, lnk_1, lnk_2).
7. Zero lost requirement relationships in end-to-end evidence packaging.
8. No fabricated evidence IDs or invalid referential linkages.
9. Identical evidence semantics before and after optimization.
10. Deadline propagation and failure handling remain fail-closed.
"""

from datetime import date, datetime, timezone
import time
from typing import List, Optional
import pytest

from app.schemas.decision_model import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
)
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
    EvidenceMapper,
    EvidenceMappingResult,
    EvidenceService,
    FakeSearchProvider,
    NormalizedSourceResult,
    SearchResultItem,
    SourceNormalizer,
)
from app.services.llm.client import FakeLLMClient, LLMError, LLMTimeoutError
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _create_requirement(
    req_id: str,
    target_id: str,
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
    description: str = "Empirical validation requirement.",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description=description,
        status=RequirementStatus.PENDING,
        suggested_queries=["benchmark query"],
    )


def _create_normalized_source(
    req_id: str,
    source_id: str,
    url: str,
    snippet: str,
    raw_content: Optional[str] = None,
    query: str = "benchmark query",
) -> NormalizedSourceResult:
    src = Source(
        id=source_id,
        url=url,
        title="Benchmark Study Report",
        publisher="Benchmark Institute",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 1, 1),
    )
    search_item = SearchResultItem(
        url=url,
        title="Benchmark Study Report",
        snippet=snippet,
        publisher="Benchmark Institute",
        published_date=date(2024, 1, 1),
        raw_content=raw_content,
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query=query,
        source=src,
        search_result=search_item,
    )


# ------------------------------------------------------------------------------
# Test 1: Same URL Retrieved for Two Different Requirements
# ------------------------------------------------------------------------------

def test_same_url_retrieved_for_two_different_requirements(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies same URL retrieved for 2 different requirements preserves both relationships."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req1 = _create_requirement(
        req_id="req_elasticity",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
        description="Verify pricing elasticity.",
    )
    req2 = _create_requirement(
        req_id="req_competitor",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
        description="Verify competitor reactions.",
    )

    # Same URL and source_id, but associated with different requirements
    norm_src1 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_shared",
        url="https://example.com/saas-report",
        snippet="Customer acquisition increased 14% with 20% price reduction.",
    )
    norm_src2 = _create_normalized_source(
        req_id="req_competitor",
        source_id="src_shared",
        url="https://example.com/saas-report",
        snippet="Customer acquisition increased 14% with 20% price reduction.",
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req1, req2],
        normalized_sources=[norm_src1, norm_src2],
    )

    # Both requirements are mapped
    assert len(result.items) == 2
    assert len(result.claim_links) == 2

    # Both items share the canonical source
    assert result.items[0].source_id == "src_shared"
    assert result.items[1].source_id == "src_shared"

    # Claim links target their respective requirement and entity IDs
    link_reqs = {l.requirement_id for l in result.claim_links}
    assert link_reqs == {"req_elasticity", "req_competitor"}

    link_targets = {l.target_entity_id for l in result.claim_links}
    assert link_targets == {"asm_elasticity", "unk_competitor_pricing"}


# ------------------------------------------------------------------------------
# Test 2: Same URL Retrieved Twice for the Same Requirement
# ------------------------------------------------------------------------------

def test_same_url_retrieved_twice_for_same_requirement(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies duplicate occurrences for same requirement and URL are deduplicated before batching."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_elasticity",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
    )

    # Two queries retrieved the exact same URL and content for the same requirement
    norm_src1 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        url="https://example.com/saas-report",
        snippet="Customer acquisition increased 14%.",
        query="query 1",
    )
    norm_src2 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        url="https://example.com/saas-report",
        snippet="Customer acquisition increased 14%.",
        query="query 2",
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src1, norm_src2],
    )

    # Deduplicated: only 1 prompt item, 1 call, 1 item, 1 link
    assert len(fake_client.call_history) == 1
    prompt = fake_client.call_history[0]["prompt"]
    assert prompt.count('<source ref="SOURCE_') == 1

    assert len(result.items) == 1
    assert len(result.claim_links) == 1
    assert result.items[0].source_id == "src_1"
    assert result.claim_links[0].requirement_id == "req_elasticity"


# ------------------------------------------------------------------------------
# Test 3: Same URL with Different Snippets
# ------------------------------------------------------------------------------

def test_same_url_with_different_snippets(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies same URL with different snippets preserves distinct factual text."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_elasticity",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
    )

    # Same URL, but two distinct snippets
    norm_src1 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        url="https://example.com/saas-report",
        snippet="Customer acquisition increased 14% with 20% price reduction.",
    )
    norm_src2 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        url="https://example.com/saas-report",
        snippet="Enterprise churn was 5% across annual contracts.",
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src1, norm_src2],
    )

    # Both snippets are scheduled because their text differs
    assert len(fake_client.call_history) == 1
    prompt = fake_client.call_history[0]["prompt"]
    assert prompt.count('<source ref="SOURCE_') == 2


# ------------------------------------------------------------------------------
# Test 4: Different URLs with Similar Content
# ------------------------------------------------------------------------------

def test_different_urls_with_similar_content(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies different URLs retain distinct Source identities even with identical text."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_elasticity",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
    )

    shared_text = "Observed customer acquisition increase was 14%."
    norm_src1 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        url="https://openview.com/report",
        snippet=shared_text,
    )
    norm_src2 = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_2",
        url="https://saas-capital.com/report",
        snippet=shared_text,
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src1, norm_src2],
    )

    # Both sources are scheduled because source_id / URL differ
    assert len(fake_client.call_history) == 1
    prompt = fake_client.call_history[0]["prompt"]
    assert prompt.count('<source ref="SOURCE_') == 2


# ------------------------------------------------------------------------------
# Test 5: Different Related Entities Sharing a Source
# ------------------------------------------------------------------------------

def test_different_related_entities_sharing_source(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies distinct target entity types (Assumption vs Objective) sharing a source."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req_asm = _create_requirement(
        req_id="req_asm",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
    )
    req_obj = _create_requirement(
        req_id="req_obj",
        target_id="obj_primary_growth",
        target_type=DecisionEntityType.OBJECTIVE,
    )

    src1 = _create_normalized_source(
        req_id="req_asm",
        source_id="src_shared",
        url="https://example.com/growth-study",
        snippet="Annual growth rate reached 35% with 14% acquisition lift.",
    )
    src2 = _create_normalized_source(
        req_id="req_obj",
        source_id="src_shared",
        url="https://example.com/growth-study",
        snippet="Annual growth rate reached 35% with 14% acquisition lift.",
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req_asm, req_obj],
        normalized_sources=[src1, src2],
    )

    assert len(result.claim_links) == 2
    types = {l.target_entity_type for l in result.claim_links}
    assert types == {DecisionEntityType.ASSUMPTION, DecisionEntityType.OBJECTIVE}


# ------------------------------------------------------------------------------
# Test 6: Stable Ordering and Deterministic Sequential IDs
# ------------------------------------------------------------------------------

def test_stable_ordering_and_deterministic_ids(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies deterministic item IDs (evi_1, evi_2) and link IDs (lnk_1, lnk_2)."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(req_id="req_1", target_id="asm_elasticity")
    s1 = _create_normalized_source("req_1", "src_1", "https://example.com/1", "Finding 1.")
    s2 = _create_normalized_source("req_1", "src_2", "https://example.com/2", "Finding 2.")

    res1 = mapper.map_evidence(saas_decision_model, [req], [s1, s2])
    res2 = mapper.map_evidence(saas_decision_model, [req], [s1, s2])

    assert [i.id for i in res1.items] == ["evi_1", "evi_2"]
    assert [l.id for l in res1.claim_links] == ["lnk_1", "lnk_2"]
    assert [i.id for i in res1.items] == [i.id for i in res2.items]
    assert [l.id for l in res1.claim_links] == [l.id for l in res2.claim_links]


# ------------------------------------------------------------------------------
# Test 7: Zero Lost Requirement Relationships in End-to-End Service
# ------------------------------------------------------------------------------

def test_zero_lost_requirement_relationships(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies end-to-end evidence packaging retains all requirement relationships."""
    item = SearchResultItem(
        title="Comprehensive SaaS Benchmark",
        url="https://example.com/benchmark",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        publisher="Benchmark Lab",
    )
    provider = FakeSearchProvider(default_results=[item])
    fake_client = FakeLLMClient()
    service = EvidenceService.create_default(fake_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    assert isinstance(package, EvidencePackage)
    # Every external research requirement with search results received claim links
    fulfilled_or_linked = {l.requirement_id for l in package.claim_links}
    for req in package.requirements:
        if req.kind == EvidenceKind.EXTERNAL_RESEARCH and req.status != RequirementStatus.UNSUPPORTED:
            assert req.id in fulfilled_or_linked


# ------------------------------------------------------------------------------
# Test 8: No Fabricated Evidence IDs or Broken Lineage
# ------------------------------------------------------------------------------

def test_no_fabricated_evidence_ids(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies internal referential integrity: every link points to valid item and requirement."""
    item = SearchResultItem(
        title="Comprehensive SaaS Benchmark",
        url="https://example.com/benchmark",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        publisher="Benchmark Lab",
    )
    provider = FakeSearchProvider(default_results=[item])
    fake_client = FakeLLMClient()
    service = EvidenceService.create_default(fake_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    item_ids = {i.id for i in package.items}
    source_ids = {s.id for s in package.sources}
    req_ids = {r.id for r in package.requirements}

    for item in package.items:
        assert item.source_id in source_ids

    for link in package.claim_links:
        assert link.evidence_item_id in item_ids
        if link.requirement_id is not None:
            assert link.requirement_id in req_ids


# ------------------------------------------------------------------------------
# Test 9: Identical Evidence Semantics Before and After Optimization
# ------------------------------------------------------------------------------

def test_identical_evidence_semantics_before_and_after_optimization(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies final items and links are semantically identical with or without duplicate inputs."""
    fake_client_single = FakeLLMClient()
    mapper_single = EvidenceMapper(llm_client=fake_client_single)

    req = _create_requirement(req_id="req_1", target_id="asm_elasticity")
    s1 = _create_normalized_source("req_1", "src_1", "https://example.com/1", "Observed 14% lift.")

    res_single = mapper_single.map_evidence(saas_decision_model, [req], [s1])

    # Now pass s1 duplicated three times
    fake_client_multi = FakeLLMClient()
    mapper_multi = EvidenceMapper(llm_client=fake_client_multi)
    s1_dup1 = _create_normalized_source("req_1", "src_1", "https://example.com/1", "Observed 14% lift.")
    s1_dup2 = _create_normalized_source("req_1", "src_1", "https://example.com/1", "Observed 14% lift.")

    res_multi = mapper_multi.map_evidence(saas_decision_model, [req], [s1, s1_dup1, s1_dup2])

    assert len(res_single.items) == len(res_multi.items)
    assert len(res_single.claim_links) == len(res_multi.claim_links)
    assert res_single.items[0].content == res_multi.items[0].content
    assert res_single.claim_links[0].stance == res_multi.claim_links[0].stance
    assert res_single.claim_links[0].target_entity_id == res_multi.claim_links[0].target_entity_id


# ------------------------------------------------------------------------------
# Test 10: Deadline Propagation and Failure Handling Unchanged
# ------------------------------------------------------------------------------

def test_deadline_propagation_and_failure_handling_unchanged(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies monotonic deadline expiration and LLM failures fail closed."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(req_id="req_1", target_id="asm_elasticity")
    s1 = _create_normalized_source("req_1", "src_1", "https://example.com/1", "Finding 1.")

    # 1. Expired deadline fails closed
    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(LLMTimeoutError):
        mapper.map_evidence(
            saas_decision_model,
            [req],
            [s1],
            deadline_monotonic=expired_deadline,
        )

    # 2. LLM error fails closed
    class FailingClient(FakeLLMClient):
        def generate_structured(self, *args, **kwargs):
            raise LLMError("Simulated LLM provider failure.")

    failing_mapper = EvidenceMapper(llm_client=FailingClient())
    with pytest.raises(LLMError) as exc_info:
        failing_mapper.map_evidence(saas_decision_model, [req], [s1])
    assert "Simulated LLM provider failure" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Test 11: Query Lineage Differences with Identical Deduplication Key
# ------------------------------------------------------------------------------

def test_deduplication_preserves_query_lineage_and_metadata(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies that differing query lineage strings with identical (req, source, text) key

    collapse safely without losing target entity binding or source attribution.
    """
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(req_id="req_1", target_id="asm_elasticity")

    # Distinct retrieval queries leading to the identical canonical source content
    s1 = _create_normalized_source(
        req_id="req_1",
        source_id="src_1",
        url="https://example.com/benchmark",
        snippet="Customer acquisition rose 14% with 20% discount.",
        query="query string alpha",
    )
    s2 = _create_normalized_source(
        req_id="req_1",
        source_id="src_1",
        url="https://example.com/benchmark",
        snippet="Customer acquisition rose 14% with 20% discount.",
        query="query string beta",
    )

    result = mapper.map_evidence(saas_decision_model, [req], [s1, s2])

    # Exactly 1 batch scheduled, 1 item and 1 link generated
    assert len(fake_client.call_history) == 1
    assert len(result.items) == 1
    assert len(result.claim_links) == 1

    # Attribution and requirement linkages strictly intact
    assert result.items[0].source_id == "src_1"
    assert result.claim_links[0].requirement_id == "req_1"
    assert result.claim_links[0].target_entity_id == "asm_elasticity"
    assert result.claim_links[0].target_entity_type == DecisionEntityType.ASSUMPTION


# ------------------------------------------------------------------------------
# Test 12: Merged Canonical Source Metadata Faithfully Retained in Prompt
# ------------------------------------------------------------------------------

def test_merged_canonical_source_metadata_retained_in_prompt(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies that metadata merged by SourceNormalizer (title, publisher, date)

    is faithfully passed to the batch prompt builder without loss.
    """
    normalizer = SourceNormalizer()
    item1 = SearchResultItem(
        title="Short Title",
        url="https://example.com/saas-pricing?utm_source=twitter",
        snippet="Customer acquisition increased 14%.",
        publisher=None,
        published_date=date(2024, 6, 1),
    )
    item2 = SearchResultItem(
        title="Comprehensive 2024 SaaS Pricing Benchmark Study",
        url="https://example.com/saas-pricing#findings",
        snippet="Customer acquisition increased 14%.",
        publisher="Authoritative Pricing Institute",
        published_date=date(2024, 6, 1),
    )

    search_results = [
        _create_requirement(req_id="req_1", target_id="asm_elasticity"),
    ]
    from app.services.evidence.retriever import RequirementSearchResults
    norm_records = normalizer.normalize([
        RequirementSearchResults(requirement_id="req_1", query="q1", results=[item1]),
        RequirementSearchResults(requirement_id="req_1", query="q2", results=[item2]),
    ])

    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    result = mapper.map_evidence(saas_decision_model, search_results, norm_records)

    # 1 batch scheduled with enriched merged title and publisher
    assert len(fake_client.call_history) == 1
    prompt = fake_client.call_history[0]["prompt"]
    assert "Comprehensive 2024 SaaS Pricing Benchmark Study" in prompt
    assert "Authoritative Pricing Institute" in prompt
    assert len(result.items) == 1
    assert result.items[0].source_id == norm_records[0].source.id
