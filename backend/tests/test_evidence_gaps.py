"""Unit and regression tests for AURA Day 3 Phase 10 EvidenceGapDetector.

Verifies:
1. EXTERNAL_RESEARCH with SUPPORTS only -> FULFILLED.
2. EXTERNAL_RESEARCH with CHALLENGES only -> FULFILLED.
3. FULFILLED does not mean target claim is true.
4. SUPPORTS + CHALLENGES -> CONTESTED.
5. SUPPORTS + CHALLENGES creates CONFLICTING_EVIDENCE.
6. conflict gap contains actual supporting/challenging EvidenceItem IDs.
7. SUPPORTS + CONTEXT does not create conflict.
8. CHALLENGES + INCONCLUSIVE does not create conflict.
9. only CONTEXT -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE.
10. only INCONCLUSIVE -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE.
11. CONTEXT + INCONCLUSIVE -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE.
12. EXTERNAL_RESEARCH claim with no mapped evidence -> UNSUPPORTED + UNSUPPORTED_CLAIM.
13. unresolved INTERNAL_DATA -> PENDING + UNRESOLVED_UNKNOWN.
14. unresolved USER_CLARIFICATION -> PENDING + UNRESOLVED_UNKNOWN.
15. DETERMINISTIC_CALCULATION is not executed by detector.
16. gap impact derives from requirement priority.
17. deterministic gap IDs.
18. conflicting_evidence_ids deduplicated.
19. invalid EvidenceItem reference rejected.
20. invalid requirement provenance rejected.
21. invalid DecisionModel target rejected.
22. duplicate requirement IDs rejected.
23. duplicate EvidenceItem IDs rejected.
24. duplicate ClaimEvidenceLink IDs rejected.
25. empty requirements/evidence returns empty result.
26. original input requirements are not mutated.
27. detector has no LLMClient dependency.
28. detector makes no SearchProvider calls.
29. no external network calls.
30. no Gemini API key required.
31. same target with two separate requirements preserves requirement-level status independently.
32. SaaS regression scenario.
33. Provenance regression scenario.
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
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
)
from app.services.evidence.gaps import (
    EvidenceGapDetectionResult,
    EvidenceGapDetector,
)
from app.services.evidence.mapper import EvidenceMappingResult
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Fixtures & Factory Helpers
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    """Canonical DecisionModel for SaaS pricing inquiry."""
    return get_default_decision_model(
        question="Should our startup reduce pricing by 20% to acquire more customers?"
    )


@pytest.fixture
def detector() -> EvidenceGapDetector:
    """Initializes standard EvidenceGapDetector."""
    return EvidenceGapDetector()


def _make_req(
    req_id: str = "req_1",
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
    kind: EvidenceKind = EvidenceKind.EXTERNAL_RESEARCH,
    priority: CriticalityLevel = CriticalityLevel.HIGH,
    description: str = "Validate price elasticity assumption.",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=kind,
        description=description,
        priority=priority,
        status=RequirementStatus.PENDING,
        suggested_queries=["price elasticity benchmarks"],
    )


def _make_item(
    item_id: str,
    source_id: str = "src_1",
    content: str = "Empirical study confirms SaaS demand elasticity of 1.4.",
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        source_id=source_id,
        content=content,
        summary="Demand elasticity exceeds 1.0.",
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime.now(timezone.utc),
    )


def _make_link(
    link_id: str,
    item_id: str,
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
    stance: EvidenceStance = EvidenceStance.SUPPORTS,
    requirement_id: Optional[str] = "req_1",
    reasoning: str = "Empirical benchmark validates the elasticity assumption.",
) -> ClaimEvidenceLink:
    return ClaimEvidenceLink(
        id=link_id,
        evidence_item_id=item_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        stance=stance,
        reasoning=reasoning,
        relationship_confidence=ConfidenceLevel.HIGH,
        requirement_id=requirement_id,
    )


# ------------------------------------------------------------------------------
# Test Cases 1-33
# ------------------------------------------------------------------------------

def test_01_external_research_supports_only_fulfilled(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """1. EXTERNAL_RESEARCH with SUPPORTS only -> FULFILLED."""
    req = _make_req(req_id="req_supports", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item = _make_item(item_id="evi_1")
    link = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)

    mapping = EvidenceMappingResult(items=[item], claim_links=[link])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert len(result.requirements) == 1
    assert result.requirements[0].status == RequirementStatus.FULFILLED
    assert len(result.gaps) == 0


def test_02_external_research_challenges_only_fulfilled(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """2. EXTERNAL_RESEARCH with CHALLENGES only -> FULFILLED."""
    req = _make_req(req_id="req_challenges", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item = _make_item(item_id="evi_1", content="Study demonstrates inelastic B2B software demand.")
    link = _make_link(
        link_id="lnk_1",
        item_id="evi_1",
        requirement_id=req.id,
        stance=EvidenceStance.CHALLENGES,
        reasoning="Shows demand elasticity is only 0.3, challenging the premise.",
    )

    mapping = EvidenceMappingResult(items=[item], claim_links=[link])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert len(result.requirements) == 1
    assert result.requirements[0].status == RequirementStatus.FULFILLED
    assert len(result.gaps) == 0


def test_03_fulfilled_does_not_mean_claim_is_true(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """3. FULFILLED means requirement was answered, NOT that target claim is proven true."""
    req = _make_req(req_id="req_falsify", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item = _make_item(item_id="evi_falsify", content="Pricing cuts failed to lift ACV across 85% of cohort.")
    link = _make_link(
        link_id="lnk_1",
        item_id="evi_falsify",
        requirement_id=req.id,
        stance=EvidenceStance.CHALLENGES,
    )

    mapping = EvidenceMappingResult(items=[item], claim_links=[link])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    # Requirement is fulfilled (the empirical inquiry was answered with definitive data)
    assert result.requirements[0].status == RequirementStatus.FULFILLED
    # But the evidence stance was CHALLENGES (the claim was not proven true)
    assert mapping.claim_links[0].stance == EvidenceStance.CHALLENGES


def test_04_supports_and_challenges_contested(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """4. SUPPORTS + CHALLENGES -> CONTESTED."""
    req = _make_req(req_id="req_conflict", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item_sup = _make_item(item_id="evi_sup", content="Price reduction increased velocity by 40%.")
    item_cha = _make_item(item_id="evi_cha", content="Price reduction degraded brand perceived value.")
    link_sup = _make_link(link_id="lnk_sup", item_id="evi_sup", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link_cha = _make_link(link_id="lnk_cha", item_id="evi_cha", requirement_id=req.id, stance=EvidenceStance.CHALLENGES)

    mapping = EvidenceMappingResult(items=[item_sup, item_cha], claim_links=[link_sup, link_cha])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert len(result.requirements) == 1
    assert result.requirements[0].status == RequirementStatus.CONTESTED


def test_05_supports_and_challenges_creates_conflicting_evidence_gap(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """5. SUPPORTS + CHALLENGES creates CONFLICTING_EVIDENCE."""
    req = _make_req(req_id="req_conflict", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item1 = _make_item(item_id="evi_1", content="Study A shows 2x conversion.")
    item2 = _make_item(item_id="evi_2", content="Study B shows flat conversion.")
    link1 = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link2 = _make_link(link_id="lnk_2", item_id="evi_2", requirement_id=req.id, stance=EvidenceStance.CHALLENGES)

    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[link1, link2])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.gap_type == EvidenceGapType.CONFLICTING_EVIDENCE
    assert gap.requirement_id == req.id
    assert gap.target_entity_id == req.target_entity_id


def test_06_conflict_gap_contains_actual_evidence_ids(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """6. Conflict gap contains actual supporting and challenging EvidenceItem IDs."""
    req = _make_req(req_id="req_conflict", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item_a = _make_item(item_id="evi_alpha", content="Alpha evidence supports.")
    item_b = _make_item(item_id="evi_beta", content="Beta evidence challenges.")
    link_a = _make_link(link_id="lnk_a", item_id="evi_alpha", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link_b = _make_link(link_id="lnk_b", item_id="evi_beta", requirement_id=req.id, stance=EvidenceStance.CHALLENGES)

    mapping = EvidenceMappingResult(items=[item_a, item_b], claim_links=[link_a, link_b])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    gap = result.gaps[0]
    assert len(gap.conflicting_evidence_ids) >= 2
    assert "evi_alpha" in gap.conflicting_evidence_ids
    assert "evi_beta" in gap.conflicting_evidence_ids


def test_07_supports_plus_context_does_not_create_conflict(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """7. SUPPORTS + CONTEXT does not create conflict."""
    req = _make_req(req_id="req_sup_ctx", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item1 = _make_item(item_id="evi_1", content="Directly supports hypothesis.")
    item2 = _make_item(item_id="evi_2", content="General market macroeconomic context.")
    link1 = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link2 = _make_link(link_id="lnk_2", item_id="evi_2", requirement_id=req.id, stance=EvidenceStance.CONTEXT)

    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[link1, link2])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.FULFILLED
    assert len(result.gaps) == 0


def test_08_challenges_plus_inconclusive_does_not_create_conflict(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """8. CHALLENGES + INCONCLUSIVE does not create conflict."""
    req = _make_req(req_id="req_cha_inc", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item1 = _make_item(item_id="evi_1", content="Directly challenges hypothesis.")
    item2 = _make_item(item_id="evi_2", content="Pilot data with mixed inconclusive signals.")
    link1 = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.CHALLENGES)
    link2 = _make_link(link_id="lnk_2", item_id="evi_2", requirement_id=req.id, stance=EvidenceStance.INCONCLUSIVE)

    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[link1, link2])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.FULFILLED
    assert len(result.gaps) == 0


def test_09_only_context_inconclusive_and_insufficient_evidence(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """9. Only CONTEXT -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE."""
    req = _make_req(req_id="req_ctx_only", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item = _make_item(item_id="evi_ctx", content="B2B software market grew by 12% in 2023.")
    link = _make_link(link_id="lnk_ctx", item_id="evi_ctx", requirement_id=req.id, stance=EvidenceStance.CONTEXT)

    mapping = EvidenceMappingResult(items=[item], claim_links=[link])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.INCONCLUSIVE
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.INSUFFICIENT_EVIDENCE


def test_10_only_inconclusive_inconclusive_and_insufficient_evidence(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """10. Only INCONCLUSIVE -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE."""
    req = _make_req(req_id="req_inc_only", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item = _make_item(item_id="evi_inc", content="Sample size insufficient to draw conclusions.")
    link = _make_link(link_id="lnk_inc", item_id="evi_inc", requirement_id=req.id, stance=EvidenceStance.INCONCLUSIVE)

    mapping = EvidenceMappingResult(items=[item], claim_links=[link])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.INCONCLUSIVE
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.INSUFFICIENT_EVIDENCE


def test_11_context_plus_inconclusive_insufficient_evidence(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """11. CONTEXT + INCONCLUSIVE -> INCONCLUSIVE + INSUFFICIENT_EVIDENCE."""
    req = _make_req(req_id="req_ctx_inc", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item1 = _make_item(item_id="evi_1", content="Market industry context.")
    item2 = _make_item(item_id="evi_2", content="Inconclusive early experiment.")
    link1 = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.CONTEXT)
    link2 = _make_link(link_id="lnk_2", item_id="evi_2", requirement_id=req.id, stance=EvidenceStance.INCONCLUSIVE)

    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[link1, link2])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.INCONCLUSIVE
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.INSUFFICIENT_EVIDENCE


def test_12_external_research_with_no_evidence_unsupported_claim(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """12. EXTERNAL_RESEARCH claim with no mapped evidence -> UNSUPPORTED + UNSUPPORTED_CLAIM."""
    req = _make_req(req_id="req_empty", kind=EvidenceKind.EXTERNAL_RESEARCH)
    mapping = EvidenceMappingResult(items=[], claim_links=[])

    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.UNSUPPORTED
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.UNSUPPORTED_CLAIM
    assert result.gaps[0].requirement_id == req.id


def test_13_unresolved_internal_data_unresolved_unknown(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """13. Unresolved INTERNAL_DATA -> PENDING + UNRESOLVED_UNKNOWN."""
    req = _make_req(
        req_id="req_cac",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Current internal blended customer acquisition cost (CAC).",
    )
    mapping = EvidenceMappingResult(items=[], claim_links=[])

    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.PENDING
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN
    assert result.gaps[0].requirement_id == req.id


def test_14_unresolved_user_clarification_unresolved_unknown(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """14. Unresolved USER_CLARIFICATION -> PENDING + UNRESOLVED_UNKNOWN."""
    req = _make_req(
        req_id="req_segment",
        target_id="asm_elasticity",
        target_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.USER_CLARIFICATION,
        description="Clarification on target enterprise vs SMB tier segment.",
    )
    mapping = EvidenceMappingResult(items=[], claim_links=[])

    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    assert result.requirements[0].status == RequirementStatus.PENDING
    assert len(result.gaps) == 1
    assert result.gaps[0].gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN
    assert result.gaps[0].requirement_id == req.id


def test_15_deterministic_calculation_not_executed_by_detector(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """15. DETERMINISTIC_CALCULATION is not executed by detector (remains PENDING, no empirical gap)."""
    req = _make_req(
        req_id="req_math",
        target_id="trd_volume_vs_arpu",
        target_type=DecisionEntityType.TRADEOFF,
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        description="Calculate break-even volume elasticity formula: 20 / (1 - 0.20).",
    )
    mapping = EvidenceMappingResult(items=[], claim_links=[])

    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    # Status remains PENDING awaiting calculation engine, with zero false empirical gaps
    assert result.requirements[0].status == RequirementStatus.PENDING
    assert len(result.gaps) == 0


def test_16_gap_impact_derives_from_requirement_priority(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """16. Gap impact derives from requirement priority."""
    req_high = _make_req(req_id="req_high", priority=CriticalityLevel.HIGH)
    req_low = _make_req(
        req_id="req_low",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        priority=CriticalityLevel.LOW,
    )

    result = detector.detect_gaps(saas_decision_model, [req_high, req_low], EvidenceMappingResult())

    assert len(result.gaps) == 2
    assert result.gaps[0].impact == CriticalityLevel.HIGH
    assert result.gaps[1].impact == CriticalityLevel.LOW


def test_17_deterministic_gap_ids(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """17. Deterministic gap IDs generated in Python sequentially (gap_1, gap_2, ...)."""
    req1 = _make_req(req_id="req_1", target_id="asm_elasticity", kind=EvidenceKind.EXTERNAL_RESEARCH)
    req2 = _make_req(req_id="req_2", target_id="unk_competitor_pricing", target_type=DecisionEntityType.UNKNOWN, kind=EvidenceKind.INTERNAL_DATA)

    result = detector.detect_gaps(saas_decision_model, [req1, req2], EvidenceMappingResult())

    assert len(result.gaps) == 2
    assert result.gaps[0].id == "gap_1"
    assert result.gaps[1].id == "gap_2"


def test_18_conflicting_evidence_ids_deduplicated(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """18. Conflicting evidence IDs deduplicated."""
    req = _make_req(req_id="req_conflict", kind=EvidenceKind.EXTERNAL_RESEARCH)
    item1 = _make_item(item_id="evi_1", content="Finding 1 supports.")
    item2 = _make_item(item_id="evi_2", content="Finding 2 challenges.")
    # Two links pointing to item 1
    link1a = _make_link(link_id="lnk_1a", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link1b = _make_link(link_id="lnk_1b", item_id="evi_1", requirement_id=req.id, stance=EvidenceStance.SUPPORTS)
    link2 = _make_link(link_id="lnk_2", item_id="evi_2", requirement_id=req.id, stance=EvidenceStance.CHALLENGES)

    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[link1a, link1b, link2])
    result = detector.detect_gaps(saas_decision_model, [req], mapping)

    gap = result.gaps[0]
    assert gap.conflicting_evidence_ids == ["evi_1", "evi_2"]
    assert len(gap.conflicting_evidence_ids) == 2


def test_19_invalid_evidence_item_reference_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """19. Invalid EvidenceItem reference rejected."""
    req = _make_req()
    # Link references non-existent evi_missing
    link = _make_link(link_id="lnk_1", item_id="evi_missing", requirement_id=req.id)
    mapping = EvidenceMappingResult(items=[], claim_links=[link])

    with pytest.raises(ValueError, match="non-existent evidence_item_id"):
        detector.detect_gaps(saas_decision_model, [req], mapping)


def test_20_invalid_requirement_provenance_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """20. Invalid requirement provenance rejected."""
    req = _make_req(req_id="req_valid")
    item = _make_item(item_id="evi_1")
    # Link references non-existent requirement_id
    link = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id="req_non_existent")
    mapping = EvidenceMappingResult(items=[item], claim_links=[link])

    with pytest.raises(ValueError, match="non-existent requirement_id"):
        detector.detect_gaps(saas_decision_model, [req], mapping)


def test_21_invalid_decision_model_target_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """21. Invalid DecisionModel target rejected."""
    req = _make_req(target_id="asm_phantom_id")
    mapping = EvidenceMappingResult(items=[], claim_links=[])

    with pytest.raises(ValueError, match="does not exist in DecisionModel"):
        detector.detect_gaps(saas_decision_model, [req], mapping)


def test_22_duplicate_requirement_ids_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """22. Duplicate requirement IDs rejected."""
    req1 = _make_req(req_id="req_dup")
    req2 = _make_req(req_id="req_dup")

    with pytest.raises(ValueError, match="Duplicate requirement ID"):
        detector.detect_gaps(saas_decision_model, [req1, req2], EvidenceMappingResult())


def test_23_duplicate_evidence_item_ids_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """23. Duplicate EvidenceItem IDs rejected."""
    req = _make_req()
    item1 = _make_item(item_id="evi_dup")
    item2 = _make_item(item_id="evi_dup")
    mapping = EvidenceMappingResult(items=[item1, item2], claim_links=[])

    with pytest.raises(ValueError, match="Duplicate EvidenceItem ID"):
        detector.detect_gaps(saas_decision_model, [req], mapping)


def test_24_duplicate_claim_evidence_link_ids_rejected(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """24. Duplicate ClaimEvidenceLink IDs rejected."""
    req = _make_req()
    item = _make_item(item_id="evi_1")
    link1 = _make_link(link_id="lnk_dup", item_id="evi_1", requirement_id=req.id)
    link2 = _make_link(link_id="lnk_dup", item_id="evi_1", requirement_id=req.id)
    mapping = EvidenceMappingResult(items=[item], claim_links=[link1, link2])

    with pytest.raises(ValueError, match="Duplicate ClaimEvidenceLink ID"):
        detector.detect_gaps(saas_decision_model, [req], mapping)


def test_25_empty_requirements_and_evidence_returns_empty_result(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """25. Empty requirements and evidence returns empty result."""
    result = detector.detect_gaps(saas_decision_model, [], EvidenceMappingResult())

    assert result.requirements == []
    assert result.gaps == []


def test_26_original_input_requirements_not_mutated(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """26. Original input requirements are not mutated in place."""
    original_req = _make_req(req_id="req_immutable", kind=EvidenceKind.EXTERNAL_RESEARCH)
    assert original_req.status == RequirementStatus.PENDING

    item = _make_item(item_id="evi_1")
    link = _make_link(link_id="lnk_1", item_id="evi_1", requirement_id=original_req.id, stance=EvidenceStance.SUPPORTS)
    mapping = EvidenceMappingResult(items=[item], claim_links=[link])

    result = detector.detect_gaps(saas_decision_model, [original_req], mapping)

    # Original caller-owned requirement MUST retain original status
    assert original_req.status == RequirementStatus.PENDING
    # Result requirement contains the updated status
    assert result.requirements[0].status == RequirementStatus.FULFILLED
    assert result.requirements[0] is not original_req


def test_27_detector_has_no_llm_client_dependency(detector: EvidenceGapDetector) -> None:
    """27. Detector has no LLMClient dependency."""
    init_params = inspect.signature(detector.__init__).parameters
    assert "llm_client" not in init_params
    assert not hasattr(detector, "llm_client")


def test_28_detector_makes_no_search_provider_calls(detector: EvidenceGapDetector) -> None:
    """28. Detector makes no SearchProvider calls."""
    assert not hasattr(detector, "search_provider")
    detect_params = inspect.signature(detector.detect_gaps).parameters
    assert "search_provider" not in detect_params


def test_29_no_external_network_calls(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """29. No external network calls during gap detection."""
    def _fail_on_socket(*args, **kwargs):
        pytest.fail("Network socket access attempted during gap detection.")

    monkeypatch.setattr("socket.socket", _fail_on_socket)

    req = _make_req()
    mapping = EvidenceMappingResult()
    result = detector.detect_gaps(saas_decision_model, [req], mapping)
    assert len(result.requirements) == 1


def test_30_no_gemini_api_key_required(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """30. No Gemini API key required."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    req = _make_req()
    mapping = EvidenceMappingResult()
    result = detector.detect_gaps(saas_decision_model, [req], mapping)
    assert result is not None


def test_31_same_target_separate_requirements_preserved_independently(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """31. Mandatory Provenance Test:
    Two requirements target the SAME assumption (asm_elasticity).
    req_1 receives SUPPORTS evidence.
    req_2 receives no evidence.
    Expected:
    req_1 = FULFILLED
    req_2 = UNSUPPORTED with its own gap.
    Must NOT aggregate evidence solely by target_entity_id.
    """
    req_1 = _make_req(
        req_id="req_1",
        target_id="asm_elasticity",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Price elasticity proof for B2B SaaS.",
    )
    req_2 = _make_req(
        req_id="req_2",
        target_id="asm_elasticity",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Competitor discounting retaliation benchmarks.",
    )

    item_1 = _make_item(item_id="evi_1", content="Elasticity benchmark is 1.5.")
    # Link explicitly associated with req_1
    link_1 = _make_link(
        link_id="lnk_1",
        item_id="evi_1",
        target_id="asm_elasticity",
        requirement_id=req_1.id,
        stance=EvidenceStance.SUPPORTS,
    )

    mapping = EvidenceMappingResult(items=[item_1], claim_links=[link_1])
    result = detector.detect_gaps(saas_decision_model, [req_1, req_2], mapping)

    req_map = {r.id: r for r in result.requirements}
    assert req_map["req_1"].status == RequirementStatus.FULFILLED
    assert req_map["req_2"].status == RequirementStatus.UNSUPPORTED

    assert len(result.gaps) == 1
    assert result.gaps[0].requirement_id == "req_2"
    assert result.gaps[0].gap_type == EvidenceGapType.UNSUPPORTED_CLAIM


def test_32_saas_regression_scenario(
    detector: EvidenceGapDetector, saas_decision_model: DecisionModel
) -> None:
    """32. SaaS Pricing Scenario Regression:
    - Assumption: "Lower pricing may materially increase customer acquisition."
      req_1: EXTERNAL_RESEARCH -> Evidence A (SUPPORTS) + Evidence B (CHALLENGES)
      Expected: req_1.status = CONTESTED, Gap = CONFLICTING_EVIDENCE (both IDs present)
    - Separately:
      Unknown: "What is our current CAC?"
      req_2: INTERNAL_DATA
      Expected: req_2.status = PENDING, Gap = UNRESOLVED_UNKNOWN
      No search. No recommendation.
    """
    req_1 = _make_req(
        req_id="req_1",
        target_id="asm_elasticity",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Demand elasticity benchmarks under 20% discount.",
    )
    req_2 = _make_req(
        req_id="req_2",
        target_id="unk_competitor_pricing",
        target_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.INTERNAL_DATA,
        description="Current blended internal CAC across customer tiers.",
    )

    item_a = _make_item(item_id="evi_a", content="Lower pricing increased customer velocity by 35%.")
    item_b = _make_item(item_id="evi_b", content="Lower pricing caused 25% drop in enterprise perceived quality.")
    link_a = _make_link(link_id="lnk_a", item_id="evi_a", requirement_id=req_1.id, stance=EvidenceStance.SUPPORTS)
    link_b = _make_link(link_id="lnk_b", item_id="evi_b", requirement_id=req_1.id, stance=EvidenceStance.CHALLENGES)

    mapping = EvidenceMappingResult(items=[item_a, item_b], claim_links=[link_a, link_b])
    result = detector.detect_gaps(saas_decision_model, [req_1, req_2], mapping)

    req_map = {r.id: r for r in result.requirements}
    assert req_map["req_1"].status == RequirementStatus.CONTESTED
    assert req_map["req_2"].status == RequirementStatus.PENDING

    gaps_by_req = {g.requirement_id: g for g in result.gaps}
    assert len(result.gaps) == 2

    # req_1 gap is CONFLICTING_EVIDENCE with both items
    gap_1 = gaps_by_req["req_1"]
    assert gap_1.gap_type == EvidenceGapType.CONFLICTING_EVIDENCE
    assert set(gap_1.conflicting_evidence_ids) == {"evi_a", "evi_b"}

    # req_2 gap is UNRESOLVED_UNKNOWN with no search
    gap_2 = gaps_by_req["req_2"]
    assert gap_2.gap_type == EvidenceGapType.UNRESOLVED_UNKNOWN
    assert gap_2.conflicting_evidence_ids == []
