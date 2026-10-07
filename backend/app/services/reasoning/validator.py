"""AURA Authoritative Grounding & Epistemic Validator.

Validates CandidatePerspectiveAnalysis proposed by an LLM against trusted
DecisionModel and EvidencePackage context:
- Enforces strict foreign-key reference resolution (rejects hallucinated IDs).
- Validates epistemic basis requirements (EVIDENCE, ASSUMPTION, UNRESOLVED, MIXED).
- Enforces requirement lineage integrity (prevents false cross-requirement claims).
- Protects private/internal-data boundaries (pending metrics cannot become evidence).
- Preserves challenging and contested evidence structures.
- Generates deterministic, Python-controlled authoritative IDs.
- Zero network calls, zero LLMs, fail-closed validation.
"""

from typing import Any, Dict, List, Optional, Set
import re

from app.schemas.evidence import (
    EvidenceKind,
    EvidenceStance,
    RequirementStatus,
)
from app.schemas.reasoning import (
    ArgumentDirection,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningPerspective,
)
from app.services.reasoning.context_builder import PerspectiveContext


# ------------------------------------------------------------------------------
# 1. Typed Reasoning Error Hierarchy
# ------------------------------------------------------------------------------

class ReasoningError(Exception):
    """Base exception for all reasoning service failures."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ReasoningPromptError(ReasoningError):
    """Raised when prompt construction fails (e.g. structural context overflow)."""
    pass


class ReasoningValidationError(ReasoningError):
    """Raised when candidate LLM analysis fails grounding, lineage, or epistemic validation."""
    pass


class ReasoningEvaluationError(ReasoningError):
    """Raised when perspective evaluation fails (e.g. LLM timeout or upstream error)."""
    pass


class ReasoningOrchestrationError(ReasoningError):
    """Raised when perspective orchestration fails (e.g. worker timeout or execution failure)."""
    pass


class ReasoningServiceError(ReasoningError):
    """Raised when high-level reasoning service orchestration fails."""

    def __init__(self, message: str, stage: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details)
        self.stage = stage


# ------------------------------------------------------------------------------
# 2. Authoritative Grounding Validator & Reconciler
# ------------------------------------------------------------------------------

def validate_and_reconcile_candidate_perspective(
    candidate: CandidatePerspectiveAnalysis,
    context: PerspectiveContext,
) -> ReasoningPerspective:
    """Validates candidate perspective output against authoritative context.

    Enforces epistemic grounding, reference resolution, and requirement lineage.
    Assigns deterministic authoritative Python IDs upon successful validation.

    Args:
        candidate: The raw candidate output from LLMClient.generate_structured.
        context: The authoritative PerspectiveContext with trusted metadata.

    Returns:
        ReasoningPerspective: Strongly typed, validated authoritative perspective.

    Raises:
        ReasoningValidationError: If any candidate reference fails to resolve,
            lineage is violated, or epistemic rules are breached.
    """
    expected_type = context.perspective.perspective_type

    # 1. Perspective Type Integrity
    if candidate.perspective_type != expected_type:
        raise ReasoningValidationError(
            f"Candidate perspective_type '{candidate.perspective_type.value}' does not match "
            f"expected perspective lens '{expected_type.value}'."
        )

    # 2. Assemble Authoritative Allowed ID Sets
    dec_ctx = context.decision_context
    evi_ctx = context.evidence_context

    valid_evidence_item_ids: Set[str] = {item.id for item in evi_ctx.items}
    valid_requirement_ids: Set[str] = {req.id for req in evi_ctx.requirements}
    valid_gap_ids: Set[str] = {gap.id for gap in evi_ctx.gaps}
    valid_assumption_ids: Set[str] = {asm.id for asm in dec_ctx.assumptions}
    valid_unknown_ids: Set[str] = {unk.id for unk in dec_ctx.unknowns}

    allowed_decision_entity_ids: Set[str] = {
        dec_ctx.decision_id,
        *(obj.id for obj in dec_ctx.objectives),
        *(var.id for var in dec_ctx.variables),
        *(cnstr.id for cnstr in dec_ctx.constraints),
        *(stk.id for stk in dec_ctx.stakeholders),
        *(trd.id for trd in dec_ctx.tradeoffs),
        *(asm.id for asm in dec_ctx.assumptions),
        *(unk.id for unk in dec_ctx.unknowns),
    }

    # Map requirements by ID for status and kind lookup
    requirements_by_id = {req.id: req for req in evi_ctx.requirements}

    # Map evidence item IDs to their parent requirement IDs via authoritative ClaimEvidenceLinks
    item_to_requirements: Dict[str, Set[str]] = {}
    item_stances: Dict[str, Set[EvidenceStance]] = {}
    for cl in evi_ctx.claim_links:
        if cl.requirement_id:
            item_to_requirements.setdefault(cl.evidence_item_id, set()).add(cl.requirement_id)
        item_stances.setdefault(cl.evidence_item_id, set()).add(cl.stance)

    # 3. Validate Top-Level Perspective References
    for aid in candidate.critical_assumption_ids:
        if aid not in valid_assumption_ids:
            raise ReasoningValidationError(
                f"Perspective '{expected_type.value}' references nonexistent critical assumption_id '{aid}'."
            )

    for gid in candidate.evidence_gap_ids:
        if gid not in valid_gap_ids:
            raise ReasoningValidationError(
                f"Perspective '{expected_type.value}' references nonexistent evidence_gap_id '{gid}'."
            )

    # 4. Validate Each Candidate Argument
    validated_arguments: List[ReasoningArgument] = []

    for idx, arg in enumerate(candidate.arguments):
        arg_label = f"Argument {idx + 1}"

        # 4a. Reference ID Resolution (Reject Hallucinated IDs)
        for eid in arg.evidence_item_ids:
            if eid not in valid_evidence_item_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent evidence_item_id '{eid}'."
                )

        for rid in arg.requirement_ids:
            if rid not in valid_requirement_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent requirement_id '{rid}'."
                )

        for aid in arg.assumption_ids:
            if aid not in valid_assumption_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent assumption_id '{aid}'."
                )

        for uid in arg.unknown_ids:
            if uid not in valid_unknown_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent unknown_id '{uid}'."
                )

        for gid in arg.evidence_gap_ids:
            if gid not in valid_gap_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent evidence_gap_id '{gid}'."
                )

        for reid in arg.related_entity_ids:
            if reid not in allowed_decision_entity_ids:
                raise ReasoningValidationError(
                    f"{arg_label} in '{expected_type.value}' references nonexistent related_entity_id '{reid}'."
                )

        # 4b. Epistemic Basis Verification
        if arg.basis == ReasoningBasis.EVIDENCE:
            if not arg.evidence_item_ids:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'evidence' but references no evidence_item_ids."
                )

        elif arg.basis == ReasoningBasis.ASSUMPTION:
            if not arg.assumption_ids:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'assumption' but references no assumption_ids."
                )

        elif arg.basis == ReasoningBasis.UNRESOLVED:
            has_unresolved = bool(arg.unknown_ids or arg.evidence_gap_ids or arg.requirement_ids)
            if not has_unresolved:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'unresolved' but references no unresolved dependency "
                    f"(unknown_ids, evidence_gap_ids, or requirement_ids)."
                )

        elif arg.basis == ReasoningBasis.MIXED:
            cat_count = sum([
                bool(arg.evidence_item_ids),
                bool(arg.assumption_ids),
                bool(arg.unknown_ids or arg.evidence_gap_ids or arg.requirement_ids),
            ])
            if cat_count < 2:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'mixed' but does not reference at least two distinct "
                    f"epistemic categories among (evidence, assumptions, unresolved dependencies)."
                )

        # 4c. Requirement Lineage Verification
        # If an argument explicitly references requirement_ids AND evidence_item_ids,
        # verify that the cited evidence items legitimately belong to the cited requirements.
        if arg.requirement_ids and arg.evidence_item_ids:
            for eid in arg.evidence_item_ids:
                parent_reqs = item_to_requirements.get(eid, set())
                # If this evidence item was retrieved under specific requirements,
                # at least one of its parent requirements must intersect with the cited requirement_ids.
                if parent_reqs and not (parent_reqs & set(arg.requirement_ids)):
                    raise ReasoningValidationError(
                        f"{arg_label} asserts false requirement lineage: evidence item '{eid}' is bound "
                        f"to requirements {sorted(parent_reqs)}, but argument cites disjoint requirement_ids {sorted(arg.requirement_ids)}."
                    )

        # 4d. Private / Internal Data & Pending Requirement Guard
        # If an argument cites an INTERNAL_DATA, DETERMINISTIC_CALCULATION, or USER_CLARIFICATION
        # requirement that remains PENDING or has no empirical findings, it cannot claim basis 'evidence'.
        if arg.basis == ReasoningBasis.EVIDENCE:
            for rid in arg.requirement_ids:
                req = requirements_by_id.get(rid)
                if req and req.status in (RequirementStatus.PENDING, RequirementStatus.UNSUPPORTED):
                    # Check if there is any empirical evidence attached to this pending requirement
                    req_bound_items = {
                        cl.evidence_item_id
                        for cl in req.claim_links
                    }
                    if not req_bound_items or not (set(arg.evidence_item_ids) & req_bound_items):
                        raise ReasoningValidationError(
                            f"{arg_label} cannot assert basis 'evidence' using {req.kind.value} requirement '{rid}' "
                            f"which remains {req.status.value} with no factual findings."
                        )

        # 4e. Contested & Challenging Stance Preservation
        # If all cited evidence items carry stance CHALLENGES, an argument cannot claim direction FAVORABLE
        # unless opposing supporting evidence is also cited.
        if arg.evidence_item_ids and arg.direction == ArgumentDirection.FAVORABLE:
            all_stances: Set[EvidenceStance] = set()
            for eid in arg.evidence_item_ids:
                all_stances.update(item_stances.get(eid, set()))
            if all_stances and all_stances == {EvidenceStance.CHALLENGES}:
                raise ReasoningValidationError(
                    f"{arg_label} asserts direction 'favorable' but only cites challenging evidence items: "
                    f"{arg.evidence_item_ids}. Challenging evidence cannot be structurally misrepresented as favorable."
                )

        # 4f. Deterministic Authoritative ID Generation (Python-controlled)
        authoritative_arg_id = f"arg_{expected_type.value}_{idx + 1:02d}"

        reasoning_arg = ReasoningArgument(
            id=authoritative_arg_id,
            claim=arg.claim,
            direction=arg.direction,
            basis=arg.basis,
            reasoning=arg.reasoning,
            evidence_item_ids=list(arg.evidence_item_ids),
            requirement_ids=list(arg.requirement_ids),
            assumption_ids=list(arg.assumption_ids),
            unknown_ids=list(arg.unknown_ids),
            evidence_gap_ids=list(arg.evidence_gap_ids),
            related_entity_ids=list(arg.related_entity_ids),
            caveat=arg.caveat,
        )
        validated_arguments.append(reasoning_arg)

    # 5. Construct Authoritative Perspective
    authoritative_perspective_id = f"persp_{expected_type.value}"

    return ReasoningPerspective(
        id=authoritative_perspective_id,
        perspective_type=expected_type,
        summary=candidate.summary,
        arguments=validated_arguments,
        critical_assumption_ids=list(candidate.critical_assumption_ids),
        evidence_gap_ids=list(candidate.evidence_gap_ids),
        unresolved_questions=list(candidate.unresolved_questions),
        limitations=list(candidate.limitations),
    )
