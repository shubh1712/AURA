"""AURA Deterministic Resilience Engine Schemas (Day 6 Phase 6A).

Defines authoritative Pydantic schemas for deterministic decision stress-testing:
- ResilienceRating: high, moderate, fragile, vulnerable.
- ResiliencePillar: the four transparent 25-point evaluation dimensions.
- ResilienceSubScore: granular score, rationale, and detected vulnerabilities.
- ResilienceReport: comprehensive 0-100 resilience assessment with deterministic SHA-256 ID.
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

class ResilienceRating(str, Enum):
    """Categorical robustness rating of the recommended decision.

    Heuristic bands:
    - 80–100: high
    - 60–<80: moderate
    - 40–<60: fragile
    - Below 40: vulnerable
    """
    HIGH = "high"
    MODERATE = "moderate"
    FRAGILE = "fragile"
    VULNERABLE = "vulnerable"


class ResiliencePillar(str, Enum):
    """Canonical four pillars of deterministic resilience scoring (0-25 points each)."""
    CONSTRAINT_BOUNDARY_TOLERANCE = "constraint_boundary_tolerance"
    PESSIMISTIC_SCENARIO_SURVIVABILITY = "pessimistic_scenario_survivability"
    CONTINGENCY_AND_FALLBACK_COVERAGE = "contingency_and_fallback_coverage"
    INFORMATION_ROBUSTNESS = "information_robustness"


# ------------------------------------------------------------------------------
# 2. Sub-Score Schema
# ------------------------------------------------------------------------------

class ResilienceSubScore(BaseModel):
    """A granular evaluation sub-score for one of the four resilience pillars."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    category: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Pillar identifier or category name.",
    )
    score: float = Field(
        ...,
        description="Calculated score bounded between 0.0 and max_score (25.0).",
    )
    max_score: float = Field(
        default=25.0,
        description="Maximum possible score for this pillar (default 25.0).",
    )
    rationale: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Explainable breakdown of factors and metrics informing this score.",
    )
    vulnerabilities_detected: List[str] = Field(
        default_factory=list,
        description="Specific structural vulnerabilities or unmitigated risks identified.",
    )

    @field_validator("score")
    @classmethod
    def validate_score_bounds(cls, v: float) -> float:
        """Enforces finite numeric score bounded between 0.0 and 25.0."""
        if not math.isfinite(v):
            raise ValueError(f"Score must be a finite number, got {v}.")
        if v < 0.0 or v > 25.0:
            raise ValueError(f"Sub-score must be between 0.0 and 25.0, got {v}.")
        return round(float(v), 2)

    @field_validator("max_score")
    @classmethod
    def validate_max_score(cls, v: float) -> float:
        """Enforces positive finite max_score."""
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"max_score must be a positive finite number, got {v}.")
        return float(v)


# ------------------------------------------------------------------------------
# 3. Comprehensive Resilience Report Schema
# ------------------------------------------------------------------------------

class ResilienceReport(BaseModel):
    """Authoritative deterministic resilience report for a decision.

    Assesses how robust the recommended decision is across adverse scenarios,
    hard constraints, fallback plans, and information uncertainty.
    """
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        pattern=r"^res_[a-f0-9]{32}$",
        description="Deterministic content-derived resilience ID with 'res_' prefix.",
    )
    decision_model_id: str = Field(
        ...,
        description="ID of the underlying DecisionModel.",
    )
    scenario_set_id: str = Field(
        ...,
        description="ID of the underlying ScenarioSet.",
    )
    recommendation_id: str = Field(
        ...,
        description="ID of the underlying DecisionRecommendation.",
    )
    overall_score: float = Field(
        ...,
        description="Composite resilience score bounded between 0.0 and 100.0.",
    )
    rating: ResilienceRating = Field(
        ...,
        description="Categorical resilience rating (high, moderate, fragile, vulnerable).",
    )
    sub_scores: List[ResilienceSubScore] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Exactly four 25-point sub-scores corresponding to the four evaluation pillars.",
    )
    critical_vulnerabilities: List[str] = Field(
        default_factory=list,
        description="High-severity vulnerabilities that threaten decision stability.",
    )
    stress_test_passed: bool = Field(
        ...,
        description="Whether the decision passed adversarial scenario stress-testing.",
    )
    recommended_hedges: List[str] = Field(
        default_factory=list,
        description="Actionable hedging strategies and contingency measures.",
    )
    calculation_version: str = Field(
        default="1.0.0",
        description="Semantic version of the deterministic scoring algorithm.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this authoritative report was generated.",
    )

    @field_validator("overall_score")
    @classmethod
    def validate_overall_score(cls, v: float) -> float:
        """Enforces finite overall score bounded between 0.0 and 100.0."""
        if not math.isfinite(v):
            raise ValueError(f"Overall score must be a finite number, got {v}.")
        if v < 0.0 or v > 100.0:
            raise ValueError(f"Overall score must be between 0.0 and 100.0, got {v}.")
        return round(float(v), 2)

    @model_validator(mode="after")
    def validate_resilience_invariants(self) -> "ResilienceReport":
        """Validates consistency between sub-scores, overall score, and rating band."""
        if len(self.sub_scores) != 4:
            raise ValueError(
                f"ResilienceReport must contain exactly 4 sub-scores, got {len(self.sub_scores)}."
            )

        categories = [s.category for s in self.sub_scores]
        if len(set(categories)) != 4:
            raise ValueError(
                f"Resilience sub-score categories must be unique, got duplicates in {categories}."
            )

        sub_total = sum(s.score for s in self.sub_scores)
        # Allow slight rounding divergence (up to 0.1)
        if abs(self.overall_score - sub_total) > 0.15:
            raise ValueError(
                f"overall_score ({self.overall_score}) does not match sum of sub-scores ({sub_total:.2f})."
            )

        # Verify rating band consistency
        expected_rating = determine_resilience_rating(self.overall_score)
        if self.rating != expected_rating:
            raise ValueError(
                f"Rating '{self.rating.value}' is inconsistent with score {self.overall_score} "
                f"(expected '{expected_rating.value}')."
            )

        return self


# ------------------------------------------------------------------------------
# 4. Helper Functions
# ------------------------------------------------------------------------------

def determine_resilience_rating(score: float) -> ResilienceRating:
    """Maps a 0.0-100.0 resilience score to its canonical heuristic rating band."""
    if score >= 80.0:
        return ResilienceRating.HIGH
    if score >= 60.0:
        return ResilienceRating.MODERATE
    if score >= 40.0:
        return ResilienceRating.FRAGILE
    return ResilienceRating.VULNERABLE


def generate_deterministic_resilience_id(
    decision_model_id: str,
    scenario_set_id: str,
    recommendation_id: str,
    overall_score: float,
    calculation_version: str,
    sub_scores: Sequence[ResilienceSubScore],
) -> str:
    """Computes a deterministic, content-derived resilience report ID using SHA-256."""
    canonical_subscores = sorted(
        [
            {
                "category": s.category,
                "score": round(float(s.score), 2),
            }
            for s in sub_scores
        ],
        key=lambda x: x["category"],
    )

    payload = {
        "decision_model_id": decision_model_id.strip(),
        "scenario_set_id": scenario_set_id.strip(),
        "recommendation_id": recommendation_id.strip(),
        "overall_score": round(float(overall_score), 2),
        "calculation_version": calculation_version.strip(),
        "sub_scores": canonical_subscores,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"res_{digest[:32]}"
