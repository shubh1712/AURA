"""AURA Scenario Generation Strict Validator (Phase 5A).

Validates CandidateScenarioSet proposed by an LLM against authoritative upstream context:
- DecisionModel (objectives, constraints, assumptions, unknowns)
- EvidencePackage (sources, items, claim links, gaps)
- ReasoningBoard (perspectives, blind spots, disagreements)
- DecisionRecommendation (status, action plan, decision gates, uncertainties)

Enforces:
- Exact 3-scenario cardinal structure (one optimistic, one base_case, one pessimistic).
- Strict probability invariants: finite, nonnegative, summing to 1.0 within 0.01 tolerance.
- Rejection of invalid probabilities rather than silent normalization or invention.
- Strict referential integrity for evidence, assumption, constraint, and gap IDs.
- Deterministic content-derived IDs for child entities, scenarios, and scenario sets.
"""

from datetime import datetime, timezone
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import (
    CandidateFutureScenario,
    CandidateScenarioSet,
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
    generate_deterministic_scenario_id,
    generate_deterministic_scenarioset_id,
)


# ------------------------------------------------------------------------------
# 1. Error Hierarchy
# ------------------------------------------------------------------------------

class ScenarioError(Exception):
    """Base exception for all scenario engine failures."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ScenarioPromptError(ScenarioError):
    """Raised when scenario prompt construction exceeds allowable bounds."""
    pass


class ScenarioValidationError(ScenarioError):
    """Raised when candidate scenarios fail schema, referential, or invariant validation."""

    @property
    def rule(self) -> Optional[str]:
        return self.details.get("rule")


class ScenarioEvaluationError(ScenarioError):
    """Raised when scenario generation fails (e.g. deadline expired or LLM timeout)."""
    pass


class ScenarioServiceError(ScenarioError):
    """Raised when scenario service encounters an unexpected execution failure."""

    def __init__(
        self,
        message: str,
        stage: str = "scenario_engine",
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
    "no_evidence",
    "no_assumptions",
    "no_constraints",
    "no_gaps",
    "no_risks",
    "no_opportunities",
    "(none)",
    "(n/a)",
    "[]",
    "{}",
}


def clean_id_list(ids: Optional[Sequence[str]]) -> List[str]:
    """Filters empty and placeholder tokens from an ID list while preserving valid IDs."""
    if not ids:
        return []
    cleaned: List[str] = []
    for raw in ids:
        token = str(raw).strip()
        if token and token.lower() not in PLACEHOLDER_TOKENS:
            cleaned.append(token)
    return cleaned


# ------------------------------------------------------------------------------
# 3. Input Validation
# ------------------------------------------------------------------------------

def validate_scenario_inputs(
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
    reasoning_board: ReasoningBoard,
    recommendation: DecisionRecommendation,
) -> None:
    """Validates authoritative upstream artifacts prior to scenario generation."""
    if not isinstance(decision_model, DecisionModel):
        raise ScenarioValidationError(
            "decision_model must be an instantiated authoritative DecisionModel.",
            details={"location": "validator.validate_scenario_inputs", "field": "decision_model"},
        )
    if not isinstance(evidence_package, EvidencePackage):
        raise ScenarioValidationError(
            "evidence_package must be an instantiated authoritative EvidencePackage.",
            details={"location": "validator.validate_scenario_inputs", "field": "evidence_package"},
        )
    if not isinstance(reasoning_board, ReasoningBoard):
        raise ScenarioValidationError(
            "reasoning_board must be an instantiated authoritative ReasoningBoard.",
            details={"location": "validator.validate_scenario_inputs", "field": "reasoning_board"},
        )
    if not isinstance(recommendation, DecisionRecommendation):
        raise ScenarioValidationError(
            "recommendation must be an instantiated authoritative DecisionRecommendation.",
            details={"location": "validator.validate_scenario_inputs", "field": "recommendation"},
        )

    # Verify ID integrity
    if not decision_model.id or not decision_model.id.strip():
        raise ScenarioValidationError("DecisionModel must have a non-empty ID.")
    if not evidence_package.id or not evidence_package.id.strip():
        raise ScenarioValidationError("EvidencePackage must have a non-empty ID.")
    if not reasoning_board.id or not reasoning_board.id.strip():
        raise ScenarioValidationError("ReasoningBoard must have a non-empty ID.")
    if not recommendation.id or not recommendation.id.strip():
        raise ScenarioValidationError("DecisionRecommendation must have a non-empty ID.")

    # Verify foreign key binding integrity
    if evidence_package.decision_model_id != decision_model.id:
        raise ScenarioValidationError(
            f"EvidencePackage decision_model_id ('{evidence_package.decision_model_id}') does not match DecisionModel.id ('{decision_model.id}').",
            details={
                "location": "validator.validate_scenario_inputs",
                "field": "evidence_package.decision_model_id",
                "rule": "mismatched_decision_model_id",
            },
        )
    if reasoning_board.decision_model_id != decision_model.id:
        raise ScenarioValidationError(
            f"ReasoningBoard decision_model_id ('{reasoning_board.decision_model_id}') does not match DecisionModel.id ('{decision_model.id}').",
            details={
                "location": "validator.validate_scenario_inputs",
                "field": "reasoning_board.decision_model_id",
                "rule": "mismatched_decision_model_id",
            },
        )
    if recommendation.decision_model_id != decision_model.id:
        raise ScenarioValidationError(
            f"DecisionRecommendation decision_model_id ('{recommendation.decision_model_id}') does not match DecisionModel.id ('{decision_model.id}').",
            details={
                "location": "validator.validate_scenario_inputs",
                "field": "recommendation.decision_model_id",
                "rule": "mismatched_decision_model_id",
            },
        )


# ------------------------------------------------------------------------------
# 4. Candidate Validation and Reconciliation
# ------------------------------------------------------------------------------

def validate_candidate_scenario_set(
    candidate: CandidateScenarioSet,
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
    reasoning_board: ReasoningBoard,
    recommendation: DecisionRecommendation,
    clock: Optional[Callable[[], datetime]] = None,
) -> ScenarioSet:
    """Validates and reconciles CandidateScenarioSet into authoritative ScenarioSet.

    Args:
        candidate: Non-authoritative candidate parsed from structured LLM generation.
        decision_model: Trusted DecisionModel context.
        evidence_package: Trusted EvidencePackage context.
        reasoning_board: Trusted ReasoningBoard context.
        recommendation: Trusted DecisionRecommendation context.
        clock: Optional clock callable for deterministic testing.

    Returns:
        Authoritative ScenarioSet object.

    Raises:
        ScenarioValidationError: If schema, referential, or invariant checks fail.
    """
    clock_fn = clock or (lambda: datetime.now(timezone.utc))

    # 1. Structural checks
    if not isinstance(candidate, CandidateScenarioSet):
        raise ScenarioValidationError(
            f"Expected CandidateScenarioSet instance, got {type(candidate).__name__}.",
            details={"location": "validator.validate_candidate_scenario_set", "field": "candidate"},
        )

    if not candidate.scenarios or len(candidate.scenarios) != 3:
        raise ScenarioValidationError(
            f"Candidate scenario set must contain exactly 3 scenarios, got {len(candidate.scenarios) if candidate.scenarios else 0}.",
            details={
                "location": "validator.validate_candidate_scenario_set",
                "field": "scenarios",
                "rule": "exact_three_scenarios",
                "count": len(candidate.scenarios) if candidate.scenarios else 0,
            },
        )

    # 2. Canonical scenario types check
    types_present = [s.scenario_type for s in candidate.scenarios]
    types_set = set(types_present)
    expected_types = {ScenarioType.OPTIMISTIC, ScenarioType.BASE_CASE, ScenarioType.PESSIMISTIC}

    if types_set != expected_types:
        missing = [t.value for t in expected_types - types_set]
        duplicates = [t.value for t in types_present if types_present.count(t) > 1]
        raise ScenarioValidationError(
            f"Candidate must contain exactly one optimistic, one base_case, and one pessimistic scenario. Missing: {missing}, Duplicates: {duplicates}.",
            details={
                "location": "validator.validate_candidate_scenario_set",
                "field": "scenarios.scenario_type",
                "rule": "canonical_types_required",
                "missing": missing,
                "duplicates": duplicates,
            },
        )

    # 3. Probability validation & invariant check
    for s in candidate.scenarios:
        if not math.isfinite(s.probability):
            raise ScenarioValidationError(
                f"Scenario '{s.scenario_type.value}' probability must be a finite number, got {s.probability}.",
                details={
                    "location": "validator.validate_candidate_scenario_set",
                    "field": f"scenarios[{s.scenario_type.value}].probability",
                    "rule": "finite_probability_required",
                    "value": s.probability,
                },
            )
        if s.probability < 0.0 or s.probability > 1.0:
            raise ScenarioValidationError(
                f"Scenario '{s.scenario_type.value}' probability must be between 0.0 and 1.0, got {s.probability}.",
                details={
                    "location": "validator.validate_candidate_scenario_set",
                    "field": f"scenarios[{s.scenario_type.value}].probability",
                    "rule": "probability_range",
                    "value": s.probability,
                },
            )

    prob_sum = sum(s.probability for s in candidate.scenarios)
    if not math.isfinite(prob_sum) or abs(prob_sum - 1.0) > 0.01:
        raise ScenarioValidationError(
            f"Scenario probabilities must sum to 1.0 within 0.01 tolerance, got sum={prob_sum:.4f}.",
            details={
                "location": "validator.validate_candidate_scenario_set",
                "field": "scenarios.probability",
                "rule": "probability_sum_tolerance",
                "sum": round(prob_sum, 4),
            },
        )

    # 4. Authoritative reference sets
    valid_evi_ids: Set[str] = {item.id for item in evidence_package.items}
    valid_asm_ids: Set[str] = {asm.id for asm in decision_model.assumptions}
    valid_con_ids: Set[str] = {c.id for c in decision_model.constraints}
    valid_gap_ids: Set[str] = {g.id for g in evidence_package.gaps}

    # 5. Build authoritative scenarios in canonical order
    type_order = [ScenarioType.OPTIMISTIC, ScenarioType.BASE_CASE, ScenarioType.PESSIMISTIC]
    scenario_by_type: Dict[ScenarioType, CandidateFutureScenario] = {
        s.scenario_type: s for s in candidate.scenarios
    }

    authoritative_scenarios: List[FutureScenario] = []

    for s_idx, stype in enumerate(type_order, 1):
        c_scen = scenario_by_type[stype]

        # Validate references
        cleaned_evi = clean_id_list(c_scen.supporting_evidence_item_ids)
        for eid in cleaned_evi:
            if eid not in valid_evi_ids:
                raise ScenarioValidationError(
                    f"Scenario '{stype.value}' referenced nonexistent evidence ID '{eid}'.",
                    details={
                        "location": "validator.validate_candidate_scenario_set",
                        "field": f"scenarios[{stype.value}].supporting_evidence_item_ids",
                        "rule": "nonexistent_evidence_reference",
                        "invalid_id": eid,
                    },
                )

        cleaned_asm = clean_id_list(c_scen.relevant_assumption_ids)
        for aid in cleaned_asm:
            if aid not in valid_asm_ids:
                raise ScenarioValidationError(
                    f"Scenario '{stype.value}' referenced nonexistent assumption ID '{aid}'.",
                    details={
                        "location": "validator.validate_candidate_scenario_set",
                        "field": f"scenarios[{stype.value}].relevant_assumption_ids",
                        "rule": "nonexistent_assumption_reference",
                        "invalid_id": aid,
                    },
                )

        cleaned_con = clean_id_list(c_scen.relevant_constraint_ids)
        for cid in cleaned_con:
            if cid not in valid_con_ids:
                raise ScenarioValidationError(
                    f"Scenario '{stype.value}' referenced nonexistent constraint ID '{cid}'.",
                    details={
                        "location": "validator.validate_candidate_scenario_set",
                        "field": f"scenarios[{stype.value}].relevant_constraint_ids",
                        "rule": "nonexistent_constraint_reference",
                        "invalid_id": cid,
                    },
                )

        cleaned_gap = clean_id_list(c_scen.relevant_gap_ids)
        for gid in cleaned_gap:
            if gid not in valid_gap_ids:
                raise ScenarioValidationError(
                    f"Scenario '{stype.value}' referenced nonexistent gap ID '{gid}'.",
                    details={
                        "location": "validator.validate_candidate_scenario_set",
                        "field": f"scenarios[{stype.value}].relevant_gap_ids",
                        "rule": "nonexistent_gap_reference",
                        "invalid_id": gid,
                    },
                )

        # Narrative check
        if not c_scen.narrative or len(c_scen.narrative.strip()) < 10:
            raise ScenarioValidationError(
                f"Scenario '{stype.value}' narrative must be at least 10 characters.",
                details={
                    "location": "validator.validate_candidate_scenario_set",
                    "field": f"scenarios[{stype.value}].narrative",
                    "rule": "short_narrative",
                },
            )

        # Reconcile key events with deterministic child IDs
        if not c_scen.key_events:
            raise ScenarioValidationError(
                f"Scenario '{stype.value}' must contain at least one key event.",
                details={
                    "location": "validator.validate_candidate_scenario_set",
                    "field": f"scenarios[{stype.value}].key_events",
                    "rule": "key_events_required",
                },
            )

        auth_events: List[ScenarioKeyEvent] = []
        for e_idx, ce in enumerate(c_scen.key_events, 1):
            auth_events.append(
                ScenarioKeyEvent(
                    id=f"ke_{stype.value}_{e_idx}",
                    title=ce.title.strip(),
                    description=ce.description.strip(),
                    timeframe=ce.timeframe.strip(),
                    trigger_condition=ce.trigger_condition.strip() if ce.trigger_condition else None,
                    impact_on_decision=ce.impact_on_decision.strip() if ce.impact_on_decision else None,
                )
            )

        # Reconcile timeline milestones with deterministic child IDs
        if not c_scen.timeline:
            raise ScenarioValidationError(
                f"Scenario '{stype.value}' must contain at least one timeline milestone.",
                details={
                    "location": "validator.validate_candidate_scenario_set",
                    "field": f"scenarios[{stype.value}].timeline",
                    "rule": "timeline_required",
                },
            )

        auth_milestones: List[ScenarioMilestone] = []
        for m_idx, cm in enumerate(c_scen.timeline, 1):
            auth_milestones.append(
                ScenarioMilestone(
                    id=f"ms_{stype.value}_{m_idx}",
                    title=cm.title.strip(),
                    description=cm.description.strip(),
                    time_horizon=cm.time_horizon.strip(),
                    expected_outcome=cm.expected_outcome.strip(),
                )
            )

        # Deterministic scenario ID
        scen_id = generate_deterministic_scenario_id(
            scenario_type=stype,
            name=c_scen.name.strip(),
            probability=c_scen.probability,
            key_event_titles=[e.title for e in auth_events],
        )

        auth_scenario = FutureScenario(
            id=scen_id,
            scenario_type=stype,
            probability=c_scen.probability,
            name=c_scen.name.strip(),
            narrative=c_scen.narrative.strip(),
            key_events=auth_events,
            risks=[r.strip() for r in c_scen.risks if r.strip() and r.strip().lower() not in PLACEHOLDER_TOKENS],
            opportunities=[o.strip() for o in c_scen.opportunities if o.strip() and o.strip().lower() not in PLACEHOLDER_TOKENS],
            timeline=auth_milestones,
            supporting_evidence_item_ids=sorted(list(set(cleaned_evi))),
            relevant_assumption_ids=sorted(list(set(cleaned_asm))),
            relevant_constraint_ids=sorted(list(set(cleaned_con))),
            relevant_gap_ids=sorted(list(set(cleaned_gap))),
        )
        authoritative_scenarios.append(auth_scenario)

    # 6. Generate deterministic ScenarioSet ID
    scenset_id = generate_deterministic_scenarioset_id(
        decision_model_id=decision_model.id,
        recommendation_id=recommendation.id,
        scenario_ids=[s.id for s in authoritative_scenarios],
    )

    # 7. Construct and return authoritative ScenarioSet
    return ScenarioSet(
        id=scenset_id,
        decision_model_id=decision_model.id,
        recommendation_id=recommendation.id,
        reasoning_board_id=reasoning_board.id,
        evidence_package_id=evidence_package.id,
        summary=candidate.summary.strip(),
        scenarios=authoritative_scenarios,
        created_at=clock_fn(),
    )
