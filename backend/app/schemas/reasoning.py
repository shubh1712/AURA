"""AURA AI Boardroom Reasoning Schemas.

Defines canonical, strongly-typed data structures for multi-perspective
cognitive deliberation, argument structures, cross-perspective disagreements,
and boardroom synthesis.

Guarantees:
- Pure schema contracts without execution logic or LLM dependencies.
- Exactly four canonical perspectives: growth, finance, customer, risk.
- Boardroom is an additive artifact; upstream DecisionModel and EvidencePackage are immutable.
- Explicit cross-artifact referential integrity validation.
- No recommendation, vote, scoring, resilience, scenario, or what-if fields.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage


# ------------------------------------------------------------------------------
# 1. Canonical Enums
# ------------------------------------------------------------------------------

class PerspectiveType(str, Enum):
    """Canonical boardroom perspective lenses.

    There are exactly four perspectives in AURA. There is no fifth agent.
    """
    GROWTH = "growth"        # Market expansion, top-line scale, opportunity capture, TAM
    FINANCE = "finance"      # Unit economics, capital efficiency, ROI, cash runway, margins
    CUSTOMER = "customer"    # User experience, retention, churn, satisfaction, trust, adoption
    RISK = "risk"            # Operational vulnerabilities, compliance, reversibility, blast radius


class ReasoningBasis(str, Enum):
    """Epistemic grounding category of a reasoning argument."""
    EVIDENCE = "evidence"        # Directly grounded in empirical EvidenceItem findings
    INFERENCE = "inference"      # Logical projection or deduction without direct empirical proof
    ASSUMPTION = "assumption"    # Premised upon an unverified decision assumption
    UNRESOLVED = "unresolved"    # Hinges on an identified empirical unknown, gap, or pending requirement
    MIXED = "mixed"              # Draws upon multiple distinct epistemic categories


class ArgumentDirection(str, Enum):
    """Analytical direction of an argument relative to the proposed decision course.

    Non-binary: avoids simplistic yes/no or approve/reject framing.
    """
    FAVORABLE = "favorable"      # Supports or strengthens the viability/merits of the proposed path
    UNFAVORABLE = "unfavorable"  # Highlights friction, downsides, or barriers against the proposed path
    NEUTRAL = "neutral"          # Contextual framing, baseline observation, or trade-off balance
    MIXED = "mixed"              # Internal tension: positive in some facets, adverse in others


class DisagreementNature(str, Enum):
    """Root-cause taxonomy of cross-perspective tensions and disagreements."""
    EVIDENCE_DEPENDENT = "evidence_dependent"      # Disagreement arises from conflicting or incomplete evidence
    ASSUMPTION_DEPENDENT = "assumption_dependent"  # Disagreement stems from divergent unverified assumptions
    INTERPRETATION = "interpretation"              # Same empirical facts interpreted through conflicting strategic lenses
    UNRESOLVED = "unresolved"                      # Critical unknowns prevent objective alignment


# ------------------------------------------------------------------------------
# 2. Authoritative Reasoning Argument
# ------------------------------------------------------------------------------

class ReasoningArgument(BaseModel):
    """Discrete, structured argument formulated from a specific boardroom perspective."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique argument identifier (e.g. 'arg_growth_01').",
    )
    claim: str = Field(
        ...,
        min_length=3,
        description="Core assertion or thesis of the argument.",
    )
    direction: ArgumentDirection = Field(
        ...,
        description="Analytical orientation of the argument (favorable, unfavorable, neutral, mixed).",
    )
    basis: ReasoningBasis = Field(
        ...,
        description="Epistemic grounding category of this argument.",
    )
    reasoning: str = Field(
        ...,
        min_length=3,
        description="Substantive justification and analytical elaboration.",
    )
    evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of EvidenceItems supporting or informing this argument.",
    )
    requirement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of related EvidenceRequirements.",
    )
    assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of DecisionModel Assumptions directly tied to this argument.",
    )
    unknown_ids: List[str] = Field(
        default_factory=list,
        description="IDs of DecisionModel Unknowns affecting this argument.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of EvidenceGaps relevant to this argument.",
    )
    related_entity_ids: List[str] = Field(
        default_factory=list,
        description="IDs of related DecisionModel entities (variables, constraints, objectives, tradeoffs).",
    )
    caveat: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional boundary condition, qualifier, or caveat.",
    )

    @model_validator(mode="after")
    def validate_epistemic_basis(self) -> "ReasoningArgument":
        """Enforces structural epistemic consistency between basis and reference IDs."""
        if self.basis == ReasoningBasis.EVIDENCE:
            if not self.evidence_item_ids:
                raise ValueError(
                    f"Argument '{self.id}' with basis 'evidence' must reference at least one evidence_item_id."
                )

        elif self.basis == ReasoningBasis.ASSUMPTION:
            if not self.assumption_ids:
                raise ValueError(
                    f"Argument '{self.id}' with basis 'assumption' must reference at least one assumption_id."
                )

        elif self.basis == ReasoningBasis.UNRESOLVED:
            has_unresolved = bool(self.unknown_ids or self.evidence_gap_ids or self.requirement_ids)
            if not has_unresolved:
                raise ValueError(
                    f"Argument '{self.id}' with basis 'unresolved' must reference at least one unresolved "
                    "dependency (unknown_ids, evidence_gap_ids, or requirement_ids)."
                )

        elif self.basis == ReasoningBasis.MIXED:
            categories_present = sum([
                bool(self.evidence_item_ids),
                bool(self.assumption_ids),
                bool(self.unknown_ids or self.evidence_gap_ids or self.requirement_ids),
            ])
            if categories_present < 2:
                raise ValueError(
                    f"Argument '{self.id}' with basis 'mixed' must contain references across at least two "
                    "distinct epistemic categories (evidence, assumption, unresolved/unknown/gap)."
                )

        return self


# ------------------------------------------------------------------------------
# 3. Authoritative Reasoning Perspective
# ------------------------------------------------------------------------------

class ReasoningPerspective(BaseModel):
    """Complete evaluation and argument portfolio from one canonical perspective lens."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique perspective evaluation identifier (e.g. 'persp_growth').",
    )
    perspective_type: PerspectiveType = Field(
        ...,
        description="Canonical perspective lens (growth, finance, customer, risk).",
    )
    summary: str = Field(
        ...,
        min_length=3,
        description="Executive narrative evaluation from this strategic vantage point.",
    )
    arguments: List[ReasoningArgument] = Field(
        default_factory=list,
        description="Discrete arguments articulating this perspective's analysis.",
    )
    critical_assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of Assumptions deemed pivotal by this perspective.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of EvidenceGaps that create strategic exposure from this perspective.",
    )
    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="High-priority open questions flagged by this perspective.",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Self-acknowledged analytical boundaries or blind spots of this lens.",
    )
    opportunities: List[str] = Field(
        default_factory=list,
        description="Key opportunities highlighted from this perspective.",
    )
    concerns: List[str] = Field(
        default_factory=list,
        description="Key risks or downside concerns emphasized from this perspective.",
    )

    @model_validator(mode="after")
    def validate_perspective_internal(self) -> "ReasoningPerspective":
        """Ensures argument IDs are unique within this perspective."""
        arg_ids = [a.id for a in self.arguments]
        if len(arg_ids) != len(set(arg_ids)):
            seen: Set[str] = set()
            dups: Set[str] = set()
            for aid in arg_ids:
                if aid in seen:
                    dups.add(aid)
                seen.add(aid)
            raise ValueError(
                f"Duplicate argument IDs found in perspective '{self.id}': {sorted(dups)}"
            )
        return self


# ------------------------------------------------------------------------------
# 4. First-Class Disagreement Model
# ------------------------------------------------------------------------------

class ReasoningDisagreement(BaseModel):
    """First-class representation of an explicit strategic tension between perspectives."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique disagreement identifier (e.g. 'dis_growth_vs_finance_01').",
    )
    topic: str = Field(
        ...,
        min_length=3,
        description="Substantive theme or tension under debate.",
    )
    perspective_ids: List[str] = Field(
        ...,
        min_length=2,
        description="IDs of at least two distinct perspectives involved in this tension.",
    )
    argument_ids: List[str] = Field(
        default_factory=list,
        description="IDs of specific ReasoningArguments articulating the competing stances.",
    )
    positions: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of perspective ID to its summarized position on this topic.",
    )
    evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="Contested or differentially interpreted EvidenceItems.",
    )
    assumption_ids: List[str] = Field(
        default_factory=list,
        description="Underlying conflicting Assumptions driving the tension.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="EvidenceGaps that sustain the disagreement.",
    )
    nature: DisagreementNature = Field(
        ...,
        description="Root cause categorization of the disagreement.",
    )

    @model_validator(mode="after")
    def validate_disagreement_structure(self) -> "ReasoningDisagreement":
        """Enforces structural constraints on cross-perspective disagreements."""
        # 1. Must involve at least two distinct perspectives
        if len(self.perspective_ids) < 2:
            raise ValueError(
                f"Disagreement '{self.id}' must involve at least two perspectives."
            )
        if len(self.perspective_ids) != len(set(self.perspective_ids)):
            raise ValueError(
                f"Disagreement '{self.id}' contains duplicate perspective IDs: {self.perspective_ids}"
            )

        # 2. Reject duplicate reference IDs
        for field_name, ids in [
            ("argument_ids", self.argument_ids),
            ("evidence_item_ids", self.evidence_item_ids),
            ("assumption_ids", self.assumption_ids),
            ("evidence_gap_ids", self.evidence_gap_ids),
        ]:
            if len(ids) != len(set(ids)):
                raise ValueError(
                    f"Disagreement '{self.id}' contains duplicate IDs in '{field_name}'."
                )

        return self


# ------------------------------------------------------------------------------
# 5. Board Synthesis Contract
# ------------------------------------------------------------------------------

class BoardSynthesis(BaseModel):
    """Cross-perspective synthesis of alignment, tensions, and critical dependencies."""
    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str = Field(
        ...,
        min_length=3,
        description="Executive summary reconciling the board's collective deliberation.",
    )
    areas_of_agreement: List[str] = Field(
        default_factory=list,
        description="Strategic common ground where perspectives converge.",
    )
    disagreement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of active ReasoningDisagreements across the board.",
    )
    critical_assumption_ids: List[str] = Field(
        default_factory=list,
        description="Cross-perspective foundational assumptions requiring vigilance.",
    )
    critical_evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="High-leverage evidence gaps that, if closed, would resolve key tensions.",
    )
    evidence_sensitive_points: List[str] = Field(
        default_factory=list,
        description="Points of deliberation where new empirical data would most alter the balance.",
    )
    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="Unresolved strategic questions demanding executive resolution.",
    )

    @model_validator(mode="after")
    def validate_synthesis_internal(self) -> "BoardSynthesis":
        """Enforces unique ID collections within synthesis."""
        for field_name, ids in [
            ("disagreement_ids", self.disagreement_ids),
            ("critical_assumption_ids", self.critical_assumption_ids),
            ("critical_evidence_gap_ids", self.critical_evidence_gap_ids),
        ]:
            if len(ids) != len(set(ids)):
                raise ValueError(
                    f"BoardSynthesis contains duplicate IDs in '{field_name}'."
                )
        return self


# ------------------------------------------------------------------------------
# 6. Top-Level Canonical ReasoningBoard
# ------------------------------------------------------------------------------

class ReasoningBoard(BaseModel):
    """Canonical domain representation of AI Boardroom multi-perspective deliberation.

    Contains exactly four perspectives (growth, finance, customer, risk),
    first-class cross-perspective disagreements, and an analytical synthesis.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Globally unique ReasoningBoard identifier (e.g. 'board_dec_sample').",
    )
    decision_model_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Foreign key to DecisionModel.id.",
    )
    evidence_package_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Foreign key to EvidencePackage.id.",
    )
    perspectives: List[ReasoningPerspective] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Exactly four canonical perspective analyses (growth, finance, customer, risk).",
    )
    disagreements: List[ReasoningDisagreement] = Field(
        default_factory=list,
        description="Structured cross-perspective disagreements.",
    )
    synthesis: BoardSynthesis = Field(
        ...,
        description="Cross-perspective synthesis and tension mapping.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp when the board deliberation completed.",
    )

    @field_validator("created_at")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Guarantees created_at is timezone-aware UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_board_structure(self) -> "ReasoningBoard":
        """Enforces structural and referential integrity inside the ReasoningBoard."""
        canonical_types = {
            PerspectiveType.GROWTH,
            PerspectiveType.FINANCE,
            PerspectiveType.CUSTOMER,
            PerspectiveType.RISK,
        }

        # 1. Exactly four distinct canonical perspectives required
        persp_types = [p.perspective_type for p in self.perspectives]
        if len(self.perspectives) != 4 or set(persp_types) != canonical_types:
            missing = canonical_types - set(persp_types)
            if missing:
                missing_str = ", ".join(m.value for m in sorted(missing, key=lambda x: x.value))
                raise ValueError(
                    f"ReasoningBoard is missing canonical perspectives: {missing_str}."
                )
            raise ValueError(
                "ReasoningBoard must contain exactly four distinct canonical perspectives "
                "(growth, finance, customer, risk) each occurring exactly once."
            )

        # 2. Unique perspective IDs
        p_ids = [p.id for p in self.perspectives]
        if len(p_ids) != len(set(p_ids)):
            raise ValueError(
                f"Duplicate perspective IDs found in ReasoningBoard: {p_ids}"
            )
        valid_perspective_ids = set(p_ids)

        # 3. Unique argument IDs across the entire board
        all_arg_ids: List[str] = []
        for p in self.perspectives:
            for a in p.arguments:
                all_arg_ids.append(a.id)

        if len(all_arg_ids) != len(set(all_arg_ids)):
            seen: Set[str] = set()
            dups: Set[str] = set()
            for aid in all_arg_ids:
                if aid in seen:
                    dups.add(aid)
                seen.add(aid)
            raise ValueError(
                f"Duplicate argument IDs found across board perspectives: {sorted(dups)}"
            )
        valid_argument_ids = set(all_arg_ids)

        # 4. Unique disagreement IDs
        d_ids = [d.id for d in self.disagreements]
        if len(d_ids) != len(set(d_ids)):
            raise ValueError(
                f"Duplicate disagreement IDs found in ReasoningBoard: {d_ids}"
            )
        valid_disagreement_ids = set(d_ids)

        # 5. Disagreement perspective_ids resolve to board perspectives
        for d in self.disagreements:
            for pid in d.perspective_ids:
                if pid not in valid_perspective_ids:
                    raise ValueError(
                        f"Disagreement '{d.id}' references nonexistent perspective ID '{pid}'."
                    )

        # 6. Disagreement argument_ids resolve to board arguments
        for d in self.disagreements:
            for aid in d.argument_ids:
                if aid not in valid_argument_ids:
                    raise ValueError(
                        f"Disagreement '{d.id}' references nonexistent argument ID '{aid}'."
                    )

        # 7. Synthesis disagreement_ids resolve to board disagreements
        for did in self.synthesis.disagreement_ids:
            if did not in valid_disagreement_ids:
                raise ValueError(
                    f"BoardSynthesis references nonexistent disagreement ID '{did}'."
                )

        return self

    def get_perspective(self, perspective_type: PerspectiveType) -> ReasoningPerspective:
        """Retrieves a specific canonical perspective from the board."""
        for p in self.perspectives:
            if p.perspective_type == perspective_type:
                return p
        raise KeyError(f"Perspective '{perspective_type.value}' not found on board.")

    def get_ordered_perspectives(self) -> List[ReasoningPerspective]:
        """Returns perspectives in canonical order: growth, finance, customer, risk."""
        order = [
            PerspectiveType.GROWTH,
            PerspectiveType.FINANCE,
            PerspectiveType.CUSTOMER,
            PerspectiveType.RISK,
        ]
        return [self.get_perspective(t) for t in order]


# ------------------------------------------------------------------------------
# 7. Cross-Artifact Pure Validation Helper
# ------------------------------------------------------------------------------

def validate_reasoning_references(
    reasoning_board: ReasoningBoard,
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
) -> None:
    """Validates referential integrity of a ReasoningBoard against DecisionModel and EvidencePackage.

    Pure function: performs no mutation, network calls, or LLM operations.

    Raises:
        ValueError: If any foreign key or entity ID reference fails to resolve.
    """
    # 1. Validate top-level artifact bindings
    if reasoning_board.decision_model_id != decision_model.id:
        raise ValueError(
            f"ReasoningBoard decision_model_id '{reasoning_board.decision_model_id}' "
            f"does not match DecisionModel id '{decision_model.id}'."
        )

    if reasoning_board.evidence_package_id != evidence_package.id:
        raise ValueError(
            f"ReasoningBoard evidence_package_id '{reasoning_board.evidence_package_id}' "
            f"does not match EvidencePackage id '{evidence_package.id}'."
        )

    # 2. Extract valid reference ID sets from upstream EvidencePackage
    valid_evidence_item_ids: Set[str] = {item.id for item in evidence_package.items}
    valid_requirement_ids: Set[str] = {req.id for req in evidence_package.requirements}
    valid_gap_ids: Set[str] = {gap.id for gap in evidence_package.gaps}

    # 3. Extract valid reference ID sets from upstream DecisionModel
    valid_assumption_ids: Set[str] = {asm.id for asm in decision_model.assumptions}
    valid_unknown_ids: Set[str] = {unk.id for unk in decision_model.unknowns}

    allowed_decision_entity_ids: Set[str] = {
        decision_model.id,
        *(obj.id for obj in decision_model.objectives),
        *(var.id for var in decision_model.variables),
        *(cnstr.id for cnstr in decision_model.constraints),
        *(stk.id for stk in decision_model.stakeholders),
        *(trd.id for trd in decision_model.tradeoffs),
        *(asm.id for asm in decision_model.assumptions),
        *(unk.id for unk in decision_model.unknowns),
    }

    # 4. Validate perspectives and their arguments
    for p in reasoning_board.perspectives:
        # Perspective-level references
        for aid in p.critical_assumption_ids:
            if aid not in valid_assumption_ids:
                raise ValueError(
                    f"Perspective '{p.id}' references nonexistent critical assumption ID '{aid}'."
                )

        for gid in p.evidence_gap_ids:
            if gid not in valid_gap_ids:
                raise ValueError(
                    f"Perspective '{p.id}' references nonexistent evidence gap ID '{gid}'."
                )

        # Argument-level references
        for arg in p.arguments:
            for eid in arg.evidence_item_ids:
                if eid not in valid_evidence_item_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent evidence_item_id '{eid}'."
                    )

            for rid in arg.requirement_ids:
                if rid not in valid_requirement_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent requirement_id '{rid}'."
                    )

            for aid in arg.assumption_ids:
                if aid not in valid_assumption_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent assumption_id '{aid}'."
                    )

            for uid in arg.unknown_ids:
                if uid not in valid_unknown_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent unknown_id '{uid}'."
                    )

            for gid in arg.evidence_gap_ids:
                if gid not in valid_gap_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent evidence_gap_id '{gid}'."
                    )

            for reid in arg.related_entity_ids:
                if reid not in allowed_decision_entity_ids:
                    raise ValueError(
                        f"Argument '{arg.id}' in perspective '{p.id}' references nonexistent related_entity_id '{reid}'."
                    )

    # 5. Validate disagreements
    for d in reasoning_board.disagreements:
        for eid in d.evidence_item_ids:
            if eid not in valid_evidence_item_ids:
                raise ValueError(
                    f"Disagreement '{d.id}' references nonexistent evidence_item_id '{eid}'."
                )

        for aid in d.assumption_ids:
            if aid not in valid_assumption_ids:
                raise ValueError(
                    f"Disagreement '{d.id}' references nonexistent assumption_id '{aid}'."
                )

        for gid in d.evidence_gap_ids:
            if gid not in valid_gap_ids:
                raise ValueError(
                    f"Disagreement '{d.id}' references nonexistent evidence_gap_id '{gid}'."
                )

    # 6. Validate synthesis
    for aid in reasoning_board.synthesis.critical_assumption_ids:
        if aid not in valid_assumption_ids:
            raise ValueError(
                f"BoardSynthesis references nonexistent critical assumption ID '{aid}'."
            )

    for gid in reasoning_board.synthesis.critical_evidence_gap_ids:
        if gid not in valid_gap_ids:
            raise ValueError(
                f"BoardSynthesis references nonexistent critical evidence gap ID '{gid}'."
            )


# ------------------------------------------------------------------------------
# 8. Candidate LLM Structured Output Schemas (Non-Authoritative)
# ------------------------------------------------------------------------------

class CandidateReasoningArgument(BaseModel):
    """Candidate argument proposed by a language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    claim: str = Field(
        ...,
        min_length=3,
        description="Core assertion or thesis of the argument.",
    )
    direction: ArgumentDirection = Field(
        ...,
        description="Analytical orientation of the argument.",
    )
    basis: ReasoningBasis = Field(
        ...,
        description="Epistemic grounding category of this argument.",
    )
    reasoning: str = Field(
        ...,
        min_length=3,
        description="Substantive justification and analytical elaboration.",
    )
    evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="IDs of referenced EvidenceItems.",
    )
    requirement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of related EvidenceRequirements (must start with 'req_').",
    )
    assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of referenced Assumptions.",
    )
    unknown_ids: List[str] = Field(
        default_factory=list,
        description="IDs of referenced Unknowns from Decision Model (must start with 'unk_'). NEVER cite requirement IDs ('req_...') here.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of referenced EvidenceGaps.",
    )
    related_entity_ids: List[str] = Field(
        default_factory=list,
        description="IDs of referenced DecisionModel entities.",
    )
    caveat: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional boundary condition or caveat.",
    )

    @model_validator(mode="after")
    def validate_candidate_epistemic_basis(self) -> "CandidateReasoningArgument":
        """Enforces structural epistemic consistency for candidate argument."""
        if self.basis == ReasoningBasis.EVIDENCE and not self.evidence_item_ids:
            raise ValueError("Candidate argument with basis 'evidence' must reference at least one evidence_item_id.")
        if self.basis == ReasoningBasis.ASSUMPTION and not self.assumption_ids:
            raise ValueError("Candidate argument with basis 'assumption' must reference at least one assumption_id.")
        if self.basis == ReasoningBasis.UNRESOLVED and not (self.unknown_ids or self.evidence_gap_ids or self.requirement_ids):
            raise ValueError(
                "Candidate argument with basis 'unresolved' must reference at least one unresolved dependency."
            )
        if self.basis == ReasoningBasis.MIXED:
            cat_count = sum([
                bool(self.evidence_item_ids),
                bool(self.assumption_ids),
                bool(self.unknown_ids or self.evidence_gap_ids or self.requirement_ids),
            ])
            if cat_count < 2:
                raise ValueError("Candidate argument with basis 'mixed' must reference at least two distinct epistemic categories.")
        return self


class CandidatePerspectiveAnalysis(BaseModel):
    """Candidate perspective evaluation proposed by language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    perspective_type: PerspectiveType = Field(
        ...,
        description="Perspective lens analyzed.",
    )
    summary: str = Field(
        ...,
        min_length=3,
        description="Executive narrative evaluation from this strategic vantage point.",
    )
    arguments: List[CandidateReasoningArgument] = Field(
        default_factory=list,
        description="Candidate arguments articulating this perspective's analysis.",
    )
    critical_assumption_ids: List[str] = Field(
        default_factory=list,
        description="IDs of critical Assumptions identified.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of critical EvidenceGaps identified.",
    )
    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="Open strategic questions flagged.",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Self-acknowledged analytical boundaries.",
    )
    opportunities: List[str] = Field(
        default_factory=list,
        description="Key opportunities highlighted.",
    )
    concerns: List[str] = Field(
        default_factory=list,
        description="Key risks or downside concerns emphasized.",
    )


class CandidateDisagreement(BaseModel):
    """Candidate disagreement identified by language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    topic: str = Field(
        ...,
        min_length=3,
        description="Substantive theme under debate.",
    )
    perspective_types: List[PerspectiveType] = Field(
        ...,
        min_length=2,
        description="Perspectives involved in tension (at least two distinct).",
    )
    positions: Dict[str, str] = Field(
        default_factory=dict,
        description="Summary of positions on this topic.",
    )
    evidence_item_ids: List[str] = Field(
        default_factory=list,
        description="Contested EvidenceItems.",
    )
    assumption_ids: List[str] = Field(
        default_factory=list,
        description="Underlying conflicting Assumptions.",
    )
    evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="Relevant EvidenceGaps.",
    )
    nature: DisagreementNature = Field(
        ...,
        description="Root cause classification.",
    )

    @model_validator(mode="after")
    def validate_candidate_disagreement(self) -> "CandidateDisagreement":
        """Ensures at least two distinct perspectives are involved."""
        if len(self.perspective_types) < 2:
            raise ValueError("Candidate disagreement must involve at least two perspectives.")
        if len(self.perspective_types) != len(set(self.perspective_types)):
            raise ValueError("Candidate disagreement contains duplicate perspective types.")
        return self


class CandidateBoardSynthesis(BaseModel):
    """Candidate cross-perspective synthesis proposed by language model prior to authoritative ID assignment."""
    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str = Field(
        ...,
        min_length=3,
        description="Executive summary reconciling the board's collective deliberation.",
    )
    areas_of_agreement: List[str] = Field(
        default_factory=list,
        description="Strategic common ground where perspectives converge.",
    )
    disagreement_ids: List[str] = Field(
        default_factory=list,
        description="IDs of authoritative ReasoningDisagreements selected as material to this synthesis.",
    )
    critical_assumption_ids: List[str] = Field(
        default_factory=list,
        description="Cross-perspective foundational assumptions.",
    )
    critical_evidence_gap_ids: List[str] = Field(
        default_factory=list,
        description="High-leverage evidence gaps.",
    )
    evidence_sensitive_points: List[str] = Field(
        default_factory=list,
        description="Points where new empirical data would alter the balance.",
    )
    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="Unresolved strategic questions.",
    )
