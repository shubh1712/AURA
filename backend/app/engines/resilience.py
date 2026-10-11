"""AURA Deterministic Resilience Engine (Day 6 Phase 6A).

Evaluates the mathematical and structural robustness of an analyzed decision across
four transparent, versioned scoring pillars (0 to 25 points each):
1. Constraint Boundary Tolerance (25 pts)
2. Pessimistic Scenario Survivability (25 pts)
3. Contingency and Fallback Coverage (25 pts)
4. Information Robustness (25 pts)

Composite resilience score: 0 to 100.
Heuristic rating bands:
- 80–100: High
- 60–<80: Moderate
- 40–<60: Fragile
- Below 40: Vulnerable

Pure deterministic Python implementation:
- No LLM arithmetic.
- Strict bounded scoring.
- Comprehensive referential integrity verification.
- Safe incomplete-input handling without denominator tricks.
- Stable deterministic SHA-256 identity.
"""

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decision_model import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
    ReversibilityLevel,
)
from app.schemas.evidence import EvidenceGap, EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import (
    DecisionReadiness,
    DecisionRecommendation,
    EvidenceStrength,
    RecommendationStability,
)
from app.schemas.resilience import (
    ResiliencePillar,
    ResilienceRating,
    ResilienceReport,
    ResilienceSubScore,
    determine_resilience_rating,
    generate_deterministic_resilience_id,
)
from app.schemas.scenario import FutureScenario, ScenarioSet, ScenarioType


# ------------------------------------------------------------------------------
# 1. Configurable Scoring Weights & Thresholds
# ------------------------------------------------------------------------------

class ResilienceConfig(BaseModel):
    """Configurable scoring weights, caps, and classification thresholds for resilience."""
    model_config = ConfigDict(frozen=True)

    calculation_version: str = "1.0.0"

    # Rating thresholds
    threshold_moderate_to_high: float = 80.0
    threshold_fragile_to_moderate: float = 60.0
    threshold_vulnerable_to_fragile: float = 40.0

    # Stress-test pass criteria
    stress_test_min_overall_score: float = 60.0
    stress_test_min_pessimistic_subscore: float = 12.5

    # Pillar A: Constraint Boundary Tolerance (25 pts)
    max_pillar_a_points: float = 25.0
    points_reversibility_reversible: float = 10.0
    points_reversibility_partially: float = 6.0
    points_reversibility_irreversible: float = 2.0
    max_hard_constraint_points: float = 15.0

    # Pillar B: Pessimistic Scenario Survivability (25 pts)
    max_pillar_b_points: float = 25.0

    # Pillar C: Contingency & Fallback Coverage (25 pts)
    max_pillar_c_points: float = 25.0
    max_decision_gate_points: float = 12.0
    max_action_mitigation_points: float = 8.0
    max_alternative_options_points: float = 5.0

    # Pillar D: Information Robustness (25 pts)
    max_pillar_d_points: float = 25.0
    max_stability_points: float = 5.0
    max_evidence_strength_points: float = 5.0
    max_gap_points: float = 6.0
    max_assumption_points: float = 5.0
    max_readiness_points: float = 4.0


DEFAULT_RESILIENCE_CONFIG = ResilienceConfig()


# ------------------------------------------------------------------------------
# 2. Text Normalization & Keyword Matching Helpers
# ------------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "during", "after",
    "will", "shall", "must", "than", "then", "into", "over", "under", "more",
    "less", "some", "such", "when", "what", "where", "which", "about", "above",
}


def _extract_keywords(text: str) -> Set[str]:
    """Extracts lowercase alphabetic keywords of length >= 4, excluding common stopwords."""
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _is_risk_addressed(risk_text: str, candidate_mitigation_texts: Sequence[str]) -> bool:
    """Checks whether an adverse risk is addressed by any candidate mitigation text."""
    risk_keywords = _extract_keywords(risk_text)
    if not risk_keywords:
        return False

    for mit_text in candidate_mitigation_texts:
        mit_keywords = _extract_keywords(mit_text)
        # Match if at least 1 significant domain keyword overlaps
        if risk_keywords.intersection(mit_keywords):
            return True
    return False


# ------------------------------------------------------------------------------
# 3. Individual Pillar Evaluators
# ------------------------------------------------------------------------------

def _evaluate_constraint_boundary_tolerance(
    decision_model: DecisionModel,
    pessimistic_scenario: FutureScenario,
    config: ResilienceConfig,
) -> Tuple[ResilienceSubScore, List[str]]:
    """Evaluates Pillar A: Constraint Boundary Tolerance (0 to 25 points)."""
    vulnerabilities: List[str] = []
    critical_vulns: List[str] = []

    constraints = decision_model.constraints
    reversibility = decision_model.complexity.reversibility

    # 1. Reversibility points
    if reversibility == ReversibilityLevel.REVERSIBLE:
        rev_score = config.points_reversibility_reversible
        rev_desc = "Reversible (two-way door) allowing low-friction rollback."
    elif reversibility == ReversibilityLevel.PARTIALLY_REVERSIBLE:
        rev_score = config.points_reversibility_partially
        rev_desc = "Partially reversible with moderate unwind friction."
    else:
        rev_score = config.points_reversibility_irreversible
        rev_desc = "Irreversible (one-way door) with prohibitive unwind costs."
        vulnerabilities.append("Decision is irreversible (one-way door); constraint breaches cannot be easily unwound.")
        critical_vulns.append("Irreversible decision commitment.")

    # 2. Constraint pressure points
    pressured_ids = set(pessimistic_scenario.relevant_constraint_ids)

    if not constraints:
        # Incomplete input policy: Missing constraints must not be awarded 15/15 points.
        # Conservative baseline of 7.5 pts applied with an explicit uncertainty vulnerability.
        cnstr_score = 7.5
        vulnerabilities.append("No operational constraints declared in DecisionModel; boundary tolerance unverified.")
        cnstr_desc = "No operational constraints declared in DecisionModel (neutral unverified baseline 7.5/15 pts)."
    else:
        hard_constraints = [c for c in constraints if c.is_hard_constraint]
        soft_constraints = [c for c in constraints if not c.is_hard_constraint]

        if hard_constraints:
            pressured_hard = sorted([c for c in hard_constraints if c.id in pressured_ids], key=lambda x: x.id)
            hard_ratio = len(pressured_hard) / len(hard_constraints)
            hard_pts = config.max_hard_constraint_points * (1.0 - hard_ratio)

            if pressured_hard:
                names = ", ".join(f"'{c.name}'" for c in pressured_hard)
                vulnerabilities.append(f"Hard constraint(s) pressured under pessimistic scenario: {names}.")
                critical_vulns.append(f"Hard constraint breach risk: {names}.")
        else:
            # Only soft constraints exist
            hard_pts = 13.0  # slight deduction for absence of firm boundaries

        # Soft constraints penalty (up to 2.0 pts)
        if soft_constraints:
            pressured_soft = sorted([c for c in soft_constraints if c.id in pressured_ids], key=lambda x: x.id)
            soft_penalty = (len(pressured_soft) / len(soft_constraints)) * 2.0
            if pressured_soft:
                vulnerabilities.append(f"{len(pressured_soft)} soft preference constraint(s) pressured under adverse conditions.")
        else:
            soft_penalty = 0.0

        cnstr_score = max(0.0, hard_pts - soft_penalty)
        cnstr_desc = (
            f"Constraint envelope score {cnstr_score:.1f}/15.0 "
            f"({len(constraints)} constraints, {len(pressured_ids)} pressured in pessimistic trajectory)."
        )

    raw_score = cnstr_score + rev_score
    final_score = round(max(0.0, min(config.max_pillar_a_points, raw_score)), 2)

    rationale = f"{cnstr_desc} Reversibility score {rev_score:.1f}/10.0: {rev_desc}"

    subscore = ResilienceSubScore(
        category=ResiliencePillar.CONSTRAINT_BOUNDARY_TOLERANCE.value,
        score=final_score,
        max_score=config.max_pillar_a_points,
        rationale=rationale,
        vulnerabilities_detected=vulnerabilities,
    )
    return subscore, critical_vulns


def _evaluate_pessimistic_survivability(
    pessimistic_scenario: FutureScenario,
    recommendation: DecisionRecommendation,
    config: ResilienceConfig,
) -> Tuple[ResilienceSubScore, List[str]]:
    """Evaluates Pillar B: Pessimistic Scenario Survivability (0 to 25 points)."""
    vulnerabilities: List[str] = []
    critical_vulns: List[str] = []

    p_pess = pessimistic_scenario.probability
    risks = pessimistic_scenario.risks

    # Collect available mitigations and fallbacks across the recommendation
    mitigations: List[str] = []
    for action in recommendation.action_plan.actions:
        mitigations.extend(action.risk_mitigations)
        if action.fallback_action:
            mitigations.append(action.fallback_action)
        for gate in action.decision_gates:
            if gate.fallback_action:
                mitigations.append(gate.fallback_action)

    if not risks:
        # Policy for missing risks:
        # Do not grant free 25/25 pts. Use neutral unmitigated ratio of 0.50.
        unmitigated_ratio = 0.50
        vulnerabilities.append("Pessimistic scenario lacks explicit risk enumeration (neutral uncertainty ratio applied).")
        risk_desc = "No explicit risks documented in pessimistic scenario; applied neutral 50% risk exposure baseline."
    else:
        unmitigated_risks: List[str] = []
        for risk in sorted(risks):
            if not _is_risk_addressed(risk, mitigations):
                unmitigated_risks.append(risk)
                vulnerabilities.append(f"Unmitigated adverse risk under pessimistic scenario: '{risk}'.")

        unmitigated_ratio = len(unmitigated_risks) / len(risks)
        risk_desc = (
            f"{len(risks) - len(unmitigated_risks)}/{len(risks)} adverse risks mitigated "
            f"({unmitigated_ratio:.0%} unmitigated risk ratio)."
        )

        if unmitigated_risks and p_pess >= 0.25:
            critical_vulns.append(
                f"High-probability adverse scenario ({p_pess:.0%}) contains {len(unmitigated_risks)} unmitigated risks."
            )

    # Core mathematical formula: survivability = 25 * (1 - p_pess * unmitigated_ratio)
    raw_score = config.max_pillar_b_points * (1.0 - (p_pess * unmitigated_ratio))
    final_score = round(max(0.0, min(config.max_pillar_b_points, raw_score)), 2)

    rationale = (
        f"Modeled pessimistic probability is {p_pess:.0%}. {risk_desc} "
        f"Calculated survivability: {final_score:.1f}/{config.max_pillar_b_points:.1f} pts."
    )

    subscore = ResilienceSubScore(
        category=ResiliencePillar.PESSIMISTIC_SCENARIO_SURVIVABILITY.value,
        score=final_score,
        max_score=config.max_pillar_b_points,
        rationale=rationale,
        vulnerabilities_detected=vulnerabilities,
    )
    return subscore, critical_vulns


def _evaluate_contingency_and_fallback_coverage(
    recommendation: DecisionRecommendation,
    config: ResilienceConfig,
) -> Tuple[ResilienceSubScore, List[str]]:
    """Evaluates Pillar C: Contingency & Fallback Coverage (0 to 25 points)."""
    vulnerabilities: List[str] = []
    critical_vulns: List[str] = []

    actions = recommendation.action_plan.actions
    all_gates = [g for a in actions for g in a.decision_gates]

    # 1. Decision gates quality (up to 12.0 pts)
    if not all_gates:
        gate_score = 0.0
        vulnerabilities.append("No decision gates defined to halt execution if conditions deteriorate.")
        critical_vulns.append("Zero decision gates established prior to execution.")
        gate_desc = "No decision gates defined (0.0/12.0 pts)."
    else:
        complete_gate_points = 0.0
        for gate in all_gates:
            g_score = 0.0
            if len(gate.condition.strip()) >= 5:
                g_score += 1.0
            if len(gate.verification_method.strip()) >= 5:
                g_score += 1.5
            if len(gate.fallback_action.strip()) >= 5:
                g_score += 1.5
            complete_gate_points += g_score

        gate_score = min(config.max_decision_gate_points, complete_gate_points)
        gate_desc = f"{len(all_gates)} decision gate(s) evaluated ({gate_score:.1f}/{config.max_decision_gate_points:.1f} pts)."

    # 2. Action item mitigations (up to 8.0 pts)
    if not actions:
        action_score = 0.0
        vulnerabilities.append("No recommended actions defined in ActionPlan.")
        action_desc = "No actions defined (0.0/8.0 pts)."
    else:
        mitigated_count = sum(
            1 for a in actions if (a.risk_mitigations or a.fallback_action is not None)
        )
        action_ratio = mitigated_count / len(actions)
        action_score = config.max_action_mitigation_points * action_ratio

        if action_ratio < 0.5:
            unmitigated_count = len(actions) - mitigated_count
            vulnerabilities.append(
                f"Majority of recommended actions ({unmitigated_count}/{len(actions)}) lack explicit risk mitigations or fallbacks."
            )
        action_desc = f"{mitigated_count}/{len(actions)} actions include proactive mitigations ({action_score:.1f}/{config.max_action_mitigation_points:.1f} pts)."

    # 3. Alternative strategic options (up to 5.0 pts)
    alternatives = recommendation.alternative_options
    if len(alternatives) >= 2:
        alt_score = config.max_alternative_options_points
        alt_desc = f"{len(alternatives)} alternative options evaluated with explicit trade-offs (5.0/5.0 pts)."
    elif len(alternatives) == 1:
        alt_score = 3.0
        alt_desc = "1 alternative option evaluated (3.0/5.0 pts)."
    else:
        alt_score = 0.0
        vulnerabilities.append("No alternative courses of action evaluated to serve as strategic pivots.")
        alt_desc = "No alternative courses of action evaluated (0.0/5.0 pts)."

    raw_score = gate_score + action_score + alt_score
    final_score = round(max(0.0, min(config.max_pillar_c_points, raw_score)), 2)

    rationale = f"{gate_desc} {action_desc} {alt_desc}"

    subscore = ResilienceSubScore(
        category=ResiliencePillar.CONTINGENCY_AND_FALLBACK_COVERAGE.value,
        score=final_score,
        max_score=config.max_pillar_c_points,
        rationale=rationale,
        vulnerabilities_detected=vulnerabilities,
    )
    return subscore, critical_vulns


def _evaluate_information_robustness(
    decision_model: DecisionModel,
    recommendation: DecisionRecommendation,
    evidence_package: Optional[EvidencePackage],
    config: ResilienceConfig,
) -> Tuple[ResilienceSubScore, List[str]]:
    """Evaluates Pillar D: Information Robustness (0 to 25 points)."""
    vulnerabilities: List[str] = []
    critical_vulns: List[str] = []

    unc = recommendation.uncertainty_assessment

    # 1. Recommendation Stability (up to 5.0 pts)
    if unc.recommendation_stability == RecommendationStability.HIGH:
        stability_score = 5.0
        stab_desc = "High recommendation stability against foreseeable variance."
    elif unc.recommendation_stability == RecommendationStability.MODERATE:
        stability_score = 3.0
        stab_desc = "Moderate stability; sensitive to key operational factors."
    else:
        stability_score = 1.0
        stab_desc = "Volatile recommendation highly sensitive to external variance."
        vulnerabilities.append("Recommendation stability is categorized as volatile.")
        critical_vulns.append("Volatile recommendation stability under epistemic variance.")

    # 2. Evidence Strength (up to 5.0 pts)
    if unc.evidence_strength == EvidenceStrength.STRONG:
        strength_score = 5.0
    elif unc.evidence_strength == EvidenceStrength.MODERATE:
        strength_score = 3.5
    elif unc.evidence_strength == EvidenceStrength.LIMITED:
        strength_score = 2.0
        vulnerabilities.append("Empirical evidence strength backing recommendation is limited.")
    elif unc.evidence_strength == EvidenceStrength.CONTESTED:
        strength_score = 1.0
        vulnerabilities.append("Empirical evidence backing recommendation is contested by contradictory findings.")
    else:  # INSUFFICIENT
        strength_score = 0.0
        vulnerabilities.append("Empirical evidence backing recommendation is insufficient.")
        critical_vulns.append("Insufficient empirical evidence backing recommendation.")

    # 3. Evidence Gaps Penalty (up to 6.0 pts)
    if evidence_package is not None:
        gaps = evidence_package.gaps
        high_gaps = [g for g in gaps if g.impact == CriticalityLevel.HIGH]
        med_gaps = [g for g in gaps if g.impact == CriticalityLevel.MEDIUM]
        low_gaps = [g for g in gaps if g.impact == CriticalityLevel.LOW]

        gap_penalty = min(config.max_gap_points, len(high_gaps) * 2.0 + len(med_gaps) * 1.0 + len(low_gaps) * 0.5)
        gap_score = max(0.0, config.max_gap_points - gap_penalty)

        for g in sorted(high_gaps, key=lambda x: x.id):
            vulnerabilities.append(f"Critical empirical evidence gap: '{g.description}'.")
            critical_vulns.append(f"Critical evidence gap: {g.description}")
        gap_desc = f"{len(gaps)} evidence gap(s) detected ({gap_score:.1f}/{config.max_gap_points:.1f} pts)."
    else:
        # Conservative neutral baseline when evidence package is not provided
        gap_score = 3.0
        vulnerabilities.append("EvidencePackage not provided; empirical gap profile unverified.")
        gap_desc = "EvidencePackage not supplied (neutral 3.0/6.0 pts applied)."

    # 4. Assumption Confidence (up to 5.0 pts)
    assumptions = decision_model.assumptions
    if not assumptions:
        assumption_score = 3.0
        vulnerabilities.append("No explicit assumptions documented in DecisionModel.")
        assump_desc = "No explicit assumptions documented (neutral 3.0/5.0 pts)."
    else:
        points_map = {
            ConfidenceLevel.HIGH: 1.0,
            ConfidenceLevel.MEDIUM: 0.6,
            ConfidenceLevel.LOW: 0.2,
            ConfidenceLevel.UNTESTED: 0.1,
        }
        total_pts = sum(points_map.get(a.confidence, 0.1) for a in assumptions)
        assumption_score = (total_pts / len(assumptions)) * config.max_assumption_points

        low_or_untested = sorted(
            [a for a in assumptions if a.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.UNTESTED)],
            key=lambda x: x.id,
        )
        for a in low_or_untested:
            vulnerabilities.append(f"Untested/low-confidence assumption relied upon: '{a.statement}'.")
        assump_desc = (
            f"{len(assumptions)} assumption(s) evaluated "
            f"({assumption_score:.1f}/{config.max_assumption_points:.1f} pts)."
        )

    # 5. Decision Readiness (up to 4.0 pts)
    if unc.decision_readiness == DecisionReadiness.READY:
        readiness_score = 4.0
    elif unc.decision_readiness == DecisionReadiness.CONDITIONAL:
        readiness_score = 3.0
    elif unc.decision_readiness == DecisionReadiness.NEEDS_VALIDATION:
        readiness_score = 1.5
        vulnerabilities.append("Operational decision readiness requires preliminary validation.")
    else:  # BLOCKED
        readiness_score = 0.0
        vulnerabilities.append("Operational decision readiness is currently blocked.")
        critical_vulns.append("Decision execution readiness is blocked.")

    raw_score = stability_score + strength_score + gap_score + assumption_score + readiness_score
    final_score = round(max(0.0, min(config.max_pillar_d_points, raw_score)), 2)

    rationale = (
        f"{stab_desc} Evidence strength: {unc.evidence_strength.value} ({strength_score:.1f}/5.0 pts). "
        f"{gap_desc} {assump_desc} Readiness: {unc.decision_readiness.value} ({readiness_score:.1f}/4.0 pts)."
    )

    subscore = ResilienceSubScore(
        category=ResiliencePillar.INFORMATION_ROBUSTNESS.value,
        score=final_score,
        max_score=config.max_pillar_d_points,
        rationale=rationale,
        vulnerabilities_detected=vulnerabilities,
    )
    return subscore, critical_vulns


# ------------------------------------------------------------------------------
# 4. Master Deterministic Resilience Evaluator
# ------------------------------------------------------------------------------

def evaluate_resilience(
    decision_model: DecisionModel,
    scenario_set: ScenarioSet,
    recommendation: DecisionRecommendation,
    evidence_package: Optional[EvidencePackage] = None,
    reasoning_board: Optional[ReasoningBoard] = None,
    config: Optional[ResilienceConfig] = None,
) -> ResilienceReport:
    """Calculates a deterministic 0-100 resilience score and report.

    Validates referential integrity across all decision artifacts, applies versioned
    transparent mathematical scoring across four 25-point pillars, and outputs an
    immutable ResilienceReport with a content-derived SHA-256 ID.

    Args:
        decision_model: Authoritative DecisionModel.
        scenario_set: Authoritative ScenarioSet (must contain 3 canonical trajectories).
        recommendation: Authoritative DecisionRecommendation.
        evidence_package: Optional EvidencePackage for gap analysis.
        reasoning_board: Optional ReasoningBoard for cross-deliberation verification.
        config: Optional configuration overrides for thresholds and weights.

    Returns:
        ResilienceReport: Authoritative resilience score, rating, sub-scores, and hedges.

    Raises:
        ValueError: If referential integrity fails or required canonical trajectories are missing.
    """
    cfg = config or DEFAULT_RESILIENCE_CONFIG

    # 1. Referential Integrity Verification
    if scenario_set.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: ScenarioSet decision_model_id ('{scenario_set.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )

    if recommendation.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: Recommendation decision_model_id ('{recommendation.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )

    if scenario_set.recommendation_id and scenario_set.recommendation_id != recommendation.id:
        raise ValueError(
            f"Referential integrity mismatch: ScenarioSet recommendation_id ('{scenario_set.recommendation_id}') "
            f"does not match Recommendation.id ('{recommendation.id}')."
        )

    if evidence_package is not None and evidence_package.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: EvidencePackage decision_model_id ('{evidence_package.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )

    if reasoning_board is not None and reasoning_board.decision_model_id != decision_model.id:
        raise ValueError(
            f"Referential integrity mismatch: ReasoningBoard decision_model_id ('{reasoning_board.decision_model_id}') "
            f"does not match DecisionModel.id ('{decision_model.id}')."
        )

    # 2. Extract Canonical Scenarios
    scenarios_by_type = {s.scenario_type: s for s in scenario_set.scenarios}
    if ScenarioType.PESSIMISTIC not in scenarios_by_type:
        raise ValueError("ScenarioSet missing required 'pessimistic' scenario trajectory.")
    if ScenarioType.OPTIMISTIC not in scenarios_by_type:
        raise ValueError("ScenarioSet missing required 'optimistic' scenario trajectory.")
    if ScenarioType.BASE_CASE not in scenarios_by_type:
        raise ValueError("ScenarioSet missing required 'base_case' scenario trajectory.")

    pessimistic_scenario = scenarios_by_type[ScenarioType.PESSIMISTIC]

    # 3. Calculate Pillar Sub-Scores
    sub_a, crit_a = _evaluate_constraint_boundary_tolerance(decision_model, pessimistic_scenario, cfg)
    sub_b, crit_b = _evaluate_pessimistic_survivability(pessimistic_scenario, recommendation, cfg)
    sub_c, crit_c = _evaluate_contingency_and_fallback_coverage(recommendation, cfg)
    sub_d, crit_d = _evaluate_information_robustness(decision_model, recommendation, evidence_package, cfg)

    sub_scores = [sub_a, sub_b, sub_c, sub_d]

    # 4. Aggregate Overall Score
    raw_total = sub_a.score + sub_b.score + sub_c.score + sub_d.score
    overall_score = round(max(0.0, min(100.0, raw_total)), 2)

    # 5. Determine Rating Band
    rating = determine_resilience_rating(overall_score)

    # 6. Evaluate Stress-Test
    stress_test_passed = (
        overall_score >= cfg.stress_test_min_overall_score
        and sub_b.score >= cfg.stress_test_min_pessimistic_subscore
    )

    # 7. Deduplicate Critical Vulnerabilities
    critical_vulnerabilities = list(dict.fromkeys(crit_a + crit_b + crit_c + crit_d))

    # 8. Formulate Proactive Recommended Hedges
    recommended_hedges: List[str] = []
    if crit_a:
        recommended_hedges.append("Implement automated telemetry monitoring and alert thresholds for operational constraints.")
    if decision_model.complexity.reversibility == ReversibilityLevel.IRREVERSIBLE:
        recommended_hedges.append("Structure execution into staged, reversible pilot phases to bound irreversible commitment.")
    if crit_b:
        recommended_hedges.append("Formulate pre-authorized contingency rollback procedures for unmitigated pessimistic scenario risks.")
    if not recommendation.action_plan.actions or not [g for a in recommendation.action_plan.actions for g in a.decision_gates]:
        recommended_hedges.append("Establish formal decision gates with quantitative verification criteria prior to cutover.")
    if crit_d:
        recommended_hedges.append("Commission targeted empirical research to resolve critical evidence gaps before final commitment.")
    if any(a.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.UNTESTED) for a in decision_model.assumptions):
        recommended_hedges.append("Define empirical falsification tests for core low-confidence operational assumptions.")

    if not recommended_hedges:
        recommended_hedges.append("Maintain continuous monitoring of key operational metrics and periodic boardroom reviews.")

    # 9. Compute Deterministic Content-Derived ID
    report_id = generate_deterministic_resilience_id(
        decision_model_id=decision_model.id,
        scenario_set_id=scenario_set.id,
        recommendation_id=recommendation.id,
        overall_score=overall_score,
        calculation_version=cfg.calculation_version,
        sub_scores=sub_scores,
    )

    return ResilienceReport(
        id=report_id,
        decision_model_id=decision_model.id,
        scenario_set_id=scenario_set.id,
        recommendation_id=recommendation.id,
        overall_score=overall_score,
        rating=rating,
        sub_scores=sub_scores,
        critical_vulnerabilities=critical_vulnerabilities,
        stress_test_passed=stress_test_passed,
        recommended_hedges=recommended_hedges,
        calculation_version=cfg.calculation_version,
    )
