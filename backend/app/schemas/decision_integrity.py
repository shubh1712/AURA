"""AURA Decision Integrity Schemas (Day 8G-A & Day 8G-B).

Defines strongly typed data contracts for deterministic calculations, cross-stage
consistency checks, alternative comparisons, evidence quality, and decision integrity reports:
- CalculationStatus and CalculationResult (precision-safe arithmetic, units, bounds, missing inputs).
- IntegritySeverity, FindingStatus, and IntegrityFinding (traceable rule codes, affected stages).
- OptionComparisonItem and OptionComparisonReport (non-fabricated, qualitative alternative matrix).
- SourceQualityClassification and EvidenceQualityReport (transparent source classification & deduplication).
- RankedEvidenceGap and UncertaintyCalibrationReport (decision-impact gap ranking, calibrated uncertainty).
- DecisionIntegrityReport: authoritative post-analysis mathematical and logical integrity assessment.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ------------------------------------------------------------------------------
# 1. Enums
# ------------------------------------------------------------------------------

class CalculationStatus(str, Enum):
    """Execution and feasibility status of a deterministic calculation."""
    FEASIBLE = "feasible"              # Calculation resolved and satisfies target/constraints
    INFEASIBLE = "infeasible"          # Calculation resolved and violates target/constraints
    UNRESOLVED = "unresolved"          # Required inputs are missing; no values manufactured
    REQUIRES_REVIEW = "requires_review"# Partial assumptions or contradictory bounds detected


class IntegritySeverity(str, Enum):
    """Categorical severity of a decision integrity finding."""
    CRITICAL = "critical"  # Major logical/mathematical contradiction that undermines the recommendation
    HIGH = "high"          # Material inconsistency or missing critical calculation
    MEDIUM = "medium"      # Scope divergence, ambiguous unit, or uncalibrated precision
    LOW = "low"            # Minor formatting or informational variance


class FindingStatus(str, Enum):
    """Verification certainty of an integrity finding."""
    CONFIRMED = "confirmed"              # Definitively proven contradiction or violation
    REQUIRES_REVIEW = "requires_review"  # Scope-aware or context-dependent divergence
    UNRESOLVED = "unresolved"            # Incomplete data prevents definitive confirmation


class IntegrityStatus(str, Enum):
    """Overall health rating of the analysis across all stages."""
    PASSED = "passed"                        # Zero critical/high findings
    WARNING = "warning"                      # High or medium findings that require human review
    CRITICAL_CONCERNS = "critical_concerns"  # Critical contradictions undermine recommendation
    INSUFFICIENT_DATA = "insufficient_data"  # Key financial/metric inputs completely missing


class DecisionReadinessStatus(str, Enum):
    """Operational readiness of the decision, distinct from technical analysis completion."""
    READY = "ready"                        # Rigorous, grounded, ready for executive commitment
    CONDITIONAL = "conditional"            # Viable pending satisfaction of explicit pre-conditions
    NEEDS_VALIDATION = "needs_validation"  # Critical empirical unknowns or calculations unverified
    BLOCKED = "blocked"                    # Infeasible bounds or non-negotiable hard constraints breached


class SourceCategory(str, Enum):
    """Transparent evidence source categorization."""
    PRIMARY_RESEARCH = "primary_empirical_research"
    INDEPENDENT_SECONDARY = "independent_secondary_research"
    OFFICIAL_STANDARDS = "official_standards_or_regulatory"
    VENDOR_PRODUCED = "vendor_produced_material"
    OPINION_COMMENTARY = "opinion_or_commentary"
    UNKNOWN = "unknown_source_type"


class GapDecisionImpact(str, Enum):
    """Categorical ranking of evidence gap impact on the final decision."""
    BLOCKS_CALCULATION = "blocks_calculation"
    DETERMINES_HARD_CONSTRAINT = "determines_hard_constraint"
    CHANGES_PREFERRED_OPTION = "changes_preferred_option"
    EXPANSION_GATE_DEPENDENCY = "expansion_gate_dependency"
    INFORMATIONAL = "informational"


# ------------------------------------------------------------------------------
# 2. Calculation Models
# ------------------------------------------------------------------------------

class CalculationResult(BaseModel):
    """A deterministic, typed arithmetic evaluation with explicit units and provenance."""
    model_config = ConfigDict(str_strip_whitespace=True)

    calculation_id: str = Field(..., description="Unique ID for this calculation (e.g. 'calc_net_savings').")
    title: str = Field(..., description="Human-readable title of the calculated metric.")
    category: str = Field(
        default="general",
        description="Category (e.g. 'net_savings', 'annualized_cost', 'cost_ceiling', 'efficiency').",
    )
    status: CalculationStatus = Field(..., description="Feasibility or resolution state.")
    value: Optional[float] = Field(default=None, description="Point estimate if single value resolved.")
    value_min: Optional[float] = Field(default=None, description="Lower bound under supported ranges.")
    value_max: Optional[float] = Field(default=None, description="Upper bound under supported ranges.")
    unit: Optional[str] = Field(default=None, description="Unit of measurement (e.g. 'USD', '%', 'hours').")
    currency: Optional[str] = Field(default=None, description="Standard ISO currency if financial (e.g. 'USD').")
    formula_expression: str = Field(..., description="Explicit mathematical relationship evaluated.")
    input_values: Dict[str, Any] = Field(default_factory=dict, description="Values of all known inputs used.")
    missing_inputs: List[str] = Field(default_factory=list, description="Names of missing required variables.")
    assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions incorporated.")
    explanation: str = Field(..., description="Human-readable explanation of the result and its implications.")


# ------------------------------------------------------------------------------
# 3. Integrity Finding Model
# ------------------------------------------------------------------------------

class IntegrityFinding(BaseModel):
    """A discrete mathematical, logical, or cross-stage consistency finding."""
    model_config = ConfigDict(str_strip_whitespace=True)

    finding_id: str = Field(..., description="Unique finding ID (e.g. 'find_csat_conflict_01').")
    rule_code: str = Field(..., description="Stable rule identifier (e.g. 'RULE_THRESHOLD_MISMATCH').")
    severity: IntegritySeverity = Field(..., description="Severity level of the finding.")
    status: FindingStatus = Field(..., description="Finding verification state.")
    affected_stages: List[int] = Field(..., description="Stage numbers involved in the conflict (e.g. [1, 4]).")
    title: str = Field(..., description="Short summary of the conflict or gap.")
    description: str = Field(..., description="Detailed explanation of the contradiction or inconsistency.")
    relevant_values: Dict[str, Any] = Field(default_factory=dict, description="Extracted values compared.")
    suggested_resolution: str = Field(..., description="Actionable recommendation to resolve the issue.")
    provenance: Optional[str] = Field(default=None, description="Source artifact references.")


# ------------------------------------------------------------------------------
# 4. Alternative Comparison Models (Day 8G-B)
# ------------------------------------------------------------------------------

class OptionComparisonItem(BaseModel):
    """Qualitative and empirical comparison item for a single viable alternative."""
    model_config = ConfigDict(str_strip_whitespace=True)

    option_id: str = Field(..., description="Unique option identifier.")
    title: str = Field(..., description="Name of the alternative option.")
    description: str = Field(..., description="Summary of the alternative approach.")
    is_recommended: bool = Field(default=False, description="True if selected as primary AI recommendation.")
    strengths: List[str] = Field(default_factory=list, description="Explicit advantages and benefits.")
    weaknesses: List[str] = Field(default_factory=list, description="Risks, costs, and downsides.")
    constraint_compatibility: str = Field(
        default="Satisfies stated constraints",
        description="Evaluation against hard and soft boundaries.",
    )
    supporting_evidence_count: int = Field(default=0, description="Count of linked empirical evidence citations.")
    missing_evidence: List[str] = Field(default_factory=list, description="Critical unverified assumptions.")
    key_tradeoffs: List[str] = Field(default_factory=list, description="Direct trade-offs inherent in this option.")
    feasibility_status: str = Field(default="feasible", description="Operational or technical feasibility state.")


class OptionComparisonReport(BaseModel):
    """Comprehensive comparison matrix across all viable alternatives."""
    model_config = ConfigDict(str_strip_whitespace=True)

    options: List[OptionComparisonItem] = Field(default_factory=list, description="All evaluated alternatives.")
    evaluation_criteria: List[str] = Field(default_factory=list, description="Explicit criteria compared.")
    evaluated_criteria: List[str] = Field(default_factory=list, description="Frontend alias for evaluation_criteria.")
    ranking_justified: bool = Field(
        default=True,
        description="False if insufficient empirical data prevents responsible ordinal ranking.",
    )
    is_conclusive: bool = Field(default=True, description="Frontend alias for ranking_justified.")
    unranked_reason: Optional[str] = Field(default=None, description="Explanation if options cannot be ranked.")
    comparison_matrix_note: str = Field(
        default="Qualitative trade-off matrix without manufactured scores",
        description="Frontend alias for matrix methodology note.",
    )
    summary: str = Field(default="", description="Synthesized executive comparison of alternatives.")

    @model_validator(mode="after")
    def sync_aliases(self) -> "OptionComparisonReport":
        if not self.evaluated_criteria and self.evaluation_criteria:
            object.__setattr__(self, "evaluated_criteria", list(self.evaluation_criteria))
        elif not self.evaluation_criteria and self.evaluated_criteria:
            object.__setattr__(self, "evaluation_criteria", list(self.evaluated_criteria))
        object.__setattr__(self, "is_conclusive", self.ranking_justified)
        if not self.summary:
            object.__setattr__(self, "summary", self.unranked_reason or self.comparison_matrix_note)
        return self


# ------------------------------------------------------------------------------
# 5. Evidence Quality Models (Day 8G-B)
# ------------------------------------------------------------------------------

class SourceQualityClassification(BaseModel):
    """Transparent source metadata and credibility classification."""
    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(..., description="Original source ID.")
    title: str = Field(..., description="Source title.")
    url: Optional[str] = Field(default=None, description="Source web URL.")
    category: SourceCategory = Field(..., description="Transparent source categorization.")
    is_independent: bool = Field(default=True, description="False for vendor whitepapers / marketing materials.")
    is_duplicate: bool = Field(default=False, description="True if URL was duplicated in citation list.")
    limitations: List[str] = Field(default_factory=list, description="Explicit methodological or scope limitations.")
    stance: str = Field(default="neutral", description="Stance relative to claim ('supporting', 'conflicting', 'neutral').")


class EvidenceQualityReport(BaseModel):
    """Authoritative evaluation of citation independence, diversity, and gaps."""
    model_config = ConfigDict(str_strip_whitespace=True)

    sources: List[SourceQualityClassification] = Field(default_factory=list)
    classifications: List[SourceQualityClassification] = Field(default_factory=list, description="Frontend alias for sources.")
    total_sources: int = Field(default=0, description="Total sources consulted.")
    primary_count: int = Field(default=0)
    secondary_count: int = Field(default=0)
    vendor_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    duplicate_sources_detected: int = Field(default=0, description="Frontend alias for duplicate_count.")
    category_breakdown: Dict[str, int] = Field(default_factory=dict, description="Category counts.")
    independence_ratio: float = Field(default=1.0, description="Ratio of independent sources (0.0 - 1.0).")
    summary: str = Field(default="", description="Summary of evidence quality and gaps.")

    @model_validator(mode="after")
    def sync_aliases(self) -> "EvidenceQualityReport":
        srcs = self.sources or self.classifications or []
        if not self.sources and srcs:
            object.__setattr__(self, "sources", list(srcs))
        if not self.classifications and srcs:
            object.__setattr__(self, "classifications", list(srcs))
        object.__setattr__(self, "total_sources", len(srcs))
        dups = self.duplicate_count or self.duplicate_sources_detected or 0
        object.__setattr__(self, "duplicate_count", dups)
        object.__setattr__(self, "duplicate_sources_detected", dups)
        if not self.category_breakdown:
            cb: Dict[str, int] = {
                "primary_empirical": self.primary_count,
                "independent_secondary": self.secondary_count,
                "vendor_produced": self.vendor_count,
            }
            object.__setattr__(self, "category_breakdown", cb)
        return self


# ------------------------------------------------------------------------------
# 6. Uncertainty & Ranked Evidence Gaps Models (Day 8G-B)
# ------------------------------------------------------------------------------

class RankedEvidenceGap(BaseModel):
    """An evidence gap ranked by its decision impact without fabricated numbers."""
    model_config = ConfigDict(str_strip_whitespace=True)

    gap_id: str = Field(..., description="Unique gap ID.")
    description: str = Field(..., description="The unverified assumption or missing measurement.")
    decision_impact: GapDecisionImpact = Field(..., description="Impact severity on the final decision.")
    rank: int = Field(..., description="Ordinal impact rank (1 = most critical).")
    concrete_validation_action: str = Field(..., description="Specific action to resolve this gap before committing.")


class UncertaintyCalibrationReport(BaseModel):
    """Calibrated uncertainty audit separating model scenario weights from true probabilities."""
    model_config = ConfigDict(str_strip_whitespace=True)

    is_calibrated: bool = Field(
        default=False,
        description="False: scenario probabilities are model heuristics, not frequentist likelihoods.",
    )
    scenario_weights_note: str = Field(
        default="Scenario probabilities represent qualitative heuristic weights, not empirical likelihoods.",
        description="Mandatory disclaimer for scenario distributions.",
    )
    ranked_gaps: List[RankedEvidenceGap] = Field(default_factory=list, description="Decision-impact ranked gaps.")
    calibration_warnings: List[str] = Field(default_factory=list, description="Warnings on overstated confidence.")


# ------------------------------------------------------------------------------
# 7. Complete Decision Integrity Report
# ------------------------------------------------------------------------------

INTEGRITY_RULE_VERSION = "day8g_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionIntegrityReport(BaseModel):
    """Authoritative decision integrity report for an analyzed decision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    analysis_id: str = Field(..., description="ID of the parent analysis evaluated.")
    overall_integrity_status: IntegrityStatus = Field(..., description="Overall integrity assessment.")
    overall_status: Optional[IntegrityStatus] = Field(default=None, description="Frontend alias for overall_integrity_status.")
    decision_readiness: DecisionReadinessStatus = Field(
        ...,
        description="Operational decision readiness (separate from technical analysis completion).",
    )
    calculations: List[CalculationResult] = Field(
        default_factory=list,
        description="Deterministic calculations evaluated.",
    )
    findings: List[IntegrityFinding] = Field(
        default_factory=list,
        description="Cross-stage consistency findings and warnings.",
    )
    severity_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of findings per severity level.",
    )
    status_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of findings per status.",
    )
    option_comparison: Optional[OptionComparisonReport] = Field(
        default=None,
        description="Qualitative and empirical comparison across all viable alternatives.",
    )
    evidence_quality: Optional[EvidenceQualityReport] = Field(
        default=None,
        description="Transparent source categorization and deduplication audit.",
    )
    uncertainty_calibration: Optional[UncertaintyCalibrationReport] = Field(
        default=None,
        description="Uncertainty calibration and decision-impact ranked gaps.",
    )
    rule_version: str = Field(default=INTEGRITY_RULE_VERSION, description="Integrity rule version.")
    evaluated_at: str = Field(default_factory=_utc_now_iso, description="ISO timestamp of evaluation.")
    evaluation_timestamp: str = Field(default="", description="Frontend alias for evaluated_at.")
    source_artifact_fingerprint: str = Field(
        default="",
        description="SHA-256 fingerprint of evaluated upstream artifacts.",
    )
    source_fingerprint: str = Field(default="", description="Frontend alias for source_artifact_fingerprint.")

    @model_validator(mode="after")
    def sync_aliases(self) -> "DecisionIntegrityReport":
        if self.overall_status is None:
            object.__setattr__(self, "overall_status", self.overall_integrity_status)
        if not self.source_fingerprint:
            object.__setattr__(self, "source_fingerprint", self.source_artifact_fingerprint)
        if not self.evaluation_timestamp:
            object.__setattr__(self, "evaluation_timestamp", self.evaluated_at)
        return self
