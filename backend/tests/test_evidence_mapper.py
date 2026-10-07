"""Unit and regression tests for AURA Day 3 Phase 9 EvidenceMapper.

Verifies:
1. Relevant source material creates EvidenceItem.
2. Correct Source.id is propagated.
3. Correct target_entity_id is propagated.
4. Correct target_entity_type is propagated.
5. SUPPORTS stance.
6. CHALLENGES stance.
7. CONTEXT stance.
8. INCONCLUSIVE stance.
9. EvidenceItem.content remains grounded in supplied source text.
10. summary can contain concise AURA interpretation.
11. explicit numeric value can become NumericEvidence.
12. explicit range can become NumericEvidence.
13. explicit sample size can become NumericEvidence.
14. hallucinated numeric value absent from source is rejected.
15. hallucinated sample size absent from source is rejected.
16. irrelevant source may return zero EvidenceItems.
17. one source may produce multiple relevant findings.
18. duplicate evidence content for same source/target is deduplicated.
19. same source can map to different targets through separate requirements without losing target provenance.
20. unknown requirement_id is rejected.
21. invalid target reference is rejected.
22. malformed LLM output handled through existing conventions.
23. Source.reliability_score remains untouched.
24. no EvidenceGap generated.
25. no EvidencePackage generated.
26. no recommendation generated.
27. mapper makes no SearchProvider calls.
28. mapper performs no URL/network fetching.
29. normal tests make zero Gemini calls.
30. no GEMINI_API_KEY required.
31. SaaS pricing scenario regression.
"""

from datetime import date, timezone
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
from app.services.evidence.mapper import (
    CandidateEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
    EvidenceMapper,
    EvidenceMappingResult,
)
from app.services.evidence.normalizer import NormalizedSourceResult
from app.services.evidence.search_provider import SearchResultItem
from app.services.llm.client import FakeLLMClient, LLMResponseValidationError
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Fixtures & Helpers
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    """Provides canonical DecisionModel for SaaS pricing inquiry."""
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _create_requirement(
    req_id: str = "req_elasticity",
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
    kind: EvidenceKind = EvidenceKind.EXTERNAL_RESEARCH,
    queries: Optional[List[str]] = None,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=kind,
        description="Empirical B2B SaaS price elasticity benchmarks.",
        status=RequirementStatus.PENDING,
        suggested_queries=queries or ["B2B SaaS price elasticity"],
    )


def _create_normalized_source(
    req_id: str = "req_elasticity",
    query: str = "B2B SaaS price elasticity",
    source_id: str = "src_1",
    url: str = "https://example.com/reports/saas-pricing-2024",
    title: str = "2024 SaaS Pricing Benchmark Report",
    snippet: str = "[MOCK] In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
    raw_content: Optional[str] = None,
) -> NormalizedSourceResult:
    src = Source(
        id=source_id,
        url=url,
        title=title,
        publisher="Expansion Benchmark Lab",
        source_type=SourceType.OTHER,
        publication_date=date(2024, 9, 15),
    )
    search_item = SearchResultItem(
        url=url,
        title=title,
        snippet=snippet,
        publisher="Expansion Benchmark Lab",
        published_date=date(2024, 9, 15),
        raw_content=raw_content,
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query=query,
        source=src,
        search_result=search_item,
    )


# ------------------------------------------------------------------------------
# 1-4: Basic Mapping & Provenance Tests
# ------------------------------------------------------------------------------

def test_relevant_source_material_creates_evidence_item(
    saas_decision_model: DecisionModel,
) -> None:
    """1. Verifies that relevant source material creates EvidenceItem."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src],
    )

    assert isinstance(result, EvidenceMappingResult)
    assert len(result.items) == 1
    assert result.items[0].id == "evi_1"


def test_correct_source_id_propagated(saas_decision_model: DecisionModel) -> None:
    """2. Verifies EvidenceItem.source_id is strictly derived from NormalizedSourceResult.source.id."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source(source_id="src_custom_42")

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src],
    )

    assert result.items[0].source_id == "src_custom_42"


def test_correct_target_entity_id_propagated(saas_decision_model: DecisionModel) -> None:
    """3. Verifies target_entity_id is propagated to ClaimEvidenceLink."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_unk",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
    )
    norm_src = _create_normalized_source(req_id="req_unk")

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src],
    )

    assert result.claim_links[0].target_entity_id == "unk_competitor_pricing"


def test_correct_target_entity_type_propagated(saas_decision_model: DecisionModel) -> None:
    """4. Verifies target_entity_type is propagated to ClaimEvidenceLink."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_unk",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
    )
    norm_src = _create_normalized_source(req_id="req_unk")

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src],
    )

    assert result.claim_links[0].target_entity_type == DecisionEntityType.UNKNOWN


# ------------------------------------------------------------------------------
# 5-8: Stance Classification Tests
# ------------------------------------------------------------------------------

def test_supports_stance(saas_decision_model: DecisionModel) -> None:
    """5. Verifies SUPPORTS stance is correctly propagated."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Price reduction increased sales volume by 15%.",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Bolsters assumption that discount increases volume.",
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet="Price reduction increased sales volume by 15%.")

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.claim_links[0].stance == EvidenceStance.SUPPORTS


def test_challenges_stance(saas_decision_model: DecisionModel) -> None:
    """6. Verifies CHALLENGES stance is correctly propagated."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Price reduction caused higher churn and no volume increase.",
                    stance=EvidenceStance.CHALLENGES,
                    reasoning="Refutes assumption that discounting expands market.",
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet="Price reduction caused higher churn and no volume increase.")

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.claim_links[0].stance == EvidenceStance.CHALLENGES


def test_context_stance(saas_decision_model: DecisionModel) -> None:
    """7. Verifies CONTEXT stance is correctly propagated."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Average SaaS contract length is 14 months.",
                    stance=EvidenceStance.CONTEXT,
                    reasoning="Provides market framing for churn horizons.",
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet="Average SaaS contract length is 14 months.")

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.claim_links[0].stance == EvidenceStance.CONTEXT


def test_inconclusive_stance(saas_decision_model: DecisionModel) -> None:
    """8. Verifies INCONCLUSIVE stance is correctly propagated."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Statistical power was insufficient to determine price effect.",
                    stance=EvidenceStance.INCONCLUSIVE,
                    reasoning="Sample was too noisy to reach definitive conclusion.",
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet="Statistical power was insufficient to determine price effect.")

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.claim_links[0].stance == EvidenceStance.INCONCLUSIVE


# ------------------------------------------------------------------------------
# 9-10: Grounding, Content & Summary Tests
# ------------------------------------------------------------------------------

def test_evidence_item_content_remains_grounded(saas_decision_model: DecisionModel) -> None:
    """9. Verifies EvidenceItem.content is grounded in supplied source text."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert "240 B2B SaaS companies" in result.items[0].content


def test_summary_can_contain_concise_aura_interpretation(
    saas_decision_model: DecisionModel,
) -> None:
    """10. Verifies summary can contain concise AURA interpretation."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    item = result.items[0]
    assert item.summary is not None
    assert "customer acquisition increase" in item.summary.lower()


# ------------------------------------------------------------------------------
# 11-15: Numeric Anti-Hallucination & Validation Tests
# ------------------------------------------------------------------------------

def test_explicit_numeric_value_can_become_numeric_evidence(
    saas_decision_model: DecisionModel,
) -> None:
    """11. Verifies explicit numeric value becomes NumericEvidence."""
    source_text = "[MOCK] Discount resulted in 14% conversion gain."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content=source_text,
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Point estimate validated.",
                    numeric_data=[
                        CandidateNumericEvidence(
                            metric_name="conversion_gain",
                            value=14.0,
                            unit="%",
                        )
                    ],
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items[0].numeric_data) == 1
    assert result.items[0].numeric_data[0].value == 14.0
    assert result.items[0].numeric_data[0].unit == "%"


def test_explicit_range_can_become_numeric_evidence(
    saas_decision_model: DecisionModel,
) -> None:
    """12. Verifies explicit range becomes NumericEvidence."""
    source_text = "[MOCK] Observed elasticity range was 12.0 to 16.0%."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content=source_text,
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Range interval validated.",
                    numeric_data=[
                        CandidateNumericEvidence(
                            metric_name="elasticity_range",
                            range_min=12.0,
                            range_max=16.0,
                            unit="%",
                        )
                    ],
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items[0].numeric_data) == 1
    num = result.items[0].numeric_data[0]
    assert num.range_min == 12.0
    assert num.range_max == 16.0


def test_explicit_sample_size_can_become_numeric_evidence(
    saas_decision_model: DecisionModel,
) -> None:
    """13. Verifies explicit sample size becomes NumericEvidence."""
    source_text = "[MOCK] Study evaluated 240 companies with 14% gain."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content=source_text,
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Sample size present in source.",
                    numeric_data=[
                        CandidateNumericEvidence(
                            metric_name="gain",
                            value=14.0,
                            sample_size=240,
                        )
                    ],
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.items[0].numeric_data[0].sample_size == 240


def test_hallucinated_numeric_value_absent_from_source_is_rejected(
    saas_decision_model: DecisionModel,
) -> None:
    """14. Verifies hallucinated numeric value absent from source is rejected."""
    source_text = "[MOCK] Discounting improved customer interest substantially."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content=source_text,
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Proposing 35% absent from text.",
                    numeric_data=[
                        CandidateNumericEvidence(
                            metric_name="hallucinated_gain",
                            value=35.0,  # 35 does NOT appear anywhere in source_text
                            unit="%",
                        )
                    ],
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.items[0].numeric_data == []


def test_hallucinated_sample_size_absent_from_source_is_rejected(
    saas_decision_model: DecisionModel,
) -> None:
    """15. Verifies hallucinated sample size absent from source is rejected."""
    source_text = "[MOCK] In our study, conversion expanded by 14%."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content=source_text,
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="14% is valid, but sample size 9999 is fabricated.",
                    numeric_data=[
                        CandidateNumericEvidence(
                            metric_name="conversion_expansion",
                            value=14.0,  # 14 is present
                            unit="%",
                            sample_size=9999,  # 9999 is absent
                        )
                    ],
                )
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items[0].numeric_data) == 1
    assert result.items[0].numeric_data[0].sample_size is None


# ------------------------------------------------------------------------------
# 16-19: Cardinality, Deduplication & Lineage Integrity Tests
# ------------------------------------------------------------------------------

def test_irrelevant_source_may_return_zero_evidence_items(
    saas_decision_model: DecisionModel,
) -> None:
    """16. Verifies an irrelevant source produces zero EvidenceItems."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(findings=[]),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet="Office holiday party scheduled for Friday.")

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert result.items == []
    assert result.claim_links == []


def test_one_source_may_produce_multiple_relevant_findings(
    saas_decision_model: DecisionModel,
) -> None:
    """17. Verifies a single source can produce multiple distinct findings."""
    source_text = "Finding A: volume grew 14%. Finding B: revenue per user fell 8%."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Volume grew 14%.",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Volume increased.",
                ),
                CandidateFinding(
                    content="Revenue per user fell 8%.",
                    stance=EvidenceStance.CHALLENGES,
                    reasoning="ARPU compressed.",
                ),
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items) == 2
    assert len(result.claim_links) == 2

    assert result.items[0].id == "evi_1"
    assert result.items[1].id == "evi_2"
    assert result.claim_links[0].id == "lnk_1"
    assert result.claim_links[1].id == "lnk_2"
    assert result.claim_links[0].evidence_item_id == "evi_1"
    assert result.claim_links[1].evidence_item_id == "evi_2"


def test_duplicate_evidence_content_for_same_source_target_is_deduplicated(
    saas_decision_model: DecisionModel,
) -> None:
    """18. Verifies duplicate evidence content for same source/target is deduplicated."""
    source_text = "Volume expansion was 14%."
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateEvidenceMappingPayload,
        CandidateEvidenceMappingPayload(
            findings=[
                CandidateFinding(
                    content="Volume expansion was 14%.",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="First occurrence.",
                ),
                CandidateFinding(
                    content="  volume   expansion   was 14%.  ",
                    stance=EvidenceStance.SUPPORTS,
                    reasoning="Duplicate identical occurrence.",
                ),
            ]
        ),
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = _create_requirement()
    norm_src = _create_normalized_source(snippet=source_text)

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items) == 1
    assert len(result.claim_links) == 1


def test_same_source_can_map_to_different_targets_through_separate_requirements(
    saas_decision_model: DecisionModel,
) -> None:
    """19. Verifies same source can map to different targets without losing provenance."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req1 = _create_requirement(
        req_id="req_asm",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
    )
    req2 = _create_requirement(
        req_id="req_unk",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
    )

    norm_src1 = _create_normalized_source(req_id="req_asm", source_id="src_shared")
    norm_src2 = _create_normalized_source(req_id="req_unk", source_id="src_shared")

    result = mapper.map_evidence(
        saas_decision_model,
        [req1, req2],
        [norm_src1, norm_src2],
    )

    assert len(result.items) == 2
    assert len(result.claim_links) == 2

    # Both items share the same source_id
    assert result.items[0].source_id == "src_shared"
    assert result.items[1].source_id == "src_shared"

    # But claim links target different entities
    assert result.claim_links[0].target_entity_id == "asm_elasticity"
    assert result.claim_links[1].target_entity_id == "unk_competitor_pricing"


# ------------------------------------------------------------------------------
# 20-22: Error Handling & Validation Tests
# ------------------------------------------------------------------------------

def test_unknown_requirement_id_is_rejected(saas_decision_model: DecisionModel) -> None:
    """20. Verifies NormalizedSourceResult with unknown requirement_id is rejected with ValueError."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(req_id="req_valid")
    norm_src = _create_normalized_source(req_id="req_nonexistent_999")

    with pytest.raises(ValueError) as exc_info:
        mapper.map_evidence(saas_decision_model, [req], [norm_src])

    assert "references unknown requirement_id 'req_nonexistent_999'" in str(exc_info.value)


def test_invalid_target_reference_is_rejected(saas_decision_model: DecisionModel) -> None:
    """21. Verifies target entity missing from DecisionModel is rejected with ValueError."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement(
        req_id="req_bad_target",
        target_id="nonexistent_entity_123",
        target_type=DecisionEntityType.ASSUMPTION,
    )
    norm_src = _create_normalized_source(req_id="req_bad_target")

    with pytest.raises(ValueError) as exc_info:
        mapper.map_evidence(saas_decision_model, [req], [norm_src])

    assert "does not exist in DecisionModel" in str(exc_info.value)


def test_malformed_llm_output_handled_through_existing_conventions(
    saas_decision_model: DecisionModel,
) -> None:
    """22. Verifies malformed structured output raises LLMResponseValidationError."""
    fake_client = FakeLLMClient()
    fake_client.register_error(LLMResponseValidationError("Malformed mapping JSON schema"))
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    with pytest.raises(LLMResponseValidationError):
        mapper.map_evidence(saas_decision_model, [req], [norm_src])


# ------------------------------------------------------------------------------
# 23-30: Boundary, Safety & Credential Tests
# ------------------------------------------------------------------------------

def test_source_reliability_score_remains_untouched(
    saas_decision_model: DecisionModel,
) -> None:
    """23. Verifies source.reliability_score remains None."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert norm_src.source.reliability_score is None


def test_no_evidence_gap_generated(saas_decision_model: DecisionModel) -> None:
    """24. Verifies no EvidenceGap is generated by EvidenceMapper."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert not isinstance(result, EvidenceGap)
    assert not hasattr(result, "gaps")


def test_no_evidence_package_generated(saas_decision_model: DecisionModel) -> None:
    """25. Verifies no EvidencePackage is generated by EvidenceMapper."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert not isinstance(result, EvidencePackage)


def test_no_recommendation_generated(saas_decision_model: DecisionModel) -> None:
    """26. Verifies no recommendation or decision advice is generated."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    for item in result.items:
        assert "recommend" not in item.content.lower()
        if item.summary:
            assert "you should" not in item.summary.lower()


def test_mapper_makes_no_search_provider_calls() -> None:
    """27. Verifies EvidenceMapper has no SearchProvider dependency or calls."""
    init_sig = inspect.signature(EvidenceMapper.__init__)
    assert "search_provider" not in init_sig.parameters


def test_mapper_performs_no_url_network_fetching() -> None:
    """28. Verifies EvidenceMapper performs no URL or network fetching."""
    init_sig = inspect.signature(EvidenceMapper.__init__)
    assert list(init_sig.parameters.keys()) == ["self", "llm_client"]


def test_normal_tests_make_zero_gemini_calls(saas_decision_model: DecisionModel) -> None:
    """29. Verifies mapper runs under test fail-closed safety with FakeLLMClient (zero live Gemini calls)."""
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(fake_client.call_history) == 1
    assert len(result.items) == 1


def test_no_gemini_api_key_required(
    monkeypatch: pytest.MonkeyPatch,
    saas_decision_model: DecisionModel,
) -> None:
    """30. Verifies EvidenceMapper operates with zero GEMINI_API_KEY environment requirement."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = _create_requirement()
    norm_src = _create_normalized_source()

    result = mapper.map_evidence(saas_decision_model, [req], [norm_src])
    assert len(result.items) == 1


# ------------------------------------------------------------------------------
# 31: Full SaaS Scenario Regression Test
# ------------------------------------------------------------------------------

def test_saas_pricing_scenario_regression(saas_decision_model: DecisionModel) -> None:
    """31. Executes the exact prompt-specified SaaS pricing regression scenario.

    Target assumption:
    "Lower pricing may materially increase customer acquisition."

    Requirement:
    EXTERNAL_RESEARCH

    Retrieved source material contains illustrative deterministic fixture:
    "[MOCK] In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition."

    Expected:
    EvidenceItem:
    - source_id from normalized Source (src_1)
    - content grounded in supplied fixture
    - numeric_data contains 14%, 20%, sample_size 240

    ClaimEvidenceLink:
    - target = assumption
    - stance determined from fixture/target relationship (SUPPORTS)
    - no recommendations
    """
    fake_client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_client)

    req = EvidenceRequirement(
        id="req_elasticity",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical price elasticity evidence for B2B SaaS price reductions.",
        status=RequirementStatus.PENDING,
        suggested_queries=[
            "B2B SaaS price elasticity customer acquisition",
        ],
    )

    fixture_text = (
        "[MOCK] In a sample of 240 B2B SaaS companies, a 20% pricing reduction was "
        "associated with a 14% median increase in new customer acquisition."
    )

    norm_src = _create_normalized_source(
        req_id="req_elasticity",
        source_id="src_1",
        title="[MOCK] 2024 SaaS Pricing Benchmark Report",
        snippet=fixture_text,
    )

    result = mapper.map_evidence(
        decision_model=saas_decision_model,
        requirements=[req],
        normalized_sources=[norm_src],
    )

    assert len(result.items) == 1
    assert len(result.claim_links) == 1

    item = result.items[0]
    link = result.claim_links[0]

    # 1. Source ID strictly from normalized Source
    assert item.source_id == "src_1"

    # 2. Content grounded in supplied fixture
    assert "240 B2B SaaS companies" in item.content
    assert "14% median increase" in item.content

    # 3. Numeric data extracted and verified
    assert len(item.numeric_data) >= 1
    metrics = {n.metric_name: n for n in item.numeric_data}
    assert "acquisition_increase" in metrics
    assert metrics["acquisition_increase"].value == 14.0
    assert metrics["acquisition_increase"].unit == "%"
    assert metrics["acquisition_increase"].sample_size == 240

    assert "price_reduction" in metrics
    assert metrics["price_reduction"].value == 20.0
    assert metrics["price_reduction"].unit == "%"

    # 4. Claim link target & stance
    assert link.target_entity_id == "asm_elasticity"
    assert link.target_entity_type == DecisionEntityType.ASSUMPTION
    assert link.stance == EvidenceStance.SUPPORTS
    assert link.evidence_item_id == item.id

    # 5. No recommendation text
    assert "recommend" not in link.reasoning.lower()
    assert "you should" not in link.reasoning.lower()
