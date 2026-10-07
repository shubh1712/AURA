"""Unit tests for AURA Day 3 Evidence & Source Provenance Pydantic schemas.

Verifies:
- NumericEvidence semantic constraints (point, range, ordering, unit length, sample size).
- Source metadata, typed dates, timezone-aware UTC timestamps, and reliability_score rules.
- EvidenceItem and ClaimEvidenceLink validations and enums.
- EvidenceRequirement with all EvidenceKind variants.
- EvidenceGap taxonomy and conflicting evidence bounds.
- EvidencePackage internal referential integrity (sources, items, requirements, links, conflicts).
- Serialization and deserialization fidelity.
"""

from datetime import date, datetime, timezone
import pytest
from pydantic import ValidationError

from app.schemas.decision_model import ConfidenceLevel, CriticalityLevel
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
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)


# ------------------------------------------------------------------------------
# 1. NumericEvidence Tests
# ------------------------------------------------------------------------------

def test_numeric_evidence_valid_point_only() -> None:
    """Verifies valid NumericEvidence with only a single point value."""
    num = NumericEvidence(
        metric_name="median_churn_rate",
        value=5.4,
        unit="%",
        context="SMB SaaS benchmark",
    )
    assert num.metric_name == "median_churn_rate"
    assert num.value == 5.4
    assert num.unit == "%"
    assert num.range_min is None
    assert num.range_max is None


def test_numeric_evidence_valid_range_only() -> None:
    """Verifies valid NumericEvidence with only a range interval."""
    num = NumericEvidence(
        metric_name="volume_expansion",
        range_min=12.0,
        range_max=16.5,
        unit="%",
        confidence_interval="95% CI [12.0, 16.5]",
        sample_size=150,
    )
    assert num.value is None
    assert num.range_min == 12.0
    assert num.range_max == 16.5
    assert num.sample_size == 150


def test_numeric_evidence_valid_both_point_and_range() -> None:
    """Verifies valid NumericEvidence with both point estimate and confidence bounds."""
    num = NumericEvidence(
        metric_name="customer_acquisition_cost",
        value=350.0,
        range_min=300.0,
        range_max=420.0,
        unit="USD",
    )
    assert num.value == 350.0
    assert num.range_min == 300.0
    assert num.range_max == 420.0


def test_numeric_evidence_invalid_reversed_range() -> None:
    """Verifies that range_min > range_max fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        NumericEvidence(
            metric_name="invalid_range_metric",
            range_min=50.0,
            range_max=20.0,
        )
    assert "range_min (50.0) cannot be greater than range_max (20.0)" in str(exc_info.value)


def test_numeric_evidence_invalid_no_numerical_information() -> None:
    """Verifies that NumericEvidence without point value or range fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        NumericEvidence(
            metric_name="empty_metric",
            unit="%",
        )
    assert "must contain a point value or a meaningful range" in str(exc_info.value)


def test_numeric_evidence_invalid_unit_length() -> None:
    """Verifies that an excessively long unit label fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        NumericEvidence(
            metric_name="metric_with_huge_unit",
            value=10.0,
            unit="percentage discount calculated over quarterly cohorts",
        )
    assert "unit" in str(exc_info.value)


def test_numeric_evidence_invalid_sample_size() -> None:
    """Verifies that sample_size < 1 fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        NumericEvidence(
            metric_name="metric_zero_sample",
            value=20.0,
            sample_size=0,
        )
    assert "sample_size" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 2. Source Tests
# ------------------------------------------------------------------------------

def test_source_valid_and_typed_publication_date() -> None:
    """Verifies Source metadata with strongly-typed publication date."""
    src = Source(
        id="src_openview_2024",
        url="https://mock.example.com/reports/2024-pricing-report",
        title="2024 SaaS Pricing Benchmark Report",
        publisher="OpenView Labs",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 9, 15),
    )
    assert src.id == "src_openview_2024"
    assert src.publication_date == date(2024, 9, 15)
    assert src.source_type == SourceType.INDUSTRY_REPORT


def test_source_string_date_parsing() -> None:
    """Verifies that ISO-8601 date strings parse into typed date objects."""
    src = Source(
        id="src_sec_10k",
        title="Form 10-K Annual Report",
        source_type=SourceType.REGULATORY_FILING,
        publication_date="2025-02-28",  # type: ignore[arg-type]
    )
    assert isinstance(src.publication_date, date)
    assert src.publication_date == date(2025, 2, 28)


def test_source_timezone_aware_retrieval_timestamp() -> None:
    """Verifies that retrieval_timestamp is timezone-aware UTC."""
    src = Source(
        id="src_academic_01",
        title="Price Elasticity in Enterprise Software Markets",
        source_type=SourceType.ACADEMIC,
    )
    assert src.retrieval_timestamp is not None
    assert src.retrieval_timestamp.tzinfo is not None

    # Providing explicit naive timestamp normalizes to timezone-aware UTC
    naive_dt = datetime(2025, 5, 1, 12, 0, 0)
    src_custom = Source(
        id="src_academic_02",
        title="Software Pricing Study",
        source_type=SourceType.ACADEMIC,
        retrieval_timestamp=naive_dt,
    )
    assert src_custom.retrieval_timestamp.tzinfo == timezone.utc


def test_source_reliability_score_defaults_to_none() -> None:
    """Verifies reliability_score defaults to None for Day 3."""
    src = Source(
        id="src_gov_01",
        title="Bureau of Labor Statistics Tech Index",
        source_type=SourceType.GOVERNMENT,
    )
    assert src.reliability_score is None


def test_source_reliability_score_bounds() -> None:
    """Verifies reliability_score bounds [0.0, 1.0] if set."""
    src_valid = Source(
        id="src_company_01",
        title="Official Developer Documentation",
        source_type=SourceType.COMPANY_PRIMARY,
        reliability_score=0.95,
    )
    assert src_valid.reliability_score == 0.95

    with pytest.raises(ValidationError) as exc_info:
        Source(
            id="src_invalid_score",
            title="Out of Bounds Score",
            source_type=SourceType.OTHER,
            reliability_score=1.5,
        )
    assert "reliability_score" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. EvidenceItem Tests
# ------------------------------------------------------------------------------

def test_evidence_item_valid_with_numeric_data() -> None:
    """Verifies EvidenceItem construction with provenance reference and numeric findings."""
    item = EvidenceItem(
        id="evi_elasticity_01",
        source_id="src_openview_2024",
        content="Discounts between 15% and 25% produced median volume gains of 14%.",
        summary="Price cuts over 15% rarely yield break-even volume expansion.",
        numeric_data=[
            NumericEvidence(
                metric_name="median_volume_gain",
                value=14.0,
                unit="%",
                range_min=12.0,
                range_max=16.0,
            )
        ],
        extraction_confidence=ConfidenceLevel.HIGH,
    )
    assert item.id == "evi_elasticity_01"
    assert item.source_id == "src_openview_2024"
    assert len(item.numeric_data) == 1
    assert item.numeric_data[0].value == 14.0
    assert item.extraction_confidence == ConfidenceLevel.HIGH
    assert item.retrieval_timestamp.tzinfo is not None


# ------------------------------------------------------------------------------
# 4. ClaimEvidenceLink Tests
# ------------------------------------------------------------------------------

def test_claim_evidence_link_valid() -> None:
    """Verifies valid ClaimEvidenceLink connecting evidence to a decision entity."""
    link = ClaimEvidenceLink(
        id="lnk_01",
        evidence_item_id="evi_elasticity_01",
        target_entity_id="asm_elasticity_expansion",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        stance=EvidenceStance.CHALLENGES,
        reasoning="Observed volume expansion of 14% is insufficient to offset a 20% price cut.",
        relationship_confidence=ConfidenceLevel.HIGH,
    )
    assert link.stance == EvidenceStance.CHALLENGES
    assert link.target_entity_type == DecisionEntityType.ASSUMPTION


def test_claim_evidence_link_invalid_stance() -> None:
    """Verifies that an unsupported stance string fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        ClaimEvidenceLink(
            id="lnk_invalid_stance",
            evidence_item_id="evi_01",
            target_entity_id="var_01",
            target_entity_type=DecisionEntityType.VARIABLE,
            stance="neutral_opinion",  # type: ignore[arg-type]
            reasoning="Valid reasoning text",
        )
    assert "stance" in str(exc_info.value)


def test_claim_evidence_link_invalid_decision_entity_type() -> None:
    """Verifies that an unsupported target_entity_type fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        ClaimEvidenceLink(
            id="lnk_invalid_type",
            evidence_item_id="evi_01",
            target_entity_id="var_01",
            target_entity_type="random_concept",  # type: ignore[arg-type]
            stance=EvidenceStance.CONTEXT,
            reasoning="Valid reasoning text",
        )
    assert "target_entity_type" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 5. EvidenceRequirement Tests
# ------------------------------------------------------------------------------

def test_evidence_requirement_all_evidence_kinds() -> None:
    """Verifies EvidenceRequirement supports all defined EvidenceKind enum values."""
    for kind in EvidenceKind:
        req = EvidenceRequirement(
            id=f"req_{kind.value}",
            target_entity_id="unk_info_gap",
            target_entity_type=DecisionEntityType.UNKNOWN,
            kind=kind,
            description=f"Requirement of kind {kind.value}",
            priority=CriticalityLevel.HIGH,
            status=RequirementStatus.PENDING,
            suggested_queries=["benchmark search query"],
        )
        assert req.kind == kind
        assert req.status == RequirementStatus.PENDING


# ------------------------------------------------------------------------------
# 6. EvidenceGap Tests
# ------------------------------------------------------------------------------

def test_evidence_gap_valid() -> None:
    """Verifies valid EvidenceGap construction across gap types."""
    gap = EvidenceGap(
        id="gap_unsupported_01",
        gap_type=EvidenceGapType.UNSUPPORTED_CLAIM,
        target_entity_id="var_cac_baseline",
        target_entity_type=DecisionEntityType.VARIABLE,
        requirement_id="req_cac_proof",
        description="No empirical data discovered to validate baseline CAC.",
        impact=CriticalityLevel.MEDIUM,
        resolution_guidance="Request internal marketing expenditure records.",
    )
    assert gap.gap_type == EvidenceGapType.UNSUPPORTED_CLAIM
    assert gap.impact == CriticalityLevel.MEDIUM


# ------------------------------------------------------------------------------
# 7. EvidencePackage Referential Integrity Tests
# ------------------------------------------------------------------------------

def _build_valid_package_components():
    """Helper creating valid components for EvidencePackage testing."""
    source = Source(
        id="src_01",
        title="SaaS Benchmark Report",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 10, 1),
    )
    item1 = EvidenceItem(
        id="evi_01",
        source_id="src_01",
        content="Report asserts 14% median volume expansion.",
    )
    item2 = EvidenceItem(
        id="evi_02",
        source_id="src_01",
        content="Report asserts 31% volume expansion in self-serve tiers.",
    )
    req = EvidenceRequirement(
        id="req_01",
        target_entity_id="asm_01",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify demand elasticity.",
    )
    link = ClaimEvidenceLink(
        id="lnk_01",
        evidence_item_id="evi_01",
        target_entity_id="asm_01",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        stance=EvidenceStance.CHALLENGES,
        reasoning="Volume growth is below 20%.",
    )
    gap = EvidenceGap(
        id="gap_01",
        gap_type=EvidenceGapType.CONFLICTING_EVIDENCE,
        target_entity_id="asm_01",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        requirement_id="req_01",
        description="Contradictory findings between mid-market and self-serve tiers.",
        conflicting_evidence_ids=["evi_01", "evi_02"],
    )
    return [req], [source], [item1, item2], [link], [gap]


def test_evidence_package_valid() -> None:
    """Verifies construction of a fully coherent, valid EvidencePackage."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    pkg = EvidencePackage(
        id="pkg_valid_01",
        decision_model_id="dec_01",
        requirements=reqs,
        sources=sources,
        items=items,
        claim_links=links,
        gaps=gaps,
        summary="Comprehensive evidence package on SaaS pricing.",
    )
    assert pkg.id == "pkg_valid_01"
    assert len(pkg.requirements) == 1
    assert len(pkg.sources) == 1
    assert len(pkg.items) == 2
    assert len(pkg.claim_links) == 1
    assert len(pkg.gaps) == 1
    assert pkg.created_at.tzinfo is not None


def test_evidence_package_duplicate_ids_rejected() -> None:
    """Verifies that duplicate entity IDs inside a package collection are rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    # Add duplicate source ID
    dup_source = Source(
        id="src_01",  # Same as first source
        title="Duplicate Source Title",
        source_type=SourceType.NEWS_MEDIA,
    )
    sources.append(dup_source)

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_dup",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with duplicate source ID",
        )
    assert "Duplicate ID 'src_01' found in 'sources' collection" in str(exc_info.value)


def test_evidence_package_missing_source_reference_rejected() -> None:
    """Verifies that an EvidenceItem referencing a non-existent Source.id is rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    # Point item1 to non-existent source
    items[0].source_id = "src_non_existent"

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_missing_source",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with missing source reference",
        )
    assert "references non-existent source_id 'src_non_existent'" in str(exc_info.value)


def test_evidence_package_missing_evidence_item_link_rejected() -> None:
    """Verifies that a ClaimEvidenceLink referencing a non-existent EvidenceItem.id is rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    # Point link to non-existent evidence item
    links[0].evidence_item_id = "evi_ghost"

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_missing_link_item",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with broken link reference",
        )
    assert "references non-existent evidence_item_id 'evi_ghost'" in str(exc_info.value)


def test_evidence_package_missing_requirement_reference_rejected() -> None:
    """Verifies that an EvidenceGap referencing a non-existent EvidenceRequirement.id is rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    # Point gap requirement_id to non-existent requirement
    gaps[0].requirement_id = "req_missing"

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_missing_req",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with broken gap requirement reference",
        )
    assert "references non-existent requirement_id 'req_missing'" in str(exc_info.value)


def test_evidence_package_conflicting_evidence_fewer_than_two_ids_rejected() -> None:
    """Verifies that a CONFLICTING_EVIDENCE gap with fewer than two conflicting IDs is rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    gaps[0].conflicting_evidence_ids = ["evi_01"]  # Only one ID

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_bad_conflict_count",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with invalid conflicting IDs count",
        )
    assert "must contain at least two conflicting_evidence_ids" in str(exc_info.value)


def test_evidence_package_conflicting_evidence_unknown_id_rejected() -> None:
    """Verifies that a CONFLICTING_EVIDENCE gap containing an unknown EvidenceItem.id is rejected."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    gaps[0].conflicting_evidence_ids = ["evi_01", "evi_unknown_999"]

    with pytest.raises(ValidationError) as exc_info:
        EvidencePackage(
            id="pkg_bad_conflict_id",
            decision_model_id="dec_01",
            requirements=reqs,
            sources=sources,
            items=items,
            claim_links=links,
            gaps=gaps,
            summary="Package with unknown conflicting evidence ID",
        )
    assert "references non-existent conflicting evidence ID 'evi_unknown_999'" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 8. Serialization & Deserialization Fidelity
# ------------------------------------------------------------------------------

def test_evidence_package_json_serialization_and_deserialization() -> None:
    """Verifies that EvidencePackage cleanly serializes to JSON and deserializes back."""
    reqs, sources, items, links, gaps = _build_valid_package_components()
    pkg = EvidencePackage(
        id="pkg_serde_01",
        decision_model_id="dec_saas_pricing_20",
        requirements=reqs,
        sources=sources,
        items=items,
        claim_links=links,
        gaps=gaps,
        summary="Serialized package test.",
    )

    json_data = pkg.model_dump_json()
    assert isinstance(json_data, str)
    assert "src_01" in json_data
    assert "evi_01" in json_data
    assert "conflicting_evidence" in json_data

    reconstituted = EvidencePackage.model_validate_json(json_data)
    assert reconstituted.id == pkg.id
    assert reconstituted.sources[0].publication_date == date(2024, 10, 1)
    assert reconstituted.gaps[0].conflicting_evidence_ids == ["evi_01", "evi_02"]
