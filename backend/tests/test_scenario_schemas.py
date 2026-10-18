"""Tests for AURA Future Scenario Engine Schemas (Phase 5A).

Comprehensive tests covering:
1. Valid authoritative ScenarioSet with optimistic, base_case, and pessimistic scenarios.
2. Missing or duplicate scenario types fail validation.
3. Fewer than or more than 3 scenarios fail validation.
4. Duplicate scenario IDs fail validation.
5. Probability invariants:
   - Negative probabilities rejected.
   - Probabilities > 1.0 rejected.
   - NaN and infinite probabilities rejected.
   - Probability sums outside [0.99, 1.01] rejected.
   - Probability sums within [0.99, 1.01] accepted.
6. Field constraints on FutureScenario, ScenarioKeyEvent, and ScenarioMilestone.
7. Deterministic ID generation for scenarios and scenario sets.
8. Candidate schemas serialization and validation.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Sequence
import pytest
from pydantic import ValidationError

from app.schemas.scenario import (
    CandidateFutureScenario,
    CandidateScenarioKeyEvent,
    CandidateScenarioMilestone,
    CandidateScenarioSet,
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
    generate_deterministic_scenario_id,
    generate_deterministic_scenarioset_id,
)


def _create_sample_event(event_id: str = "ke_1", title: str = "Market Expansion") -> ScenarioKeyEvent:
    return ScenarioKeyEvent(
        id=event_id,
        title=title,
        description="Favorable enterprise adoption in targeted segment.",
        timeframe="Q1-Q2",
        trigger_condition="ARR growth > 15%",
        impact_on_decision="Accelerates profitability timeline.",
    )


def _create_sample_milestone(ms_id: str = "ms_1", title: str = "Initial Rollout") -> ScenarioMilestone:
    return ScenarioMilestone(
        id=ms_id,
        title=title,
        description="Rollout completed to primary tier users.",
        time_horizon="near_term",
        expected_outcome="User retention rate >= 85%",
    )


def _create_sample_scenario(
    stype: ScenarioType,
    prob: float,
    scen_id: Optional[str] = None,
) -> FutureScenario:
    hex_char = {"optimistic": "a", "base_case": "b", "pessimistic": "c"}.get(stype.value, "0")
    sid = scen_id or f"scen_{hex_char * 16}"
    return FutureScenario(
        id=sid,
        scenario_type=stype,
        probability=prob,
        name=f"Trajectory: {stype.value.title()}",
        narrative=f"Detailed operational trajectory describing conditions under the {stype.value} environment.",
        key_events=[_create_sample_event(f"ke_{stype.value}_1")],
        risks=[f"Risk associated with {stype.value} scenario."],
        opportunities=[f"Upside associated with {stype.value} scenario."],
        timeline=[_create_sample_milestone(f"ms_{stype.value}_1")],
        supporting_evidence_item_ids=["evi_1"],
        relevant_assumption_ids=["asm_1"],
        relevant_constraint_ids=["con_1"],
        relevant_gap_ids=["gap_1"],
    )


# ------------------------------------------------------------------------------
# 1. Valid Three-Scenario Portfolio
# ------------------------------------------------------------------------------

def test_valid_three_scenario_set():
    """Verify that a valid 3-scenario portfolio satisfying all invariants instantiates cleanly."""
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.25, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.50, "scen_bbbbbbbbbbbbbbbb"),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.25, "scen_cccccccccccccccc"),
    ]

    scenset = ScenarioSet(
        id="scenset_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_sample_1",
        recommendation_id="rec_sample_1",
        reasoning_board_id="rb_sample_1",
        evidence_package_id="evpkg_sample_1",
        summary="Balanced future outlook across optimistic, base case, and pessimistic environments.",
        scenarios=scenarios,
    )

    assert scenset.id.startswith("scenset_")
    assert len(scenset.scenarios) == 3
    assert scenset.scenarios[0].scenario_type == ScenarioType.OPTIMISTIC
    assert scenset.scenarios[1].scenario_type == ScenarioType.BASE_CASE
    assert scenset.scenarios[2].scenario_type == ScenarioType.PESSIMISTIC
    assert sum(s.probability for s in scenset.scenarios) == pytest.approx(1.0, abs=0.001)


# ------------------------------------------------------------------------------
# 2. Canonical Scenario Type Invariants
# ------------------------------------------------------------------------------

def test_missing_scenario_type_rejected():
    """Verify that omitting a canonical scenario type raises ValidationError."""
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.50, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.50, "scen_bbbbbbbbbbbbbbbb"),
        # Missing pessimistic, duplicate base_case
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.00, "scen_b2b2b2b2b2b2b2b2"),
    ]

    with pytest.raises(ValidationError) as exc_info:
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Invalid set with duplicate base_case.",
            scenarios=scenarios,
        )
    assert "canonical" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()


def test_fewer_than_three_scenarios_rejected():
    """Verify that ScenarioSet rejects fewer than 3 scenarios."""
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.50, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.50, "scen_bbbbbbbbbbbbbbbb"),
    ]

    with pytest.raises(ValidationError):
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Invalid set with 2 scenarios.",
            scenarios=scenarios,
        )


def test_more_than_three_scenarios_rejected():
    """Verify that ScenarioSet rejects more than 3 scenarios."""
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.20, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.50, "scen_bbbbbbbbbbbbbbbb"),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.20, "scen_cccccccccccccccc"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.10, "scen_b2b2b2b2b2b2b2b2"),
    ]

    with pytest.raises(ValidationError):
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Invalid set with 4 scenarios.",
            scenarios=scenarios,
        )


def test_duplicate_scenario_ids_rejected():
    """Verify that ScenarioSet enforces unique scenario IDs across the portfolio."""
    duplicate_id = "scen_dddddddddddddddd"
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.25, duplicate_id),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.50, duplicate_id),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.25, "scen_cccccccccccccccc"),
    ]

    with pytest.raises(ValidationError) as exc_info:
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Duplicate scenario IDs.",
            scenarios=scenarios,
        )
    assert "unique" in str(exc_info.value).lower() or "duplicate" in str(exc_info.value).lower()


# ------------------------------------------------------------------------------
# 3. Probability Invariant & Boundary Tests
# ------------------------------------------------------------------------------

def test_negative_probability_rejected():
    """Verify that negative scenario probability fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        _create_sample_scenario(ScenarioType.OPTIMISTIC, -0.10)
    assert "between 0.0 and 1.0" in str(exc_info.value)


def test_probability_greater_than_one_rejected():
    """Verify that scenario probability > 1.0 fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 1.05)
    assert "between 0.0 and 1.0" in str(exc_info.value)


def test_nan_probability_rejected():
    """Verify that NaN probability is rejected on FutureScenario."""
    with pytest.raises(ValidationError) as exc_info:
        _create_sample_scenario(ScenarioType.OPTIMISTIC, float("nan"))
    assert "finite" in str(exc_info.value).lower()


def test_infinite_probability_rejected():
    """Verify that infinite probability is rejected on FutureScenario."""
    with pytest.raises(ValidationError) as exc_info:
        _create_sample_scenario(ScenarioType.OPTIMISTIC, float("inf"))
    assert "finite" in str(exc_info.value).lower()


def test_probability_sum_outside_tolerance_rejected():
    """Verify that probabilities summing to 0.90 or 1.10 fail ScenarioSet validation."""
    # Under-allocation (sum = 0.85)
    scenarios_under = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.20, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.45, "scen_bbbbbbbbbbbbbbbb"),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.20, "scen_cccccccccccccccc"),
    ]
    with pytest.raises(ValidationError) as exc_info:
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Under-allocated probabilities sum to 0.85.",
            scenarios=scenarios_under,
        )
    assert "sum" in str(exc_info.value).lower()

    # Over-allocation (sum = 1.15)
    scenarios_over = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.35, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.55, "scen_bbbbbbbbbbbbbbbb"),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.25, "scen_cccccccccccccccc"),
    ]
    with pytest.raises(ValidationError) as exc_info:
        ScenarioSet(
            id="scenset_0123456789abcdef0123456789abcdef",
            decision_model_id="dec_sample_1",
            summary="Over-allocated probabilities sum to 1.15.",
            scenarios=scenarios_over,
        )
    assert "sum" in str(exc_info.value).lower()


def test_probability_sum_within_tolerance_accepted():
    """Verify that probabilities summing to 0.995 or 1.005 pass within 0.01 tolerance."""
    # Sum = 0.995 (diff = 0.005 <= 0.01)
    scenarios = [
        _create_sample_scenario(ScenarioType.OPTIMISTIC, 0.245, "scen_aaaaaaaaaaaaaaaa"),
        _create_sample_scenario(ScenarioType.BASE_CASE, 0.500, "scen_bbbbbbbbbbbbbbbb"),
        _create_sample_scenario(ScenarioType.PESSIMISTIC, 0.250, "scen_cccccccccccccccc"),
    ]
    scenset = ScenarioSet(
        id="scenset_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_sample_1",
        summary="Slight tolerance test.",
        scenarios=scenarios,
    )
    assert scenset is not None


# ------------------------------------------------------------------------------
# 4. Content Boundaries on Child Schemas
# ------------------------------------------------------------------------------

def test_future_scenario_empty_events_rejected():
    """Verify that FutureScenario requires at least one key event."""
    with pytest.raises(ValidationError):
        FutureScenario(
            id="scen_optimistic12345",
            scenario_type=ScenarioType.OPTIMISTIC,
            probability=0.25,
            name="Valid Name",
            narrative="A detailed valid narrative of the trajectory.",
            key_events=[],  # Empty list violates min_length=1
            timeline=[_create_sample_milestone()],
        )


def test_future_scenario_empty_timeline_rejected():
    """Verify that FutureScenario requires at least one milestone."""
    with pytest.raises(ValidationError):
        FutureScenario(
            id="scen_optimistic12345",
            scenario_type=ScenarioType.OPTIMISTIC,
            probability=0.25,
            name="Valid Name",
            narrative="A detailed valid narrative of the trajectory.",
            key_events=[_create_sample_event()],
            timeline=[],  # Empty list violates min_length=1
        )


def test_future_scenario_short_narrative_rejected():
    """Verify that narrative under 10 characters is rejected."""
    with pytest.raises(ValidationError):
        FutureScenario(
            id="scen_optimistic12345",
            scenario_type=ScenarioType.OPTIMISTIC,
            probability=0.25,
            name="Valid Name",
            narrative="Short",  # < 10 chars
            key_events=[_create_sample_event()],
            timeline=[_create_sample_milestone()],
        )


# ------------------------------------------------------------------------------
# 5. Deterministic ID Helpers
# ------------------------------------------------------------------------------

def test_deterministic_scenario_id_generation():
    """Verify deterministic scenario ID computation is repeatable and differentiated."""
    id1 = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.OPTIMISTIC,
        name="Rapid Expansion",
        probability=0.30,
        key_event_titles=["Series B Secured", "Customer Count 2x"],
    )
    id2 = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.OPTIMISTIC,
        name="Rapid Expansion",
        probability=0.30,
        key_event_titles=["Customer Count 2x", "Series B Secured"],  # Order shuffled
    )
    id3 = generate_deterministic_scenario_id(
        scenario_type=ScenarioType.PESSIMISTIC,
        name="Market Contraction",
        probability=0.30,
        key_event_titles=["Churn Increases"],
    )

    assert id1.startswith("scen_")
    assert len(id1) == 21  # 'scen_' (5) + 16 hex chars
    assert id1 == id2  # Key events order sorted internally
    assert id1 != id3


def test_deterministic_scenarioset_id_generation():
    """Verify deterministic scenario set ID computation."""
    scen_ids = ["scen_1111111111111111", "scen_2222222222222222", "scen_3333333333333333"]
    set_id1 = generate_deterministic_scenarioset_id(
        decision_model_id="dec_001",
        recommendation_id="rec_001",
        scenario_ids=scen_ids,
    )
    set_id2 = generate_deterministic_scenarioset_id(
        decision_model_id="dec_001",
        recommendation_id="rec_001",
        scenario_ids=list(reversed(scen_ids)),  # Reversed
    )

    assert set_id1.startswith("scenset_")
    assert len(set_id1) == 40  # 'scenset_' (8) + 32 hex chars
    assert set_id1 == set_id2


# ------------------------------------------------------------------------------
# 6. Candidate Schemas Validation
# ------------------------------------------------------------------------------

def test_candidate_scenario_set_schema():
    """Verify that CandidateScenarioSet parses candidate LLM structured generation."""
    raw_data = {
        "summary": "Executive summary of the candidate scenarios.",
        "scenarios": [
            {
                "scenario_type": "optimistic",
                "probability": 0.20,
                "name": "High Market Growth",
                "narrative": "Expansion across sectors accelerates adoption beyond targets.",
                "key_events": [
                    {
                        "title": "Adoption Surges",
                        "description": "Enterprise customer acquisition doubles.",
                        "timeframe": "Q1",
                        "trigger_condition": "Competitor pricing increases",
                        "impact_on_decision": "Strengthens ROI justification",
                    }
                ],
                "risks": ["Talent scaling bottlenecks"],
                "opportunities": ["Market leadership establishment"],
                "timeline": [
                    {
                        "title": "Phase 1 Launch",
                        "description": "Beta deployment",
                        "time_horizon": "near_term",
                        "expected_outcome": "99.9% uptime",
                    }
                ],
                "supporting_evidence_item_ids": ["evi_101"],
                "relevant_assumption_ids": ["asm_201"],
                "relevant_constraint_ids": ["con_301"],
                "relevant_gap_ids": ["gap_401"],
            },
            {
                "scenario_type": "base_case",
                "probability": 0.60,
                "name": "Expected Linear Growth",
                "narrative": "Standard adoption trajectory with predictable sales cycles.",
                "key_events": [
                    {
                        "title": "Baseline Onboarding",
                        "description": "Linear user growth matching historical benchmarks.",
                        "timeframe": "Q1-Q2",
                    }
                ],
                "risks": ["Minor margin compression"],
                "opportunities": ["Incremental margin improvements"],
                "timeline": [
                    {
                        "title": "Milestone 1",
                        "description": "Initial target reached",
                        "time_horizon": "medium_term",
                        "expected_outcome": "On budget",
                    }
                ],
            },
            {
                "scenario_type": "pessimistic",
                "probability": 0.20,
                "name": "Macro Slowdown",
                "narrative": "Constrained budgets delay enterprise procurement cycles.",
                "key_events": [
                    {
                        "title": "Sales Cycle Extends",
                        "description": "Average deal velocity slows by 45%.",
                        "timeframe": "Q2",
                    }
                ],
                "risks": ["Runway reduction"],
                "opportunities": ["Cost optimization focus"],
                "timeline": [
                    {
                        "title": "Contingency Gate",
                        "description": "Review spend threshold",
                        "time_horizon": "near_term",
                        "expected_outcome": "Preserve 12 months runway",
                    }
                ],
            },
        ],
    }

    cand = CandidateScenarioSet.model_validate(raw_data)
    assert len(cand.scenarios) == 3
    assert cand.scenarios[0].scenario_type == ScenarioType.OPTIMISTIC
    assert cand.scenarios[1].scenario_type == ScenarioType.BASE_CASE
    assert cand.scenarios[2].scenario_type == ScenarioType.PESSIMISTIC
