"""AURA Deterministic What-if Simulation Engine Schemas (Day 7 Phase 7A).

Defines authoritative, strongly typed Pydantic v2 schemas for offline what-if simulations:
- SimulationVariable: Authoritative numeric parameter discovered from decision model.
- SimulationAdjustment: User-proposed adjustment to a supported variable.
- SimulationRequest: Encapsulates cross-artifact references and adjustments.
- SimulationImpact: Granular record of affected fields and causal explanation.
- SimulationResult: Deterministic simulation report with optional resilience delta.

Enforces:
- Strict rejection of NaN, infinity, and inverted bounds.
- Rejection of duplicate adjustments per variable.
- Deterministic SHA-256 identity generation with 'sim_' prefix.
- Zero arithmetic fabrication for unmapped business variables.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ------------------------------------------------------------------------------
# 1. Enums
# ------------------------------------------------------------------------------

class SimulationVariableType(str, Enum):
    """Categorical classification of simulation variable values."""
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    NUMERIC = "numeric"
    COUNT = "count"
    RATIO = "ratio"


class SimulationUnit(str, Enum):
    """Standardized units for simulation variables and adjustments."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    PERCENT = "%"
    COUNT = "count"
    USERS = "users"
    DAYS = "days"
    MILLISECONDS = "ms"
    RATIO = "ratio"
    OTHER = "other"


class SimulationCalculationStatus(str, Enum):
    """Execution status for simulation impact and overall result."""
    CALCULATED = "calculated"
    UNSUPPORTED_NO_CAUSAL_MAPPING = "unsupported_no_causal_mapping"
    UNSUPPORTED_VARIABLE = "unsupported_variable"
    INVALID_BOUNDS = "invalid_bounds"
    REFERENCE_MISMATCH = "reference_mismatch"
    NO_ADJUSTMENTS = "no_adjustments"


# ------------------------------------------------------------------------------
# 2. Component Schemas
# ------------------------------------------------------------------------------

class SimulationVariable(BaseModel):
    """An authoritative numerical variable discovered from structured decision artifacts."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    variable_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier matching the source artifact (e.g. 'var_budget').",
    )
    label: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Human-readable variable label for display.",
    )
    description: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Detailed explanation of the variable's role and domain.",
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Unit of measurement (e.g. 'USD', '%', 'users', 'ms').",
    )
    value_type: SimulationVariableType = Field(
        ...,
        description="Numerical classification for mathematical simulation.",
    )
    baseline_value: float = Field(
        ...,
        description="Authoritative baseline numeric value extracted from structured artifact.",
    )
    minimum_value: Optional[float] = Field(
        default=None,
        description="Optional lower bound for realistic simulation.",
    )
    maximum_value: Optional[float] = Field(
        default=None,
        description="Optional upper bound for realistic simulation.",
    )
    source_artifact_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the authoritative artifact containing this baseline variable.",
    )
    source_field_path: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Exact JSON attribute path to the source field.",
    )
    simulation_supported: bool = Field(
        default=False,
        description="True if AURA currently has a validated causal transformation path for this variable.",
    )
    support_reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Transparent explanation of why this variable is or is not supported for simulation.",
    )

    @field_validator("baseline_value", "minimum_value", "maximum_value")
    @classmethod
    def validate_finite_floats(cls, v: Optional[float]) -> Optional[float]:
        """Rejects NaN and infinity."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"Value must be a finite number, got {v}.")
        return v

    @model_validator(mode="after")
    def validate_bounds(self) -> "SimulationVariable":
        """Enforces that minimum_value <= maximum_value and baseline is within bounds."""
        if self.minimum_value is not None and self.maximum_value is not None:
            if self.minimum_value > self.maximum_value:
                raise ValueError(
                    f"minimum_value ({self.minimum_value}) cannot exceed maximum_value ({self.maximum_value})."
                )
        if self.minimum_value is not None and self.baseline_value < self.minimum_value:
            raise ValueError(
                f"baseline_value ({self.baseline_value}) is below minimum_value ({self.minimum_value})."
            )
        if self.maximum_value is not None and self.baseline_value > self.maximum_value:
            raise ValueError(
                f"baseline_value ({self.baseline_value}) exceeds maximum_value ({self.maximum_value})."
            )
        return self


class SimulationAdjustment(BaseModel):
    """A user-proposed adjustment to a specific simulation variable."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    variable_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Identifier of the target variable to adjust.",
    )
    proposed_value: float = Field(
        ...,
        description="New candidate numerical value for simulation.",
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Unit of measurement, must match target variable unit if specified.",
    )

    @field_validator("proposed_value")
    @classmethod
    def validate_finite_proposed_value(cls, v: float) -> float:
        """Rejects NaN and infinity in proposed adjustment value."""
        if not math.isfinite(v):
            raise ValueError(f"proposed_value must be a finite number, got {v}.")
        return v


class SimulationRequest(BaseModel):
    """Request payload specifying baseline decision references and adjustments."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    decision_model_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline DecisionModel.",
    )
    scenario_set_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline ScenarioSet.",
    )
    recommendation_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline DecisionRecommendation.",
    )
    adjustments: List[SimulationAdjustment] = Field(
        ...,
        min_length=1,
        description="List of one or more variable adjustments.",
    )

    @field_validator("adjustments")
    @classmethod
    def validate_unique_adjustments(cls, v: List[SimulationAdjustment]) -> List[SimulationAdjustment]:
        """Rejects duplicate adjustments for the same variable."""
        seen = set()
        for adj in v:
            if adj.variable_id in seen:
                raise ValueError(
                    f"Duplicate adjustment for variable '{adj.variable_id}'. "
                    f"Each variable can only be adjusted once per simulation request."
                )
            seen.add(adj.variable_id)
        return v


class SimulationImpact(BaseModel):
    """Detailed record of how an individual adjustment transformed internal artifacts."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    variable_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target variable ID.",
    )
    original_value: float = Field(
        ...,
        description="Authoritative baseline value before adjustment.",
    )
    adjusted_value: float = Field(
        ...,
        description="Simulated proposed value after adjustment.",
    )
    transformation_rule_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identifier of the mathematical or logical transformation rule applied.",
    )
    affected_fields: List[str] = Field(
        ...,
        description="List of exact structured attribute paths updated by this adjustment.",
    )
    calculation_status: SimulationCalculationStatus = Field(
        ...,
        description="Calculation status for this specific impact.",
    )
    explanation: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Explainable rationale clarifying what was and was not modeled.",
    )

    @field_validator("original_value", "adjusted_value")
    @classmethod
    def validate_finite_floats(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"Impact values must be finite, got {v}.")
        return v


class SimulationResult(BaseModel):
    """Authoritative deterministic result of a what-if simulation."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        pattern=r"^sim_[a-f0-9]{32}$",
        description="Deterministic content-derived simulation ID with 'sim_' prefix.",
    )
    decision_model_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline DecisionModel.",
    )
    scenario_set_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline ScenarioSet.",
    )
    recommendation_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the baseline DecisionRecommendation.",
    )
    applied_adjustments: List[SimulationAdjustment] = Field(
        ...,
        description="List of applied adjustments in canonical order.",
    )
    impacts: List[SimulationImpact] = Field(
        ...,
        description="Granular impact records per variable.",
    )
    baseline_fingerprint: str = Field(
        default="",
        description="Canonical SHA-256 fingerprint of the baseline artifacts used for simulation.",
    )
    baseline_resilience_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Baseline resilience score (0-100), if available.",
    )
    simulated_resilience_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Simulated resilience score (0-100), only present if legitimately calculated.",
    )
    score_delta: Optional[float] = Field(
        default=None,
        ge=-100.0,
        le=100.0,
        description="Simulated minus baseline resilience score, only present if legitimately calculated.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Modeling caveats, bound violations, or unmapped variable warnings.",
    )
    status: SimulationCalculationStatus = Field(
        ...,
        description="Overall simulation calculation status.",
    )

    @field_validator("baseline_resilience_score", "simulated_resilience_score", "score_delta")
    @classmethod
    def validate_finite_scores(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not math.isfinite(v):
            raise ValueError(f"Score must be a finite number, got {v}.")
        return v


class SimulationVariableDiscoveryResponse(BaseModel):
    """API response contract for discovered adjustable simulation variables."""
    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(..., description="Target analysis ID.")
    job_id: Optional[str] = Field(default=None, description="Parent job ID, if applicable.")
    baseline_fingerprint: str = Field(..., description="Canonical SHA-256 fingerprint of baseline artifacts.")
    variables: List[SimulationVariable] = Field(..., description="Discovered numerical variables.")
    supported_count: int = Field(..., description="Count of variables supported for what-if simulation.")
    unsupported_count: int = Field(..., description="Count of variables discovered but not supported.")
    recalculation_capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supported recalculation capabilities and explanations.",
    )


class SimulationSubmitRequest(BaseModel):
    """API request contract for submitting what-if simulation adjustments."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    adjustments: List[SimulationAdjustment] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Collection of variable adjustments to evaluate (1 to 10 adjustments).",
    )
    baseline_fingerprint: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional client-verified baseline fingerprint to protect against stale simulations.",
    )

    @field_validator("adjustments")
    @classmethod
    def validate_unique_adjustments(cls, adjs: List[SimulationAdjustment]) -> List[SimulationAdjustment]:
        seen: set = set()
        for a in adjs:
            if a.variable_id in seen:
                raise ValueError(f"Duplicate adjustment for variable '{a.variable_id}'.")
            seen.add(a.variable_id)
        return adjs


class SimulationListResponse(BaseModel):
    """API response contract for listing persisted simulations for an analysis."""
    model_config = ConfigDict(frozen=True)

    analysis_id: str = Field(..., description="Target analysis ID.")
    simulations: List[SimulationResult] = Field(..., description="List of persisted simulation results.")
    total_count: int = Field(..., description="Total count of simulations retrieved.")


# ------------------------------------------------------------------------------
# 3. Deterministic Identity & Fingerprint Generation
# ------------------------------------------------------------------------------

def compute_baseline_fingerprint(
    decision_model: Any,
    scenario_set: Any,
    recommendation: Any,
    resilience_report: Optional[Any] = None,
) -> str:
    """Computes an immutable canonical SHA-256 fingerprint for baseline analysis artifacts.

    Invariants strictly enforced:
    - Same baseline artifact contents produce the exact same fingerprint.
    - Any material change to variables, constraints, scenarios, recommendation status,
      or baseline resilience score alters the fingerprint.
    - Prefix 'bfp_' followed by 32 hexadecimal characters.
    """
    decision_model_id = getattr(decision_model, "id", str(decision_model))
    raw_vars = getattr(decision_model, "variables", [])
    variables = [
        {
            "id": getattr(v, "id", ""),
            "baseline_value": getattr(v, "baseline_value", None),
            "proposed_value": getattr(v, "proposed_value", None),
            "unit": (getattr(v, "unit", "") or "").strip().lower(),
        }
        for v in raw_vars
    ]
    raw_cnstrs = getattr(decision_model, "constraints", [])
    constraints = [
        {
            "id": getattr(c, "id", ""),
            "threshold_expression": getattr(c, "threshold_expression", None),
            "is_hard": getattr(c, "is_hard_constraint", False),
        }
        for c in raw_cnstrs
    ]

    scenario_set_id = getattr(scenario_set, "id", str(scenario_set))
    raw_scens = getattr(scenario_set, "scenarios", [])
    scenarios = [
        {
            "id": getattr(s, "id", ""),
            "probability": round(float(getattr(s, "probability", 0.0)), 4),
            "type": getattr(getattr(s, "scenario_type", ""), "value", str(getattr(s, "scenario_type", ""))),
            "relevant_constraint_ids": sorted(list(getattr(s, "relevant_constraint_ids", []))),
        }
        for s in raw_scens
    ]

    recommendation_id = getattr(recommendation, "id", str(recommendation))
    status_obj = getattr(recommendation, "decision_status", "")
    rec_status = getattr(status_obj, "value", str(status_obj))

    res_score = getattr(resilience_report, "overall_score", None) if resilience_report is not None else None

    payload = {
        "decision_model_id": decision_model_id,
        "variables": sorted(variables, key=lambda x: str(x["id"])),
        "constraints": sorted(constraints, key=lambda x: str(x["id"])),
        "scenario_set_id": scenario_set_id,
        "scenarios": sorted(scenarios, key=lambda x: str(x["id"])),
        "recommendation_id": recommendation_id,
        "recommendation_status": rec_status,
        "resilience_score": res_score,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:32]
    return f"bfp_{digest}"


def generate_deterministic_simulation_id(
    decision_model_id: str,
    scenario_set_id: str,
    recommendation_id: str,
    adjustments: Sequence[SimulationAdjustment],
    baseline_fingerprint: Optional[str] = None,
) -> str:
    """Generates an immutable, repeatable 36-character simulation ID using SHA-256.

    Invariants strictly enforced:
    - Same baseline artifacts + same adjustments = same simulation ID.
    - Adjustment order invariance: adjustments are canonically sorted by variable_id.
    - Changing any input value, baseline artifact ID, or baseline fingerprint changes the ID.
    - Zero timestamps or randomness.
    - Prefix 'sim_' followed by 32 hexadecimal characters.
    """
    sorted_adjs = sorted(adjustments, key=lambda a: a.variable_id)
    payload = {
        "decision_model_id": decision_model_id,
        "scenario_set_id": scenario_set_id,
        "recommendation_id": recommendation_id,
        "baseline_fingerprint": baseline_fingerprint or "",
        "adjustments": [
            {
                "variable_id": a.variable_id,
                "proposed_value": round(float(a.proposed_value), 6),
                "unit": (a.unit or "").strip().lower(),
            }
            for a in sorted_adjs
        ],
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:32]
    return f"sim_{digest}"
