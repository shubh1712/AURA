"""AURA Deterministic Complexity Engine.

Evaluates decision complexity deterministically based on structured signals
(variable counts, constraints, stakeholders, trade-offs, unknowns, dependencies,
uncertainty level, and reversibility) without relying on probabilistic LLM arithmetic.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.decision_model import ComplexityLevel, ReversibilityLevel


class UncertaintyLevel(str, Enum):
    """Categorical level of epistemic uncertainty in the decision environment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ------------------------------------------------------------------------------
# Configurable Weights & Thresholds
# ------------------------------------------------------------------------------

class ComplexityConfig(BaseModel):
    """Configurable scoring weights, caps, and classification thresholds."""
    model_config = ConfigDict(frozen=True)

    # Weights per unit
    weight_per_variable: float = 3.0
    weight_per_constraint: float = 2.5
    weight_per_dependency: float = 2.5
    weight_per_stakeholder: float = 2.0
    weight_per_tradeoff: float = 8.0
    weight_per_unknown: float = 5.0

    # Dimension Maximum Caps (Prevents any single outlier signal from dominating)
    max_variable_points: float = 15.0       # Caps at 5+ variables
    max_constraint_points: float = 10.0     # Caps at 4+ constraints
    max_dependency_points: float = 10.0     # Caps at 4+ dependencies
    max_stakeholder_points: float = 10.0    # Caps at 5+ stakeholders
    max_tradeoff_points: float = 24.0       # Caps at 3+ trade-offs
    max_unknown_points: float = 15.0        # Caps at 3+ unknowns

    # Qualitative Level Points
    points_uncertainty_low: float = 2.0
    points_uncertainty_medium: float = 7.0
    points_uncertainty_high: float = 12.0

    points_reversibility_reversible: float = 1.0
    points_reversibility_partially: float = 6.0
    points_reversibility_irreversible: float = 14.0

    # Classification Thresholds (0 - 100 Scale)
    threshold_low_to_medium: float = 35.0
    threshold_medium_to_high: float = 65.0


# ------------------------------------------------------------------------------
# Input Signals & Output Assessment
# ------------------------------------------------------------------------------

class ComplexitySignals(BaseModel):
    """Structured input signals extracted from question understanding."""
    model_config = ConfigDict(str_strip_whitespace=True)

    variable_count: int = Field(default=0, ge=0, description="Number of identified variables/levers.")
    constraint_count: int = Field(default=0, ge=0, description="Number of operational boundaries or constraints.")
    stakeholder_count: int = Field(default=0, ge=0, description="Number of distinct affected stakeholder groups.")
    tradeoff_count: int = Field(default=0, ge=0, description="Number of competing trade-offs identified.")
    unknown_count: int = Field(default=0, ge=0, description="Number of critical missing factual unknowns.")
    dependency_count: int = Field(default=0, ge=0, description="Number of coupled technical, operational, or business dependencies.")
    uncertainty_level: UncertaintyLevel = Field(
        default=UncertaintyLevel.LOW,
        description="Assessed environmental/epistemic uncertainty."
    )
    irreversibility: ReversibilityLevel = Field(
        default=ReversibilityLevel.REVERSIBLE,
        description="Reversibility cost (reversible, partially_reversible, irreversible)."
    )


class ComplexityResult(BaseModel):
    """Deterministic assessment result."""
    model_config = ConfigDict(str_strip_whitespace=True)

    score: float = Field(..., ge=0.0, le=100.0, description="Normalized complexity score between 0.0 and 100.0.")
    level: ComplexityLevel = Field(..., description="Categorical complexity level (low, medium, high).")
    reasons: List[str] = Field(..., min_length=1, description="Explainable justifications for the assessed score and level.")


# ------------------------------------------------------------------------------
# Deterministic Calculator Function
# ------------------------------------------------------------------------------

DEFAULT_COMPLEXITY_CONFIG = ComplexityConfig()


def calculate_complexity(
    signals: ComplexitySignals,
    config: Optional[ComplexityConfig] = None,
) -> ComplexityResult:
    """Calculates a deterministic complexity score, level, and reasons.

    Pure deterministic function: given the exact same signals and config,
    always returns the exact same score and level.

    Args:
        signals: Extracted structural signals.
        config: Optional configuration overrides for thresholds and weights.

    Returns:
        ComplexityResult containing score, level, and human-readable reasons.
    """
    cfg = config or DEFAULT_COMPLEXITY_CONFIG
    reasons: List[str] = []

    # 1. Structural Multiplicity Points
    var_pts = min(signals.variable_count * cfg.weight_per_variable, cfg.max_variable_points)
    cnstr_pts = min(signals.constraint_count * cfg.weight_per_constraint, cfg.max_constraint_points)
    dep_pts = min(signals.dependency_count * cfg.weight_per_dependency, cfg.max_dependency_points)
    stk_pts = min(signals.stakeholder_count * cfg.weight_per_stakeholder, cfg.max_stakeholder_points)

    # 2. Friction & Trade-off Points
    trd_pts = min(signals.tradeoff_count * cfg.weight_per_tradeoff, cfg.max_tradeoff_points)

    # 3. Epistemic Uncertainty Points
    unk_pts = min(signals.unknown_count * cfg.weight_per_unknown, cfg.max_unknown_points)

    if signals.uncertainty_level == UncertaintyLevel.HIGH:
        unc_pts = cfg.points_uncertainty_high
    elif signals.uncertainty_level == UncertaintyLevel.MEDIUM:
        unc_pts = cfg.points_uncertainty_medium
    else:
        unc_pts = cfg.points_uncertainty_low

    # 4. Irreversibility Points
    if signals.irreversibility == ReversibilityLevel.IRREVERSIBLE:
        rev_pts = cfg.points_reversibility_irreversible
    elif signals.irreversibility == ReversibilityLevel.PARTIALLY_REVERSIBLE:
        rev_pts = cfg.points_reversibility_partially
    else:
        rev_pts = cfg.points_reversibility_reversible

    # Aggregate & Bound (0.0 to 100.0)
    raw_score = var_pts + cnstr_pts + dep_pts + stk_pts + trd_pts + unk_pts + unc_pts + rev_pts
    final_score = round(max(0.0, min(100.0, raw_score)), 1)

    # Determine Classification Level
    if final_score >= cfg.threshold_medium_to_high:
        level = ComplexityLevel.HIGH
    elif final_score >= cfg.threshold_low_to_medium:
        level = ComplexityLevel.MEDIUM
    else:
        level = ComplexityLevel.LOW

    # Generate Explainable Reasons
    if signals.variable_count >= 4:
        reasons.append(f"Broad parameter space with {signals.variable_count} interacting decision variables.")
    elif signals.variable_count > 0:
        reasons.append(f"Defined decision scope across {signals.variable_count} variable(s).")
    else:
        reasons.append("Minimal variable surface area.")

    if signals.constraint_count >= 3:
        reasons.append(f"Highly constrained operating envelope with {signals.constraint_count} explicit boundaries.")
    elif signals.constraint_count > 0:
        reasons.append(f"Bound by {signals.constraint_count} operational constraint(s).")

    if signals.tradeoff_count >= 2:
        reasons.append(f"High optimization friction involving {signals.tradeoff_count} competing trade-offs.")
    elif signals.tradeoff_count == 1:
        reasons.append("Contains a core primary trade-off.")

    if signals.irreversibility == ReversibilityLevel.IRREVERSIBLE:
        reasons.append("One-way door decision: irreversible consequences or prohibitive unwind costs.")
    elif signals.irreversibility == ReversibilityLevel.PARTIALLY_REVERSIBLE:
        reasons.append("Moderate unwind friction requiring structured rollback planning.")
    else:
        reasons.append("Two-way door: decision can be reversed with low friction.")

    if signals.uncertainty_level == UncertaintyLevel.HIGH:
        reasons.append(f"High environmental uncertainty compounded by {signals.unknown_count} critical unknown(s).")
    elif signals.unknown_count >= 2:
        reasons.append(f"Significant knowledge gaps ({signals.unknown_count} unresolved unknowns).")

    if signals.stakeholder_count >= 3:
        reasons.append(f"Broad organizational blast radius affecting {signals.stakeholder_count} stakeholder groups.")

    if signals.dependency_count >= 3:
        reasons.append(f"Coupled architectural or operational dependencies ({signals.dependency_count} dependencies).")

    return ComplexityResult(
        score=final_score,
        level=level,
        reasons=reasons,
    )
