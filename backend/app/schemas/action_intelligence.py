"""AURA Action Intelligence Schemas (Day 8A).

Defines strongly typed, authoritative Pydantic v2 schemas for Intelligent Action Plans:
- ActionCriterion: Structured operational, threshold, or qualitative criterion with provenance.
- IntelligentActionItem: Sequenced, role-assigned action item with dependencies, risk controls, and criteria.
- IntelligentDecisionGate: Checkpoint with evaluation criteria, failure response, and references.
- ValidationWarning: Deterministic conflict, review-required, or structural warning.
- IntelligentActionPlan: Immutable, grounded post-analysis action execution plan.
- Fingerprint generation for source recommendations and analyses.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ------------------------------------------------------------------------------
# 1. Enums
# ------------------------------------------------------------------------------

class CriterionType(str, Enum):
    """Categorical classification of an action or gate criterion."""
    HARD_CONSTRAINT = "hard_constraint"
    RECOMMENDATION_TARGET = "recommendation_target"
    EVIDENCE_THRESHOLD = "evidence_threshold"
    QUALITATIVE = "qualitative"
    UNSUPPORTED_METRIC = "unsupported_metric"


class ComparisonOperator(str, Enum):
    """Standard comparison operators for deterministic threshold evaluation."""
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    EQUAL = "=="
    NOT_EQUAL = "!="
    CONTAINS = "contains"
    QUALITATIVE = "qualitative"


class ActionPriority(str, Enum):
    """Operational urgency or criticality ranking."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ValidationSeverity(str, Enum):
    """Severity classification for deterministic validation findings."""
    CONFLICT = "conflict"
    REVIEW_REQUIRED = "review_required"
    WARNING = "warning"
    INFO = "info"


# ------------------------------------------------------------------------------
# 2. Component Models
# ------------------------------------------------------------------------------

class ActionCriterion(BaseModel):
    """A structured threshold, metric, or qualitative verification condition."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    criterion_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier for this criterion (e.g. 'crit_csat_floor').",
    )
    criterion_type: CriterionType = Field(
        ...,
        description="Categorical origin and nature of the criterion.",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Human-readable description of the condition or requirement.",
    )
    metric_name: Optional[str] = Field(
        default=None,
        description="Normalized name of the evaluated metric (e.g. 'csat', 'budget_usd', 'cohort_size').",
    )
    operator: Optional[ComparisonOperator] = Field(
        default=None,
        description="Comparison operator for quantitative thresholds.",
    )
    threshold_value: Optional[float] = Field(
        default=None,
        description="Numeric threshold if quantitatively comparable. Strictly None if qualitative.",
    )
    threshold_raw: Optional[str] = Field(
        default=None,
        description="Verbatim textual representation of the threshold (e.g. '90%', '$150,000').",
    )
    unit: Optional[str] = Field(
        default=None,
        description="Standardized unit of measurement (e.g. '%', 'USD', 'customers').",
    )
    provenance_type: str = Field(
        ...,
        description="Source category (e.g. 'decision_model.constraints', 'recommendation.action_plan').",
    )
    source_reference: Optional[str] = Field(
        default=None,
        description="ID of the authoritative upstream artifact (e.g. 'cnstr_pilot_cohort', 'obj_csat').",
    )
    is_hard: bool = Field(
        default=False,
        description="True if derived from a non-negotiable user hard constraint.",
    )

    @field_validator("threshold_value")
    @classmethod
    def validate_threshold_numeric(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            import math
            if math.isnan(v) or math.isinf(v):
                raise ValueError("threshold_value must be a finite numerical float.")
        return v


class IntelligentActionItem(BaseModel):
    """A prioritized, role-assigned, sequenced action item in an IntelligentActionPlan."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    action_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier for this action (e.g. 'act_1', 'act_pilot_setup').",
    )
    source_action_reference: Optional[str] = Field(
        default=None,
        description="ID of the corresponding Stage 4 action item in DecisionRecommendation (e.g. 'act_1').",
    )
    title: str = Field(
        ...,
        min_length=3,
        description="Concise operational title of the action item.",
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Detailed execution scope and operational procedure.",
    )
    priority: ActionPriority = Field(
        ...,
        description="Action priority within the implementation plan.",
    )
    sequence: int = Field(
        ...,
        ge=1,
        description="1-indexed sequence order within the execution roadmap.",
    )
    owner_role: str = Field(
        ...,
        min_length=2,
        description="Organizational role or department responsible (e.g. 'Head of Support', 'VP Engineering').",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Action IDs that must complete before this action begins.",
    )
    timing: Optional[str] = Field(
        default=None,
        description="Time horizon or milestone window (e.g. 'Immediate', 'Weeks 1-2', 'Month 1').",
    )
    prerequisites: List[str] = Field(
        default_factory=list,
        description="Technical, operational, or governance prerequisites required prior to execution.",
    )
    success_criteria: List[ActionCriterion] = Field(
        default_factory=list,
        description="Measurable verification criteria or thresholds marking successful completion.",
    )
    risk_mitigations: List[str] = Field(
        default_factory=list,
        description="Proactive mitigations for execution, privacy, or reliability risks.",
    )
    contingency_or_rollback: Optional[str] = Field(
        default=None,
        description="Contingency protocol or rollback instructions if the action fails or triggers a breach.",
    )
    evidence_references: List[str] = Field(
        default_factory=list,
        description="IDs of supporting EvidenceItems from Stage 2 EvidencePackage.",
    )
    rationale: str = Field(
        ...,
        min_length=5,
        description="Analytical rationale explaining why this action is necessary and defensible.",
    )
    confidence_label: str = Field(
        default="high",
        description="Confidence label ('high', 'moderate', 'low').",
    )
    confidence_rationale: Optional[str] = Field(
        default=None,
        description="Explanation supporting the assigned confidence label.",
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Identified data gaps, unknowns, or unverified assumptions impacting this action.",
    )

    @property
    def id(self) -> str:
        """Alias for action_id for cross-model consistency."""
        return self.action_id


class IntelligentDecisionGate(BaseModel):
    """A strategic checkpoint requiring verification of specific criteria before proceeding."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    gate_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier for this decision gate (e.g. 'gate_pilot_review').",
    )
    title: str = Field(
        ...,
        min_length=3,
        description="Descriptive title of the gate checkpoint.",
    )
    checkpoint: str = Field(
        ...,
        min_length=3,
        description="Evaluation point or milestone timing (e.g. 'End of Month 1', 'Prior to Scale Cutover').",
    )
    criteria: List[ActionCriterion] = Field(
        ...,
        min_length=1,
        description="Mandatory conditions or thresholds required to pass this gate.",
    )
    related_action_ids: List[str] = Field(
        default_factory=list,
        description="Action IDs directly gated or governed by this checkpoint.",
    )
    failure_response: str = Field(
        ...,
        min_length=5,
        description="Enforced response or rollback procedure if gate criteria are not satisfied.",
    )

    @property
    def id(self) -> str:
        """Alias for gate_id for cross-model consistency."""
        return self.gate_id

    @property
    def gate_name(self) -> str:
        """Alias for title for cross-model consistency."""
        return self.title
    source_references: List[str] = Field(
        default_factory=list,
        description="Authoritative artifact IDs underpinning this gate (e.g. 'cnstr_pilot_cohort').",
    )
    unresolved_conflicts: List[str] = Field(
        default_factory=list,
        description="Documented disagreements, boardroom disputes, or trade-offs evaluated at this gate.",
    )


class ValidationWarning(BaseModel):
    """A structured finding emitted by deterministic action plan validators."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    warning_id: str = Field(
        ...,
        description="Unique identifier for the warning (e.g. 'warn_threshold_conflict_1').",
    )
    severity: ValidationSeverity = Field(
        ...,
        description="Categorical severity of the finding.",
    )
    message: str = Field(
        ...,
        min_length=5,
        description="Actionable explanation of the conflict, cycle, or review requirement.",
    )
    related_action_ids: List[str] = Field(
        default_factory=list,
        description="Action IDs involved in the finding.",
    )
    related_gate_ids: List[str] = Field(
        default_factory=list,
        description="Decision gate IDs involved in the finding.",
    )
    related_criterion_ids: List[str] = Field(
        default_factory=list,
        description="ActionCriterion IDs involved in the finding.",
    )


# ------------------------------------------------------------------------------
# 3. Root Domain Model
# ------------------------------------------------------------------------------

class IntelligentActionPlan(BaseModel):
    """An authoritative, grounded Intelligent Action Plan generated from Stage 4 recommendation.

    Invariants strictly enforced:
    - Immutable (frozen=True) domain model.
    - Deterministic SHA-256 plan_id with 'plan_' prefix.
    - Exact source recommendation fingerprint with 'srfp_' prefix.
    - Preserves deterministic validation findings and warnings.
    - Zero quantitative hallucination or fabricated metrics.
    """
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    plan_id: str = Field(
        ...,
        pattern=r"^plan_[a-f0-9]{32}$",
        description="Deterministic content-derived plan ID with 'plan_' prefix.",
    )
    analysis_id: str = Field(
        ...,
        min_length=1,
        description="ID of the parent completed analysis.",
    )
    source_recommendation_fingerprint: str = Field(
        ...,
        pattern=r"^srfp_[a-f0-9]{32}$",
        description="Immutable SHA-256 fingerprint of the source recommendation and baseline model.",
    )
    schema_version: str = Field(
        default="1.0",
        description="Schema contract version.",
    )
    generator_version: str = Field(
        default="day8b_v1",
        description="Version identifier of the action intelligence generator.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 UTC creation timestamp.",
    )
    strategy_summary: str = Field(
        ...,
        min_length=10,
        description="Executive summary synthesizing the sequenced action intelligence strategy.",
    )
    actions: List[IntelligentActionItem] = Field(
        ...,
        min_length=1,
        description="Prioritized, sequenced action items.",
    )
    decision_gates: List[IntelligentDecisionGate] = Field(
        default_factory=list,
        description="Strategic checkpoints and decision gates governing roadmap execution.",
    )
    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="Key open strategic questions requiring ongoing telemetry or empirical testing.",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Explicitly surfaced analytical boundaries, unmodeled risks, or informational gaps.",
    )
    validation_warnings: List[ValidationWarning] = Field(
        default_factory=list,
        description="Deterministic validation findings, threshold conflicts, or review items.",
    )
    generation_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supplemental generator metadata (e.g. execution duration, prompt version).",
    )


# ------------------------------------------------------------------------------
# 4. Candidate Models for Structured Gemini Generation (Day 8B)
# ------------------------------------------------------------------------------

class CandidateActionCriterion(BaseModel):
    """Candidate verification condition produced during structured generation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    criterion_id: str = Field(..., min_length=1, max_length=64)
    criterion_type: CriterionType = Field(default=CriterionType.RECOMMENDATION_TARGET)
    description: str = Field(..., min_length=3)
    metric_name: Optional[str] = None
    operator: Optional[ComparisonOperator] = None
    threshold_value: Optional[float] = None
    threshold_raw: Optional[str] = None
    unit: Optional[str] = None
    provenance_type: str = Field(default="recommendation.action_plan")
    source_reference: Optional[str] = None
    is_hard: bool = False


class CandidateActionItem(BaseModel):
    """Candidate action item produced during structured generation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    action_id: str = Field(..., min_length=1, max_length=64)
    source_action_reference: str = Field(
        ...,
        min_length=1,
        description="ID of the authoritative Stage 4 action item being operationalized.",
    )
    title: str = Field(..., min_length=3)
    description: str = Field(..., min_length=5)
    priority: ActionPriority = Field(default=ActionPriority.HIGH)
    sequence: int = Field(default=1, ge=1)
    owner_role: str = Field(..., min_length=2)
    dependencies: List[str] = Field(default_factory=list)
    timing: Optional[str] = None
    prerequisites: List[str] = Field(default_factory=list)
    success_criteria: List[CandidateActionCriterion] = Field(default_factory=list)
    risk_mitigations: List[str] = Field(default_factory=list)
    contingency_or_rollback: Optional[str] = None
    evidence_references: List[str] = Field(default_factory=list)
    rationale: str = Field(..., min_length=5)
    confidence_label: str = Field(default="high")
    confidence_rationale: Optional[str] = None
    missing_information: List[str] = Field(default_factory=list)


class CandidateDecisionGate(BaseModel):
    """Candidate decision gate produced during structured generation."""
    model_config = ConfigDict(str_strip_whitespace=True)

    gate_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=3)
    checkpoint: str = Field(..., min_length=3)
    criteria: List[CandidateActionCriterion] = Field(default_factory=list)
    related_action_ids: List[str] = Field(default_factory=list)
    failure_response: str = Field(..., min_length=5)
    source_references: List[str] = Field(default_factory=list)
    unresolved_conflicts: List[str] = Field(default_factory=list)


class CandidateActionPlan(BaseModel):
    """Unvalidated candidate action plan generated directly by Google Gemini structured output."""
    model_config = ConfigDict(str_strip_whitespace=True)

    strategy_summary: str = Field(..., min_length=10)
    actions: List[CandidateActionItem] = Field(..., min_length=1)
    decision_gates: List[CandidateDecisionGate] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 5. Version Constants
# ------------------------------------------------------------------------------

ACTION_INTELLIGENCE_SCHEMA_VERSION = "1.0"
ACTION_INTELLIGENCE_GENERATOR_VERSION = "day8b_v1"
CURRENT_ACTION_INTELLIGENCE_PROMPT_VERSION = "v1"


# ------------------------------------------------------------------------------
# 6. Deterministic Identity & Fingerprint Generation
# ------------------------------------------------------------------------------

def compute_source_recommendation_fingerprint(
    recommendation: Any,
    decision_model: Any,
    scenario_set: Optional[Any] = None,
    resilience_report: Optional[Any] = None,
) -> str:
    """Computes an immutable canonical SHA-256 fingerprint for the source recommendation.

    Invariants strictly enforced:
    - Same recommendation action plan + decision model constraints produce identical fingerprint.
    - Any change to recommended action, action items, hard constraints, or baseline resilience
      score alters the fingerprint.
    - Uses SHA-256 (never Python's randomized hash()).
    - Returns 'srfp_' prefix followed by 32 hexadecimal characters.
    """
    rec_id = getattr(recommendation, "id", str(recommendation))
    rec_status = getattr(
        getattr(recommendation, "decision_status", ""),
        "value",
        str(getattr(recommendation, "decision_status", "")),
    )
    rec_action = (getattr(recommendation, "recommended_action", "") or "").strip()

    raw_actions = []
    action_plan = getattr(recommendation, "action_plan", None)
    if action_plan is not None:
        raw_items = getattr(action_plan, "actions", [])
        for act in raw_items:
            raw_actions.append({
                "id": getattr(act, "id", ""),
                "title": (getattr(act, "title", "") or "").strip(),
                "priority": getattr(getattr(act, "priority", ""), "value", str(getattr(act, "priority", ""))),
                "dependencies": sorted(list(getattr(act, "dependencies", []))),
            })

    raw_cnstrs = getattr(decision_model, "constraints", [])
    constraints = []
    for c in raw_cnstrs:
        constraints.append({
            "id": getattr(c, "id", ""),
            "threshold": getattr(c, "threshold", None),
            "threshold_expression": getattr(c, "threshold_expression", None),
            "unit": (getattr(c, "unit", "") or "").strip().lower(),
            "is_hard": getattr(c, "is_hard_constraint", False) or getattr(c, "type", "") == "hard",
        })

    canonical_payload = {
        "recommendation_id": rec_id,
        "decision_status": rec_status,
        "recommended_action": rec_action,
        "actions": sorted(raw_actions, key=lambda a: a["id"]),
        "constraints": sorted(constraints, key=lambda c: c["id"]),
        "resilience_score": getattr(resilience_report, "overall_score", None),
    }

    raw_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()[:32]
    return f"srfp_{digest}"


def compute_plan_id(
    analysis_id: str,
    source_recommendation_fingerprint: str,
    actions: List[Any],
) -> str:
    """Computes a deterministic content-derived identifier for an IntelligentActionPlan."""
    action_ids = [getattr(a, "action_id", getattr(a, "id", "")) for a in actions]
    canonical_payload = {
        "analysis_id": analysis_id,
        "source_recommendation_fingerprint": source_recommendation_fingerprint,
        "action_ids": sorted(action_ids),
    }
    raw_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()[:32]
    return f"plan_{digest}"
