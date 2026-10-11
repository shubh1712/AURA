"""AURA Deterministic What-if Simulation Engine (Day 7 Phase 7A).

Provides offline, pure deterministic evaluation of what-if scenarios:
- Accepts immutable baseline artifacts (DecisionModel, ScenarioSet, DecisionRecommendation, ResilienceReport).
- Discovers and validates candidate variables against structured baselines.
- Applies documented parameter substitutions and constraint threshold evaluations to deep copies.
- Strictly preserves the original baseline artifacts without mutation.
- Only recalculates resilience when an adjustment genuinely alters authoritative inputs consumed by the resilience engine.
- Explicitly reports unmapped variables without arithmetic fabrication.
- Preserves the three canonical scenario trajectories and probability distributions.
- Generates deterministic SHA-256 simulation IDs with 'sim_' prefix.
"""

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.engines.resilience import evaluate_resilience
from app.schemas.decision_model import (
    Constraint,
    DecisionModel,
    Variable,
)
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.resilience import ResilienceReport
from app.schemas.scenario import (
    FutureScenario,
    ScenarioSet,
    ScenarioType,
)
from app.schemas.simulation import (
    SimulationAdjustment,
    SimulationCalculationStatus,
    SimulationImpact,
    SimulationRequest,
    SimulationResult,
    SimulationVariable,
    compute_baseline_fingerprint,
    generate_deterministic_simulation_id,
)
from app.services.simulation.variables import discover_simulation_variables


# ------------------------------------------------------------------------------
# 1. Transformation Rule Identifiers
# ------------------------------------------------------------------------------

RULE_DIRECT_VARIABLE_SUBSTITUTION = "RULE_DIRECT_VARIABLE_SUBSTITUTION"
RULE_CONSTRAINT_THRESHOLD_EVALUATION = "RULE_CONSTRAINT_THRESHOLD_EVALUATION"


# ------------------------------------------------------------------------------
# 2. Constraint Threshold Evaluator
# ------------------------------------------------------------------------------

_THRESHOLD_REGEX = re.compile(
    r"(<=|>=|<|>|==|!=)\s*([+-]?[0-9]+(?:\.[0-9]+)?)"
)


def _evaluate_threshold_breach(proposed_value: float, expression: Optional[str]) -> Optional[bool]:
    """Deterministically evaluates if a proposed value breaches a constraint threshold expression.

    Returns:
        True: If the proposed value breaches/violates the condition.
        False: If the proposed value satisfies the condition.
        None: If the expression cannot be parsed into a deterministic comparison.
    """
    if not expression:
        return None

    match = _THRESHOLD_REGEX.search(expression)
    if not match:
        return None

    op = match.group(1)
    limit = float(match.group(2))

    if op == "<=":
        # Condition: val <= limit. Breached if val > limit.
        return proposed_value > limit
    elif op == "<":
        # Condition: val < limit. Breached if val >= limit.
        return proposed_value >= limit
    elif op == ">=":
        # Condition: val >= limit. Breached if val < limit.
        return proposed_value < limit
    elif op == ">":
        # Condition: val > limit. Breached if val <= limit.
        return proposed_value <= limit
    elif op == "==":
        return proposed_value != limit
    elif op == "!=":
        return proposed_value == limit

    return None


def _find_linked_constraint(var_id: str, var_name: str, constraints: Sequence[Constraint]) -> Optional[Constraint]:
    """Finds an operational constraint linked to the adjusted variable."""
    var_id_norm = var_id.lower()
    var_name_norm = var_name.lower()

    for c in constraints:
        if c.threshold_expression:
            expr_norm = c.threshold_expression.lower()
            if var_id_norm in expr_norm or var_name_norm in expr_norm:
                return c
        if c.name.lower() == var_name_norm or var_name_norm in c.name.lower():
            return c
    return None


# ------------------------------------------------------------------------------
# 3. Master Deterministic Simulation Function
# ------------------------------------------------------------------------------

def simulate_what_if(
    request: SimulationRequest,
    decision_model: DecisionModel,
    scenario_set: ScenarioSet,
    recommendation: DecisionRecommendation,
    evidence_package: Optional[EvidencePackage] = None,
    reasoning_board: Optional[ReasoningBoard] = None,
    baseline_resilience_report: Optional[ResilienceReport] = None,
    baseline_fingerprint: Optional[str] = None,
) -> SimulationResult:
    """Executes a pure deterministic what-if simulation against authoritative decision artifacts.

    Args:
        request: Validated SimulationRequest containing target artifact IDs and adjustments.
        decision_model: Authoritative baseline DecisionModel (immutable).
        scenario_set: Authoritative baseline ScenarioSet (immutable).
        recommendation: Authoritative baseline DecisionRecommendation (immutable).
        evidence_package: Optional baseline EvidencePackage (immutable).
        reasoning_board: Optional baseline ReasoningBoard (immutable).
        baseline_resilience_report: Optional baseline ResilienceReport for delta calculation.

    Returns:
        SimulationResult: Deterministic simulation output with granular impact records.

    Raises:
        ValueError: If referential integrity fails, an unknown variable is requested,
                    units mismatch, or bounds are violated.
    """
    # 1. Referential Integrity Verification
    if request.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: request.decision_model_id ('{request.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )
    if request.scenario_set_id != scenario_set.id:
        raise ValueError(
            f"Referential integrity mismatch: request.scenario_set_id ('{request.scenario_set_id}') "
            f"does not match ScenarioSet.id ('{scenario_set.id}')."
        )
    if request.recommendation_id != recommendation.id:
        raise ValueError(
            f"Referential integrity mismatch: request.recommendation_id ('{request.recommendation_id}') "
            f"does not match DecisionRecommendation.id ('{recommendation.id}')."
        )
    if scenario_set.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: ScenarioSet decision_model_id ('{scenario_set.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )
    if recommendation.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: DecisionRecommendation decision_model_id ('{recommendation.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )
    if scenario_set.recommendation_id != recommendation.id:
        raise ValueError(
            f"Referential integrity mismatch: ScenarioSet recommendation_id ('{scenario_set.recommendation_id}') "
            f"does not match DecisionRecommendation.id ('{recommendation.id}')."
        )

    # 2. Discover Available Variables and Validate Adjustments
    available_vars = discover_simulation_variables(
        decision_model=decision_model,
        scenario_set=scenario_set,
        recommendation=recommendation,
    )
    var_map: Dict[str, SimulationVariable] = {v.variable_id: v for v in available_vars}

    for adj in request.adjustments:
        if adj.variable_id not in var_map:
            raise ValueError(
                f"Unknown variable_id '{adj.variable_id}'. Only structured numerical variables "
                f"discovered from DecisionModel can be simulated."
            )

        target_var = var_map[adj.variable_id]

        # Unit mismatch validation
        if adj.unit and target_var.unit:
            if adj.unit.strip().lower() != target_var.unit.strip().lower():
                raise ValueError(
                    f"Unit mismatch for variable '{adj.variable_id}': proposed unit '{adj.unit}' "
                    f"does not match baseline unit '{target_var.unit}'."
                )

        # Bounds validation
        if target_var.minimum_value is not None and adj.proposed_value < target_var.minimum_value:
            raise ValueError(
                f"Adjustment for '{adj.variable_id}' ({adj.proposed_value}) violates minimum bound ({target_var.minimum_value})."
            )
        if target_var.maximum_value is not None and adj.proposed_value > target_var.maximum_value:
            raise ValueError(
                f"Adjustment for '{adj.variable_id}' ({adj.proposed_value}) violates maximum bound ({target_var.maximum_value})."
            )

    # 3. Create Deep Copies to Preserve Baseline Immutability
    sim_decision_model = decision_model.model_copy(deep=True)
    sim_scenario_set = scenario_set.model_copy(deep=True)
    sim_recommendation = recommendation.model_copy(deep=True)

    impacts: List[SimulationImpact] = []
    warnings: List[str] = []
    resilience_input_altered = False

    # 4. Apply Documented Transformations
    for adj in request.adjustments:
        target_var = var_map[adj.variable_id]
        orig_val = target_var.baseline_value

        # A. Direct Variable Value Substitution in Cloned DecisionModel
        new_variables: List[Variable] = []
        for v in sim_decision_model.variables:
            if v.id == adj.variable_id:
                new_v = v.model_copy(update={"proposed_value": adj.proposed_value})
                new_variables.append(new_v)
            else:
                new_variables.append(v)
        sim_decision_model = sim_decision_model.model_copy(update={"variables": new_variables})

        affected_fields = [f"decision_model.variables[{adj.variable_id}].proposed_value"]

        # B. Check for Causal Constraint Threshold Linkage
        linked_cnstr = _find_linked_constraint(
            target_var.variable_id, target_var.label, sim_decision_model.constraints
        )

        breach_status = None
        if linked_cnstr is not None:
            breach_status = _evaluate_threshold_breach(adj.proposed_value, linked_cnstr.threshold_expression)

        if linked_cnstr is not None and breach_status is not None:
            rule_id = RULE_CONSTRAINT_THRESHOLD_EVALUATION
            calc_status = SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
            if breach_status is True:
                explanation = (
                    f"Adjustment ({adj.proposed_value} {adj.unit or ''}) breached threshold for constraint "
                    f"'{linked_cnstr.name}' ('{linked_cnstr.threshold_expression}'). "
                    f"Active constraint breach detected. Note: Scenario constraint relevance (relevant_constraint_ids) "
                    f"is preserved unchanged to protect scenario narrative integrity. The resilience engine scoring formula "
                    f"evaluates structural scenario narrative relevance rather than dynamic variable scaling; "
                    f"score impact is therefore explicitly reported as unsupported rather than fabricated."
                )
                warnings.append(
                    f"Constraint breach detected for '{linked_cnstr.name}'. "
                    f"Score delta is unsupported as scenario narrative relevance cannot be dynamically rewritten."
                )
            else:
                explanation = (
                    f"Adjustment ({adj.proposed_value} {adj.unit or ''}) satisfied threshold for constraint "
                    f"'{linked_cnstr.name}' ('{linked_cnstr.threshold_expression}'). "
                    f"Constraint remains satisfied. Score delta is unsupported as direct parameter-to-resilience scaling is not modeled."
                )
        else:
            rule_id = RULE_DIRECT_VARIABLE_SUBSTITUTION
            calc_status = SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
            explanation = (
                f"Variable '{adj.variable_id}' proposed value updated from {orig_val} to {adj.proposed_value} {adj.unit or ''}. "
                f"No verified causal mapping exists connecting this metric to downstream resilience inputs. "
                f"Resilience score impact cannot be calculated without fabricating synthetic formulas."
            )
            warnings.append(
                f"Variable '{adj.variable_id}' has no causal path to resilience scoring inputs. Score delta unavailable."
            )

        impact = SimulationImpact(
            variable_id=adj.variable_id,
            original_value=orig_val,
            adjusted_value=adj.proposed_value,
            transformation_rule_id=rule_id,
            affected_fields=affected_fields,
            calculation_status=calc_status,
            explanation=explanation,
        )
        impacts.append(impact)

    # 5. Baseline Score & Simulation Score Assessment
    baseline_score: Optional[float] = None
    if baseline_resilience_report is not None:
        baseline_score = baseline_resilience_report.overall_score
    else:
        try:
            base_rep = evaluate_resilience(
                decision_model=decision_model,
                scenario_set=scenario_set,
                recommendation=recommendation,
                evidence_package=evidence_package,
                reasoning_board=reasoning_board,
            )
            baseline_score = base_rep.overall_score
        except Exception:
            baseline_score = None

    # Because no input consumed by evaluate_resilience was legitimately mutated without corrupting scenario relevance:
    simulated_score: Optional[float] = None
    score_delta: Optional[float] = None
    overall_status = SimulationCalculationStatus.UNSUPPORTED_NO_CAUSAL_MAPPING
    warnings.append(
        "None of the applied adjustments produced a verified causal change in resilience scoring inputs "
        "(reversibility, scenario probability distribution, rollback gate structure, or empirical evidence gaps). "
        "Resilience score delta cannot be calculated without fabricating synthetic relationships."
    )

    # 6. Compute Canonical Baseline Fingerprint & Simulation ID
    effective_fingerprint = baseline_fingerprint or compute_baseline_fingerprint(
        decision_model=decision_model,
        scenario_set=scenario_set,
        recommendation=recommendation,
        resilience_report=baseline_resilience_report,
    )

    sim_id = generate_deterministic_simulation_id(
        decision_model_id=decision_model.id,
        scenario_set_id=scenario_set.id,
        recommendation_id=recommendation.id,
        adjustments=request.adjustments,
        baseline_fingerprint=effective_fingerprint,
    )

    return SimulationResult(
        id=sim_id,
        decision_model_id=decision_model.id,
        scenario_set_id=scenario_set.id,
        recommendation_id=recommendation.id,
        applied_adjustments=request.adjustments,
        impacts=impacts,
        baseline_fingerprint=effective_fingerprint,
        baseline_resilience_score=baseline_score,
        simulated_resilience_score=simulated_score,
        score_delta=score_delta,
        warnings=warnings,
        status=overall_status,
    )
