"""Offline unit tests for canonical AI Boardroom perspectives.

Verifies:
1. Exactly four canonical perspective definitions exist.
2. Authoritative ordering is growth, finance, customer, risk.
3. Deterministic lookup returns the correct definition for each PerspectiveType.
4. No arbitrary/custom fifth perspective can be looked up or created.
5. PerspectiveDefinition instances and their containers are strictly immutable (frozen).
6. Every perspective explicitly contains no-recommendation prohibitions.
7. Finance perspective explicitly prohibits fabricated financial metrics (ROI, NPV, IRR, etc.).
8. Risk perspective explicitly distinguishes uncertainty from negative evidence.
9. All four perspectives inherit the common boardroom epistemic rules.
"""

import pytest
from dataclasses import FrozenInstanceError

from app.schemas.reasoning import PerspectiveType
from app.services.reasoning.perspectives import (
    CANONICAL_PERSPECTIVES,
    COMMON_EPISTEMIC_RULES,
    CUSTOMER,
    FINANCE,
    GROWTH,
    PerspectiveDefinition,
    RISK,
    get_perspective_definition,
)


def test_01_exactly_four_perspectives_exist() -> None:
    """Test 1: Verify exactly four canonical boardroom perspectives exist."""
    assert len(CANONICAL_PERSPECTIVES) == 4
    types = [p.perspective_type for p in CANONICAL_PERSPECTIVES]
    assert set(types) == {
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    }


def test_02_canonical_order_is_growth_finance_customer_risk() -> None:
    """Test 2: Authoritative canonical ordering is growth -> finance -> customer -> risk."""
    expected_order = (
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    )
    actual_order = tuple(p.perspective_type for p in CANONICAL_PERSPECTIVES)
    assert actual_order == expected_order
    assert CANONICAL_PERSPECTIVES[0] == GROWTH
    assert CANONICAL_PERSPECTIVES[1] == FINANCE
    assert CANONICAL_PERSPECTIVES[2] == CUSTOMER
    assert CANONICAL_PERSPECTIVES[3] == RISK


def test_03_lookup_returns_correct_definition() -> None:
    """Test 3: get_perspective_definition returns correct definition deterministically."""
    assert get_perspective_definition(PerspectiveType.GROWTH) == GROWTH
    assert get_perspective_definition(PerspectiveType.FINANCE) == FINANCE
    assert get_perspective_definition(PerspectiveType.CUSTOMER) == CUSTOMER
    assert get_perspective_definition(PerspectiveType.RISK) == RISK


def test_04_no_custom_fifth_perspective_exists() -> None:
    """Test 4: Rejects arbitrary or non-canonical perspective types."""
    with pytest.raises(ValueError, match="Invalid perspective type"):
        get_perspective_definition("strategy")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid perspective type"):
        get_perspective_definition("legal")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid perspective type"):
        get_perspective_definition(None)  # type: ignore[arg-type]


def test_05_definitions_are_immutable() -> None:
    """Test 5: PerspectiveDefinition instances and their attributes are frozen/immutable."""
    growth_def = get_perspective_definition(PerspectiveType.GROWTH)

    with pytest.raises((FrozenInstanceError, AttributeError)):
        growth_def.title = "New Title"  # type: ignore[misc]

    with pytest.raises((FrozenInstanceError, AttributeError)):
        growth_def.mandate = "Mutated Mandate"  # type: ignore[misc]

    # Verify tuple attributes cannot be mutated in place
    assert isinstance(growth_def.focus_areas, tuple)
    assert isinstance(growth_def.prohibitions, tuple)
    assert isinstance(growth_def.epistemic_rules, tuple)


def test_06_every_perspective_contains_no_recommendation_mandate() -> None:
    """Test 6: Every perspective strictly prohibits formulating final recommendations."""
    for p in CANONICAL_PERSPECTIVES:
        prohibition_texts = " ".join(p.prohibitions).lower()
        mandate_text = p.mandate.lower()
        # Must prohibit final recommendation/approval
        assert any(
            phrase in prohibition_texts
            for phrase in ["recommendation", "final recommendation", "approvals"]
        ), f"Perspective {p.perspective_type.value} does not explicitly prohibit recommendations"
        # Must not mandate final recommendation
        assert "final recommendation" not in mandate_text


def test_07_finance_prohibits_fabricated_metrics() -> None:
    """Test 7: Finance explicitly prohibits fabricated ROI, NPV, IRR, LTV, CAC, etc."""
    finance_prohibitions = " ".join(FINANCE.prohibitions)
    required_prohibitions = ["ROI", "NPV", "IRR", "CAC", "LTV", "revenue forecast", "margin impact"]
    for metric in required_prohibitions:
        assert metric in finance_prohibitions, f"Finance missing prohibition on {metric}"

    # Verify Finance mandates reasoning from UNRESOLVED dependencies when data is missing
    assert "UNRESOLVED" in FINANCE.mandate


def test_08_risk_distinguishes_uncertainty_from_negative_evidence() -> None:
    """Test 8: Risk explicitly preserves the distinction between uncertainty and negative evidence."""
    risk_mandate = RISK.mandate
    risk_prohibitions = " ".join(RISK.prohibitions)

    # Must distinguish 'we do not know' from 'evidence indicates failure'
    assert "we do not know" in risk_mandate
    assert "evidence indicates this will fail" in risk_mandate

    # Must prohibit converting uncertainty into evidence of failure
    assert "convert uncertainty" in risk_prohibitions
    assert "missing evidence as negative evidence" in risk_prohibitions


def test_09_all_perspectives_inherit_common_epistemic_rules() -> None:
    """Test 9: All perspectives expose the complete common boardroom epistemic rules."""
    assert len(COMMON_EPISTEMIC_RULES) >= 15
    for p in CANONICAL_PERSPECTIVES:
        assert p.epistemic_rules == COMMON_EPISTEMIC_RULES
        rules_text = " ".join(p.epistemic_rules).lower()
        # Verifies core epistemic guardrails
        assert "evidence is not certainty" in rules_text
        assert "inference is not evidence" in rules_text
        assert "assumption is not fact" in rules_text
        assert "unknown remains unknown" in rules_text
        assert "missing evidence is not negative evidence" in rules_text
        assert "contested evidence must remain contested" in rules_text
        assert "challenging evidence must never be suppressed" in rules_text
        assert "internal-data requirements cannot be filled" in rules_text
        assert "deterministic-calculation requirements cannot be fabricated" in rules_text
        assert "no final recommendation" in rules_text
        assert "no voting" in rules_text
        assert "no scenarios" in rules_text
        assert "no resilience scoring" in rules_text
        assert "no what-if" in rules_text
