"""Unit tests for AURA Deterministic Complexity Engine."""

import pytest
from pydantic import ValidationError

from app.engines.complexity import (
    ComplexityConfig,
    ComplexityResult,
    ComplexitySignals,
    UncertaintyLevel,
    calculate_complexity,
)
from app.schemas.decision_model import ComplexityLevel, ReversibilityLevel


# ------------------------------------------------------------------------------
# 1. Simple Decision Test
# ------------------------------------------------------------------------------

def test_simple_decision_complexity() -> None:
    """Tests an isolated, low-risk, reversible decision (e.g., internal test tool choice)."""
    signals = ComplexitySignals(
        variable_count=1,
        constraint_count=0,
        stakeholder_count=1,
        tradeoff_count=1,
        unknown_count=0,
        dependency_count=0,
        uncertainty_level=UncertaintyLevel.LOW,
        irreversibility=ReversibilityLevel.REVERSIBLE,
    )

    result = calculate_complexity(signals)

    # Score breakdown:
    # var(1*3=3) + cnstr(0) + dep(0) + stk(1*2=2) + trd(1*8=8) + unk(0) + unc(2) + rev(1) = 16.0
    assert result.score == 16.0
    assert result.level == ComplexityLevel.LOW
    assert any("Two-way door" in r for r in result.reasons)
    assert any("1 variable" in r for r in result.reasons)


# ------------------------------------------------------------------------------
# 2. Medium Decision Test
# ------------------------------------------------------------------------------

def test_medium_decision_complexity() -> None:
    """Tests a typical AURA target decision (e.g., SaaS 20% price reduction under uncertainty)."""
    signals = ComplexitySignals(
        variable_count=2,
        constraint_count=1,
        stakeholder_count=2,
        tradeoff_count=1,
        unknown_count=1,
        dependency_count=1,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        irreversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
    )

    result = calculate_complexity(signals)

    # Score breakdown:
    # var(2*3=6) + cnstr(1*2.5=2.5) + dep(1*2.5=2.5) + stk(2*2=4) + trd(1*8=8) + unk(1*5=5) + unc(7) + rev(6) = 41.0
    assert result.score == 41.0
    assert result.level == ComplexityLevel.MEDIUM
    assert any("Moderate unwind friction" in r for r in result.reasons)
    assert any("1 operational constraint" in r for r in result.reasons)


# ------------------------------------------------------------------------------
# 3. Complex Decision Test
# ------------------------------------------------------------------------------

def test_complex_decision_complexity() -> None:
    """Tests a high-stakes, systemic, one-way door decision (e.g., monolith to distributed DB migration)."""
    signals = ComplexitySignals(
        variable_count=5,
        constraint_count=4,
        stakeholder_count=4,
        tradeoff_count=3,
        unknown_count=3,
        dependency_count=4,
        uncertainty_level=UncertaintyLevel.HIGH,
        irreversibility=ReversibilityLevel.IRREVERSIBLE,
    )

    result = calculate_complexity(signals)

    # Score breakdown (all hitting max caps):
    # var(min 15, 15) + cnstr(min 10, 10) + dep(min 10, 10) + stk(min 8, 10=8) + trd(min 24, 24) + unk(min 15, 15) + unc(12) + rev(14)
    # 15 + 10 + 10 + 8 + 24 + 15 + 12 + 14 = 98.0
    assert result.score >= 65.0
    assert result.level == ComplexityLevel.HIGH
    assert any("One-way door decision" in r for r in result.reasons)
    assert any("High environmental uncertainty" in r for r in result.reasons)
    assert any("Broad parameter space" in r for r in result.reasons)


# ------------------------------------------------------------------------------
# 4. Boundary Values & Edge Cases
# ------------------------------------------------------------------------------

def test_boundary_all_zeros() -> None:
    """Verifies behavior when all counts are 0 with lowest qualitative levels."""
    signals = ComplexitySignals(
        variable_count=0,
        constraint_count=0,
        stakeholder_count=0,
        tradeoff_count=0,
        unknown_count=0,
        dependency_count=0,
        uncertainty_level=UncertaintyLevel.LOW,
        irreversibility=ReversibilityLevel.REVERSIBLE,
    )

    result = calculate_complexity(signals)

    # Base minimum: unc_low(2.0) + rev_reversible(1.0) = 3.0
    assert result.score == 3.0
    assert result.level == ComplexityLevel.LOW
    assert len(result.reasons) > 0


def test_boundary_exact_threshold_transitions() -> None:
    """Tests exact edge transitions at low-to-medium (35.0) and medium-to-high (65.0)."""
    # Test exactly on 35.0
    custom_cfg = ComplexityConfig(
        threshold_low_to_medium=35.0,
        threshold_medium_to_high=65.0,
    )

    # Construct signals that yield exactly 34.9 vs 35.0:
    # 1. Below threshold (34.0):
    signals_34 = ComplexitySignals(
        variable_count=3,       # 9.0
        constraint_count=2,     # 5.0
        tradeoff_count=1,       # 8.0
        unknown_count=1,        # 5.0
        uncertainty_level=UncertaintyLevel.LOW,         # 2.0
        irreversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE, # 6.0
        # Total = 9 + 5 + 8 + 5 + 2 + 6 = 35.0!
    )
    result_35 = calculate_complexity(signals_34, config=custom_cfg)
    assert result_35.score == 35.0
    assert result_35.level == ComplexityLevel.MEDIUM

    # Signals yielding 34.0 (1 less variable point: 2 variables = 6.0 instead of 9.0 -> 32.0):
    signals_32 = ComplexitySignals(
        variable_count=2,       # 6.0
        constraint_count=2,     # 5.0
        tradeoff_count=1,       # 8.0
        unknown_count=1,        # 5.0
        uncertainty_level=UncertaintyLevel.LOW,         # 2.0
        irreversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE, # 6.0
    )
    result_32 = calculate_complexity(signals_32, config=custom_cfg)
    assert result_32.score == 32.0
    assert result_32.level == ComplexityLevel.LOW

    # Test High threshold (65.0):
    # Signals yielding exactly 65.0:
    # var(4*3=12) + cnstr(2*2.5=5) + dep(2*2.5=5) + stk(2*2=4) + trd(2*8=16) + unk(1*5=5) + unc_med(7) + rev_partially(6) = 60.0
    # + unc_high(12 instead of 7 = +5) -> 65.0!
    signals_65 = ComplexitySignals(
        variable_count=4,       # 12.0
        constraint_count=2,     # 5.0
        dependency_count=2,     # 5.0
        stakeholder_count=2,    # 4.0
        tradeoff_count=2,       # 16.0
        unknown_count=1,        # 5.0
        uncertainty_level=UncertaintyLevel.HIGH, # 12.0
        irreversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE, # 6.0
    )
    result_65 = calculate_complexity(signals_65, config=custom_cfg)
    assert result_65.score == 65.0
    assert result_65.level == ComplexityLevel.HIGH


def test_boundary_extreme_saturation_caps() -> None:
    """Verifies that massive counts smoothly saturate caps and stay <= 100.0 without errors."""
    signals_extreme = ComplexitySignals(
        variable_count=1000,
        constraint_count=500,
        stakeholder_count=300,
        tradeoff_count=200,
        unknown_count=400,
        dependency_count=600,
        uncertainty_level=UncertaintyLevel.HIGH,
        irreversibility=ReversibilityLevel.IRREVERSIBLE,
    )

    result = calculate_complexity(signals_extreme)

    # Caps: 15 + 10 + 10 + 10 + 24 + 15 + 12 + 14 = 100.0
    assert result.score == 100.0
    assert result.level == ComplexityLevel.HIGH


def test_validation_negative_counts_rejected() -> None:
    """Ensures negative counts are rejected by Pydantic ge=0 validation."""
    with pytest.raises(ValidationError):
        ComplexitySignals(variable_count=-1)

    with pytest.raises(ValidationError):
        ComplexitySignals(constraint_count=-5)


def test_custom_config_override() -> None:
    """Verifies that passing custom weights and thresholds changes calculation without side effects."""
    strict_config = ComplexityConfig(
        threshold_low_to_medium=20.0,
        threshold_medium_to_high=40.0,
    )

    signals = ComplexitySignals(
        variable_count=2,
        tradeoff_count=1,
        uncertainty_level=UncertaintyLevel.LOW,
        irreversibility=ReversibilityLevel.REVERSIBLE,
    )

    # With default config (threshold 35.0), this score (17.0) is LOW
    default_result = calculate_complexity(signals)
    assert default_result.level == ComplexityLevel.LOW

    # With strict config (threshold 20.0, score 17.0 is still < 20.0), if we add 1 constraint (+2.5 -> 19.5):
    # Add 1 unknown (+5.0 -> 22.0)
    signals_higher = signals.model_copy(update={"unknown_count": 1})
    strict_result = calculate_complexity(signals_higher, config=strict_config)
    assert strict_result.score == 22.0
    assert strict_result.level == ComplexityLevel.MEDIUM
