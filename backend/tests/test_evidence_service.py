"""Unit and integration tests for AURA Day 3 Phase 11 EvidenceService.

Verifies:
1. Full DecisionModel -> EvidencePackage pipeline succeeds.
2. EvidencePackage contains final updated requirement statuses.
3. EXTERNAL_RESEARCH requirement reaches FakeSearchProvider.
4. INTERNAL_DATA does not reach FakeSearchProvider.
5. USER_CLARIFICATION does not reach FakeSearchProvider.
6. DETERMINISTIC_CALCULATION does not reach FakeSearchProvider.
7. canonical duplicate URLs produce one Source in package.
8. duplicate source lineage does not break evidence provenance.
9. EvidenceItem.source_id resolves to packaged Source.
10. ClaimEvidenceLink.evidence_item_id resolves to packaged item.
11. ClaimEvidenceLink.requirement_id resolves to packaged requirement.
12. EvidenceGap.requirement_id resolves to packaged requirement.
13. conflicting evidence IDs resolve to packaged items.
14. requirement target references resolve against DecisionModel.
15. link target references resolve against DecisionModel.
16. gap target references resolve against DecisionModel.
17. package summary is deterministic.
18. package summary contains factual counts.
19. package summary contains no recommendation.
20. empty requirement pipeline returns valid empty EvidencePackage.
21. INTERNAL_DATA-only package produces UNRESOLVED_UNKNOWN.
22. USER_CLARIFICATION-only package produces UNRESOLVED_UNKNOWN.
23. DETERMINISTIC_CALCULATION-only package remains pending without fabricated empirical evidence.
24. provider empty search result does not crash package assembly.
25. irrelevant retrieved material can yield zero EvidenceItems and an appropriate unsupported/insufficient state according to existing detector rules.
26. provider error is not converted to empty evidence.
27. malformed LLM candidate output propagates controlled error.
28. package construction does not mutate caller-owned DecisionModel.
29. package construction does not mutate original requirement objects unexpectedly.
30. EvidenceService has no direct Gemini dependency.
31. EvidenceService has no direct concrete search vendor dependency.
32. normal tests require no GEMINI_API_KEY.
33. normal tests make zero external network calls.
34. SaaS End-to-End Regression.
35. Conflict End-to-End Regression.
"""

from datetime import datetime, timezone
import inspect
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
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence.gaps import EvidenceGapDetector
from app.services.evidence.mapper import (
    CandidateEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
    EvidenceMapper,
)
from app.services.evidence.normalizer import SourceNormalizer
from app.services.evidence.requirements import (
    CandidateEvidenceRequirement,
    CandidateRequirementsPayload,
    EvidenceRequirementEngine,
    validate_target_reference,
)
from app.services.evidence.retriever import (
    EvidenceRetriever,
    EvidenceRetrieverError,
)
from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchProviderError,
    SearchResultItem,
)
from app.services.evidence.service import (
    EvidenceService,
    EvidenceServiceError,
    build_deterministic_summary,
)
from app.services.llm.client import (
    FakeLLMClient,
    LLMResponseValidationError,
)
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Fixtures & Test Data
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    """Canonical DecisionModel for SaaS pricing inquiry."""
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


@pytest.fixture
def mock_search_item() -> SearchResultItem:
    return SearchResultItem(
        title="B2B SaaS Pricing Elasticity Research",
        url="https://metrics.example.com/saas-elasticity?utm_source=feed",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        publisher="SaaS Metrics Journal",
    )


@pytest.fixture
def fake_search_provider(mock_search_item: SearchResultItem) -> FakeSearchProvider:
    return FakeSearchProvider(default_results=[mock_search_item])


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def evidence_service(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
) -> EvidenceService:
    return EvidenceService.create_default(
        llm_client=fake_llm_client,
        search_provider=fake_search_provider,
    )


# ------------------------------------------------------------------------------
# Tests 1-35
# ------------------------------------------------------------------------------

def test_01_full_pipeline_succeeds(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """1. Full DecisionModel -> EvidencePackage pipeline succeeds."""
    package = evidence_service.build_evidence_package(saas_decision_model)

    assert isinstance(package, EvidencePackage)
    assert package.decision_model_id == saas_decision_model.id
    assert len(package.requirements) > 0
    assert len(package.sources) > 0
    assert len(package.items) > 0
    assert len(package.claim_links) > 0


def test_02_package_contains_final_updated_statuses(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """2. EvidencePackage contains final updated requirement statuses (not just PENDING)."""
    package = evidence_service.build_evidence_package(saas_decision_model)

    statuses = [r.status for r in package.requirements]
    # At least one requirement should be resolved (e.g. FULFILLED)
    assert RequirementStatus.FULFILLED in statuses


def test_03_external_research_reaches_search_provider(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """3. EXTERNAL_RESEARCH requirement reaches FakeSearchProvider."""
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    service.build_evidence_package(saas_decision_model)

    assert len(fake_search_provider.queries_executed) > 0
    assert any("price" in q.lower() or "saas" in q.lower() for q in fake_search_provider.queries_executed)


def test_04_to_06_non_external_requirements_do_not_reach_search_provider(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """4-6. INTERNAL_DATA, USER_CLARIFICATION, and DETERMINISTIC_CALCULATION do not reach SearchProvider."""
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="var_monthly_churn",
                    target_entity_type=DecisionEntityType.VARIABLE,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Internal churn rate.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["should not be searched"],
                ),
                CandidateEvidenceRequirement(
                    target_entity_id="stk_prospects",
                    target_entity_type=DecisionEntityType.STAKEHOLDER,
                    kind=EvidenceKind.USER_CLARIFICATION,
                    description="Target segment clarification.",
                    priority=CriticalityLevel.MEDIUM,
                    suggested_queries=["should not be searched"],
                ),
                CandidateEvidenceRequirement(
                    target_entity_id="trd_volume_vs_arpu",
                    target_entity_type=DecisionEntityType.TRADEOFF,
                    kind=EvidenceKind.DETERMINISTIC_CALCULATION,
                    description="Break-even calculation.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["should not be searched"],
                ),
            ]
        ),
    )
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    # Search provider was never called
    assert len(fake_search_provider.queries_executed) == 0
    assert len(package.requirements) == 3


def test_07_canonical_duplicate_urls_produce_one_source(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """7. Canonical duplicate URLs produce one Source in package."""
    # Two search results with different tracking params / fragments pointing to the same article
    item1 = SearchResultItem(
        title="Price Elasticity A",
        url="https://example.com/elasticity?utm_source=twitter",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
    )
    item2 = SearchResultItem(
        title="Price Elasticity B",
        url="https://example.com/elasticity#summary",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
    )
    provider = FakeSearchProvider(default_results=[item1, item2])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    # Deduplicated by canonical URL
    urls = [s.url for s in package.sources]
    assert len(urls) == len(set(urls))
    assert "https://example.com/elasticity" in urls


def test_08_duplicate_source_lineage_preserves_provenance(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """8. Duplicate source lineage does not break evidence provenance."""
    item = SearchResultItem(
        title="Multi-Query SaaS Benchmark",
        url="https://example.com/report",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
    )
    provider = FakeSearchProvider(default_results=[item])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    # Every item and link has valid references
    source_ids = {s.id for s in package.sources}
    for evi_item in package.items:
        assert evi_item.source_id in source_ids


def test_09_evidence_item_source_resolves_to_packaged_source(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """9. EvidenceItem.source_id resolves to packaged Source."""
    package = evidence_service.build_evidence_package(saas_decision_model)
    source_ids = {s.id for s in package.sources}
    for item in package.items:
        assert item.source_id in source_ids


def test_10_claim_evidence_link_resolves_to_packaged_item(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """10. ClaimEvidenceLink.evidence_item_id resolves to packaged item."""
    package = evidence_service.build_evidence_package(saas_decision_model)
    item_ids = {i.id for i in package.items}
    for link in package.claim_links:
        assert link.evidence_item_id in item_ids


def test_11_claim_evidence_link_requirement_id_resolves_to_packaged_requirement(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """11. ClaimEvidenceLink.requirement_id resolves to packaged requirement."""
    package = evidence_service.build_evidence_package(saas_decision_model)
    req_ids = {r.id for r in package.requirements}
    for link in package.claim_links:
        if link.requirement_id is not None:
            assert link.requirement_id in req_ids


def test_12_evidence_gap_requirement_id_resolves_to_packaged_requirement(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """12. EvidenceGap.requirement_id resolves to packaged requirement."""
    package = evidence_service.build_evidence_package(saas_decision_model)
    req_ids = {r.id for r in package.requirements}
    for gap in package.gaps:
        if gap.requirement_id is not None:
            assert gap.requirement_id in req_ids


def test_13_conflicting_evidence_ids_resolve_to_packaged_items(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """13. Conflicting evidence IDs resolve to packaged items."""
    # Register candidate requirement
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Validate price elasticity assumption.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["price elasticity conflict test"],
                )
            ]
        ),
    )
    # Register candidate findings with both SUPPORTS and CHALLENGES
    fake_llm_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Price reduction increased customer conversion by 30%.",
                    summary="30% lift in conversion.",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Supports acquisition lift.",
                ),
                CandidateFinding(
                    content="Price reduction caused brand dilution and 20% higher churn.",
                    summary="Brand dilution observed.",
                    stance=EvidenceStance.CHALLENGES,
                    reasoning="Challenges price reduction value.",
                ),
            ]
        ),
    )
    item = SearchResultItem(
        title="Price Elasticity Studies",
        url="https://example.com/elasticity-studies",
        snippet="Price reduction increased customer conversion by 30%. Price reduction caused brand dilution and 20% higher churn.",
        raw_content="Price reduction increased customer conversion by 30%. Price reduction caused brand dilution and 20% higher churn.",
    )
    provider = FakeSearchProvider(default_results=[item])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    assert package.requirements[0].status == RequirementStatus.CONTESTED
    assert len(package.gaps) == 1
    gap = package.gaps[0]
    assert gap.gap_type == EvidenceGapType.CONFLICTING_EVIDENCE
    item_ids = {i.id for i in package.items}
    for eid in gap.conflicting_evidence_ids:
        assert eid in item_ids


def test_14_to_16_cross_model_target_references_resolve(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """14-16. Requirement, link, and gap target references resolve against DecisionModel."""
    package = evidence_service.build_evidence_package(saas_decision_model)

    for r in package.requirements:
        validate_target_reference(saas_decision_model, r.target_entity_id, r.target_entity_type)
    for link in package.claim_links:
        validate_target_reference(saas_decision_model, link.target_entity_id, link.target_entity_type)
    for gap in package.gaps:
        validate_target_reference(saas_decision_model, gap.target_entity_id, gap.target_entity_type)


def test_17_package_summary_is_deterministic(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """17. Package summary is strictly deterministic across repeated runs."""
    pkg1 = evidence_service.build_evidence_package(saas_decision_model)
    pkg2 = evidence_service.build_evidence_package(saas_decision_model)

    assert pkg1.summary == pkg2.summary


def test_18_package_summary_contains_factual_counts(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """18. Package summary contains factual counts."""
    package = evidence_service.build_evidence_package(saas_decision_model)

    assert f"{len(package.requirements)} evidence requirements" in package.summary
    assert f"{len(package.sources)} unique sources" in package.summary
    assert f"{len(package.items)} evidence findings" in package.summary
    assert "gap" in package.summary


def test_19_package_summary_contains_no_recommendation(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """19. Package summary contains no business recommendation."""
    package = evidence_service.build_evidence_package(saas_decision_model)
    summary_lower = package.summary.lower()

    assert "recommend" not in summary_lower
    assert "should reduce" not in summary_lower
    assert "therefore" not in summary_lower
    assert "best decision" not in summary_lower


def test_20_empty_requirement_pipeline_returns_valid_package(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """20. Empty requirement pipeline returns valid empty EvidencePackage."""
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(requirements=[]),
    )
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    assert package.requirements == []
    assert package.sources == []
    assert package.items == []
    assert package.claim_links == []
    assert package.gaps == []
    assert "0 evidence requirements" in package.summary


def test_21_internal_data_only_produces_unresolved_unknown(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """21. INTERNAL_DATA-only package produces UNRESOLVED_UNKNOWN."""
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="var_monthly_churn",
                    target_entity_type=DecisionEntityType.VARIABLE,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Internal proprietary historical churn rate.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=[],
                )
            ]
        ),
    )
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    assert len(package.requirements) == 1
    assert package.requirements[0].status == RequirementStatus.PENDING
    assert len(package.gaps) == 1
    assert package.gaps[0].gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN


def test_22_user_clarification_only_produces_unresolved_unknown(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """22. USER_CLARIFICATION-only package produces UNRESOLVED_UNKNOWN."""
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="stk_prospects",
                    target_entity_type=DecisionEntityType.STAKEHOLDER,
                    kind=EvidenceKind.USER_CLARIFICATION,
                    description="Clarification on target prospect price sensitivity threshold.",
                    priority=CriticalityLevel.MEDIUM,
                    suggested_queries=[],
                )
            ]
        ),
    )
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    assert len(package.requirements) == 1
    assert package.requirements[0].status == RequirementStatus.PENDING
    assert len(package.gaps) == 1
    assert package.gaps[0].gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN


def test_23_deterministic_calculation_remains_pending_without_fabricated_evidence(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """23. DETERMINISTIC_CALCULATION-only package remains pending without fabricated empirical evidence."""
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="trd_volume_vs_arpu",
                    target_entity_type=DecisionEntityType.TRADEOFF,
                    kind=EvidenceKind.DETERMINISTIC_CALCULATION,
                    description="Calculate break-even sales volume increase required to offset 20% ARPU decline.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=[],
                )
            ]
        ),
    )
    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    assert len(package.requirements) == 1
    assert package.requirements[0].status == RequirementStatus.PENDING
    assert len(package.gaps) == 0
    assert len(package.items) == 0


def test_24_provider_empty_search_result_does_not_crash(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """24. Provider empty search result does not crash package assembly."""
    empty_provider = FakeSearchProvider(default_results=[])
    service = EvidenceService.create_default(fake_llm_client, empty_provider)

    package = service.build_evidence_package(saas_decision_model)

    assert isinstance(package, EvidencePackage)
    # External research requirements should be UNSUPPORTED
    ext_reqs = [r for r in package.requirements if r.kind == EvidenceKind.EXTERNAL_RESEARCH]
    for r in ext_reqs:
        assert r.status == RequirementStatus.UNSUPPORTED


def test_25_irrelevant_retrieved_material_yields_unsupported_state(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """25. Irrelevant retrieved material yields zero EvidenceItems and appropriate gap."""
    fake_llm_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(findings=[]),
    )
    item = SearchResultItem(
        title="Unrelated Topic",
        url="https://example.com/unrelated",
        snippet="Completely unrelated article discussing gardening tips and soil pH levels.",
        raw_content="Completely unrelated article discussing gardening tips and soil pH levels.",
    )
    provider = FakeSearchProvider(default_results=[item])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    assert len(package.items) == 0
    assert len(package.claim_links) == 0
    # External requirements become UNSUPPORTED with UNSUPPORTED_CLAIM gaps
    unsupported_gaps = [g for g in package.gaps if g.gap_type == EvidenceGapType.UNSUPPORTED_CLAIM]
    assert len(unsupported_gaps) > 0


def test_26_provider_error_is_not_converted_to_empty_evidence(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """26. Search provider error propagates controlled EvidenceServiceError."""
    failing_provider = FakeSearchProvider()
    failing_provider.register_error(SearchProviderError("Mock search API timeout."))

    service = EvidenceService.create_default(fake_llm_client, failing_provider)

    with pytest.raises(EvidenceServiceError) as exc_info:
        service.build_evidence_package(saas_decision_model)

    assert exc_info.value.stage == "retrieval"
    assert isinstance(exc_info.value.__cause__, (EvidenceRetrieverError, SearchProviderError))


def test_27_malformed_llm_output_propagates_controlled_error(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """27. Malformed LLM candidate output propagates controlled EvidenceServiceError."""
    fake_llm_client.register_error(LLMResponseValidationError("Mock malformed candidate JSON."))

    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)

    with pytest.raises(EvidenceServiceError) as exc_info:
        service.build_evidence_package(saas_decision_model)

    assert exc_info.value.stage == "requirement_generation"
    assert isinstance(exc_info.value.__cause__, LLMResponseValidationError)


def test_28_package_construction_does_not_mutate_decision_model(
    evidence_service: EvidenceService, saas_decision_model: DecisionModel
) -> None:
    """28. Package construction does not mutate caller-owned DecisionModel."""
    model_json_before = saas_decision_model.model_dump_json()

    evidence_service.build_evidence_package(saas_decision_model)

    assert saas_decision_model.model_dump_json() == model_json_before


def test_29_package_construction_does_not_mutate_original_requirements_unexpectedly(
    fake_llm_client: FakeLLMClient,
    fake_search_provider: FakeSearchProvider,
    saas_decision_model: DecisionModel,
) -> None:
    """29. Package construction returns new copies with updated statuses without mutating original requirements."""
    engine = EvidenceRequirementEngine(llm_client=fake_llm_client)
    orig_reqs = engine.generate_requirements(saas_decision_model)
    assert all(r.status == RequirementStatus.PENDING for r in orig_reqs)

    service = EvidenceService.create_default(fake_llm_client, fake_search_provider)
    package = service.build_evidence_package(saas_decision_model)

    # Package requirements have updated statuses
    assert any(r.status == RequirementStatus.FULFILLED for r in package.requirements)
    # Original requirements remain PENDING
    assert all(r.status == RequirementStatus.PENDING for r in orig_reqs)


def test_30_service_has_no_direct_gemini_dependency() -> None:
    """30. EvidenceService has no direct Gemini dependency."""
    init_sig = inspect.signature(EvidenceService.__init__)
    assert "gemini" not in str(init_sig).lower()
    src = inspect.getsource(EvidenceService)
    assert "GeminiLLMClient" not in src


def test_31_service_has_no_direct_concrete_search_vendor_dependency() -> None:
    """31. EvidenceService has no direct concrete search vendor dependency."""
    src = inspect.getsource(EvidenceService)
    assert "tavily" not in src.lower()
    assert "serp" not in src.lower()
    assert "bing" not in src.lower()


def test_32_normal_tests_require_no_gemini_api_key(
    evidence_service: EvidenceService,
    saas_decision_model: DecisionModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """32. Normal tests require no GEMINI_API_KEY."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    package = evidence_service.build_evidence_package(saas_decision_model)
    assert package is not None


def test_33_normal_tests_make_zero_external_network_calls(
    evidence_service: EvidenceService,
    saas_decision_model: DecisionModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """33. Normal tests make zero external network calls."""
    def _fail_on_socket(*args, **kwargs):
        pytest.fail("Network socket access attempted during EvidenceService execution.")

    monkeypatch.setattr("socket.socket", _fail_on_socket)

    package = evidence_service.build_evidence_package(saas_decision_model)
    assert package is not None


def test_34_saas_end_to_end_regression(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """34. SaaS End-to-End Regression:
    - req_1: EXTERNAL_RESEARCH on asm_elasticity -> receives grounded search evidence -> FULFILLED
    - req_2: INTERNAL_DATA on unk_competitor_pricing -> PENDING + UNRESOLVED_UNKNOWN
    - req_3: DETERMINISTIC_CALCULATION on trd_volume_vs_arpu -> PENDING without fake calculation
    - Sources: deduplicated canonical Sources
    - Evidence: grounded EvidenceItems
    - Links: requirement_id preserved
    - Gaps: correctly derived
    - Summary: deterministic counts only
    - No recommendation.
    """
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Price elasticity proof for B2B SaaS under 20% discount.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["B2B SaaS 20 percent price discount elasticity study"],
                ),
                CandidateEvidenceRequirement(
                    target_entity_id="unk_competitor_pricing",
                    target_entity_type=DecisionEntityType.UNKNOWN,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Current blended internal CAC across customer tiers.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=[],
                ),
                CandidateEvidenceRequirement(
                    target_entity_id="trd_volume_vs_arpu",
                    target_entity_type=DecisionEntityType.TRADEOFF,
                    kind=EvidenceKind.DETERMINISTIC_CALCULATION,
                    description="Break-even sales volume increase required to offset 20% ARPU decline.",
                    priority=CriticalityLevel.MEDIUM,
                    suggested_queries=[],
                ),
            ]
        ),
    )

    item = SearchResultItem(
        title="B2B SaaS Price Elasticity Study",
        url="https://research.example.com/elasticity",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        publisher="SaaS Metrics Journal",
    )
    provider = FakeSearchProvider(default_results=[item])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    req_map = {r.id: r for r in package.requirements}
    req_1 = [r for r in package.requirements if r.kind == EvidenceKind.EXTERNAL_RESEARCH][0]
    req_2 = [r for r in package.requirements if r.kind == EvidenceKind.INTERNAL_DATA][0]
    req_3 = [r for r in package.requirements if r.kind == EvidenceKind.DETERMINISTIC_CALCULATION][0]

    # req_1 is FULFILLED with mapped evidence
    assert req_1.status == RequirementStatus.FULFILLED
    # req_2 is PENDING
    assert req_2.status == RequirementStatus.PENDING
    # req_3 is PENDING
    assert req_3.status == RequirementStatus.PENDING

    # Gaps check
    assert len(package.gaps) == 1
    assert package.gaps[0].gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN
    assert package.gaps[0].requirement_id == req_2.id

    # Sources check
    assert len(package.sources) == 1
    assert package.sources[0].url == "https://research.example.com/elasticity"

    # EvidenceItems check
    assert len(package.items) >= 1
    assert package.items[0].source_id == package.sources[0].id

    # ClaimEvidenceLinks check
    assert len(package.claim_links) >= 1
    assert package.claim_links[0].requirement_id == req_1.id
    assert package.claim_links[0].stance == EvidenceStance.SUPPORTS

    # Summary check
    assert "3 evidence requirements" in package.summary
    assert "1 fulfilled" in package.summary
    assert "2 pending" in package.summary
    assert "recommend" not in package.summary.lower()


def test_35_conflict_end_to_end_regression(
    fake_llm_client: FakeLLMClient,
    saas_decision_model: DecisionModel,
) -> None:
    """35. Conflict End-to-End Regression:
    - One EXTERNAL_RESEARCH requirement receives 1 SUPPORTS finding and 1 CHALLENGES finding
    - requirement.status = CONTESTED
    - Exactly 1 CONFLICTING_EVIDENCE gap
    - conflicting_evidence_ids contains actual packaged EvidenceItem IDs.
    """
    fake_llm_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Validate price elasticity assumption.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["price elasticity conflict study"],
                )
            ]
        ),
    )
    fake_llm_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Price reduction increased customer conversion by 30%.",
                    summary="30% lift in conversion.",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Supports acquisition lift.",
                ),
                CandidateFinding(
                    content="Price reduction caused brand dilution and 20% higher churn.",
                    summary="Brand dilution observed.",
                    stance=EvidenceStance.CHALLENGES,
                    reasoning="Challenges price reduction value.",
                ),
            ]
        ),
    )

    item = SearchResultItem(
        title="Price Elasticity Findings",
        url="https://example.com/conflict",
        snippet="Price reduction increased customer conversion by 30%. Price reduction caused brand dilution and 20% higher churn.",
        raw_content="Price reduction increased customer conversion by 30%. Price reduction caused brand dilution and 20% higher churn.",
    )
    provider = FakeSearchProvider(default_results=[item])
    service = EvidenceService.create_default(fake_llm_client, provider)

    package = service.build_evidence_package(saas_decision_model)

    assert len(package.requirements) == 1
    assert package.requirements[0].status == RequirementStatus.CONTESTED

    assert len(package.gaps) == 1
    gap = package.gaps[0]
    assert gap.gap_type == EvidenceGapType.CONFLICTING_EVIDENCE
    assert len(gap.conflicting_evidence_ids) == 2
    item_ids = {i.id for i in package.items}
    for cid in gap.conflicting_evidence_ids:
        assert cid in item_ids
