"""Tests for AURA Resilience Engine Schemas (Day 6 Phase 6A).

Validates:
- ResilienceRating enum and category mappings
- ResilienceSubScore boundary validation and numeric constraints
- ResilienceReport invariants (exact 4 pillars, score sum consistency, rating band sync)
- Deterministic SHA-256 ID repeatability and pattern matching
- Serialization and deserialization round-trip
"""

import pytest
from pydantic import ValidationError

from app.schemas.resilience import (
    ResiliencePillar,
    ResilienceRating,
    ResilienceReport,
    ResilienceSubScore,
    determine_resilience_rating,
    generate_deterministic_resilience_id,
)


def _build_valid_subscores():
    return [
        ResilienceSubScore(
            category=ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value,
            score=20.0,
            max_score=25.0,
            rationale="Robust constraint tolerance with reversible unwinding.",
            vulnerabilities_detected=[],
        ),
        ResilienceSubScore(
            category=ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value,
            score=22.5,
            max_score=25.0,
            rationale="Low adverse probability and all critical risks mitigated.",
            vulnerabilities_detected=[],
        ),
        ResilienceSubScore(
            category=ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value,
            score=21.0,
            max_score=25.0,
            rationale="Multiple verified decision gates and actionable rollback playbooks.",
            vulnerabilities_detected=[],
        ),
        ResilienceSubScore(
            category=ResiliencePillar.INFORMATION_ROBUSTNESS.value,
            score=18.5,
            max_score=25.0,
            rationale="Strong evidence and high stability with minimal gaps.",
            vulnerabilities_detected=[],
        ),
    ]


def test_resilience_rating_mapping():
    assert determine_resilience_rating(100.0) == ResilienceRating.HIGH
    assert determine_resilience_rating(80.0) == ResilienceRating.HIGH
    assert determine_resilience_rating(79.9) == ResilienceRating.MODERATE
    assert determine_resilience_rating(60.0) == ResilienceRating.MODERATE
    assert determine_resilience_rating(59.9) == ResilienceRating.FRAGILE
    assert determine_resilience_rating(40.0) == ResilienceRating.FRAGILE
    assert determine_resilience_rating(39.9) == ResilienceRating.VULNERABLE
    assert determine_resilience_rating(0.0) == ResilienceRating.VULNERABLE


def test_subscore_bounds_validation():
    # Valid bounds
    sub = ResilienceSubScore(
        category="test_pillar",
        score=25.0,
        max_score=25.0,
        rationale="Perfect subscore",
    )
    assert sub.score == 25.0

    # Negative score rejected
    with pytest.raises(ValidationError):
        ResilienceSubScore(
            category="test_pillar",
            score=-1.0,
            max_score=25.0,
            rationale="Negative score",
        )

    # Score exceeding 25.0 rejected
    with pytest.raises(ValidationError):
        ResilienceSubScore(
            category="test_pillar",
            score=25.1,
            max_score=25.0,
            rationale="Exceeding max score",
        )

    # Non-finite score rejected
    with pytest.raises(ValidationError):
        ResilienceSubScore(
            category="test_pillar",
            score=float("nan"),
            max_score=25.0,
            rationale="NaN score",
        )


def test_resilience_report_valid_instantiation():
    subscores = _build_valid_subscores()
    total = sum(s.score for s in subscores)  # 20.0 + 22.5 + 21.0 + 18.5 = 82.0
    report_id = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=total,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )

    report = ResilienceReport(
        id=report_id,
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=total,
        rating=ResilienceRating.HIGH,
        sub_scores=subscores,
        critical_vulnerabilities=[],
        stress_test_passed=True,
        recommended_hedges=["Monitor operational indicators."],
        calculation_version="1.0.0",
    )

    assert report.id.startswith("res_")
    assert len(report.id) == 36
    assert report.overall_score == 82.0
    assert report.rating == ResilienceRating.HIGH
    assert report.stress_test_passed is True


def test_resilience_report_subscore_sum_mismatch_rejected():
    subscores = _build_valid_subscores()  # sum is 82.0
    report_id = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )

    # Mismatched overall score
    with pytest.raises(ValidationError, match="does not match sum of sub-scores"):
        ResilienceReport(
            id=report_id,
            decision_model_id="dm_123",
            scenario_set_id="scenset_456",
            recommendation_id="rec_789",
            overall_score=95.0,  # deliberately wrong
            rating=ResilienceRating.HIGH,
            sub_scores=subscores,
            critical_vulnerabilities=[],
            stress_test_passed=True,
            recommended_hedges=[],
        )


def test_resilience_report_rating_mismatch_rejected():
    subscores = _build_valid_subscores()  # sum is 82.0 (should be HIGH)
    report_id = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )

    # Inconsistent rating specified
    with pytest.raises(ValidationError, match="is inconsistent with score"):
        ResilienceReport(
            id=report_id,
            decision_model_id="dm_123",
            scenario_set_id="scenset_456",
            recommendation_id="rec_789",
            overall_score=82.0,
            rating=ResilienceRating.VULNERABLE,  # deliberately wrong
            sub_scores=subscores,
            critical_vulnerabilities=[],
            stress_test_passed=True,
            recommended_hedges=[],
        )


def test_resilience_report_fewer_than_four_subscores_rejected():
    subscores = _build_valid_subscores()[:3]  # only 3
    with pytest.raises(ValidationError):
        ResilienceReport(
            id="res_0123456789abcdef0123456789abcdef",
            decision_model_id="dm_123",
            scenario_set_id="scenset_456",
            recommendation_id="rec_789",
            overall_score=60.0,
            rating=ResilienceRating.MODERATE,
            sub_scores=subscores,
            critical_vulnerabilities=[],
            stress_test_passed=True,
            recommended_hedges=[],
        )


def test_deterministic_id_generation_consistency():
    subscores = _build_valid_subscores()
    id1 = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )
    id2 = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )
    assert id1 == id2
    assert id1.startswith("res_")
    assert len(id1) == 36


def test_resilience_report_duplicate_categories_rejected():
    subscores = [
        ResilienceSubScore(
            category=ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value,
            score=20.0,
            max_score=25.0,
            rationale="Rationale 1",
        ),
        ResilienceSubScore(
            category=ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value,  # duplicate category
            score=20.0,
            max_score=25.0,
            rationale="Rationale 2",
        ),
        ResilienceSubScore(
            category=ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value,
            score=20.0,
            max_score=25.0,
            rationale="Rationale 3",
        ),
        ResilienceSubScore(
            category=ResiliencePillar.INFORMATION_ROBUSTNESS.value,
            score=20.0,
            max_score=25.0,
            rationale="Rationale 4",
        ),
    ]
    with pytest.raises(ValidationError, match="categories must be unique"):
        ResilienceReport(
            id="res_0123456789abcdef0123456789abcdef",
            decision_model_id="dm_123",
            scenario_set_id="scenset_456",
            recommendation_id="rec_789",
            overall_score=80.0,
            rating=ResilienceRating.HIGH,
            sub_scores=subscores,
            critical_vulnerabilities=[],
            stress_test_passed=True,
            recommended_hedges=[],
        )


def test_resilience_report_id_pattern_validation():
    subscores = _build_valid_subscores()
    # Invalid ID without res_ prefix
    with pytest.raises(ValidationError):
        ResilienceReport(
            id="invalid_id_format_1234567890abcdef",
            decision_model_id="dm_123",
            scenario_set_id="scenset_456",
            recommendation_id="rec_789",
            overall_score=82.0,
            rating=ResilienceRating.HIGH,
            sub_scores=subscores,
            critical_vulnerabilities=[],
            stress_test_passed=True,
            recommended_hedges=[],
        )


def test_resilience_report_frozen_immutability():
    subscores = _build_valid_subscores()
    report_id = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )
    report = ResilienceReport(
        id=report_id,
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        rating=ResilienceRating.HIGH,
        sub_scores=subscores,
        critical_vulnerabilities=[],
        stress_test_passed=True,
        recommended_hedges=[],
    )
    with pytest.raises(ValidationError):
        report.overall_score = 90.0  # Cannot mutate frozen model


def test_resilience_report_serialization_roundtrip():
    subscores = _build_valid_subscores()
    report_id = generate_deterministic_resilience_id(
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        calculation_version="1.0.0",
        sub_scores=subscores,
    )
    report = ResilienceReport(
        id=report_id,
        decision_model_id="dm_123",
        scenario_set_id="scenset_456",
        recommendation_id="rec_789",
        overall_score=82.0,
        rating=ResilienceRating.HIGH,
        sub_scores=subscores,
        critical_vulnerabilities=["Some critical risk"],
        stress_test_passed=True,
        recommended_hedges=["Some hedge"],
    )

    data = report.model_dump(mode="json")
    deserialized = ResilienceReport.model_validate(data)
    assert deserialized.id == report.id
    assert deserialized.overall_score == report.overall_score
    assert deserialized.rating == report.rating
    assert len(deserialized.sub_scores) == 4

