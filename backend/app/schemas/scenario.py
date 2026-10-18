"""AURA Future Scenario Engine Schemas (Phase 5A).

Defines authoritative and candidate Pydantic schemas for the Scenario Generation Engine:
- Canonical ScenarioType enum: optimistic, base_case, pessimistic.
- Structured FutureScenario with probability, narrative, risks, opportunities,
  key events, timeline milestones, and upstream references.
- ScenarioSet enforcing exactly 3 scenarios, unique types, finite probabilities
  summing to 1.0 within 0.01 tolerance, and deterministic content-derived IDs.
- Candidate schemas for structured LLM generation.
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

class ScenarioType(str, Enum):
    """Canonical future scenario categories for decision stress-testing."""
    OPTIMISTIC = "optimistic"
    BASE_CASE = "base_case"
    PESSIMISTIC = "pessimistic"


# ------------------------------------------------------------------------------
# 2. Authoritative Component Schemas
# ------------------------------------------------------------------------------

class ScenarioKeyEvent(BaseModel):
    """A critical event, milestone, or trigger condition within a future scenario."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier for this scenario key event (e.g. 'ke_1_1').",
    )
    title: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Concise headline for the event.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Detailed description of the event occurrence and dynamics.",
    )
    timeframe: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Expected temporal window or milestone marker (e.g. 'Month 1-3', 'Q2').",
    )
    trigger_condition: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Specific precursor condition or metric shift that triggers this event.",
    )
    impact_on_decision: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Direct impact on decision objectives or operational constraints.",
    )


class ScenarioMilestone(BaseModel):
    """A projected timeline milestone marking progress along a scenario trajectory."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier for this scenario milestone (e.g. 'ms_1_1').",
    )
    title: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Concise name of the milestone.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Operational state or checkpoint details.",
    )
    time_horizon: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Target time horizon (e.g. 'immediate', 'near_term', 'medium_term', 'long_term').",
    )
    expected_outcome: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Observable outcome or metric threshold defining milestone achievement.",
    )


class FutureScenario(BaseModel):
    """Authoritative structured future scenario."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        pattern=r"^scen_[a-f0-9]{16,32}$",
        description="Deterministic content-derived scenario ID with 'scen_' prefix.",
    )
    scenario_type: ScenarioType = Field(
        ...,
        description="Canonical scenario category (optimistic, base_case, pessimistic).",
    )
    probability: float = Field(
        ...,
        description="Modeled probability estimate between 0.0 and 1.0.",
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Descriptive, distinctive title for this future scenario.",
    )
    narrative: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Comprehensive narrative describing operational conditions and environment.",
    )
    key_events: List[ScenarioKeyEvent] = Field(
        ...,
        min_length=1,
        description="Sequenced or critical events defining this scenario trajectory.",
    )
    risks: List[str] = Field(
        default_factory=list,
        description="Specific operational or strategic risks manifest in this scenario.",
    )
    opportunities: List[str] = Field(
        default_factory=list,
        description="Specific strategic opportunities or upsides available in this scenario.",
    )
    timeline: List[ScenarioMilestone] = Field(
        ...,
        min_length=1,
        description="Projected timeline milestones for this scenario.",
    )
    supporting_evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceItems supporting this scenario narrative.",
    )
    relevant_assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Assumptions directly tested or realized in this scenario.",
    )
    relevant_constraint_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Constraints pressured or respected in this scenario.",
    )
    relevant_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceGaps relevant to uncertainty in this scenario.",
    )

    @field_validator("probability")
    @classmethod
    def validate_scenario_probability(cls, v: float) -> float:
        """Enforces finite probability strictly bounded between 0.0 and 1.0."""
        if not math.isfinite(v):
            raise ValueError(f"Probability must be a finite number, got {v}.")
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Probability must be between 0.0 and 1.0, got {v}.")
        return round(float(v), 4)


# ------------------------------------------------------------------------------
# 3. Authoritative ScenarioSet
# ------------------------------------------------------------------------------

class ScenarioSet(BaseModel):
    """Authoritative portfolio of exactly three distinct future scenarios.

    Invariants strictly enforced:
    - Exactly three scenarios.
    - Exactly one optimistic, one base_case, and one pessimistic scenario.
    - Unique scenario IDs.
    - Finite, nonnegative probabilities summing to 1.0 within 0.01 tolerance.
    """
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        pattern=r"^scenset_[a-f0-9]{32}$",
        description="Deterministic content-derived scenario set ID with 'scenset_' prefix.",
    )
    decision_model_id: str = Field(
        ...,
        description="ID of the underlying DecisionModel.",
    )
    recommendation_id: Optional[str] = Field(
        default=None,
        description="ID of the underlying DecisionRecommendation, if available.",
    )
    reasoning_board_id: Optional[str] = Field(
        default=None,
        description="ID of the underlying ReasoningBoard, if available.",
    )
    evidence_package_id: Optional[str] = Field(
        default=None,
        description="ID of the underlying EvidencePackage, if available.",
    )
    summary: str = Field(
        ...,
        min_length=10,
        max_length=3000,
        description="Executive synthesis comparing the three future scenarios.",
    )
    scenarios: List[FutureScenario] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly three future scenarios: optimistic, base_case, and pessimistic.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this authoritative ScenarioSet was generated.",
    )

    @model_validator(mode="after")
    def validate_scenario_set_invariants(self) -> "ScenarioSet":
        """Validates cardinal invariants for three-scenario portfolio."""
        if len(self.scenarios) != 3:
            raise ValueError(
                f"ScenarioSet must contain exactly 3 scenarios, got {len(self.scenarios)}."
            )

        types_found = {s.scenario_type for s in self.scenarios}
        expected_types = {ScenarioType.OPTIMISTIC, ScenarioType.BASE_CASE, ScenarioType.PESSIMISTIC}
        if types_found != expected_types:
            missing = expected_types - types_found
            duplicates = [s.scenario_type.value for s in self.scenarios if list(types_found).count(s.scenario_type) > 1]
            raise ValueError(
                f"ScenarioSet must contain exactly one optimistic, one base_case, and one pessimistic scenario. "
                f"Missing: {missing}, Duplicates: {duplicates}."
            )

        ids_found = [s.id for s in self.scenarios]
        if len(set(ids_found)) != len(ids_found):
            raise ValueError(
                f"Scenario IDs must be unique across the portfolio, got duplicates in {ids_found}."
            )

        for s in self.scenarios:
            if not math.isfinite(s.probability):
                raise ValueError(
                    f"Scenario '{s.scenario_type.value}' probability must be finite, got {s.probability}."
                )
            if s.probability < 0.0 or s.probability > 1.0:
                raise ValueError(
                    f"Scenario '{s.scenario_type.value}' probability must be between 0.0 and 1.0, got {s.probability}."
                )

        prob_sum = sum(s.probability for s in self.scenarios)
        if not math.isfinite(prob_sum) or abs(prob_sum - 1.0) > 0.01:
            raise ValueError(
                f"Scenario probabilities must sum to 1.0 within 0.01 tolerance, got sum={prob_sum:.4f}."
            )

        return self


# ------------------------------------------------------------------------------
# 4. Deterministic Identity Helpers
# ------------------------------------------------------------------------------

def generate_deterministic_scenario_id(
    scenario_type: ScenarioType,
    name: str,
    probability: float,
    key_event_titles: Sequence[str],
) -> str:
    """Computes a deterministic, content-derived scenario ID using SHA-256."""
    payload = {
        "scenario_type": scenario_type.value if isinstance(scenario_type, ScenarioType) else str(scenario_type),
        "name": name.strip(),
        "probability": round(float(probability), 4),
        "key_event_titles": sorted([t.strip() for t in key_event_titles]),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"scen_{digest[:16]}"


def generate_deterministic_scenarioset_id(
    decision_model_id: str,
    recommendation_id: Optional[str],
    scenario_ids: Sequence[str],
) -> str:
    """Computes a deterministic, content-derived scenario set ID using SHA-256."""
    payload = {
        "decision_model_id": decision_model_id,
        "recommendation_id": recommendation_id or "",
        "scenario_ids": sorted(list(scenario_ids)),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"scenset_{digest[:32]}"


# ------------------------------------------------------------------------------
# 5. Candidate LLM Structured Output Schemas (Non-Authoritative)
# ------------------------------------------------------------------------------

class CandidateScenarioKeyEvent(BaseModel):
    """Candidate scenario key event proposed by language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Headline of the key event.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Detailed description of the event occurrence.",
    )
    timeframe: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Temporal window (e.g. 'Month 1-3', 'Q2').",
    )
    trigger_condition: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Condition or threshold triggering this event.",
    )
    impact_on_decision: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Impact on decision objectives or constraints.",
    )


class CandidateScenarioMilestone(BaseModel):
    """Candidate scenario milestone proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Milestone title.",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Milestone description.",
    )
    time_horizon: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Time horizon (immediate, near_term, medium_term, long_term).",
    )
    expected_outcome: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Expected outcome or metric threshold.",
    )


class CandidateFutureScenario(BaseModel):
    """Candidate scenario proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    scenario_type: ScenarioType = Field(
        ...,
        description="Canonical scenario category (optimistic, base_case, pessimistic).",
    )
    probability: float = Field(
        ...,
        description="Modeled probability estimate between 0.0 and 1.0.",
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Descriptive title for the scenario.",
    )
    narrative: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Comprehensive narrative describing the operating environment.",
    )
    key_events: List[CandidateScenarioKeyEvent] = Field(
        ...,
        min_length=1,
        description="Critical events in this scenario.",
    )
    risks: List[str] = Field(
        default_factory=list,
        description="Risks anticipated in this scenario.",
    )
    opportunities: List[str] = Field(
        default_factory=list,
        description="Opportunities anticipated in this scenario.",
    )
    timeline: List[CandidateScenarioMilestone] = Field(
        ...,
        min_length=1,
        description="Timeline milestones.",
    )
    supporting_evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="Authoritative EvidenceItem IDs supporting this scenario.",
    )
    relevant_assumption_ids: List[str] = Field(
        default_factory=list,
        description="Authoritative Assumption IDs tested in this scenario.",
    )
    relevant_constraint_ids: List[str] = Field(
        default_factory=list,
        description="Authoritative Constraint IDs relevant to this scenario.",
    )
    relevant_gap_ids: List[str] = Field(
        default_factory=list,
        description="Authoritative EvidenceGap IDs relevant to uncertainty in this scenario.",
    )

    @field_validator("probability")
    @classmethod
    def validate_candidate_probability(cls, v: float) -> float:
        """Validates finite probability between 0.0 and 1.0 on candidate model."""
        if not math.isfinite(v):
            raise ValueError(f"Probability must be a finite number, got {v}.")
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Probability must be between 0.0 and 1.0, got {v}.")
        return float(v)


class CandidateScenarioSet(BaseModel):
    """Candidate scenario set requested from LLMClient via generate_structured."""
    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str = Field(
        ...,
        min_length=10,
        max_length=3000,
        description="Executive summary comparing the three future scenarios.",
    )
    scenarios: List[CandidateFutureScenario] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Candidate scenarios: exactly one optimistic, one base_case, and one pessimistic.",
    )
