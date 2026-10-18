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

from typing import Any, Dict, List, Optional, Sequence, Set
import re

from app.schemas.evidence import (
    DecisionEntityType,
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
# 2. Token Cleaning and Authoritative Grounding Validator & Reconciler
# ------------------------------------------------------------------------------

PLACEHOLDER_TOKENS: Set[str] = {
    "",
    "none",
    "n/a",
    "na",
    "null",
    "nil",
    "no_disagreements",
    "none_detected",
    "no_gaps",
    "no_critical_assumptions",
    "no_assumptions",
    "no_evidence_gaps",
    "no_unknowns",
    "(none)",
    "(n/a)",
    "[]",
    "{}",
}


def clean_id_list(ids: Optional[Sequence[str]]) -> List[str]:
    """Filters empty and placeholder tokens from an ID list while preserving valid IDs.

    Strips whitespace from each ID token and discards common LLM empty-state representations
    ('none', 'N/A', 'null', etc.).
    """
    if not ids:
        return []
    cleaned: List[str] = []
    for raw in ids:
        if not isinstance(raw, str):
            continue
        token = raw.strip()
        norm = token.lower()
        if not norm or norm in PLACEHOLDER_TOKENS:
            continue
        cleaned.append(token)
    return cleaned


def resolve_canonical_id(
    candidate_id: str,
    valid_ids: Set[str],
    conflicting_ids: Optional[Set[str]] = None,
) -> Optional[str]:
    """Deterministically resolves a candidate ID against an authoritative ID set.

    Allows exact matches or unambiguous canonical IDs followed by stray trailing prose/punctuation.
    Strictly rejects:
    - Nonexistent IDs (no matching canonical ID exists).
    - Arbitrary prefixes or partial matches (e.g., 'unk_foo' will NOT match 'unk_foobar').
    - Ambiguous references (e.g. multiple canonical IDs, or matches in conflicting ID namespaces).
    - Fabricated or hallucinated IDs.
    """
    if not isinstance(candidate_id, str):
        return None

    cleaned = candidate_id.strip()
    if not cleaned:
        return None

    # 1. Exact match fast path
    if cleaned in valid_ids:
        return cleaned

    # Strip surrounding single or double quotes if present (e.g. "'unk_123'" -> "unk_123")
    unquoted = cleaned.strip("'\"")
    if unquoted in valid_ids:
        return unquoted

    # 2. Extract leading identifier token delimited by whitespace or non-identifier characters.
    # Canonical IDs in AURA consist of alphanumeric characters and underscores/hyphens.
    match = re.match(r"^['\"]?([a-zA-Z0-9_-]+)['\"]?(.*)$", cleaned)
    if not match:
        return None

    leading_token = match.group(1)
    trailing_prose = match.group(2)

    # The leading token MUST exactly match a known canonical ID in valid_ids.
    # This strictly prevents prefix or partial guessing (e.g. 'unk_foo' cannot match 'unk_foobar').
    if leading_token not in valid_ids:
        return None

    # If there is trailing prose, ensure delimiter is whitespace or punctuation (not alphanumeric)
    if trailing_prose:
        first_char = trailing_prose.lstrip("'\"")[:1]
        if first_char and first_char.isalnum():
            # If the character immediately following is alphanumeric, this wasn't an isolated token
            return None

        # Inspect trailing tokens to ensure no other canonical or conflicting IDs appear (rejects ambiguity).
        trailing_tokens = set(re.findall(r"[a-zA-Z0-9_-]+", trailing_prose))
        if any(t in valid_ids for t in trailing_tokens):
            return None
        if conflicting_ids and any(t in conflicting_ids for t in trailing_tokens):
            return None

    return leading_token


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
            f"expected perspective lens '{expected_type.value}'.",
            details={
                "location": "validator.perspective_type",
                "field": "candidate.perspective_type",
                "rule": "perspective_type_mismatch",
                "expected": expected_type.value,
                "got": candidate.perspective_type.value,
            },
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
    clean_top_asms = clean_id_list(candidate.critical_assumption_ids)
    clean_top_gaps = clean_id_list(candidate.evidence_gap_ids)

    resolved_top_asms: List[str] = []
    for aid in clean_top_asms:
        if aid in valid_assumption_ids:
            if aid not in resolved_top_asms:
                resolved_top_asms.append(aid)
        else:
            resolved = resolve_canonical_id(aid, valid_assumption_ids)
            if resolved:
                if resolved not in resolved_top_asms:
                    resolved_top_asms.append(resolved)
            else:
                raise ReasoningValidationError(
                    f"Perspective '{expected_type.value}' references nonexistent critical assumption_id '{aid}'.",
                    details={
                        "location": "validator.top_level_references",
                        "field": "candidate.critical_assumption_ids",
                        "rule": "nonexistent_critical_assumption_id",
                        "invalid_id": str(aid)[:50],
                    },
                )
    clean_top_asms = resolved_top_asms

    resolved_top_gaps: List[str] = []
    for gid in clean_top_gaps:
        if gid in valid_gap_ids:
            if gid not in resolved_top_gaps:
                resolved_top_gaps.append(gid)
        else:
            resolved = resolve_canonical_id(gid, valid_gap_ids)
            if resolved:
                if resolved not in resolved_top_gaps:
                    resolved_top_gaps.append(resolved)
            else:
                raise ReasoningValidationError(
                    f"Perspective '{expected_type.value}' references nonexistent evidence_gap_id '{gid}'.",
                    details={
                        "location": "validator.top_level_references",
                        "field": "candidate.evidence_gap_ids",
                        "rule": "nonexistent_evidence_gap_id",
                        "invalid_id": str(gid)[:50],
                    },
                )
    clean_top_gaps = resolved_top_gaps

    # 4. Validate Each Candidate Argument
    validated_arguments: List[ReasoningArgument] = []

    for idx, arg in enumerate(candidate.arguments):
        arg_label = f"Argument {idx + 1}"

        clean_eids = clean_id_list(arg.evidence_item_ids)
        clean_rids = clean_id_list(arg.requirement_ids)
        clean_aids = clean_id_list(arg.assumption_ids)
        clean_uids = clean_id_list(arg.unknown_ids)
        clean_gids = clean_id_list(arg.evidence_gap_ids)
        clean_reids = clean_id_list(arg.related_entity_ids)

        # 4a. Reference ID Resolution (Reject Hallucinated IDs)
        resolved_eids: List[str] = []
        for eid in clean_eids:
            if eid in valid_evidence_item_ids:
                if eid not in resolved_eids:
                    resolved_eids.append(eid)
            else:
                resolved = resolve_canonical_id(eid, valid_evidence_item_ids)
                if resolved:
                    if resolved not in resolved_eids:
                        resolved_eids.append(resolved)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent evidence_item_id '{eid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].evidence_item_ids",
                            "rule": "nonexistent_evidence_item_id",
                            "invalid_id": str(eid)[:50],
                        },
                    )
        clean_eids = resolved_eids

        resolved_rids: List[str] = []
        for rid in clean_rids:
            if rid in valid_requirement_ids:
                if rid not in resolved_rids:
                    resolved_rids.append(rid)
            else:
                resolved = resolve_canonical_id(rid, valid_requirement_ids)
                if resolved:
                    if resolved not in resolved_rids:
                        resolved_rids.append(resolved)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent requirement_id '{rid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].requirement_ids",
                            "rule": "nonexistent_requirement_id",
                            "invalid_id": str(rid)[:50],
                        },
                    )
        clean_rids = resolved_rids

        resolved_aids: List[str] = []
        for aid in clean_aids:
            if aid in valid_assumption_ids:
                if aid not in resolved_aids:
                    resolved_aids.append(aid)
            else:
                resolved = resolve_canonical_id(aid, valid_assumption_ids)
                if resolved:
                    if resolved not in resolved_aids:
                        resolved_aids.append(resolved)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent assumption_id '{aid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].assumption_ids",
                            "rule": "nonexistent_assumption_id",
                            "invalid_id": str(aid)[:50],
                        },
                    )
        clean_aids = resolved_aids

        resolved_uids: List[str] = []
        for uid in clean_uids:
            if uid in valid_unknown_ids:
                if uid not in resolved_uids:
                    resolved_uids.append(uid)
            elif uid in requirements_by_id:
                req = requirements_by_id[uid]
                # Canonical mapping is ONLY permitted when an exact, unambiguous mapping exists:
                # the requirement must specifically target an UNKNOWN entity, and that target ID
                # must exist in valid_unknown_ids. Arbitrary requirement IDs targeting other entity
                # types (assumptions, tradeoffs, variables) remain strictly rejected.
                if req.target_entity_type == DecisionEntityType.UNKNOWN and req.target_entity_id in valid_unknown_ids:
                    canonical_uid = req.target_entity_id
                    if canonical_uid not in resolved_uids:
                        resolved_uids.append(canonical_uid)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent unknown_id '{uid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].unknown_ids",
                            "rule": "nonexistent_unknown_id",
                            "invalid_id": str(uid)[:50],
                        },
                    )
            else:
                # Check for canonical unknown ID with stray trailing prose
                resolved_unk = resolve_canonical_id(
                    uid,
                    valid_unknown_ids,
                    conflicting_ids=set(requirements_by_id.keys()),
                )
                if resolved_unk:
                    if resolved_unk not in resolved_uids:
                        resolved_uids.append(resolved_unk)
                else:
                    # Check for requirement ID with stray trailing prose targeting an Unknown
                    resolved_req = resolve_canonical_id(
                        uid,
                        set(requirements_by_id.keys()),
                        conflicting_ids=valid_unknown_ids,
                    )
                    if resolved_req:
                        req = requirements_by_id[resolved_req]
                        if req.target_entity_type == DecisionEntityType.UNKNOWN and req.target_entity_id in valid_unknown_ids:
                            canonical_uid = req.target_entity_id
                            if canonical_uid not in resolved_uids:
                                resolved_uids.append(canonical_uid)
                        else:
                            raise ReasoningValidationError(
                                f"{arg_label} in '{expected_type.value}' references nonexistent unknown_id '{uid}'.",
                                details={
                                    "location": "validator.argument_references",
                                    "field": f"candidate.arguments[{idx}].unknown_ids",
                                    "rule": "nonexistent_unknown_id",
                                    "invalid_id": str(uid)[:50],
                                },
                            )
                    else:
                        raise ReasoningValidationError(
                            f"{arg_label} in '{expected_type.value}' references nonexistent unknown_id '{uid}'.",
                            details={
                                "location": "validator.argument_references",
                                "field": f"candidate.arguments[{idx}].unknown_ids",
                                "rule": "nonexistent_unknown_id",
                                "invalid_id": str(uid)[:50],
                            },
                        )
        clean_uids = resolved_uids

        resolved_gids: List[str] = []
        for gid in clean_gids:
            if gid in valid_gap_ids:
                if gid not in resolved_gids:
                    resolved_gids.append(gid)
            else:
                resolved = resolve_canonical_id(gid, valid_gap_ids)
                if resolved:
                    if resolved not in resolved_gids:
                        resolved_gids.append(resolved)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent evidence_gap_id '{gid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].evidence_gap_ids",
                            "rule": "nonexistent_evidence_gap_id",
                            "invalid_id": str(gid)[:50],
                        },
                    )
        clean_gids = resolved_gids

        resolved_reids: List[str] = []
        for reid in clean_reids:
            if reid in allowed_decision_entity_ids:
                if reid not in resolved_reids:
                    resolved_reids.append(reid)
            else:
                resolved = resolve_canonical_id(reid, allowed_decision_entity_ids)
                if resolved:
                    if resolved not in resolved_reids:
                        resolved_reids.append(resolved)
                else:
                    raise ReasoningValidationError(
                        f"{arg_label} in '{expected_type.value}' references nonexistent related_entity_id '{reid}'.",
                        details={
                            "location": "validator.argument_references",
                            "field": f"candidate.arguments[{idx}].related_entity_ids",
                            "rule": "nonexistent_related_entity_id",
                            "invalid_id": str(reid)[:50],
                        },
                    )
        clean_reids = resolved_reids

        # 4b. Epistemic Basis Verification
        if arg.basis == ReasoningBasis.EVIDENCE:
            if not clean_eids:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'evidence' but references no evidence_item_ids.",
                    details={
                        "location": "validator.epistemic_basis",
                        "field": f"candidate.arguments[{idx}].evidence_item_ids",
                        "rule": "evidence_basis_missing_evidence",
                    },
                )

        elif arg.basis == ReasoningBasis.ASSUMPTION:
            if not clean_aids:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'assumption' but references no assumption_ids.",
                    details={
                        "location": "validator.epistemic_basis",
                        "field": f"candidate.arguments[{idx}].assumption_ids",
                        "rule": "assumption_basis_missing_assumptions",
                    },
                )

        elif arg.basis == ReasoningBasis.UNRESOLVED:
            has_unresolved = bool(clean_uids or clean_gids or clean_rids)
            if not has_unresolved:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'unresolved' but references no unresolved dependency "
                    f"(unknown_ids, evidence_gap_ids, or requirement_ids).",
                    details={
                        "location": "validator.epistemic_basis",
                        "field": f"candidate.arguments[{idx}]",
                        "rule": "unresolved_basis_missing_dependencies",
                    },
                )

        elif arg.basis == ReasoningBasis.MIXED:
            cat_count = sum([
                bool(clean_eids),
                bool(clean_aids),
                bool(clean_uids or clean_gids or clean_rids),
            ])
            if cat_count < 2:
                raise ReasoningValidationError(
                    f"{arg_label} has basis 'mixed' but does not reference at least two distinct "
                    f"epistemic categories among (evidence, assumptions, unresolved dependencies).",
                    details={
                        "location": "validator.epistemic_basis",
                        "field": f"candidate.arguments[{idx}]",
                        "rule": "mixed_basis_insufficient_categories",
                    },
                )

        # 4c. Requirement Lineage Verification
        # If an argument explicitly references requirement_ids AND evidence_item_ids,
        # verify that the cited evidence items legitimately belong to the cited requirements.
        if clean_rids and clean_eids:
            for eid in clean_eids:
                parent_reqs = item_to_requirements.get(eid, set())
                # If this evidence item was retrieved under specific requirements,
                # at least one of its parent requirements must intersect with the cited requirement_ids.
                if parent_reqs and not (parent_reqs & set(clean_rids)):
                    raise ReasoningValidationError(
                        f"{arg_label} asserts false requirement lineage: evidence item '{eid}' is bound "
                        f"to requirements {sorted(parent_reqs)}, but argument cites disjoint requirement_ids {sorted(clean_rids)}.",
                        details={
                            "location": "validator.requirement_lineage",
                            "field": f"candidate.arguments[{idx}].requirement_ids",
                            "rule": "false_requirement_lineage",
                            "evidence_item_id": eid,
                            "parent_requirements": sorted(parent_reqs),
                            "cited_requirements": sorted(clean_rids),
                        },
                    )

        # 4d. Private / Internal Data & Pending Requirement Guard
        # If an argument cites an INTERNAL_DATA, DETERMINISTIC_CALCULATION, or USER_CLARIFICATION
        # requirement that remains PENDING or has no empirical findings, it cannot claim basis 'evidence'.
        if arg.basis == ReasoningBasis.EVIDENCE:
            for rid in clean_rids:
                req = requirements_by_id.get(rid)
                if req and req.status in (RequirementStatus.PENDING, RequirementStatus.UNSUPPORTED):
                    # Check if there is any empirical evidence attached to this pending requirement
                    req_bound_items = {
                        cl.evidence_item_id
                        for cl in req.claim_links
                    }
                    if not req_bound_items or not (set(clean_eids) & req_bound_items):
                        raise ReasoningValidationError(
                            f"{arg_label} cannot assert basis 'evidence' using {req.kind.value} requirement '{rid}' "
                            f"which remains {req.status.value} with no factual findings.",
                            details={
                                "location": "validator.pending_requirement_guard",
                                "field": f"candidate.arguments[{idx}].requirement_ids",
                                "rule": "pending_requirement_claimed_as_evidence",
                                "requirement_id": rid,
                            },
                        )

        # 4e. Contested & Challenging Stance Preservation
        # If all cited evidence items carry stance CHALLENGES, an argument cannot claim direction FAVORABLE
        # unless opposing supporting evidence is also cited.
        if clean_eids and arg.direction == ArgumentDirection.FAVORABLE:
            all_stances: Set[EvidenceStance] = set()
            for eid in clean_eids:
                all_stances.update(item_stances.get(eid, set()))
            if all_stances and all_stances == {EvidenceStance.CHALLENGES}:
                raise ReasoningValidationError(
                    f"{arg_label} asserts direction 'favorable' but only cites challenging evidence items: "
                    f"{clean_eids}. Challenging evidence cannot be structurally misrepresented as favorable.",
                    details={
                        "location": "validator.stance_preservation",
                        "field": f"candidate.arguments[{idx}].direction",
                        "rule": "challenging_evidence_claimed_as_favorable",
                    },
                )

        # 4f. Deterministic Authoritative ID Generation (Python-controlled)
        authoritative_arg_id = f"arg_{expected_type.value}_{idx + 1:02d}"

        reasoning_arg = ReasoningArgument(
            id=authoritative_arg_id,
            claim=arg.claim,
            direction=arg.direction,
            basis=arg.basis,
            reasoning=arg.reasoning,
            evidence_item_ids=list(clean_eids),
            requirement_ids=list(clean_rids),
            assumption_ids=list(clean_aids),
            unknown_ids=list(clean_uids),
            evidence_gap_ids=list(clean_gids),
            related_entity_ids=list(clean_reids),
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
        critical_assumption_ids=list(clean_top_asms),
        evidence_gap_ids=list(clean_top_gaps),
        unresolved_questions=list(candidate.unresolved_questions),
        limitations=list(candidate.limitations),
    )
