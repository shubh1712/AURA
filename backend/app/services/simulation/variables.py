"""AURA Deterministic Variable Discovery Service (Day 7 Phase 7A).

Inspects authoritative decision artifacts and discovers valid, structured numerical variables
eligible for what-if simulation.

Enforces:
- Pure deterministic execution with zero side effects.
- Authoritative baseline extraction from structured fields only.
- Strict avoidance of regex-parsing narrative text for numbers.
- Exclusion of scenario probabilities from arbitrary adjustment.
- Distinction between controllable levers and external factors.
- Stable, repeatable variable IDs with exact source lineage.
"""

import math
import re
from typing import List, Optional, Set
from app.schemas.decision_model import (
    Constraint,
    DecisionModel,
    Variable,
    VariableType,
)
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import ScenarioSet
from app.schemas.simulation import (
    SimulationVariable,
    SimulationVariableType,
)

_THRESHOLD_REGEX = re.compile(
    r"(<=|>=|<|>|==|!=)\s*([+-]?[0-9]+(?:\.[0-9]+)?)"
)


def _determine_variable_type(var: Variable) -> SimulationVariableType:
    """Classifies a DecisionModel Variable into a SimulationVariableType."""
    unit_lower = (var.unit or "").strip().lower()

    if (
        var.variable_type == VariableType.CURRENCY
        or unit_lower in ("usd", "$", "eur", "€", "gbp", "£", "cad", "aud", "inr", "jpy", "cny")
        or any(unit_lower.startswith(prefix) for prefix in ("usd", "eur", "gbp", "$", "€", "£"))
    ):
        return SimulationVariableType.CURRENCY
    elif var.variable_type == VariableType.PERCENTAGE or unit_lower in ("%", "pct", "percent", "percentage"):
        return SimulationVariableType.PERCENTAGE
    elif unit_lower in (
        "users", "customers", "nodes", "count", "headcount", "days", "months",
        "scans", "vehicles", "units", "accounts", "tickets", "seats", "patients",
        "procedures", "items", "hours", "weeks", "years", "fte", "servers",
        "records", "transactions",
    ):
        return SimulationVariableType.COUNT
    elif unit_lower in ("ratio", "multiple", "x", "factor"):
        return SimulationVariableType.RATIO
    return SimulationVariableType.NUMERIC


def _determine_bounds(
    val_type: SimulationVariableType,
    baseline: float,
    linked_constraint: Optional[Constraint] = None,
) -> tuple[Optional[float], Optional[float]]:
    """Determines realistic, unit-aware, scale-aware bounds for a simulation variable.

    Guarantees minimum_value <= baseline <= maximum_value for all discovered variables.
    """
    min_val: Optional[float] = None
    max_val: Optional[float] = None

    if val_type == SimulationVariableType.PERCENTAGE:
        if 0.0 <= baseline <= 1.0:
            min_val, max_val = 0.0, 1.0
        elif -1.0 <= baseline < 0.0:
            min_val, max_val = -1.0, 1.0
        elif 0.0 <= baseline <= 100.0:
            min_val, max_val = 0.0, 100.0
        elif -100.0 <= baseline < 0.0:
            min_val, max_val = -100.0, 100.0
        elif 100.0 < baseline <= 1000.0:
            min_val, max_val = 0.0, max(100.0, round(baseline * 2.5, 1))
        else:
            # Baseline exceeds standard percentage scale (e.g. 180,000 scan count).
            # Assign valid non-clamped bounds so Pydantic validation passes,
            # while the variable is flagged as unsupported for simulation.
            min_val = 0.0
            max_val = max(100.0, round(baseline * 2.0, 1))

    elif val_type in (SimulationVariableType.CURRENCY, SimulationVariableType.COUNT, SimulationVariableType.NUMERIC):
        if baseline >= 0.0:
            min_val = 0.0
            scale_floor = 1000.0 if val_type == SimulationVariableType.CURRENCY else 100.0
            max_val = max(scale_floor, round(baseline * 2.5, 2)) if baseline > 0 else scale_floor
        else:
            min_val = round(baseline * 2.5, 2)
            max_val = round(abs(baseline) * 2.5, 2)

    elif val_type == SimulationVariableType.RATIO:
        if baseline >= 0.0:
            min_val = 0.0
            max_val = max(5.0, round(baseline * 2.5, 2))
        else:
            min_val = round(baseline * 2.5, 2)
            max_val = max(5.0, round(abs(baseline) * 2.5, 2))

    # If a linked operational constraint specifies a threshold limit exceeding max_val,
    # expand max_val so the breach condition can be tested via simulation slider
    if linked_constraint and linked_constraint.threshold_expression and max_val is not None:
        match = _THRESHOLD_REGEX.search(linked_constraint.threshold_expression)
        if match:
            try:
                limit = float(match.group(2))
                if limit > max_val:
                    max_val = round(limit * 1.5, 2)
            except (ValueError, TypeError):
                pass

    # Invariant guarantee: minimum_value <= baseline <= maximum_value
    if min_val is not None and baseline < min_val:
        min_val = baseline
    if max_val is not None and baseline > max_val:
        max_val = max(max_val * 2.0, baseline * 2.0)
    if min_val is not None and max_val is not None and min_val > max_val:
        max_val = max(min_val * 2.0, baseline * 2.0)

    return min_val, max_val


def _find_linked_constraint(var: Variable, constraints: List[Constraint]) -> Optional[Constraint]:
    """Finds an operational constraint linked to this variable by name or threshold expression."""
    var_id_norm = var.id.lower()
    var_name_norm = var.name.lower()

    for c in constraints:
        # Check threshold expression reference
        if c.threshold_expression:
            expr_norm = c.threshold_expression.lower()
            if var_id_norm in expr_norm or var_name_norm in expr_norm:
                return c
        # Check name alignment
        if c.name.lower() == var_name_norm or var_name_norm in c.name.lower():
            return c
    return None


def discover_simulation_variables(
    decision_model: DecisionModel,
    scenario_set: Optional[ScenarioSet] = None,
    recommendation: Optional[DecisionRecommendation] = None,
) -> List[SimulationVariable]:
    """Discovers eligible structured numerical simulation variables from authoritative artifacts.

    Inspects DecisionModel.variables and returns only those with verified numerical values.
    Does NOT derive numerical baselines from unverified prose (e.g. $150k mentioned in text).
    Excludes scenario probabilities from variable discovery.

    Args:
        decision_model: Authoritative baseline DecisionModel.
        scenario_set: Optional authoritative ScenarioSet (probabilities strictly excluded).
        recommendation: Optional authoritative DecisionRecommendation.

    Returns:
        List[SimulationVariable]: Deterministically discovered simulation variables in canonical order.
    """
    discovered: List[SimulationVariable] = []
    seen_ids: Set[str] = set()

    for var in decision_model.variables:
        # Avoid duplicate IDs
        if var.id in seen_ids:
            continue

        # 1. Check for authoritative numerical baseline
        baseline_num: Optional[float] = None
        source_field = ""

        # We strictly require isinstance(int, float) and NOT bool
        if isinstance(var.baseline_value, (int, float)) and not isinstance(var.baseline_value, bool):
            baseline_num = float(var.baseline_value)
            source_field = f"variables[{var.id}].baseline_value"
        elif isinstance(var.proposed_value, (int, float)) and not isinstance(var.proposed_value, bool):
            baseline_num = float(var.proposed_value)
            source_field = f"variables[{var.id}].proposed_value"

        # If no structured numerical baseline exists or is non-finite, skip it!
        # Do not parse numbers from descriptions, prompts, or prose narratives.
        if baseline_num is None or not math.isfinite(baseline_num):
            continue

        seen_ids.add(var.id)

        # 2. Determine value type, linked constraint, and bounds
        val_type = _determine_variable_type(var)
        linked_constraint = _find_linked_constraint(var, decision_model.constraints)
        min_val, max_val = _determine_bounds(val_type, baseline_num, linked_constraint)

        # 3. Determine simulation support and transparent diagnostic reason
        is_scale_contradiction = (
            val_type == SimulationVariableType.PERCENTAGE and baseline_num > 1000.0
        )

        if is_scale_contradiction:
            is_supported = False
            support_reason = (
                f"Cannot be safely modeled: baseline value ({baseline_num:g}) exceeds realistic percentage bounds (0-100%) "
                f"for unit '{var.unit or '%'}', indicating an unnormalized scale or unit mismatch between absolute volume "
                f"and percentage rate."
            )
        elif not var.is_controllable:
            is_supported = False
            support_reason = (
                "External environmental variable; not directly controllable as an executive decision lever."
            )
        elif linked_constraint is not None:
            is_supported = True
            support_reason = (
                f"Controllable decision lever linked to operational constraint '{linked_constraint.name}' "
                f"(threshold: {linked_constraint.threshold_expression or 'unspecified'})."
            )
        else:
            is_supported = True
            support_reason = (
                "Controllable decision lever. Direct parameter substitution in DecisionModel is supported; "
                "downstream resilience score impact currently unmapped."
            )

        sim_var = SimulationVariable(
            variable_id=var.id,
            label=var.name,
            description=var.description,
            unit=var.unit,
            value_type=val_type,
            baseline_value=baseline_num,
            minimum_value=min_val,
            maximum_value=max_val,
            source_artifact_id=decision_model.id,
            source_field_path=source_field,
            simulation_supported=is_supported,
            support_reason=support_reason,
        )
        discovered.append(sim_var)

    return discovered

