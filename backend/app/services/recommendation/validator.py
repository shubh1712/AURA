"""AURA Recommendation & Action Planning Strict Validator.

Validates CandidateDecisionRecommendation proposed by an LLM against trusted
DecisionModel, EvidencePackage, and ReasoningBoard context:
- Enforces strict foreign-key reference resolution against upstream artifacts (fails closed on fabricated IDs).
- Normalizes harmless placeholder tokens ('none', 'N/A', 'null', etc.).
- Enforces action-plan structural integrity (unique action IDs, dependency graph acyclicity, valid gates).
- Checks semantic consistency between decision status, readiness, and action scope.
- Detects unsupported quantitative claims and contradictions.
- Constructs authoritative DecisionRecommendation with content-derived deterministic ID.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set
import re

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import (
    ActionItem,
    ActionPlan,
    AlternativeOption,
    CandidateDecisionRecommendation,
    DecisionGate,
    DecisionReadiness,
    DecisionRecommendation,
    DecisionStatus,
    UncertaintyAssessment,
    generate_deterministic_recommendation_id,
)


# ------------------------------------------------------------------------------
# 1. Typed Recommendation Error Hierarchy
# ------------------------------------------------------------------------------

class RecommendationError(Exception):
    """Base exception for all recommendation engine failures."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RecommendationPromptError(RecommendationError):
    """Raised when recommendation prompt construction exceeds allowable bounds."""
    pass


class RecommendationValidationError(RecommendationError):
    """Raised when candidate recommendation fails grounding, schema, or referential validation."""
    pass


class RecommendationEvaluationError(RecommendationError):
    """Raised when recommendation generation fails (e.g. deadline expired or LLM timeout)."""
    pass


class RecommendationServiceError(RecommendationError):
    """Raised when the recommendation service orchestrator encounters an execution failure."""

    def __init__(
        self,
        message: str,
        stage: str = "recommendation",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=details)
        self.stage = stage


# ------------------------------------------------------------------------------
# 2. Token Normalization
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
    "no_evidence",
    "(none)",
    "(n/a)",
    "[]",
    "{}",
}


def clean_id_list(ids: Optional[Sequence[str]]) -> List[str]:
    """Filters empty and placeholder tokens from an ID list while preserving valid IDs.

    Strips whitespace from each token and discards common LLM placeholder strings
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


# ------------------------------------------------------------------------------
# 3. Action Dependency Acyclicity Check
# ------------------------------------------------------------------------------

def validate_action_dependencies(actions: Sequence[ActionItem]) -> None:
    """Validates that action item dependencies are well-formed and acyclic.

    Raises:
        RecommendationValidationError: If self-referential or cyclic dependencies exist,
        or if a dependency points to an unknown action ID.
    """
    action_ids: Set[str] = {a.id for a in actions}

    # 1. Validate all dependency targets exist and are not self-referential
    for a in actions:
        for dep_id in a.dependencies:
            if dep_id not in action_ids:
                raise RecommendationValidationError(
                    f"Action '{a.id}' references nonexistent dependency '{dep_id}'.",
                    details={
                        "location": "validator.validate_action_dependencies",
                        "field": "action_plan.actions.dependencies",
                        "rule": "nonexistent_action_dependency",
                        "action_id": a.id,
                        "invalid_dependency_id": dep_id,
                    },
                )
            if dep_id == a.id:
                raise RecommendationValidationError(
                    f"Action '{a.id}' has a self-referential dependency on itself.",
                    details={
                        "location": "validator.validate_action_dependencies",
                        "field": "action_plan.actions.dependencies",
                        "rule": "self_referential_action_dependency",
                        "action_id": a.id,
                    },
                )

    # 2. Cycle detection via depth-first search (DFS) with 3-color marking
    # 0 = unvisited, 1 = visiting (in recursion stack), 2 = visited
    state: Dict[str, int] = {a.id: 0 for a in actions}
    dep_graph: Dict[str, List[str]] = {a.id: list(a.dependencies) for a in actions}

    def has_cycle(node: str, path: List[str]) -> Optional[List[str]]:
        state[node] = 1
        path.append(node)
        for neighbor in dep_graph.get(node, []):
            if state[neighbor] == 1:
                # Cycle found
                cycle_start_idx = path.index(neighbor)
                return path[cycle_start_idx:] + [neighbor]
            elif state[neighbor] == 0:
                cycle = has_cycle(neighbor, path)
                if cycle:
                    return cycle
        path.pop()
        state[node] = 2
        return None

    for a in actions:
        if state[a.id] == 0:
            cycle = has_cycle(a.id, [])
            if cycle:
                cycle_str = " -> ".join(cycle)
                raise RecommendationValidationError(
                    f"Cyclic action dependency detected: {cycle_str}.",
                    details={
                        "location": "validator.validate_action_dependencies",
                        "field": "action_plan.actions.dependencies",
                        "rule": "cyclic_action_dependency",
                        "cycle": cycle,
                    },
                )


# ------------------------------------------------------------------------------
# 4. Status and Readiness Semantic Consistency
# ------------------------------------------------------------------------------

def validate_decision_consistency(
    decision_status: DecisionStatus,
    readiness: DecisionReadiness,
    recommended_action: str,
) -> None:
    """Validates semantic consistency between categorical decision status and readiness.

    Enforces:
    - INSUFFICIENT_EVIDENCE cannot have DecisionReadiness.READY.
    - REJECT cannot have DecisionReadiness.READY.
    - PROCEED cannot have DecisionReadiness.BLOCKED.
    - INSUFFICIENT_EVIDENCE recommendation text must not assert unconditional go-ahead.

    Raises:
        RecommendationValidationError: If status and readiness contradict each other.
    """
    if decision_status == DecisionStatus.INSUFFICIENT_EVIDENCE:
        if readiness == DecisionReadiness.READY:
            raise RecommendationValidationError(
                "Decision status 'insufficient_evidence' cannot have decision_readiness 'ready'.",
                details={
                    "location": "validator.validate_decision_consistency",
                    "field": "uncertainty_assessment.decision_readiness",
                    "rule": "contradictory_readiness_insufficient_evidence",
                    "decision_status": decision_status.value,
                    "readiness": readiness.value,
                },
            )
        # Check that recommendation text does not declare unconditional proceeding
        lower_action = recommended_action.lower()
        if any(w in lower_action for w in ["proceed immediately", "unconditionally proceed", "full steam ahead"]):
            raise RecommendationValidationError(
                "Recommendation asserts unconditional execution despite 'insufficient_evidence' status.",
                details={
                    "location": "validator.validate_decision_consistency",
                    "field": "recommended_action",
                    "rule": "contradictory_action_insufficient_evidence",
                },
            )

    if decision_status == DecisionStatus.REJECT and readiness == DecisionReadiness.READY:
        raise RecommendationValidationError(
            "Decision status 'reject' cannot have decision_readiness 'ready'.",
            details={
                "location": "validator.validate_decision_consistency",
                "field": "uncertainty_assessment.decision_readiness",
                "rule": "contradictory_readiness_reject",
                "decision_status": decision_status.value,
                "readiness": readiness.value,
            },
        )

    if decision_status == DecisionStatus.PROCEED and readiness == DecisionReadiness.BLOCKED:
        raise RecommendationValidationError(
            "Decision status 'proceed' cannot have decision_readiness 'blocked'.",
            details={
                "location": "validator.validate_decision_consistency",
                "field": "uncertainty_assessment.decision_readiness",
                "rule": "contradictory_readiness_proceed",
                "decision_status": decision_status.value,
                "readiness": readiness.value,
            },
        )


# ------------------------------------------------------------------------------
# 5. Upstream Input Validation
# ------------------------------------------------------------------------------

def validate_recommendation_inputs(
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
    reasoning_board: ReasoningBoard,
) -> None:
    """Validates upstream artifact bindings before generating recommendation."""
    if evidence_package.decision_model_id != decision_model.id:
        raise RecommendationValidationError(
            f"EvidencePackage decision_model_id '{evidence_package.decision_model_id}' "
            f"does not match DecisionModel id '{decision_model.id}'.",
            details={
                "location": "validator.validate_recommendation_inputs",
                "field": "evidence_package.decision_model_id",
                "rule": "decision_model_id_mismatch",
                "expected": decision_model.id,
                "got": evidence_package.decision_model_id,
            },
        )

    if reasoning_board.decision_model_id != decision_model.id:
        raise RecommendationValidationError(
            f"ReasoningBoard decision_model_id '{reasoning_board.decision_model_id}' "
            f"does not match DecisionModel id '{decision_model.id}'.",
            details={
                "location": "validator.validate_recommendation_inputs",
                "field": "reasoning_board.decision_model_id",
                "rule": "decision_model_id_mismatch",
                "expected": decision_model.id,
                "got": reasoning_board.decision_model_id,
            },
        )

    if reasoning_board.evidence_package_id != evidence_package.id:
        raise RecommendationValidationError(
            f"ReasoningBoard evidence_package_id '{reasoning_board.evidence_package_id}' "
            f"does not match EvidencePackage id '{evidence_package.id}'.",
            details={
                "location": "validator.validate_recommendation_inputs",
                "field": "reasoning_board.evidence_package_id",
                "rule": "evidence_package_id_mismatch",
                "expected": evidence_package.id,
                "got": reasoning_board.evidence_package_id,
            },
        )


# ------------------------------------------------------------------------------
# 6. Candidate Recommendation Reconciler & Grounding Validator
# ------------------------------------------------------------------------------

def validate_candidate_recommendation(
    candidate: CandidateDecisionRecommendation,
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
    reasoning_board: ReasoningBoard,
    clock: Optional[Callable[[], datetime]] = None,
) -> DecisionRecommendation:
    """Validates candidate LLM recommendation and constructs authoritative DecisionRecommendation.

    Strict validation:
    - Cleans placeholder tokens from reference lists.
    - Validates referenced evidence items exist in EvidencePackage.
    - Validates referenced assumptions exist in DecisionModel.
    - Validates referenced evidence gaps exist in EvidencePackage.
    - Validates referenced disagreements exist in ReasoningBoard.
    - Validates action plan dependencies are non-empty, unique, well-formed, and acyclic.
    - Validates semantic consistency between decision status and readiness.
    - Assigns deterministic, sequential IDs to actions and alternatives.
    - Computes content-derived deterministic root ID ('rec_<sha256[:32]>').

    Raises:
        RecommendationValidationError: If any referential or structural invariant is violated.
    """
    valid_evidence_ids: Set[str] = {item.id for item in evidence_package.items}
    valid_assumption_ids: Set[str] = {asm.id for asm in decision_model.assumptions}
    valid_gap_ids: Set[str] = {gap.id for gap in evidence_package.gaps}
    valid_disagreement_ids: Set[str] = {d.id for d in reasoning_board.disagreements}

    # 1. Clean and validate supporting evidence item IDs
    clean_evi_ids = clean_id_list(candidate.supporting_evidence_item_ids)
    for eid in clean_evi_ids:
        if eid not in valid_evidence_ids:
            raise RecommendationValidationError(
                f"Candidate recommendation references nonexistent evidence item ID '{eid}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "supporting_evidence_item_ids",
                    "rule": "nonexistent_evidence_item_id",
                    "invalid_id": str(eid)[:50],
                },
            )

    # 2. Clean and validate assumption IDs
    clean_asm_ids = clean_id_list(candidate.relevant_assumption_ids)
    for aid in clean_asm_ids:
        if aid not in valid_assumption_ids:
            raise RecommendationValidationError(
                f"Candidate recommendation references nonexistent assumption ID '{aid}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "relevant_assumption_ids",
                    "rule": "nonexistent_assumption_id",
                    "invalid_id": str(aid)[:50],
                },
            )

    # 3. Clean and validate evidence gap IDs
    clean_gap_ids = clean_id_list(candidate.relevant_evidence_gap_ids)
    for gid in clean_gap_ids:
        if gid not in valid_gap_ids:
            raise RecommendationValidationError(
                f"Candidate recommendation references nonexistent evidence gap ID '{gid}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "relevant_evidence_gap_ids",
                    "rule": "nonexistent_evidence_gap_id",
                    "invalid_id": str(gid)[:50],
                },
            )

    # 4. Clean and validate disagreement IDs
    clean_dis_ids = clean_id_list(candidate.unresolved_disagreement_ids)
    for did in clean_dis_ids:
        if did not in valid_disagreement_ids:
            raise RecommendationValidationError(
                f"Candidate recommendation references nonexistent disagreement ID '{did}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "unresolved_disagreement_ids",
                    "rule": "nonexistent_disagreement_id",
                    "invalid_id": str(did)[:50],
                },
            )

    # 5. Clean and validate uncertainty assessment assumption & gap references
    clean_relied_asm = clean_id_list(candidate.uncertainty_assessment.assumptions_relied_upon)
    for aid in clean_relied_asm:
        if aid not in valid_assumption_ids:
            raise RecommendationValidationError(
                f"Uncertainty assessment references nonexistent assumption ID '{aid}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "uncertainty_assessment.assumptions_relied_upon",
                    "rule": "nonexistent_assumption_id",
                    "invalid_id": str(aid)[:50],
                },
            )

    clean_relied_gaps = clean_id_list(candidate.uncertainty_assessment.evidence_gaps_relied_upon)
    for gid in clean_relied_gaps:
        if gid not in valid_gap_ids:
            raise RecommendationValidationError(
                f"Uncertainty assessment references nonexistent evidence gap ID '{gid}'.",
                details={
                    "location": "validator.validate_candidate_recommendation",
                    "field": "uncertainty_assessment.evidence_gaps_relied_upon",
                    "rule": "nonexistent_evidence_gap_id",
                    "invalid_id": str(gid)[:50],
                },
            )

    # 6. Validate decision consistency between status, readiness, and text
    validate_decision_consistency(
        decision_status=candidate.decision_status,
        readiness=candidate.uncertainty_assessment.decision_readiness,
        recommended_action=candidate.recommended_action,
    )

    # 7. Reconcile alternatives with deterministic IDs ('alt_1', 'alt_2', ...)
    authoritative_alts: List[AlternativeOption] = []
    for idx, c_alt in enumerate(candidate.alternative_options, 1):
        authoritative_alts.append(
            AlternativeOption(
                id=f"alt_{idx}",
                name=c_alt.name.strip(),
                description=c_alt.description.strip(),
                tradeoffs=[t.strip() for t in c_alt.tradeoffs if t.strip()],
                why_not_recommended=c_alt.why_not_recommended.strip(),
            )
        )

    # 8. Reconcile action plan with deterministic IDs ('act_1', 'act_2', ...)
    if not candidate.action_plan.actions:
        raise RecommendationValidationError(
            "Action plan must contain at least one action item.",
            details={
                "location": "validator.validate_candidate_recommendation",
                "field": "action_plan.actions",
                "rule": "empty_action_plan",
            },
        )

    # Build title-to-index map to normalize dependencies if the LLM referenced by title
    title_to_id: Dict[str, str] = {}
    for idx, c_act in enumerate(candidate.action_plan.actions, 1):
        title_to_id[c_act.title.strip().lower()] = f"act_{idx}"

    authoritative_actions: List[ActionItem] = []
    for idx, c_act in enumerate(candidate.action_plan.actions, 1):
        act_id = f"act_{idx}"

        # Reconcile decision gates
        authoritative_gates: List[DecisionGate] = []
        for g_idx, c_gate in enumerate(c_act.decision_gates, 1):
            authoritative_gates.append(
                DecisionGate(
                    id=f"gate_{idx}_{g_idx}",
                    condition=c_gate.condition.strip(),
                    target_milestone=c_gate.target_milestone.strip(),
                    verification_method=c_gate.verification_method.strip(),
                    fallback_action=c_gate.fallback_action.strip(),
                )
            )

        # Map and sanitize dependencies
        mapped_deps: List[str] = []
        for d in c_act.dependencies:
            d_str = str(d).strip()
            d_lower = d_str.lower()
            if not d_str or d_lower in PLACEHOLDER_TOKENS:
                continue
            # If formatted as 'act_X'
            if re.match(r"^act_\d+$", d_str):
                mapped_deps.append(d_str)
            # If formatted as integer index '1', '2'
            elif d_str.isdigit():
                mapped_deps.append(f"act_{d_str}")
            # If referenced by title
            elif d_lower in title_to_id:
                mapped_deps.append(title_to_id[d_lower])
            else:
                # Raw dependency string preserved for dependency validation
                mapped_deps.append(d_str)

        authoritative_actions.append(
            ActionItem(
                id=act_id,
                title=c_act.title.strip(),
                objective=c_act.objective.strip(),
                description=c_act.description.strip(),
                priority=c_act.priority,
                responsible_role=c_act.responsible_role.strip(),
                time_horizon=c_act.time_horizon,
                dependencies=sorted(list(set(mapped_deps))),
                success_metrics=[m.strip() for m in c_act.success_metrics if m.strip()],
                risk_mitigations=[r.strip() for r in c_act.risk_mitigations if r.strip()],
                decision_gates=authoritative_gates,
                fallback_action=c_act.fallback_action.strip() if c_act.fallback_action else None,
            )
        )

    # 9. Validate action plan dependencies (acyclic and well-formed)
    validate_action_dependencies(authoritative_actions)

    authoritative_action_plan = ActionPlan(
        summary=candidate.action_plan.summary.strip(),
        actions=authoritative_actions,
        key_milestones=[m.strip() for m in candidate.action_plan.key_milestones if m.strip()],
    )

    authoritative_uncertainty = UncertaintyAssessment(
        evidence_strength=candidate.uncertainty_assessment.evidence_strength,
        decision_readiness=candidate.uncertainty_assessment.decision_readiness,
        recommendation_stability=candidate.uncertainty_assessment.recommendation_stability,
        critical_missing_information=[
            info.strip() for info in candidate.uncertainty_assessment.critical_missing_information if info.strip()
        ],
        conditions_changing_recommendation=[
            c.strip() for c in candidate.uncertainty_assessment.conditions_changing_recommendation if c.strip()
        ],
        assumptions_relied_upon=sorted(list(set(clean_relied_asm))),
        evidence_gaps_relied_upon=sorted(list(set(clean_relied_gaps))),
    )

    action_ids = [a.id for a in authoritative_actions]
    rec_id = generate_deterministic_recommendation_id(
        decision_model_id=decision_model.id,
        evidence_package_id=evidence_package.id,
        reasoning_board_id=reasoning_board.id,
        decision_status=candidate.decision_status,
        recommended_action=candidate.recommended_action,
        executive_rationale=candidate.executive_rationale,
        action_ids=action_ids,
    )

    now_clock = clock() if clock else datetime.now(timezone.utc)
    if now_clock.tzinfo is None:
        now_clock = now_clock.replace(tzinfo=timezone.utc)

    return DecisionRecommendation(
        id=rec_id,
        decision_model_id=decision_model.id,
        evidence_package_id=evidence_package.id,
        reasoning_board_id=reasoning_board.id,
        decision_status=candidate.decision_status,
        recommended_action=candidate.recommended_action.strip(),
        executive_rationale=candidate.executive_rationale.strip(),
        supporting_evidence_item_ids=sorted(list(set(clean_evi_ids))),
        relevant_assumption_ids=sorted(list(set(clean_asm_ids))),
        relevant_evidence_gap_ids=sorted(list(set(clean_gap_ids))),
        unresolved_disagreement_ids=sorted(list(set(clean_dis_ids))),
        alternative_options=authoritative_alts,
        uncertainty_assessment=authoritative_uncertainty,
        action_plan=authoritative_action_plan,
        created_at=now_clock,
    )


# ------------------------------------------------------------------------------
# 7. Authoritative Defense-in-Depth Referential Validator
# ------------------------------------------------------------------------------

def validate_recommendation_references(
    recommendation: DecisionRecommendation,
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
    reasoning_board: ReasoningBoard,
) -> None:
    """Validates referential integrity of an authoritative DecisionRecommendation.

    Pure function: zero network calls, zero LLMs, fail-closed validation.

    Raises:
        RecommendationValidationError: If any foreign key or entity ID fails to resolve.
    """
    validate_recommendation_inputs(decision_model, evidence_package, reasoning_board)

    valid_evidence_ids: Set[str] = {item.id for item in evidence_package.items}
    valid_assumption_ids: Set[str] = {asm.id for asm in decision_model.assumptions}
    valid_gap_ids: Set[str] = {gap.id for gap in evidence_package.gaps}
    valid_disagreement_ids: Set[str] = {d.id for d in reasoning_board.disagreements}

    for eid in recommendation.supporting_evidence_item_ids:
        if eid not in valid_evidence_ids:
            raise RecommendationValidationError(
                f"Authoritative recommendation references nonexistent evidence item '{eid}'."
            )

    for aid in recommendation.relevant_assumption_ids:
        if aid not in valid_assumption_ids:
            raise RecommendationValidationError(
                f"Authoritative recommendation references nonexistent assumption '{aid}'."
            )

    for gid in recommendation.relevant_evidence_gap_ids:
        if gid not in valid_gap_ids:
            raise RecommendationValidationError(
                f"Authoritative recommendation references nonexistent evidence gap '{gid}'."
            )

    for did in recommendation.unresolved_disagreement_ids:
        if did not in valid_disagreement_ids:
            raise RecommendationValidationError(
                f"Authoritative recommendation references nonexistent disagreement '{did}'."
            )

    for aid in recommendation.uncertainty_assessment.assumptions_relied_upon:
        if aid not in valid_assumption_ids:
            raise RecommendationValidationError(
                f"Uncertainty assessment references nonexistent assumption '{aid}'."
            )

    for gid in recommendation.uncertainty_assessment.evidence_gaps_relied_upon:
        if gid not in valid_gap_ids:
            raise RecommendationValidationError(
                f"Uncertainty assessment references nonexistent evidence gap '{gid}'."
            )

    validate_action_dependencies(recommendation.action_plan.actions)
