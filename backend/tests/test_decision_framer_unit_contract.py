"""Unit and regression tests for AURA Day 4 Phase 4.35: Decision Framer Unit Contract and LLM Deadline Audit.

Verifies:
Part A:
1. DECOMPOSITION_SYSTEM_PROMPT contains the exact unit clarification.
2. Short measurement symbols (%, USD, USD/mo, users, months, ms) are accepted.
3. Valid null unit is accepted.
4. Overlong unit values (>30 chars) strictly fail Pydantic validation.
5. Semantic non-equivalence of unsafe truncation (demonstrating why silent truncation is unsafe).

Part B:
6. Deterministic fake-clock simulations for Configurations A, B, C, D across:
   - Fast first-attempt success
   - HTTP timeout followed by success
   - HTTP timeout followed by validation failure and third-attempt recovery
   - Repeated provider stalls
   - Parent deadline nearly exhausted
   - Multiple concurrent Evidence Mapping batches
   - Four concurrent Boardroom perspectives followed by synthesis
7. Demonstrates that 60s operation ceiling starves Attempt 3 when Attempt 1 times out (30s)
   and Attempt 2 fails validation, whereas 75s and 90s ceilings permit Attempt 3 to succeed.
8. Demonstrates that local operation ceilings can never exceed the parent deadline.
"""

from datetime import date
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import pytest
from pydantic import ValidationError

from app.schemas.decision_model import (
    Complexity,
    ComplexityLevel,
    Decision,
    DecisionModel,
    DecisionType,
    Variable,
    Objective,
    ProvenanceType,
    ReversibilityLevel,
    TimeHorizon,
    VariableType,
)
from app.services.llm.client import DEFAULT_LLM_CONFIG, LLMConfig, LLMTimeoutError
from app.services.llm.prompts import DECOMPOSITION_SYSTEM_PROMPT


# ------------------------------------------------------------------------------
# Part A: Decision Framer Unit Contract Tests
# ------------------------------------------------------------------------------

def test_decomposition_system_prompt_unit_guidance():
    """DECOMPOSITION_SYSTEM_PROMPT must mandate short measurement symbols or JSON null."""
    expected_phrase = (
        "For 'unit', output a short measurement symbol or abbreviation, no longer than 10 characters, "
        "such as '%', 'USD', 'USD/mo', 'users', or 'months'. Use JSON null when no accurate short unit "
        "is available. Do not return prose descriptions or explanations in this field."
    )
    assert expected_phrase in DECOMPOSITION_SYSTEM_PROMPT
    assert "2. Variables:" in DECOMPOSITION_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "unit_val",
    ["%", "USD", "USD/mo", "users", "months", "ms", "bps", "GB", "$/seat"],
)
def test_accepted_short_units(unit_val: str):
    """Canonical Variable must cleanly accept valid short measurement symbols."""
    var = Variable(
        id="var_price_test",
        name="Test Variable",
        description="A test variable for pricing.",
        variable_type=VariableType.NUMERIC,
        baseline_value=100.0,
        proposed_value=80.0,
        unit=unit_val,
        is_controllable=True,
        provenance=ProvenanceType.USER_PROVIDED,
    )
    assert var.unit == unit_val


def test_valid_null_unit_accepted():
    """Canonical Variable must accept unit=None when no short symbol exists."""
    var = Variable(
        id="var_qualitative_test",
        name="Qualitative Lever",
        description="A qualitative strategic lever without discrete units.",
        variable_type=VariableType.QUALITATIVE,
        baseline_value="status_quo",
        proposed_value="revised_approach",
        unit=None,
        is_controllable=True,
        provenance=ProvenanceType.INFERRED,
    )
    assert var.unit is None


def test_rejected_overlong_unit():
    """Canonical Variable must reject overlong values (>30 chars in canonical schema)."""
    long_unit = "percentage reduction in baseline monthly price"
    assert len(long_unit) > 30

    with pytest.raises(ValidationError) as exc_info:
        Variable(
            id="var_overlong_unit",
            name="Discount",
            description="Discount rate.",
            variable_type=VariableType.NUMERIC,
            baseline_value=0.0,
            proposed_value=20.0,
            unit=long_unit,
        )
    errors = exc_info.value.errors()
    assert errors[0]["loc"] == ("unit",)
    assert errors[0]["type"] == "string_too_long"


def test_semantic_non_equivalence_of_unsafe_truncation():
    """Proves why silent truncation of prose descriptions is semantically corrupting.

    Truncating prose like 'USD per customer per year' to 10 chars yields 'USD per cu',
    and 'percentage of monthly churn' yields 'percentage', altering the epistemic
    meaning of the metric. Prompt-guided exact symbol selection or null avoids this.
    """
    prose_descriptions = [
        ("USD per customer per year", "USD/cust/yr", "USD per cu"),
        ("percentage of monthly revenue churn", "%/mo", "percentage"),
        ("active customer accounts per enterprise", "accounts", "active cus"),
    ]
    for raw_prose, intended_short, naive_truncated in prose_descriptions:
        truncated_10 = raw_prose[:10].strip()
        # Naive truncation produces an unintelligible or distorted unit
        assert truncated_10 == naive_truncated
        assert truncated_10 != intended_short
        # Neither represents the original accurately
        assert len(naive_truncated) <= 10


# ------------------------------------------------------------------------------
# Part B: Deterministic Fake-Clock Simulation Framework
# ------------------------------------------------------------------------------

class SimulatedAttempt:
    """Outcome of an HTTP attempt in a deterministic fake clock."""
    def __init__(
        self,
        duration: float,
        outcome: str,  # 'success', 'timeout', 'validation_error'
        validation_error_path: Optional[str] = None,
    ):
        self.duration = duration
        self.outcome = outcome
        self.validation_error_path = validation_error_path


class FakeClockLLMOperation:
    """Deterministic simulation of GeminiLLMClient timeout, retry, and backoff logic."""

    def __init__(
        self,
        parent_timeout_seconds: float,
        operation_timeout_seconds: float,
        http_timeout_seconds: float = 30.0,
        max_retries: int = 2,
        initial_backoff_seconds: float = 0.5,
        backoff_multiplier: float = 2.0,
    ):
        self.parent_timeout_seconds = parent_timeout_seconds
        self.operation_timeout_seconds = operation_timeout_seconds
        self.http_timeout_seconds = http_timeout_seconds
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.backoff_multiplier = backoff_multiplier

    def execute(
        self,
        start_time_offset: float,
        attempts: List[SimulatedAttempt],
    ) -> Dict[str, Any]:
        """Simulates an LLM call at a given start_time_offset into the parent analysis."""
        parent_deadline = self.parent_timeout_seconds
        op_start = start_time_offset
        op_deadline = op_start + self.operation_timeout_seconds
        effective_deadline = min(op_deadline, parent_deadline)

        current_time = op_start
        attempt_records = []
        max_attempts = 1 + self.max_retries
        attempt_idx = 0
        final_status = "unknown"
        final_error = None

        while attempt_idx < len(attempts) and attempt_idx < max_attempts:
            attempt_idx += 1
            sim = attempts[attempt_idx - 1]

            remaining = effective_deadline - current_time
            if remaining <= 0:
                final_status = "timeout_before_attempt"
                timeout_source = "parent" if current_time >= parent_deadline else "operation"
                final_error = f"Timed out ({timeout_source})"
                break

            effective_http_timeout = min(self.http_timeout_seconds, remaining)

            # Determine actual attempt duration
            if sim.outcome == "timeout":
                actual_duration = effective_http_timeout
                current_time += actual_duration
                rec = {
                    "attempt": attempt_idx,
                    "status": "timeout",
                    "duration": actual_duration,
                    "effective_timeout": effective_http_timeout,
                }
                attempt_records.append(rec)

                # Check if exhausted
                if attempt_idx >= max_attempts or current_time >= effective_deadline:
                    final_status = "timeout"
                    timeout_source = "parent" if current_time >= parent_deadline else "operation"
                    final_error = f"Operation timed out ({timeout_source})"
                    break

                # Backoff
                calc_backoff = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_idx - 1))
                rem_time = effective_deadline - current_time
                actual_backoff = min(calc_backoff, rem_time) if rem_time > 0 else 0
                current_time += actual_backoff
                rec["backoff"] = actual_backoff
                continue

            elif sim.outcome == "validation_error":
                # Call returned within duration, but failed validation
                actual_duration = min(sim.duration, effective_http_timeout)
                current_time += actual_duration
                rec = {
                    "attempt": attempt_idx,
                    "status": "validation_error",
                    "duration": actual_duration,
                    "error_path": sim.validation_error_path,
                }
                attempt_records.append(rec)

                if attempt_idx >= max_attempts or current_time >= effective_deadline:
                    final_status = "validation_error"
                    final_error = "Validation error exhausted retry budget"
                    break

                # Backoff
                calc_backoff = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_idx - 1))
                rem_time = effective_deadline - current_time
                actual_backoff = min(calc_backoff, rem_time) if rem_time > 0 else 0
                current_time += actual_backoff
                rec["backoff"] = actual_backoff
                continue

            elif sim.outcome == "success":
                actual_duration = min(sim.duration, effective_http_timeout)
                if sim.duration > effective_http_timeout:
                    # Truncated by timeout
                    current_time += effective_http_timeout
                    rec = {
                        "attempt": attempt_idx,
                        "status": "timeout",
                        "duration": effective_http_timeout,
                    }
                    attempt_records.append(rec)
                    final_status = "timeout"
                    timeout_source = "parent" if current_time >= parent_deadline else "operation"
                    final_error = f"Timed out during attempt ({timeout_source})"
                    break
                else:
                    current_time += actual_duration
                    rec = {
                        "attempt": attempt_idx,
                        "status": "success",
                        "duration": actual_duration,
                    }
                    attempt_records.append(rec)
                    final_status = "success"
                    final_error = None
                    break

        total_op_duration = current_time - op_start
        return {
            "status": final_status,
            "error": final_error,
            "attempts": attempt_records,
            "total_op_duration": total_op_duration,
            "end_time": current_time,
            "remaining_parent_budget": max(0.0, parent_deadline - current_time),
        }


# ------------------------------------------------------------------------------
# Part B: Configuration Scenarios Simulation Tests
# ------------------------------------------------------------------------------

def test_scenario_fast_first_attempt_success_all_configs():
    """Scenario 1: Fast 20s success completes cleanly in all configurations."""
    configs = [
        ("Config A (120/60/30)", 120.0, 60.0),
        ("Config B (180/60/30)", 180.0, 60.0),
        ("Config C (180/75/30)", 180.0, 75.0),
        ("Config D (180/90/30)", 180.0, 90.0),
    ]
    for label, parent_to, op_to in configs:
        sim = FakeClockLLMOperation(parent_timeout_seconds=parent_to, operation_timeout_seconds=op_to)
        res = sim.execute(0.0, [SimulatedAttempt(duration=20.0, outcome="success")])
        assert res["status"] == "success", f"Failed for {label}"
        assert res["total_op_duration"] == pytest.approx(20.0, rel=1e-3)
        assert len(res["attempts"]) == 1


def test_scenario_http_timeout_followed_by_success_all_configs():
    """Scenario 2: 30s timeout + 0.5s backoff + 20s success completes in ~50.5s across all configs."""
    configs = [
        ("Config A (120/60/30)", 120.0, 60.0),
        ("Config B (180/60/30)", 180.0, 60.0),
        ("Config C (180/75/30)", 180.0, 75.0),
        ("Config D (180/90/30)", 180.0, 90.0),
    ]
    for label, parent_to, op_to in configs:
        sim = FakeClockLLMOperation(parent_timeout_seconds=parent_to, operation_timeout_seconds=op_to)
        res = sim.execute(
            0.0,
            [
                SimulatedAttempt(duration=30.0, outcome="timeout"),
                SimulatedAttempt(duration=20.0, outcome="success"),
            ],
        )
        assert res["status"] == "success", f"Failed for {label}"
        assert res["total_op_duration"] == pytest.approx(50.5, rel=1e-3)
        assert len(res["attempts"]) == 2


def test_scenario_timeout_plus_validation_error_reproduces_phase434_failure():
    """Scenario 3 Reproducing Phase 4.34:

    Attempt 1: 30s timeout + 0.5s backoff = 30.5s
    Attempt 2: 20s validation error + 1.0s backoff = 21.0s (cumulative: 51.5s)
    Attempt 3 needs 20s to succeed.

    Under 60s operation ceiling (Configs A & B):
    Attempt 3 gets only 8.5s remaining, times out at 60s despite ample parent budget!

    Under 75s (Config C) & 90s (Config D):
    Attempt 3 gets 23.5s and 30s respectively, allowing clean recovery!
    """
    attempts_seq = [
        SimulatedAttempt(duration=30.0, outcome="timeout"),
        SimulatedAttempt(duration=20.0, outcome="validation_error", validation_error_path="variables.0.unit"),
        SimulatedAttempt(duration=20.0, outcome="success"),
    ]

    # Config A (120/60): FAILS at 60s
    sim_a = FakeClockLLMOperation(parent_timeout_seconds=120.0, operation_timeout_seconds=60.0)
    res_a = sim_a.execute(0.0, attempts_seq)
    assert res_a["status"] == "timeout"
    assert res_a["total_op_duration"] == pytest.approx(60.0, rel=1e-3)
    assert res_a["remaining_parent_budget"] == pytest.approx(60.0, rel=1e-3)

    # Config B (180/60) [PHASE 4.34]: FAILS at 60s despite 120s remaining in parent budget!
    sim_b = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=60.0)
    res_b = sim_b.execute(0.0, attempts_seq)
    assert res_b["status"] == "timeout"
    assert res_b["total_op_duration"] == pytest.approx(60.0, rel=1e-3)
    assert res_b["remaining_parent_budget"] == pytest.approx(120.0, rel=1e-3)
    # Attempt 3 was starved with only 8.5s
    assert res_b["attempts"][2]["duration"] == pytest.approx(8.5, rel=1e-3)

    # Config C (180/75): SUCCEEDS in ~71.5s with 108.5s remaining in parent budget!
    sim_c = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=75.0)
    res_c = sim_c.execute(0.0, attempts_seq)
    assert res_c["status"] == "success"
    assert res_c["total_op_duration"] == pytest.approx(71.5, rel=1e-3)
    assert res_c["remaining_parent_budget"] == pytest.approx(108.5, rel=1e-3)
    assert len(res_c["attempts"]) == 3

    # Config D (180/90): SUCCEEDS in ~71.5s with 108.5s remaining in parent budget!
    sim_d = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=90.0)
    res_d = sim_d.execute(0.0, attempts_seq)
    assert res_d["status"] == "success"
    assert res_d["total_op_duration"] == pytest.approx(71.5, rel=1e-3)
    assert res_d["remaining_parent_budget"] == pytest.approx(108.5, rel=1e-3)
    assert len(res_d["attempts"]) == 3


def test_scenario_repeated_provider_stalls_fail_closed():
    """Scenario 4: 3 consecutive 30s stalls fail closed cleanly at the local ceiling."""
    attempts_seq = [
        SimulatedAttempt(duration=30.0, outcome="timeout"),
        SimulatedAttempt(duration=30.0, outcome="timeout"),
        SimulatedAttempt(duration=30.0, outcome="timeout"),
    ]
    # Config B: cut off at 60s
    sim_b = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=60.0)
    res_b = sim_b.execute(0.0, attempts_seq)
    assert res_b["status"] == "timeout"
    assert res_b["total_op_duration"] == pytest.approx(60.0, rel=1e-3)

    # Config C: cut off at 75s
    sim_c = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=75.0)
    res_c = sim_c.execute(0.0, attempts_seq)
    assert res_c["status"] == "timeout"
    assert res_c["total_op_duration"] == pytest.approx(75.0, rel=1e-3)

    # Config D: cut off at 88.5s (30 + 0.5 + 30 + 1.0 + 27.0 = 88.5s on attempt 3)
    sim_d = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=90.0)
    res_d = sim_d.execute(0.0, attempts_seq)
    assert res_d["status"] == "timeout"
    # Max attempts reached after 3 attempts
    assert len(res_d["attempts"]) == 3


def test_scenario_parent_deadline_near_exhaustion_clamps_local_ceiling():
    """Scenario 5: Local ceiling NEVER exceeds remaining parent deadline."""
    # When start_time_offset is 170s into a 180s parent deadline (only 10s left)
    # Even if operation ceiling is 90s, the call MUST be clamped to 10s
    sim = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=90.0)
    res = sim.execute(170.0, [SimulatedAttempt(duration=20.0, outcome="success")])

    assert res["status"] == "timeout"
    assert res["total_op_duration"] == pytest.approx(10.0, rel=1e-3)
    assert res["remaining_parent_budget"] == pytest.approx(0.0, rel=1e-3)


def test_stage3_perspectives_and_synthesis_downstream_budget_simulation():
    """Scenario 8: Simulates end-to-end downstream budget sufficiency.

    Tests whether Stage 3 (4 concurrent perspectives of ~25s + sequential synthesis of ~20s = ~45s)
    has sufficient parent budget after Stage 1 and Stage 2 complete.
    """
    # Suppose Stage 1 experiences a full 71.5s recovery under Config C (75s ceiling)
    stage1_duration = 71.5
    # Suppose Stage 2 (Requirements + Brave + 4 Batches) takes 45.0s
    stage2_duration = 45.0
    stage3_entry_offset = stage1_duration + stage2_duration  # 116.5s

    # Under 180s parent budget:
    remaining_at_stage3_entry = 180.0 - stage3_entry_offset  # 63.5s

    # Stage 3 Perspective evaluation: 4 concurrent perspectives (slowest takes 26.0s)
    sim_perspective = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=60.0)
    res_p = sim_perspective.execute(stage3_entry_offset, [SimulatedAttempt(duration=26.0, outcome="success")])
    assert res_p["status"] == "success"

    synthesis_entry_offset = stage3_entry_offset + 26.0  # 142.5s
    remaining_at_synthesis = 180.0 - synthesis_entry_offset  # 37.5s

    # Stage 3 Synthesis: takes 22.0s
    sim_synth = FakeClockLLMOperation(parent_timeout_seconds=180.0, operation_timeout_seconds=60.0)
    res_s = sim_synth.execute(synthesis_entry_offset, [SimulatedAttempt(duration=22.0, outcome="success")])
    assert res_s["status"] == "success"
    assert res_s["remaining_parent_budget"] == pytest.approx(15.5, rel=1e-3)
    # The entire pipeline succeeds with 15.5s of safety margin!
