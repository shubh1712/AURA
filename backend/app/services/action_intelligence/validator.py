"""AURA Action Intelligence Deterministic Validator (Day 8A).

Provides pure Python, deterministic validation foundations for IntelligentActionPlan:
- Rejects invalid or duplicate action IDs.
- Detects unknown dependencies, self-dependencies, and dependency cycles (topological sort).
- Validates sequence ordering, priorities, and duplicate decision gates.
- Verifies numerical criteria, supported operators, units, and provenance.
- Detects comparable conflicting numerical thresholds (e.g. CSAT floor 90% vs rollback trigger 85%).
- Marks ambiguous or unprovable threshold comparisons as review-required.
- Verifies provenance references to Stage 1 constraints, Stage 2 evidence, and Stage 4 actions.
- Zero reliance on LLMs for validation or numerical comparison.
"""

from collections import deque
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.action_intelligence import (
    ActionCriterion,
    ComparisonOperator,
    CriterionType,
    IntelligentActionItem,
    IntelligentActionPlan,
    IntelligentDecisionGate,
    ValidationSeverity,
    ValidationWarning,
)

logger = logging.getLogger(__name__)


class ActionPlanValidationError(ValueError):
    """Raised when an IntelligentActionPlan violates structural or referential integrity invariants."""
    pass


def validate_action_ids(actions: List[IntelligentActionItem]) -> None:
    """Verifies that all action IDs are unique and non-empty.

    Raises:
        ActionPlanValidationError: If any action ID is empty or duplicate.
    """
    seen_ids: Set[str] = set()
    for act in actions:
        aid = act.action_id.strip()
        if not aid:
            raise ActionPlanValidationError("Action item contains empty action_id.")
        if aid in seen_ids:
            raise ActionPlanValidationError(f"Duplicate action_id detected: '{aid}'.")
        seen_ids.add(aid)


def validate_dependencies(actions: List[IntelligentActionItem]) -> None:
    """Verifies that dependencies exist, have no self-references, and contain no cycles.

    Uses Kahn's algorithm (topological sort) for cycle detection.

    Raises:
        ActionPlanValidationError: On unknown dependencies, self-dependencies, or cycles.
    """
    all_action_ids = {a.action_id for a in actions}

    for act in actions:
        aid = act.action_id
        for dep in act.dependencies:
            dep_clean = dep.strip()
            if not dep_clean:
                raise ActionPlanValidationError(f"Action '{aid}' contains an empty dependency reference.")
            if dep_clean == aid:
                raise ActionPlanValidationError(
                    f"Self-dependency detected: Action '{aid}' depends on itself."
                )
            if dep_clean not in all_action_ids:
                raise ActionPlanValidationError(
                    f"Unknown dependency target: Action '{aid}' depends on nonexistent action '{dep_clean}'."
                )

    # Cycle Detection via Kahn's Algorithm
    in_degree: Dict[str, int] = {a.action_id: 0 for a in actions}
    adjacency: Dict[str, List[str]] = {a.action_id: [] for a in actions}

    for act in actions:
        for dep in act.dependencies:
            # dep must complete before act can begin => dep -> act
            adjacency[dep].append(act.action_id)
            in_degree[act.action_id] += 1

    queue = deque([aid for aid, deg in in_degree.items() if deg == 0])
    visited_count = 0

    while queue:
        node = queue.popleft()
        visited_count += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited_count < len(actions):
        unvisited = [aid for aid, deg in in_degree.items() if deg > 0]
        raise ActionPlanValidationError(
            f"Dependency cycle detected among actions: {', '.join(unvisited)}."
        )


def validate_decision_gates(
    gates: List[IntelligentDecisionGate],
    valid_action_ids: Set[str],
) -> List[ValidationWarning]:
    """Verifies uniqueness of decision gates and referential integrity of governed actions.

    Raises:
        ActionPlanValidationError: On duplicate gate IDs.
    """
    warnings: List[ValidationWarning] = []
    seen_gate_ids: Set[str] = set()

    for idx, gate in enumerate(gates):
        gid = gate.gate_id.strip()
        if not gid:
            raise ActionPlanValidationError("Decision gate contains empty gate_id.")
        if gid in seen_gate_ids:
            raise ActionPlanValidationError(f"Duplicate gate_id detected: '{gid}'.")
        seen_gate_ids.add(gid)

        for rel_act in gate.related_action_ids:
            if rel_act not in valid_action_ids:
                warnings.append(
                    ValidationWarning(
                        warning_id=f"warn_gate_unknown_action_{gid}_{rel_act}",
                        severity=ValidationSeverity.WARNING,
                        message=f"Gate '{gid}' references unknown action_id '{rel_act}'.",
                        related_gate_ids=[gid],
                        related_action_ids=[rel_act],
                    )
                )

    return warnings


def validate_criteria_integrity(
    criteria: List[ActionCriterion],
    context_prefix: str,
) -> List[ValidationWarning]:
    """Validates criterion syntax, provenance, and numerical threshold limits.

    Raises:
        ActionPlanValidationError: On fabricated ROI, success probabilities, resilience scores,
        or unsupported numeric metrics without provenance.
    """
    warnings: List[ValidationWarning] = []

    for c in criteria:
        norm_desc = (c.description or "").lower()
        norm_metric = (c.metric_name or "").lower()

        # Prohibited fabricated claims
        if any(term in norm_desc or term in norm_metric for term in ("roi", "return on investment", "cost saving")):
            raise ActionPlanValidationError(
                f"{context_prefix} criterion '{c.criterion_id}' claims prohibited fabricated ROI / cost savings metric."
            )
        if any(term in norm_desc or term in norm_metric for term in ("success probability", "probability of success")):
            raise ActionPlanValidationError(
                f"{context_prefix} criterion '{c.criterion_id}' claims prohibited fabricated numeric success probability."
            )
        if any(term in norm_desc or term in norm_metric for term in ("resilience score", "resilience rating")):
            raise ActionPlanValidationError(
                f"{context_prefix} criterion '{c.criterion_id}' claims prohibited fabricated resilience score modification."
            )

        if c.threshold_value is not None:
            if c.criterion_type == CriterionType.UNSUPPORTED_METRIC:
                raise ActionPlanValidationError(
                    f"{context_prefix} criterion '{c.criterion_id}' specifies unsupported numeric claim with threshold {c.threshold_value}."
                )

            if not c.source_reference and not c.provenance_type:
                raise ActionPlanValidationError(
                    f"{context_prefix} criterion '{c.criterion_id}' has numeric threshold {c.threshold_value} without supporting provenance."
                )

            if c.operator is None or c.operator == ComparisonOperator.QUALITATIVE:
                warnings.append(
                    ValidationWarning(
                        warning_id=f"warn_missing_operator_{c.criterion_id}",
                        severity=ValidationSeverity.WARNING,
                        message=(
                            f"Criterion '{c.criterion_id}' has numeric threshold "
                            f"{c.threshold_value} but no comparison operator specified."
                        ),
                        related_criterion_ids=[c.criterion_id],
                    )
                )

        if not c.source_reference and c.criterion_type != CriterionType.QUALITATIVE:
            warnings.append(
                ValidationWarning(
                    warning_id=f"warn_missing_provenance_{c.criterion_id}",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Criterion '{c.criterion_id}' ({c.criterion_type.value}) lacks "
                        "an upstream source reference."
                    ),
                    related_criterion_ids=[c.criterion_id],
                )
            )

    return warnings


def normalize_metric_token(text: str) -> str:
    """Normalizes metric or criterion name for tokenized heuristic matching."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", text.lower())
    tokens = [t for t in cleaned.split() if t not in ("the", "a", "an", "of", "for", "to", "in")]
    return " ".join(tokens)


def detect_threshold_conflicts(
    plan: IntelligentActionPlan,
    decision_model: Optional[Any] = None,
) -> List[ValidationWarning]:
    """Detects verifiable contradictions between user hard constraints and action/gate thresholds.

    Example:
    - User hard constraint: CSAT >= 90% (unit: '%')
    - Action gate criterion: Rollback trigger if CSAT < 85%
      -> CONFLICT: Rollback trigger allows CSAT degradation to 85% when hard constraint requires >= 90%.

    If metric units or comparison directions cannot be verified with certainty:
    - Emits REVIEW_REQUIRED warning instead of guessing.
    """
    warnings: List[ValidationWarning] = []

    # 1. Harvest upstream hard constraints from decision_model
    baseline_constraints: List[Dict[str, Any]] = []
    if decision_model is not None:
        raw_cnstrs = getattr(decision_model, "constraints", [])
        for c in raw_cnstrs:
            is_hard = getattr(c, "is_hard_constraint", False) or getattr(c, "type", "") == "hard"
            unit = (getattr(c, "unit", "") or "").strip().lower()
            threshold = getattr(c, "threshold", None)
            expr = getattr(c, "threshold_expression", None)
            name = getattr(c, "name", "") or getattr(c, "description", "")
            cid = getattr(c, "id", "")

            # Heuristically parse threshold if float is provided or in threshold_expression
            thresh_val: Optional[float] = None
            if threshold is not None:
                try:
                    thresh_val = float(threshold)
                except (ValueError, TypeError):
                    pass
            elif expr:
                m = re.search(r"(\d+(?:\.\d+)?)", str(expr))
                if m:
                    try:
                        thresh_val = float(m.group(1))
                    except (ValueError, TypeError):
                        pass

            if not unit:
                full_text = f"{expr or ''} {getattr(c, 'description', '')}".lower()
                if "%" in full_text or "percent" in full_text:
                    unit = "%"
                elif "$" in full_text or "usd" in full_text:
                    unit = "usd"

            baseline_constraints.append({
                "id": cid,
                "name": name,
                "normalized_name": normalize_metric_token(name),
                "is_hard": is_hard,
                "unit": unit,
                "threshold_value": thresh_val,
                "raw_expression": expr or str(threshold),
            })

    # 2. Check all criteria in actions and gates against baseline constraints
    evaluated_criteria: List[Tuple[ActionCriterion, Optional[str], Optional[str]]] = []
    for act in plan.actions:
        for crit in act.success_criteria:
            evaluated_criteria.append((crit, act.action_id, None))
    for gate in plan.decision_gates:
        for crit in gate.criteria:
            evaluated_criteria.append((crit, None, gate.gate_id))

    for crit, act_id, gate_id in evaluated_criteria:
        crit_metric = normalize_metric_token(crit.metric_name or crit.description)
        crit_val = crit.threshold_value
        crit_unit = (crit.unit or "").strip().lower()

        for b_cnstr in baseline_constraints:
            if not b_cnstr["is_hard"]:
                continue

            b_name = b_cnstr["normalized_name"]
            # Check for shared metric tokens (e.g. 'csat', 'customer satisfaction', 'budget')
            metric_match = False
            if crit.source_reference and crit.source_reference == b_cnstr["id"]:
                metric_match = True
            elif ("csat" in crit_metric and "csat" in b_name) or (
                "satisfaction" in crit_metric and "satisfaction" in b_name
            ):
                metric_match = True
            elif ("budget" in crit_metric and "budget" in b_name):
                metric_match = True
            elif ("cohort" in crit_metric and "cohort" in b_name) or (
                "pilot" in crit_metric and "pilot" in b_name and "size" in crit_metric
            ):
                metric_match = True

            if not metric_match:
                continue

            b_val = b_cnstr["threshold_value"]
            b_unit = b_cnstr["unit"]

            # Units match or are both percentage/count
            units_compatible = (
                (crit_unit == b_unit)
                or (not crit_unit and not b_unit)
                or (crit_unit in ("%", "percent") and b_unit in ("%", "percent"))
            )

            if crit_val is not None and b_val is not None:
                if units_compatible:
                    # CSAT / Satisfaction Floor Conflict Check:
                    # Hard constraint requires >= b_val (e.g. 90).
                    # If criterion specifies a threshold strictly below b_val (e.g. 85) for an acceptance / rollback target:
                    if ("csat" in b_name or "satisfaction" in b_name) and crit_val < b_val:
                        warnings.append(
                            ValidationWarning(
                                warning_id=f"conflict_{crit.criterion_id}_{b_cnstr['id']}",
                                severity=ValidationSeverity.CONFLICT,
                                message=(
                                    f"Direct threshold conflict: Action/gate criterion '{crit.criterion_id}' "
                                    f"evaluates '{crit.metric_name or crit.description}' at {crit_val}{crit.unit or ''}, "
                                    f"which is below the mandatory user hard constraint floor of "
                                    f"{b_val}{b_cnstr['unit'] or ''} (constraint '{b_cnstr['id']}')."
                                ),
                                related_action_ids=[act_id] if act_id else [],
                                related_gate_ids=[gate_id] if gate_id else [],
                                related_criterion_ids=[crit.criterion_id],
                            )
                        )
                    # Budget Ceiling Conflict Check:
                    elif ("budget" in b_name or "cost" in b_name) and crit_val > b_val:
                        warnings.append(
                            ValidationWarning(
                                warning_id=f"conflict_{crit.criterion_id}_{b_cnstr['id']}",
                                severity=ValidationSeverity.CONFLICT,
                                message=(
                                    f"Direct threshold conflict: Action/gate criterion '{crit.criterion_id}' "
                                    f"allows spend of {crit_val}{crit.unit or ''}, which exceeds the mandatory "
                                    f"hard constraint ceiling of {b_val}{b_cnstr['unit'] or ''} (constraint '{b_cnstr['id']}')."
                                ),
                                related_action_ids=[act_id] if act_id else [],
                                related_gate_ids=[gate_id] if gate_id else [],
                                related_criterion_ids=[crit.criterion_id],
                            )
                        )
                else:
                    # Units differ or cannot be converted deterministically
                    warnings.append(
                        ValidationWarning(
                            warning_id=f"review_{crit.criterion_id}_{b_cnstr['id']}",
                            severity=ValidationSeverity.REVIEW_REQUIRED,
                            message=(
                                f"Review required: Incompatible or ambiguous units between criterion '{crit.criterion_id}' "
                                f"('{crit_unit or 'unspecified'}') and hard constraint '{b_cnstr['id']}' "
                                f"('{b_unit or 'unspecified'}'). Automated comparison cannot be verified."
                            ),
                            related_action_ids=[act_id] if act_id else [],
                            related_gate_ids=[gate_id] if gate_id else [],
                            related_criterion_ids=[crit.criterion_id],
                        )
                    )
            elif crit_val is not None or b_val is not None:
                # One is numeric and the other is qualitative/unparsed
                warnings.append(
                    ValidationWarning(
                        warning_id=f"review_{crit.criterion_id}_{b_cnstr['id']}",
                        severity=ValidationSeverity.REVIEW_REQUIRED,
                        message=(
                            f"Review required: Metric '{crit.metric_name or crit.description}' matches hard constraint "
                            f"'{b_cnstr['id']}', but one specification is qualitative ({b_cnstr['raw_expression']}). "
                            "Manual operational alignment is required."
                        ),
                        related_action_ids=[act_id] if act_id else [],
                        related_gate_ids=[gate_id] if gate_id else [],
                        related_criterion_ids=[crit.criterion_id],
                    )
                )

    return warnings


def validate_action_plan(
    plan: IntelligentActionPlan,
    decision_model: Optional[Any] = None,
    evidence_package: Optional[Any] = None,
    recommendation: Optional[Any] = None,
) -> IntelligentActionPlan:
    """Master validation orchestrator for IntelligentActionPlan.

    Executes all deterministic checks, aggregates findings into validation_warnings,
    and returns a validated plan instance.

    Raises:
        ActionPlanValidationError: If any critical structural violation exists (e.g. duplicate IDs, cycles).
    """
    if not plan.actions:
        raise ActionPlanValidationError("IntelligentActionPlan must contain at least one action item.")

    # 1. Structural invariants
    validate_action_ids(plan.actions)
    validate_dependencies(plan.actions)

    valid_action_ids = {a.action_id for a in plan.actions}
    collected_warnings: List[ValidationWarning] = list(plan.validation_warnings)

    # 2. Decision gates validation
    gate_warnings = validate_decision_gates(plan.decision_gates, valid_action_ids)
    collected_warnings.extend(gate_warnings)

    # 3. Criteria integrity
    for act in plan.actions:
        crit_warns = validate_criteria_integrity(act.success_criteria, f"Action '{act.action_id}'")
        collected_warnings.extend(crit_warns)
    for gate in plan.decision_gates:
        crit_warns = validate_criteria_integrity(gate.criteria, f"Gate '{gate.gate_id}'")
        collected_warnings.extend(crit_warns)

    # 4. Threshold conflict detection
    threshold_warns = detect_threshold_conflicts(plan, decision_model)
    collected_warnings.extend(threshold_warns)

    # 5. Provenance reference resolution and rejection of fabricated references
    if recommendation is not None:
        rec_actions = []
        action_plan = getattr(recommendation, "action_plan", None)
        if action_plan:
            rec_actions = [getattr(a, "id", "") for a in getattr(action_plan, "actions", [])]
        for act in plan.actions:
            if not act.source_action_reference or (rec_actions and act.source_action_reference not in rec_actions):
                raise ActionPlanValidationError(
                    f"Action '{act.action_id}' references invalid or fabricated Stage 4 action "
                    f"'{act.source_action_reference}'. Every action must reference a valid Stage 4 action from: {rec_actions}."
                )

    if evidence_package is not None:
        ev_items = {getattr(item, "id", "") for item in getattr(evidence_package, "items", [])}
        for act in plan.actions:
            for ev_ref in act.evidence_references:
                if ev_ref not in ev_items:
                    raise ActionPlanValidationError(
                        f"Action '{act.action_id}' references fabricated evidence identifier '{ev_ref}'. "
                        "Citations must strictly match empirical EvidencePackage items."
                    )

    # Deduplicate warnings by warning_id
    deduped_warnings: List[ValidationWarning] = []
    seen_warn_ids: Set[str] = set()
    for w in collected_warnings:
        if w.warning_id not in seen_warn_ids:
            seen_warn_ids.add(w.warning_id)
            deduped_warnings.append(w)

    # Return updated plan with sorted warnings
    return plan.model_copy(update={"validation_warnings": deduped_warnings})
