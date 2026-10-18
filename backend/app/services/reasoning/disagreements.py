"""AURA Deterministic Cross-Perspective Disagreement Detector.

Detects structured, defensible analytical tensions across authoritative
boardroom perspectives (Phase 4.4).

Guarantees:
- Zero LLM calls, zero search calls, zero external network calls.
- Purely deterministic; no UUIDs, no timestamps, no Python hash() randomization.
- Structural signals only: no NLP, embeddings, keyword matching, or sentiment analysis.
- Direction conflict requires explicit opposing poles: FAVORABLE vs UNFAVORABLE.
  NEUTRAL and MIXED directions never automatically conflict.
- Conservative shared scope: arguments must share authoritative entity, requirement,
  evidence, or assumption references. Shared unknowns/gaps alone do not establish shared scope.
- Strict DisagreementNature precedence:
    1. EVIDENCE_DEPENDENT: shared evidence items or evidence requirements.
    2. ASSUMPTION_DEPENDENT: shared assumptions (without shared evidence/requirements).
    3. UNRESOLVED: shared unknowns/gaps or dual UNRESOLVED bases anchored on shared entity scope.
    4. INTERPRETATION: entity-only directional conflict with no stronger dependency.
- Deterministic IDs: SHA-256 content-derived hash using prefix 'dis_'.
- Deduplication: Invariant under permutation of perspectives or arguments.
- Fail-closed validation on malformed inputs (duplicate perspective or argument IDs).
  Returns empty list safely if fewer than 2 perspectives are provided.
- Absolute exclusion of voting, consensus scoring, tallying, or recommendations.
"""

import hashlib
from typing import Dict, List, Sequence, Set, Tuple

from app.schemas.reasoning import (
    ArgumentDirection,
    DisagreementNature,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningDisagreement,
    ReasoningPerspective,
)
from app.services.reasoning.validator import ReasoningValidationError


# Canonical boardroom perspective ordering for deterministic evaluation
CANONICAL_PERSPECTIVE_ORDER: Dict[PerspectiveType, int] = {
    PerspectiveType.GROWTH: 0,
    PerspectiveType.FINANCE: 1,
    PerspectiveType.CUSTOMER: 2,
    PerspectiveType.RISK: 3,
}


def _canonicalize_argument_pair(
    p1: ReasoningPerspective,
    arg1: ReasoningArgument,
    p2: ReasoningPerspective,
    arg2: ReasoningArgument,
) -> Tuple[ReasoningPerspective, ReasoningArgument, ReasoningPerspective, ReasoningArgument]:
    """Sorts a perspective-argument pair into canonical ordering.

    Ordering key:
    1. Canonical perspective order (growth < finance < customer < risk)
    2. Perspective ID
    3. Argument ID
    """
    key1 = (CANONICAL_PERSPECTIVE_ORDER.get(p1.perspective_type, 99), p1.id, arg1.id)
    key2 = (CANONICAL_PERSPECTIVE_ORDER.get(p2.perspective_type, 99), p2.id, arg2.id)
    if key1 <= key2:
        return p1, arg1, p2, arg2
    return p2, arg2, p1, arg1


def generate_deterministic_disagreement_id(
    perspective_a: ReasoningPerspective,
    argument_a: ReasoningArgument,
    perspective_b: ReasoningPerspective,
    argument_b: ReasoningArgument,
) -> str:
    """Generates a stable, deterministic ID for a disagreement between two arguments.

    The ID is content-derived using SHA-256 over the canonicalized pair of argument IDs:
        dis_{persp_type_a}_{persp_type_b}_{hash_hex[:12]}

    Properties:
    - Length is bounded (always <= 64 characters, typically 28-34 characters).
    - Invariant to input order of (perspective_a, argument_a) vs (perspective_b, argument_b).
    - Stable when unrelated arguments or perspectives are added or removed.
    - Zero dependence on Python process hash seeds (PYTHONHASHSEED) or UUIDs.
    """
    p_a, arg_a, p_b, arg_b = _canonicalize_argument_pair(
        perspective_a, argument_a, perspective_b, argument_b
    )
    raw_key = f"{arg_a.id}:{arg_b.id}"
    hash_hex = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
    return f"dis_{p_a.perspective_type.value}_{p_b.perspective_type.value}_{hash_hex}"


def classify_disagreement_nature(
    arg_a: ReasoningArgument,
    arg_b: ReasoningArgument,
    shared_evidence: Set[str],
    shared_requirements: Set[str],
    shared_assumptions: Set[str],
    shared_unknowns: Set[str],
    shared_gaps: Set[str],
) -> DisagreementNature:
    """Classifies the root-cause nature of a disagreement using strict deterministic precedence.

    Conservative Precedence:
    1. EVIDENCE_DEPENDENT: Conflicting arguments materially depend on shared evidence
       items or shared evidence requirements.
    2. ASSUMPTION_DEPENDENT: Conflict materially depends on shared unverified assumptions
       and is not already classified as evidence-dependent.
    3. UNRESOLVED: Conflict is anchored in unresolved dependencies (shared unknowns/gaps
       or both arguments have UNRESOLVED epistemic basis) while sharing entity scope.
    4. INTERPRETATION: Conflicting arguments share authoritative entity scope, but differ
       purely in strategic assessment without stronger evidence/assumption/unresolved anchors.
    """
    if shared_evidence or shared_requirements:
        return DisagreementNature.EVIDENCE_DEPENDENT
    if shared_assumptions:
        return DisagreementNature.ASSUMPTION_DEPENDENT
    if (
        shared_unknowns
        or shared_gaps
        or (arg_a.basis == ReasoningBasis.UNRESOLVED and arg_b.basis == ReasoningBasis.UNRESOLVED)
    ):
        return DisagreementNature.UNRESOLVED
    return DisagreementNature.INTERPRETATION


def _format_disagreement_topic(
    arg_a: ReasoningArgument,
    arg_b: ReasoningArgument,
    shared_entities: Set[str],
    shared_requirements: Set[str],
    shared_evidence: Set[str],
    shared_assumptions: Set[str],
) -> str:
    """Constructs a deterministic, bounded topic description from trusted structural identifiers."""
    if shared_entities:
        sorted_ents = sorted(shared_entities)
        ent_repr = ", ".join(sorted_ents[:3]) + ("..." if len(sorted_ents) > 3 else "")
        scope_str = f"entity ({ent_repr})"
    elif shared_requirements:
        sorted_reqs = sorted(shared_requirements)
        req_repr = ", ".join(sorted_reqs[:3]) + ("..." if len(sorted_reqs) > 3 else "")
        scope_str = f"requirement ({req_repr})"
    elif shared_evidence:
        sorted_evs = sorted(shared_evidence)
        ev_repr = ", ".join(sorted_evs[:3]) + ("..." if len(sorted_evs) > 3 else "")
        scope_str = f"evidence ({ev_repr})"
    elif shared_assumptions:
        sorted_asms = sorted(shared_assumptions)
        asm_repr = ", ".join(sorted_asms[:3]) + ("..." if len(sorted_asms) > 3 else "")
        scope_str = f"assumption ({asm_repr})"
    else:
        scope_str = "shared scope"

    claim_a_brief = arg_a.claim[:60].strip()
    claim_b_brief = arg_b.claim[:60].strip()
    return f"Tension on {scope_str}: '{claim_a_brief}' vs '{claim_b_brief}'"


def detect_disagreements(
    perspectives: Sequence[ReasoningPerspective],
) -> List[ReasoningDisagreement]:
    """Detects deterministic, structurally defensible disagreements across perspectives.

    Consumes authoritative ReasoningPerspective objects and evaluates cross-perspective
    argument pairs for directional incompatibility under shared structural scope.

    Args:
        perspectives: Sequence of authoritative ReasoningPerspective evaluations.

    Returns:
        Deterministic list of ReasoningDisagreement records.
        Returns an empty list if fewer than 2 perspectives are provided.

    Raises:
        ReasoningValidationError: If duplicate perspective IDs or duplicate argument IDs
            are encountered across perspectives, or if invalid types are passed.
    """
    if isinstance(perspectives, (str, bytes, bytearray, dict)) or not isinstance(perspectives, (list, tuple, Sequence)):
        raise ReasoningValidationError(
            f"Expected Sequence[ReasoningPerspective], got {type(perspectives).__name__}.",
            details={
                "location": "disagreements.detect_disagreements",
                "field": "perspectives",
                "rule": "invalid_sequence_type",
            },
        )

    for idx, p in enumerate(perspectives):
        if not isinstance(p, ReasoningPerspective):
            raise ReasoningValidationError(
                f"Perspective at index {idx} is not an instance of ReasoningPerspective.",
                details={
                    "location": "disagreements.detect_disagreements",
                    "field": f"perspectives[{idx}]",
                    "rule": "invalid_element_type",
                },
            )

    # Fewer than two perspectives cannot produce cross-perspective disagreements
    if len(perspectives) < 2:
        return []

    # Validate perspective ID uniqueness
    persp_ids = [p.id for p in perspectives]
    if len(persp_ids) != len(set(persp_ids)):
        seen_pids: Set[str] = set()
        dup_pids: Set[str] = set()
        for pid in persp_ids:
            if pid in seen_pids:
                dup_pids.add(pid)
            seen_pids.add(pid)
        raise ReasoningValidationError(
            f"Duplicate perspective IDs detected in input: {sorted(dup_pids)}",
            details={
                "location": "disagreements.detect_disagreements",
                "field": "perspectives.id",
                "rule": "duplicate_perspective_id",
            },
        )

    # Validate argument ID uniqueness across perspectives
    all_arg_ids: Set[str] = set()
    for p in perspectives:
        for arg in p.arguments:
            if arg.id in all_arg_ids:
                raise ReasoningValidationError(
                    f"Duplicate argument ID '{arg.id}' detected across perspectives.",
                    details={
                        "location": "disagreements.detect_disagreements",
                        "field": "arguments.id",
                        "rule": "duplicate_argument_id",
                        "invalid_id": str(arg.id)[:50],
                    },
                )
            all_arg_ids.add(arg.id)

    # Canonicalize perspective ordering for deterministic pairwise traversal
    ordered_perspectives = sorted(
        perspectives,
        key=lambda p: (CANONICAL_PERSPECTIVE_ORDER.get(p.perspective_type, 99), p.id),
    )

    disagreements: List[ReasoningDisagreement] = []
    seen_pair_keys: Set[Tuple[str, str]] = set()

    # Pairwise cross-perspective comparison (arguments within same perspective are never paired)
    for i in range(len(ordered_perspectives)):
        p_i = ordered_perspectives[i]
        args_i = sorted(p_i.arguments, key=lambda a: a.id)

        for j in range(i + 1, len(ordered_perspectives)):
            p_j = ordered_perspectives[j]
            args_j = sorted(p_j.arguments, key=lambda a: a.id)

            for arg_a in args_i:
                for arg_b in args_j:
                    pair_key = (
                        min(arg_a.id, arg_b.id),
                        max(arg_a.id, arg_b.id),
                    )
                    if pair_key in seen_pair_keys:
                        continue

                    # Direction conflict: strictly FAVORABLE vs UNFAVORABLE
                    is_directional_conflict = (
                        (arg_a.direction == ArgumentDirection.FAVORABLE and arg_b.direction == ArgumentDirection.UNFAVORABLE)
                        or (arg_a.direction == ArgumentDirection.UNFAVORABLE and arg_b.direction == ArgumentDirection.FAVORABLE)
                    )
                    if not is_directional_conflict:
                        continue

                    # Structural shared scope calculation
                    shared_evidence = set(arg_a.evidence_item_ids) & set(arg_b.evidence_item_ids)
                    shared_requirements = set(arg_a.requirement_ids) & set(arg_b.requirement_ids)
                    shared_assumptions = set(arg_a.assumption_ids) & set(arg_b.assumption_ids)
                    shared_entities = set(arg_a.related_entity_ids) & set(arg_b.related_entity_ids)
                    shared_unknowns = set(arg_a.unknown_ids) & set(arg_b.unknown_ids)
                    shared_gaps = set(arg_a.evidence_gap_ids) & set(arg_b.evidence_gap_ids)

                    has_shared_scope = bool(
                        shared_evidence
                        or shared_requirements
                        or shared_assumptions
                        or shared_entities
                    )
                    if not has_shared_scope:
                        continue

                    seen_pair_keys.add(pair_key)

                    # Classify nature using deterministic precedence
                    nature = classify_disagreement_nature(
                        arg_a=arg_a,
                        arg_b=arg_b,
                        shared_evidence=shared_evidence,
                        shared_requirements=shared_requirements,
                        shared_assumptions=shared_assumptions,
                        shared_unknowns=shared_unknowns,
                        shared_gaps=shared_gaps,
                    )

                    # Canonicalize perspective and argument assignment
                    p_1, a_1, p_2, a_2 = _canonicalize_argument_pair(
                        p_i, arg_a, p_j, arg_b
                    )

                    dis_id = generate_deterministic_disagreement_id(
                        p_1, a_1, p_2, a_2
                    )

                    topic = _format_disagreement_topic(
                        arg_a=a_1,
                        arg_b=a_2,
                        shared_entities=shared_entities,
                        shared_requirements=shared_requirements,
                        shared_evidence=shared_evidence,
                        shared_assumptions=shared_assumptions,
                    )

                    positions = {
                        p_1.id: f"[{a_1.direction.value.upper()}] {a_1.claim}",
                        p_2.id: f"[{a_2.direction.value.upper()}] {a_2.claim}",
                    }

                    ev_ids = sorted(list(set(a_1.evidence_item_ids) | set(a_2.evidence_item_ids)))
                    as_ids = sorted(list(set(a_1.assumption_ids) | set(a_2.assumption_ids)))
                    gap_ids = sorted(list(set(a_1.evidence_gap_ids) | set(a_2.evidence_gap_ids)))

                    disagreement = ReasoningDisagreement(
                        id=dis_id,
                        topic=topic,
                        perspective_ids=[p_1.id, p_2.id],
                        argument_ids=[a_1.id, a_2.id],
                        positions=positions,
                        evidence_item_ids=ev_ids,
                        assumption_ids=as_ids,
                        evidence_gap_ids=gap_ids,
                        nature=nature,
                    )
                    disagreements.append(disagreement)

    # Sort final disagreements deterministically by ID
    disagreements.sort(key=lambda d: d.id)
    return disagreements
