"""AURA Decision Recommendation & Action Planning Schemas (Day 5 Phase 1).

Defines authoritative and candidate Pydantic schemas for the Decision Recommendation
and Action Planning Engine:
- Categorical decision status (proceed, conditional, pilot, defer, reject, insufficient_evidence).
- Explainable uncertainty assessments (evidence strength, readiness, stability).
- Actionable implementation plans with dependencies, decision gates, and fallbacks.
- Strict referential integrity: evidence_item_ids, assumption_ids, evidence_gap_ids, disagreement_ids.
- Non-authoritative candidate schemas for LLM structured output generation.
- Authoritative schemas with deterministic, content-derived SHA-256 IDs.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Set
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard


# ------------------------------------------------------------------------------
# 1. Enums & Categorical Value Spaces
# ------------------------------------------------------------------------------

class DecisionStatus(str, Enum):
    """Categorical decision status for the recommended course of action."""
    PROCEED = "proceed"
    CONDITIONAL = "conditional"
    PILOT = "pilot"
    DEFER = "defer"
    REJECT = "reject"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceStrength(str, Enum):
    """Explainable categorical assessment of empirical evidence support."""
    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"
    CONTESTED = "contested"
    INSUFFICIENT = "insufficient"


class DecisionReadiness(str, Enum):
    """Explainable operational readiness to execute the recommendation."""
    READY = "ready"
    CONDITIONAL = "conditional"
    NEEDS_VALIDATION = "needs_validation"
    BLOCKED = "blocked"


class RecommendationStability(str, Enum):
    """Sensitivity of recommendation to new empirical data or changing assumptions."""
    HIGH = "high"
    MODERATE = "moderate"
    VOLATILE = "volatile"


class ActionPriority(str, Enum):
    """Priority level for an action item within the implementation plan."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionTimeHorizon(str, Enum):
    """Target execution time horizon for an action item."""
    IMMEDIATE = "immediate"      # 0-30 days
    NEAR_TERM = "near_term"      # 1-3 months
    MEDIUM_TERM = "medium_term"  # 3-6 months
    LONG_TERM = "long_term"      # 6+ months


# ------------------------------------------------------------------------------
# 2. Authoritative Component Schemas
# ------------------------------------------------------------------------------

class AlternativeOption(BaseModel):
    """An alternative strategic course of action considered during deliberation."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this alternative option (e.g. 'alt_1').",
    )
    name: str = Field(
        ...,
        min_length=2,
        description="Concise name of the alternative course of action.",
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Description of what this alternative entails.",
    )
    tradeoffs: List[str] = Field(
        default_factory=list,
        description="Key advantages and disadvantages relative to the recommended course.",
    )
    why_not_recommended: str = Field(
        ...,
        min_length=5,
        description="Analytical rationale explaining why this alternative was rejected or deprioritized.",
    )


class DecisionGate(BaseModel):
    """Measurable criteria, milestone, or condition required before proceeding."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this decision gate (e.g. 'gate_1').",
    )
    condition: str = Field(
        ...,
        min_length=3,
        description="Specific threshold, metric, or event required to pass this gate.",
    )
    target_milestone: str = Field(
        ...,
        min_length=2,
        description="Milestone, review checkpoint, or time marker when this gate is evaluated.",
    )
    verification_method: str = Field(
        ...,
        min_length=3,
        description="How the gate condition will be objectively verified.",
    )
    fallback_action: str = Field(
        ...,
        min_length=3,
        description="Contingency or rollback plan if the gate condition is not satisfied.",
    )


class ActionItem(BaseModel):
    """A prioritized, role-assigned action item in the implementation or validation plan."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this action (e.g. 'act_1').",
    )
    title: str = Field(
        ...,
        min_length=3,
        description="Concise title of the action item.",
    )
    objective: str = Field(
        ...,
        min_length=3,
        description="Direct operational objective of this action.",
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Actionable operational details and scope.",
    )
    priority: ActionPriority = Field(
        ...,
        description="Action priority within the implementation plan.",
    )
    responsible_role: str = Field(
        ...,
        min_length=2,
        description="Role or organizational entity responsible for execution.",
    )
    time_horizon: ActionTimeHorizon = Field(
        ...,
        description="Execution time horizon.",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Action IDs that must complete before this action begins.",
    )
    success_metrics: List[str] = Field(
        default_factory=list,
        description="Measurable criteria or empirical indicators of success.",
    )
    risk_mitigations: List[str] = Field(
        default_factory=list,
        description="Proactive mitigations for execution or strategic risks.",
    )
    decision_gates: List[DecisionGate] = Field(
        default_factory=list,
        description="Decision gates associated with this action item.",
    )
    fallback_action: Optional[str] = Field(
        default=None,
        description="Optional fallback action if this action cannot complete as planned.",
    )


class ActionPlan(BaseModel):
    """Comprehensive, sequenced action plan supporting the decision recommendation."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    summary: str = Field(
        ...,
        min_length=5,
        description="Executive summary of the implementation or validation roadmap.",
    )
    actions: List[ActionItem] = Field(
        ...,
        min_length=1,
        description="Prioritized, sequenced action items.",
    )
    key_milestones: List[str] = Field(
        default_factory=list,
        description="Major checkpoints marking strategic progress.",
    )


class UncertaintyAssessment(BaseModel):
    """Explainable, categorical assessment of epistemic uncertainty and decision stability."""
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    evidence_strength: EvidenceStrength = Field(
        ...,
        description="Categorical evaluation of empirical evidence backing this decision.",
    )
    decision_readiness: DecisionReadiness = Field(
        ...,
        description="Readiness to execute without preliminary validation or discovery.",
    )
    recommendation_stability: RecommendationStability = Field(
        ...,
        description="Stability of this recommendation in the face of foreseeable variance.",
    )
    critical_missing_information: List[str] = Field(
        default_factory=list,
        description="Information gaps that directly impair decision certainty.",
    )
    conditions_changing_recommendation: List[str] = Field(
        default_factory=list,
        description="Specific events, thresholds, or evidence discoveries that would alter the recommendation.",
    )
    assumptions_relied_upon: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Assumptions directly underpinning this recommendation.",
    )
    evidence_gaps_relied_upon: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceGaps that must be monitored.",
    )


# ------------------------------------------------------------------------------
# 3. Authoritative Root Recommendation Model
# ------------------------------------------------------------------------------

class DecisionRecommendation(BaseModel):
    """Authoritative decision recommendation and actionable execution plan.

    Reconciles upstream DecisionModel, EvidencePackage, and ReasoningBoard
    into a defensible strategic direction, explainable uncertainty assessment,
    and structured action plan.
    """
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    id: str = Field(
        ...,
        pattern=r"^rec_[a-f0-9]{32}$",
        description="Deterministic content-derived recommendation ID with 'rec_' prefix.",
    )
    decision_model_id: str = Field(
        ...,
        description="ID of the underlying DecisionModel.",
    )
    evidence_package_id: str = Field(
        ...,
        description="ID of the underlying EvidencePackage.",
    )
    reasoning_board_id: str = Field(
        ...,
        description="ID of the underlying ReasoningBoard.",
    )
    decision_status: DecisionStatus = Field(
        ...,
        description="Categorical strategic status of the recommendation.",
    )
    recommended_action: str = Field(
        ...,
        min_length=5,
        description="Clear, authoritative statement of the recommended course of action.",
    )
    executive_rationale: str = Field(
        ...,
        min_length=10,
        description="Executive rationale synthesizing why this course of action was selected.",
    )
    supporting_evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceItems directly supporting the recommendation.",
    )
    relevant_assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Assumptions critical to this recommendation.",
    )
    relevant_evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceGaps relevant to the decision.",
    )
    unresolved_disagreement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative ReasoningDisagreements factored into this recommendation.",
    )
    alternative_options: List[AlternativeOption] = Field(
        default_factory=list,
        description="Viable alternative options evaluated and their explicit trade-offs.",
    )
    uncertainty_assessment: UncertaintyAssessment = Field(
        ...,
        description="Explainable uncertainty, evidence strength, and stability assessment.",
    )
    action_plan: ActionPlan = Field(
        ...,
        description="Actionable, prioritized implementation or validation roadmap.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this authoritative recommendation was generated.",
    )


# ------------------------------------------------------------------------------
# 4. Deterministic Recommendation Identity Helper
# ------------------------------------------------------------------------------

def generate_deterministic_recommendation_id(
    decision_model_id: str,
    evidence_package_id: str,
    reasoning_board_id: str,
    decision_status: DecisionStatus,
    recommended_action: str,
    executive_rationale: str,
    action_ids: Sequence[str],
) -> str:
    """Computes a deterministic, content-derived recommendation ID using SHA-256.

    Canonicalizes all authoritative components to ensure exact stability
    regardless of timestamps, worker completion order, memory addresses,
    or execution platform.

    Returns:
        str: Stable ID with 'rec_' prefix and 32 hex chars (length 36 <= 64).
    """
    payload = {
        "decision_model_id": decision_model_id,
        "evidence_package_id": evidence_package_id,
        "reasoning_board_id": reasoning_board_id,
        "decision_status": decision_status.value if isinstance(decision_status, DecisionStatus) else str(decision_status),
        "recommended_action": recommended_action.strip(),
        "executive_rationale": executive_rationale.strip(),
        "action_ids": sorted(list(action_ids)),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"rec_{digest[:32]}"


# ------------------------------------------------------------------------------
# 5. Candidate LLM Structured Output Schemas (Non-Authoritative)
# ------------------------------------------------------------------------------

class CandidateAlternativeOption(BaseModel):
    """Candidate alternative course proposed by language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=2,
        description="Name of the alternative course of action.",
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Description of what this alternative entails.",
    )
    tradeoffs: List[str] = Field(
        default_factory=list,
        description="Key advantages and disadvantages relative to the recommendation.",
    )
    why_not_recommended: str = Field(
        ...,
        min_length=5,
        description="Analytical rationale explaining why this alternative was deprioritized.",
    )


class CandidateDecisionGate(BaseModel):
    """Candidate decision gate proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    condition: str = Field(
        ...,
        min_length=3,
        description="Condition or threshold required to pass this gate.",
    )
    target_milestone: str = Field(
        ...,
        min_length=2,
        description="Milestone or checkpoint when this gate is evaluated.",
    )
    verification_method: str = Field(
        ...,
        min_length=3,
        description="How the gate condition will be objectively verified.",
    )
    fallback_action: str = Field(
        ...,
        min_length=3,
        description="Fallback plan if the gate condition is not satisfied.",
    )


class CandidateActionItem(BaseModel):
    """Candidate action item proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(
        ...,
        min_length=3,
        description="Concise title of the action item.",
    )
    objective: str = Field(
        ...,
        min_length=3,
        description="Direct operational objective.",
    )
    description: str = Field(
        ...,
        min_length=5,
        description="Actionable operational scope and steps.",
    )
    priority: ActionPriority = Field(
        ...,
        description="Action priority.",
    )
    responsible_role: str = Field(
        ...,
        min_length=2,
        description="Responsible role or department.",
    )
    time_horizon: ActionTimeHorizon = Field(
        ...,
        description="Execution time horizon.",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Titles or temporary indices of actions that must complete before this action.",
    )
    success_metrics: List[str] = Field(
        default_factory=list,
        description="Measurable indicators of success.",
    )
    risk_mitigations: List[str] = Field(
        default_factory=list,
        description="Proactive mitigations for execution risks.",
    )
    decision_gates: List[CandidateDecisionGate] = Field(
        default_factory=list,
        description="Decision gates associated with this action item.",
    )
    fallback_action: Optional[str] = Field(
        default=None,
        description="Optional fallback action.",
    )


class CandidateActionPlan(BaseModel):
    """Candidate action plan proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str = Field(
        ...,
        min_length=5,
        description="Executive summary of the action plan.",
    )
    actions: List[CandidateActionItem] = Field(
        ...,
        min_length=1,
        description="Sequence of recommended actions.",
    )
    key_milestones: List[str] = Field(
        default_factory=list,
        description="Major checkpoints marking strategic progress.",
    )


class CandidateUncertaintyAssessment(BaseModel):
    """Candidate uncertainty assessment proposed by language model."""
    model_config = ConfigDict(str_strip_whitespace=True)

    evidence_strength: EvidenceStrength = Field(
        ...,
        description="Categorical evaluation of empirical evidence backing this decision.",
    )
    decision_readiness: DecisionReadiness = Field(
        ...,
        description="Readiness to execute without preliminary discovery.",
    )
    recommendation_stability: RecommendationStability = Field(
        ...,
        description="Stability of this recommendation in the face of variance.",
    )
    critical_missing_information: List[str] = Field(
        default_factory=list,
        description="Information gaps that directly impair decision certainty.",
    )
    conditions_changing_recommendation: List[str] = Field(
        default_factory=list,
        description="Specific events or evidence that would alter the recommendation.",
    )
    assumptions_relied_upon: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Assumptions directly underpinning this recommendation.",
    )
    evidence_gaps_relied_upon: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceGaps that must be monitored.",
    )


class CandidateDecisionRecommendation(BaseModel):
    """Candidate decision recommendation requested from LLMClient via generate_structured."""
    model_config = ConfigDict(str_strip_whitespace=True)

    decision_status: DecisionStatus = Field(
        ...,
        description="Categorical status: 'proceed', 'conditional', 'pilot', 'defer', 'reject', or 'insufficient_evidence'.",
    )
    recommended_action: str = Field(
        ...,
        min_length=5,
        description="Authoritative statement of the recommended course of action.",
    )
    executive_rationale: str = Field(
        ...,
        min_length=10,
        description="Concise executive rationale synthesizing the recommendation.",
    )
    supporting_evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceItems ('evi_...') supporting this recommendation.",
    )
    relevant_assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative Assumptions ('asm_...') relevant to this recommendation.",
    )
    relevant_evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative EvidenceGaps ('gap_...') relevant to this recommendation.",
    )
    unresolved_disagreement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative ReasoningDisagreements ('dis_...') factored into this recommendation.",
    )
    alternative_options: List[CandidateAlternativeOption] = Field(
        default_factory=list,
        description="Viable alternative options and their trade-offs.",
    )
    uncertainty_assessment: CandidateUncertaintyAssessment = Field(
        ...,
        description="Categorical assessment of uncertainty, evidence strength, and stability.",
    )
    action_plan: CandidateActionPlan = Field(
        ...,
        description="Actionable implementation or validation roadmap.",
    )
