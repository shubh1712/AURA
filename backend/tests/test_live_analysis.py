"""Opt-in live integration test for end-to-end Decision Analysis with EvidenceService.

Excluded by default from normal test runs. To execute explicitly:
    RUN_LIVE_ANALYSIS_TESTS=1 pytest tests/test_live_analysis.py -m live_analysis -v

Requires:
    RUN_LIVE_ANALYSIS_TESTS=1
    GOOGLE_CLOUD_PROJECT (or GCP ADC)
    BRAVE_SEARCH_API_KEY
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple
import pytest

from app.config import settings
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningBoard,
    validate_reasoning_references,
)
from app.services.analysis_service import AnalysisService
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.evidence.service import EvidenceService
from app.services.llm.gemini import GeminiLLMClient
import app.services.reasoning.service as reasoning_service_module
from fastapi import HTTPException


def compute_interval_union_duration(
    intervals: List[Tuple[float, float]],
) -> float:
    """Computes the total wall-clock duration covered by the union of time intervals.

    Deterministically merges overlapping or contiguous intervals:
    1. Filters invalid/empty intervals (where end <= start).
    2. Sorts intervals by start time, then end time.
    3. Merges overlapping intervals [s1, e1] and [s2, e2] where s2 <= e1 into [s1, max(e1, e2)].
    4. Sums the lengths of disjoint merged intervals.
    """
    valid = [(s, e) for s, e in intervals if e > s]
    if not valid:
        return 0.0

    sorted_intervals = sorted(valid, key=lambda x: (x[0], x[1]))
    merged: List[Tuple[float, float]] = []

    cur_start, cur_end = sorted_intervals[0]
    for s, e in sorted_intervals[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = s, e
    merged.append((cur_start, cur_end))

    return sum(e - s for s, e in merged)


class LiveTelemetryRecorder:
    """Thread-safe telemetry wrapper for LLM client invocations during live tests.

    Assigns unique, monotonically increasing call IDs at invocation start time
    using a dedicated threading.Lock, records timing and thread-local diagnostics,
    tracks start/end timestamps for interval-union analysis, and protects call history
    mutations with a records lock.
    """

    def __init__(
        self,
        target_fn: Any,
        llm_client: Any,
        diagnostics_enabled: bool = True,
    ) -> None:
        self._target_fn = target_fn
        self._llm_client = llm_client
        self.diagnostics_enabled = diagnostics_enabled
        self._counter_lock = threading.Lock()
        self._next_call_id = 1
        self._records_lock = threading.Lock()
        self._print_lock = threading.Lock()
        self.recorded_calls: List[Dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        with self._counter_lock:
            call_id = self._next_call_id
            self._next_call_id += 1

        t_call_start = time.monotonic()
        schema_cls = kwargs.get("response_schema") or (args[1] if len(args) > 1 else None)
        schema_name = getattr(schema_cls, "__name__", "UnknownSchema")

        success = False
        try:
            result = self._target_fn(*args, **kwargs)
            success = True
            return result
        finally:
            try:
                duration = time.monotonic() - t_call_start
                t_call_end = t_call_start + duration
                diag = getattr(self._llm_client, "last_diagnostic", None)
                diag_copy = dict(diag) if isinstance(diag, dict) else None

                system_instruction = kwargs.get("system_instruction")
                perspective_name = None
                if schema_name == "CandidatePerspectiveAnalysis" and system_instruction:
                    for p_cand in ("growth", "finance", "customer", "risk"):
                        if f"({p_cand})" in str(system_instruction).lower():
                            perspective_name = p_cand
                            break

                call_info: Dict[str, Any] = {
                    "call_id": call_id,
                    "call_index": call_id,
                    "schema_name": schema_name,
                    "perspective": perspective_name,
                    "start_timestamp": t_call_start,
                    "end_timestamp": t_call_end,
                    "duration": duration,
                    "success": success,
                    "diagnostic": diag_copy,
                }

                with self._records_lock:
                    self.recorded_calls.append(call_info)

                if self.diagnostics_enabled:
                    self._print_telemetry(call_info)
            except Exception:
                # Telemetry recording must never mask or alter the underlying exception/return
                pass

    def get_execution_intervals(self) -> List[Tuple[float, float]]:
        """Returns the list of (start_timestamp, end_timestamp) for all recorded calls."""
        with self._records_lock:
            return [
                (
                    c["start_timestamp"],
                    c.get("end_timestamp", c["start_timestamp"] + c["duration"]),
                )
                for c in self.recorded_calls
            ]

    def get_occupied_wall_time(self) -> float:
        """Returns the union duration of all recorded LLM execution intervals."""
        return compute_interval_union_duration(self.get_execution_intervals())

    def _print_telemetry(self, call_info: Dict[str, Any]) -> None:
        call_id = call_info["call_id"]
        schema_name = call_info["schema_name"]
        duration = call_info["duration"]
        diag = call_info.get("diagnostic") or {}

        persp_label = f" ({call_info['perspective'].upper()})" if call_info.get("perspective") else ""
        with self._print_lock:
            if call_info["success"]:
                print(f"\n--- [LLM Call #{call_id}: {schema_name}{persp_label}] ---")
                print(f"Total generate_structured Wall Time: {duration:.3f}s")
                if diag:
                    vertex_dur = diag.get("call_duration_seconds", 0.0)
                    print(f"Diagnostic Vertex API Call Duration: {vertex_dur:.3f}s")
                    print(f"Diagnostic Attempt Number: {diag.get('attempt')}")
                    print(f"Diagnostic Status: {diag.get('status')}")
                    print(f"Model: {diag.get('model')}")
                    print(f"Location: {diag.get('location')}")
                    print(f"Schema Build Duration: {diag.get('schema_build_seconds', 0.0):.4f}s")
                    print(f"Parse & Validation Duration: {diag.get('parse_duration_seconds', 0.0):.4f}s")
                    print(f"Total Call Duration: {diag.get('total_duration_seconds', duration):.3f}s")
                    print(f"Serialized Schema Chars: {diag.get('schema_chars')}")
                    print(f"System Prompt Chars: {diag.get('system_prompt_chars')}")
                    print(f"User Prompt Chars: {diag.get('user_prompt_chars')}")
                    if diag.get("attempts") and len(diag["attempts"]) > 1:
                        print("Per-Attempt Diagnostic Breakdown:")
                        for att in diag["attempts"]:
                            backoff_str = f" | backoff={att['backoff_seconds']:.2f}s" if att.get("backoff_seconds") else ""
                            rem_op_str = f" | rem_op={att['remaining_operation_seconds']:.2f}s" if "remaining_operation_seconds" in att else ""
                            val_cat = att.get("validation_category")
                            val_str = f" | val_cat={val_cat}" if val_cat else ""
                            paths = att.get("validation_field_paths")
                            paths_str = f" (paths: {','.join(paths)})" if paths else ""
                            print(
                                f"  - Attempt #{att.get('attempt_index')}: duration={att.get('duration_seconds', 0.0):.3f}s | "
                                f"status={att.get('status')} | timeout_applied={att.get('effective_http_timeout_seconds', 0.0):.1f}s"
                                f"{backoff_str}{rem_op_str}{val_str}{paths_str}"
                            )
                else:
                    print("Diagnostic Vertex API Call Duration: N/A")
                    print("Diagnostic Attempt Number: N/A")
                print("-" * 45)
            else:
                print(f"\n--- [LLM Call #{call_id}: {schema_name}{persp_label} (FAILED)] ---")
                print(f"Total generate_structured Wall Time: {duration:.3f}s")
                if diag:
                    vertex_dur = diag.get("call_duration_seconds")
                    vertex_str = f"{vertex_dur:.3f}s" if isinstance(vertex_dur, (int, float)) else "N/A"
                    print(f"Final Diagnostic Vertex API Call Duration: {vertex_str}")
                    print(f"Final Diagnostic Attempt Number: {diag.get('attempt', 'N/A')}")
                    raw_status = str(diag.get("status", "unknown"))
                    sanitized_status = raw_status.split("\n")[0][:100]
                    print(f"Final Diagnostic Status: {sanitized_status}")
                    if diag.get("final_validation_category"):
                        print(f"Final Diagnostic Validation Category: {diag.get('final_validation_category')}")
                    if diag.get("final_timeout_source"):
                        print(f"Final Diagnostic Timeout Source: {diag.get('final_timeout_source')}")
                    if diag.get("attempts"):
                        print("Per-Attempt Diagnostic Breakdown:")
                        for att in diag["attempts"]:
                            backoff_str = f" | backoff={att['backoff_seconds']:.2f}s" if att.get("backoff_seconds") else ""
                            rem_op_str = f" | rem_op={att['remaining_operation_seconds']:.2f}s" if "remaining_operation_seconds" in att else ""
                            val_cat = att.get("validation_category")
                            val_str = f" | val_cat={val_cat}" if val_cat else ""
                            paths = att.get("validation_field_paths")
                            paths_str = f" (paths: {','.join(paths)})" if paths else ""
                            print(
                                f"  - Attempt #{att.get('attempt_index')}: duration={att.get('duration_seconds', 0.0):.3f}s | "
                                f"status={att.get('status')} | timeout_applied={att.get('effective_http_timeout_seconds', 0.0):.1f}s"
                                f"{backoff_str}{rem_op_str}{val_str}{paths_str}"
                            )
                else:
                    print("Final Diagnostic Vertex API Call Duration: N/A")
                    print("Final Diagnostic Attempt Number: N/A")
                    print("Final Diagnostic Status: N/A")
                print("-" * 45)


class SearchTelemetryRecorder:
    """Thread-safe telemetry wrapper for search provider invocations during live tests."""

    def __init__(self, target_fn: Any) -> None:
        self._target_fn = target_fn
        self._lock = threading.Lock()
        self.recorded_searches: List[Dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        success = False
        num_results = 0
        error_name = None
        try:
            results = self._target_fn(*args, **kwargs)
            success = True
            num_results = len(results) if isinstance(results, list) else 0
            return results
        except Exception as e:
            error_name = type(e).__name__
            raise
        finally:
            duration = time.monotonic() - t0
            with self._lock:
                self.recorded_searches.append({
                    "duration": duration,
                    "num_results": num_results,
                    "success": success,
                    "error_name": error_name,
                })

    def get_total_search_duration(self) -> float:
        with self._lock:
            return sum(s["duration"] for s in self.recorded_searches)

    def get_search_count(self) -> int:
        with self._lock:
            return len(self.recorded_searches)


class PipelineTimingRecorder:
    """Thread-safe recorder for pipeline stage boundaries, perspective durations, and deadline tracking."""

    def __init__(self, deadline_monotonic: float) -> None:
        self.deadline_monotonic = deadline_monotonic
        self._lock = threading.Lock()
        self.stage_timings: Dict[str, Dict[str, float]] = {}
        self.perspective_timings: Dict[str, Dict[str, float]] = {}
        self.parallel_perspectives_timing: Optional[Dict[str, float]] = None
        self.disagreement_timing: Optional[Dict[str, float]] = None
        self.synthesis_timing: Optional[Dict[str, float]] = None
        self.completion_remaining_deadline: Optional[float] = None

    def record_stage(
        self,
        stage_name: str,
        start_time: float,
        end_time: float,
        rem_before: float,
        rem_after: float,
    ) -> None:
        with self._lock:
            self.stage_timings[stage_name] = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
                "remaining_before": rem_before,
                "remaining_after": rem_after,
            }

    def record_perspective(
        self,
        ptype: str,
        start_time: float,
        end_time: float,
    ) -> None:
        with self._lock:
            self.perspective_timings[ptype] = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
            }

    def record_parallel_perspectives(
        self,
        start_time: float,
        end_time: float,
    ) -> None:
        with self._lock:
            self.parallel_perspectives_timing = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
            }

    def record_disagreements(
        self,
        start_time: float,
        end_time: float,
        count: int,
    ) -> None:
        with self._lock:
            self.disagreement_timing = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
                "count": count,
            }

    def record_synthesis(
        self,
        start_time: float,
        end_time: float,
    ) -> None:
        with self._lock:
            self.synthesis_timing = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
            }

    def record_completion(self, now: float) -> None:
        with self._lock:
            self.completion_remaining_deadline = self.deadline_monotonic - now


@pytest.mark.live
@pytest.mark.live_analysis
def test_live_end_to_end_analysis() -> None:
    """Performs a live, real end-to-end analysis using Gemini on Vertex AI and Brave Search.

    Validates structural invariants across the complete DecisionModel -> EvidencePackage -> ReasoningBoard pipeline:
    - DecisionModel exists and matches contract.
    - EvidencePackage exists and matches contract.
    - ReasoningBoard exists and matches contract.
    - Exactly four canonical perspectives exist (growth, finance, customer, risk).
    - All authoritative references validate across the three-artifact chain.
    - Disagreements are structurally valid and reference >= 2 perspectives.
    - Board synthesis references authoritative disagreements.
    - Source reliability_score remains strictly None.
    - No recommendation, resilience score, scenario, or what-if artifact was generated.
    - HTTP status is 200 OK.
    """
    run_flag = os.environ.get("RUN_LIVE_ANALYSIS_TESTS") == "1"
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or settings.GOOGLE_CLOUD_PROJECT
        or os.environ.get("GCP_PROJECT")
    )
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY") or settings.BRAVE_SEARCH_API_KEY

    if not run_flag or not project or not project.strip() or not brave_key or not brave_key.strip():
        pytest.skip(
            "RUN_LIVE_ANALYSIS_TESTS=1, GOOGLE_CLOUD_PROJECT, and BRAVE_SEARCH_API_KEY are required for live analysis tests."
        )

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or settings.GOOGLE_CLOUD_LOCATION
        or "global"
    )
    real_llm = GeminiLLMClient(project=project.strip(), location=location.strip())

    diagnostics_enabled = os.environ.get("AURA_LLM_DIAGNOSTICS") == "1"
    telemetry_recorder = LiveTelemetryRecorder(
        target_fn=real_llm.generate_structured,
        llm_client=real_llm,
        diagnostics_enabled=diagnostics_enabled,
    )
    real_llm.generate_structured = telemetry_recorder
    recorded_llm_calls = telemetry_recorder.recorded_calls

    real_search = BraveSearchProvider(api_key=brave_key.strip())
    search_recorder = SearchTelemetryRecorder(target_fn=real_search.search)
    real_search.search = search_recorder

    real_evidence_svc = EvidenceService.create_default(
        llm_client=real_llm,
        search_provider=real_search,
    )
    analysis_timeout = float(
        os.environ.get(
            "ANALYSIS_TIMEOUT_SECONDS",
            str(settings.ANALYSIS_TIMEOUT_SECONDS),
        )
    )
    analysis_svc = AnalysisService(
        llm_client=real_llm,
        evidence_service=real_evidence_svc,
        analysis_timeout_seconds=analysis_timeout,
    )

    request = AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )

    t_analysis_start = time.monotonic()
    deadline = t_analysis_start + analysis_timeout
    timing_recorder = PipelineTimingRecorder(deadline_monotonic=deadline)

    # Instrument Stage 1 (Decision Framer)
    orig_deconstruct = analysis_svc.engine.deconstruct
    def instrumented_deconstruct(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        try:
            return orig_deconstruct(*args, **kwargs)
        finally:
            t1 = time.monotonic()
            rem_after = deadline - time.monotonic()
            timing_recorder.record_stage("stage1_decision_framer", t0, t1, rem_before, rem_after)
    analysis_svc.engine.deconstruct = instrumented_deconstruct

    # Instrument Stage 2 (Evidence Engine)
    orig_build_evidence = analysis_svc.evidence_service.build_evidence_package
    def instrumented_build_evidence(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        try:
            return orig_build_evidence(*args, **kwargs)
        finally:
            t1 = time.monotonic()
            rem_after = deadline - time.monotonic()
            timing_recorder.record_stage("stage2_evidence_engine", t0, t1, rem_before, rem_after)
    analysis_svc.evidence_service.build_evidence_package = instrumented_build_evidence

    # Instrument Stage 3 (AI Boardroom)
    orig_build_board = analysis_svc.reasoning_service.build_reasoning_board
    def instrumented_build_board(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        try:
            return orig_build_board(*args, **kwargs)
        finally:
            t1 = time.monotonic()
            rem_after = deadline - time.monotonic()
            timing_recorder.record_stage("stage3_ai_boardroom", t0, t1, rem_before, rem_after)
    analysis_svc.reasoning_service.build_reasoning_board = instrumented_build_board

    # Instrument Parallel Perspectives Wall Time
    orig_evaluate_all = analysis_svc.reasoning_service.orchestrator.evaluate_all
    def instrumented_evaluate_all(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        try:
            return orig_evaluate_all(*args, **kwargs)
        finally:
            t1 = time.monotonic()
            timing_recorder.record_parallel_perspectives(t0, t1)
    analysis_svc.reasoning_service.orchestrator.evaluate_all = instrumented_evaluate_all

    # Instrument Individual Perspective Evaluations
    orig_evaluate = analysis_svc.reasoning_service.orchestrator.reasoner.evaluate
    def instrumented_evaluate(ctx: Any, *args: Any, **kwargs: Any) -> Any:
        ptype = getattr(ctx.perspective.perspective_type, "value", str(ctx.perspective.perspective_type))
        t0 = time.monotonic()
        try:
            return orig_evaluate(ctx, *args, **kwargs)
        finally:
            t1 = time.monotonic()
            timing_recorder.record_perspective(ptype, t0, t1)
    analysis_svc.reasoning_service.orchestrator.reasoner.evaluate = instrumented_evaluate

    # Instrument Disagreement Detection
    orig_detect_disagreements = reasoning_service_module.detect_disagreements
    def instrumented_detect_disagreements(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        try:
            result = orig_detect_disagreements(*args, **kwargs)
            return result
        finally:
            t1 = time.monotonic()
            count = len(result) if "result" in locals() and isinstance(result, (list, tuple)) else 0
            timing_recorder.record_disagreements(t0, t1, count)
    reasoning_service_module.detect_disagreements = instrumented_detect_disagreements

    # Instrument Board Synthesis
    orig_synthesize = analysis_svc.reasoning_service.synthesizer.synthesize
    def instrumented_synthesize(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        try:
            return orig_synthesize(*args, **kwargs)
        finally:
            t1 = time.monotonic()
            timing_recorder.record_synthesis(t0, t1)
    analysis_svc.reasoning_service.synthesizer.synthesize = instrumented_synthesize

    final_http_status = 200
    caught_error = None
    response = None
    try:
        response = analysis_svc.analyze(
            request,
            deadline_monotonic=deadline,
        )
    except HTTPException as he:
        final_http_status = he.status_code
        caught_error = he
    except Exception as exc:
        final_http_status = 500
        caught_error = exc
    finally:
        t_analysis_end = time.monotonic()
        timing_recorder.record_completion(t_analysis_end)
        total_analysis_duration = t_analysis_end - t_analysis_start
        reasoning_service_module.detect_disagreements = orig_detect_disagreements

    if diagnostics_enabled or caught_error is not None:
        print("\n" + "=" * 70)
        print("--- AURA Live End-to-End Analysis Diagnostic & Profiling Summary ---")
        print("=" * 70)
        print(f"Final HTTP Status: {final_http_status}")
        print(f"Total Analysis Wall Time: {total_analysis_duration:.2f}s (Budget: {analysis_timeout:.1f}s)")
        rem_comp = timing_recorder.completion_remaining_deadline
        rem_comp_str = f"{rem_comp:.2f}s" if rem_comp is not None else "N/A"
        print(f"Remaining Shared Deadline at Completion: {rem_comp_str}")

        print("\n--- Pipeline Stage Timing Breakdown ---")
        st1 = timing_recorder.stage_timings.get("stage1_decision_framer", {})
        if st1:
            print(f"  Stage 1 (Decision Framer): {st1.get('duration', 0.0):.3f}s | rem_before={st1.get('remaining_before', 0.0):.2f}s | rem_after={st1.get('remaining_after', 0.0):.2f}s")
        else:
            print("  Stage 1 (Decision Framer): N/A (not reached or failed before start)")

        st2 = timing_recorder.stage_timings.get("stage2_evidence_engine", {})
        if st2:
            print(f"  Stage 2 (Evidence Engine): {st2.get('duration', 0.0):.3f}s | rem_before={st2.get('remaining_before', 0.0):.2f}s | rem_after={st2.get('remaining_after', 0.0):.2f}s")
            print(f"    - Search Requests Executed: {search_recorder.get_search_count()} | Total Search Wall Time: {search_recorder.get_total_search_duration():.3f}s")
        else:
            print("  Stage 2 (Evidence Engine): N/A (not reached or failed before start)")

        st3 = timing_recorder.stage_timings.get("stage3_ai_boardroom", {})
        if st3:
            print(f"  Stage 3 (AI Boardroom):    {st3.get('duration', 0.0):.3f}s | rem_before={st3.get('remaining_before', 0.0):.2f}s | rem_after={st3.get('remaining_after', 0.0):.2f}s")
            par_p = timing_recorder.parallel_perspectives_timing or {}
            print(f"    - Parallel Perspectives Wall Duration: {par_p.get('duration', 0.0):.3f}s")
            for ptype in ("growth", "finance", "customer", "risk"):
                pt_timing = timing_recorder.perspective_timings.get(ptype, {})
                print(f"      * Perspective [{ptype.upper():8s}]: {pt_timing.get('duration', 0.0):.3f}s")
            dis_timing = timing_recorder.disagreement_timing or {}
            print(f"    - Disagreement Detection Duration: {dis_timing.get('duration', 0.0):.4f}s (Disagreements found: {dis_timing.get('count', 0)})")
            synth_timing = timing_recorder.synthesis_timing or {}
            print(f"    - Board Synthesis Duration: {synth_timing.get('duration', 0.0):.3f}s")
        else:
            print("  Stage 3 (AI Boardroom):    N/A (not reached or failed before start)")

        print("\n--- LLM Telemetry Summary ---")
        print(f"Total LLM Calls: {len(recorded_llm_calls)}")
        cumulative_vertex_time = sum(
            c.get("diagnostic", {}).get("call_duration_seconds", c["duration"])
            if c.get("diagnostic")
            else c["duration"]
            for c in recorded_llm_calls
        )
        cumulative_llm_time = sum(
            c.get("diagnostic", {}).get("total_duration_seconds", c["duration"])
            if c.get("diagnostic")
            else c["duration"]
            for c in recorded_llm_calls
        )
        print(f"Cumulative Final-Attempt Vertex Time (includes overlap): {cumulative_vertex_time:.3f}s")
        print(f"Cumulative LLM Call Time (includes overlap): {cumulative_llm_time:.3f}s")

        llm_occupied_wall_time = telemetry_recorder.get_occupied_wall_time()
        print(f"LLM Occupied Wall Time (union of overlapping LLM intervals): {llm_occupied_wall_time:.3f}s")

        raw_non_llm = total_analysis_duration - llm_occupied_wall_time
        if -1e-4 <= raw_non_llm < 0.0:
            non_llm_wall_time = 0.0
        else:
            non_llm_wall_time = raw_non_llm
        print(f"Non-LLM/Inter-Stage Wall Time: {non_llm_wall_time:.2f}s")

        print("\n--- Per-Call Breakdown ---")
        sorted_calls = sorted(recorded_llm_calls, key=lambda c: c.get("call_id", c.get("call_index", 0)))
        for c in sorted_calls:
            d = c.get("diagnostic") or {}
            persp_str = f" ({c['perspective']})" if c.get("perspective") else ""
            val_cat_str = f" | val_cat={d['final_validation_category']}" if d.get("final_validation_category") else ""
            print(
                f"  Call #{c.get('call_id', c.get('call_index', '?'))} [{c['schema_name']}{persp_str}]: "
                f"wall_duration={c['duration']:.3f}s | "
                f"vertex={d.get('call_duration_seconds', c['duration']):.3f}s | "
                f"schema_build={d.get('schema_build_seconds', 0.0):.4f}s | "
                f"parse={d.get('parse_duration_seconds', 0.0):.4f}s | "
                f"total={d.get('total_duration_seconds', c['duration']):.3f}s | "
                f"attempt={d.get('attempt', 'N/A')} | "
                f"status={d.get('status', 'unknown')}"
                f"{val_cat_str}"
            )
        print("=" * 70 + "\n")

    if caught_error is not None:
        safe_error_cat = type(caught_error).__name__
        sanitized_detail = str(caught_error)
        if isinstance(caught_error, HTTPException):
            sanitized_detail = str(caught_error.detail)
        pytest.fail(
            f"Live analysis failed with HTTP {final_http_status} ({safe_error_cat}): {sanitized_detail}"
        )

    assert response is not None
    assert final_http_status == 200

    # 1. DecisionModel exists and matches contract
    assert response.decision_model is not None
    assert isinstance(response.decision_model, DecisionModel)
    assert len(response.decision_model.objectives) >= 1
    assert len(response.decision_model.variables) >= 1

    # 2. EvidencePackage exists and matches contract
    assert response.evidence_package is not None
    assert isinstance(response.evidence_package, EvidencePackage)
    pkg = response.evidence_package
    assert pkg.decision_model_id == response.decision_model.id

    # 3. Source IDs are unique
    source_ids = [s.id for s in pkg.sources]
    assert len(source_ids) == len(set(source_ids))
    source_id_set = set(source_ids)

    # 4. EvidenceItem.source_id references resolve
    item_id_set: Set[str] = set()
    for item in pkg.items:
        item_id_set.add(item.id)
        assert item.source_id in source_id_set

    # 5. ClaimEvidenceLink references resolve
    req_id_set = {r.id for r in pkg.requirements}
    for link in pkg.claim_links:
        assert link.evidence_item_id in item_id_set
        if link.requirement_id:
            assert link.requirement_id in req_id_set

    # 6. Source reliability_score remains strictly None
    for s in pkg.sources:
        assert s.reliability_score is None
    assert not hasattr(EvidencePackage, "reliability_score")

    # 7. ReasoningBoard exists and matches contract
    assert response.reasoning_board is not None
    assert isinstance(response.reasoning_board, ReasoningBoard)
    board = response.reasoning_board
    assert board.decision_model_id == response.decision_model.id
    assert board.evidence_package_id == response.evidence_package.id

    # 8. Exactly four canonical perspectives exist in order
    assert len(board.perspectives) == 4
    assert [p.perspective_type.value for p in board.perspectives] == [
        "growth",
        "finance",
        "customer",
        "risk",
    ]
    perspective_ids = {p.id for p in board.perspectives}
    assert len(perspective_ids) == 4

    # 9. All authoritative references validate across the three-artifact chain
    validate_reasoning_references(board, response.decision_model, response.evidence_package)

    # 10. Disagreements are structurally valid
    board_arg_ids = {a.id for p in board.perspectives for a in p.arguments}
    for d in board.disagreements:
        assert len(d.perspective_ids) >= 2
        for pid in d.perspective_ids:
            assert pid in perspective_ids
        for aid in d.argument_ids:
            assert aid in board_arg_ids
        assert len(d.positions) >= 2
        assert d.topic and d.topic.strip()

    # 11. Board synthesis references authoritative disagreements
    board_disagreement_ids = {d.id for d in board.disagreements}
    for did in board.synthesis.disagreement_ids:
        assert did in board_disagreement_ids

    # 12. No unsupported internal business metrics were invented
    assert not hasattr(board, "internal_metrics")

    # 13. No recommendation, resilience score, scenario, or what-if artifact was generated
    assert "recommendation" not in AnalysisResponse.model_fields
    assert not hasattr(response, "recommendation")
    assert not hasattr(board, "recommendation")
    assert not hasattr(board, "resilience_score")
    assert not hasattr(board, "scenario")
    assert not hasattr(board, "scenarios")
    assert not hasattr(board, "what_if")
    response_dict = response.model_dump()
    for forbidden in ("recommendation", "resilience_score", "scenario", "scenarios", "what_if"):
        assert forbidden not in response_dict
        assert forbidden not in response_dict["reasoning_board"]


def test_interval_union_accounting() -> None:
    """Offline test proving interval-union duration calculation across overlapping, non-overlapping, and nested cases."""
    # 1. User specified overlapping scenario:
    # [0, 10], [5, 15], [20, 25] -> union is [0, 15] (len 15) and [20, 25] (len 5) -> occupied = 20 (not 25)
    test_intervals_1 = [(0.0, 10.0), (5.0, 15.0), (20.0, 25.0)]
    assert compute_interval_union_duration(test_intervals_1) == pytest.approx(20.0)

    # 2. Non-overlapping intervals:
    # [0, 5], [10, 15], [20, 25] -> union is 5 + 5 + 5 = 15
    test_intervals_disjoint = [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)]
    assert compute_interval_union_duration(test_intervals_disjoint) == pytest.approx(15.0)

    # 3. Fully nested intervals:
    # [0, 30], [5, 15], [2, 25] -> union is [0, 30] -> occupied = 30
    test_intervals_nested = [(0.0, 30.0), (5.0, 15.0), (2.0, 25.0)]
    assert compute_interval_union_duration(test_intervals_nested) == pytest.approx(30.0)

    # 4. Adjacent (touching boundary) intervals:
    # [0, 10], [10, 20] -> union is [0, 20] -> occupied = 20
    test_intervals_adjacent = [(0.0, 10.0), (10.0, 20.0)]
    assert compute_interval_union_duration(test_intervals_adjacent) == pytest.approx(20.0)

    # 5. Out of order intervals:
    test_intervals_unsorted = [(20.0, 25.0), (0.0, 10.0), (5.0, 15.0)]
    assert compute_interval_union_duration(test_intervals_unsorted) == pytest.approx(20.0)

    # 6. Empty / degenerate cases:
    assert compute_interval_union_duration([]) == 0.0
    assert compute_interval_union_duration([(5.0, 5.0), (10.0, 8.0)]) == 0.0


def test_live_telemetry_recorder_interval_union() -> None:
    """Offline test verifying LiveTelemetryRecorder tracks execution intervals and calculates occupied wall time."""
    thread_local = threading.local()

    class MockLLM:
        @property
        def last_diagnostic(self) -> Optional[Dict[str, Any]]:
            return getattr(thread_local, "diag", None)

    mock_llm = MockLLM()

    # Pre-defined timestamps: simulate two calls overlapping
    # Call 1: start=100.0, duration=10.0 -> end=110.0
    # Call 2: start=105.0, duration=10.0 -> end=115.0
    # Union should be [100.0, 115.0] = 15.0s, while sum of durations is 20.0s.
    recorder = LiveTelemetryRecorder(
        target_fn=lambda *a, **kw: None,
        llm_client=mock_llm,
        diagnostics_enabled=False,
    )
    recorder.recorded_calls = [
        {
            "call_id": 1,
            "schema_name": "SchemaA",
            "start_timestamp": 100.0,
            "end_timestamp": 110.0,
            "duration": 10.0,
            "success": True,
            "diagnostic": {"call_duration_seconds": 9.5, "attempt": 1, "status": "success"},
        },
        {
            "call_id": 2,
            "schema_name": "SchemaB",
            "start_timestamp": 105.0,
            "end_timestamp": 115.0,
            "duration": 10.0,
            "success": True,
            "diagnostic": {"call_duration_seconds": 9.2, "attempt": 1, "status": "success"},
        },
    ]

    intervals = recorder.get_execution_intervals()
    occupied = recorder.get_occupied_wall_time()
    assert len(intervals) == 2
    assert occupied == pytest.approx(15.0)

    # If total analysis wall time is 25.0s, non-LLM wall time = 25.0 - 15.0 = 10.0s (not 25 - 20 = 5.0s)
    analysis_wall_time = 25.0
    non_llm_time = analysis_wall_time - occupied
    assert non_llm_time == pytest.approx(10.0)


def test_live_telemetry_recorder_concurrency() -> None:
    """Offline test verifying LiveTelemetryRecorder assigns unique call IDs concurrently."""
    from pydantic import BaseModel

    class DummySchemaA(BaseModel):
        val: str

    class DummySchemaB(BaseModel):
        val: int

    thread_local = threading.local()

    class MockLLM:
        @property
        def last_diagnostic(self) -> Optional[Dict[str, Any]]:
            return getattr(thread_local, "diag", None)

    mock_llm = MockLLM()

    barrier = threading.Barrier(4)

    def mock_generate_structured(prompt: str, response_schema: Any, **kwargs: Any) -> Any:
        # Deterministically synchronize concurrent worker threads via barrier
        barrier.wait(timeout=5.0)
        thread_local.diag = {
            "call_duration_seconds": 0.01,
            "attempt": 1,
            "status": "success",
            "model": "mock-model",
            "location": "mock-loc",
        }
        return {"result": prompt}

    recorder = LiveTelemetryRecorder(
        target_fn=mock_generate_structured,
        llm_client=mock_llm,
        diagnostics_enabled=False,
    )

    num_concurrent_calls = 20
    schemas = [DummySchemaA, DummySchemaB]

    def worker(i: int) -> Any:
        schema = schemas[i % 2]
        return recorder(prompt=f"call_{i}", response_schema=schema)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, range(num_concurrent_calls)))

    assert len(results) == num_concurrent_calls
    assert len(recorder.recorded_calls) == num_concurrent_calls

    call_ids = [c["call_id"] for c in recorder.recorded_calls]
    assert len(call_ids) == len(set(call_ids)), "Call IDs must be strictly unique"
    assert set(call_ids) == set(range(1, num_concurrent_calls + 1)), "Call IDs must cover 1..N"

    for record in recorder.recorded_calls:
        assert "call_id" in record
        assert "call_index" in record
        assert record["call_id"] == record["call_index"]
        assert "schema_name" in record
        assert record["schema_name"] in ("DummySchemaA", "DummySchemaB")
        assert "start_timestamp" in record
        assert isinstance(record["start_timestamp"], float)
        assert "end_timestamp" in record
        assert isinstance(record["end_timestamp"], float)
        assert record["end_timestamp"] >= record["start_timestamp"]
        assert "duration" in record
        assert record["duration"] >= 0.0
        assert record["end_timestamp"] == pytest.approx(record["start_timestamp"] + record["duration"])
        assert record["success"] is True
        assert record["diagnostic"] is not None
        assert record["diagnostic"]["status"] == "success"
        assert record["diagnostic"]["attempt"] == 1


def test_live_telemetry_recorder_failure_and_duration() -> None:
    """Offline test verifying failure recording, sanitized status, and duration differences."""
    thread_local = threading.local()

    class MockLLM:
        @property
        def last_diagnostic(self) -> Optional[Dict[str, Any]]:
            return getattr(thread_local, "diag", None)

    mock_llm = MockLLM()

    def mock_failing_generate(prompt: str, **kwargs: Any) -> Any:
        time.sleep(0.015)
        thread_local.diag = {
            "call_duration_seconds": 0.005,  # Only the final attempt
            "attempt": 2,
            "status": "timeout",
        }
        raise RuntimeError("Simulated upstream timeout")

    recorder = LiveTelemetryRecorder(
        target_fn=mock_failing_generate,
        llm_client=mock_llm,
        diagnostics_enabled=False,
    )

    with pytest.raises(RuntimeError, match="Simulated upstream timeout"):
        recorder(prompt="test", response_schema=dict)

    assert len(recorder.recorded_calls) == 1
    rec = recorder.recorded_calls[0]
    assert rec["call_id"] == 1
    assert rec["success"] is False
    assert rec["duration"] >= 0.010  # Total wall-clock duration of whole generate_structured
    assert rec["diagnostic"]["call_duration_seconds"] == 0.005  # Final attempt duration
    assert rec["duration"] > rec["diagnostic"]["call_duration_seconds"]
    assert rec["diagnostic"]["status"] == "timeout"
    assert rec["diagnostic"]["attempt"] == 2


def test_pipeline_profiling_recorder_offline() -> None:
    """Offline test verifying PipelineTimingRecorder and SearchTelemetryRecorder with Fake components."""
    from app.services.llm.client import FakeLLMClient
    from app.services.evidence.search_provider import FakeSearchProvider, SearchResultItem
    from datetime import date

    fake_llm = FakeLLMClient()
    fake_item = SearchResultItem(
        title="Test Title",
        url="https://example.com/item",
        snippet="Test snippet for profiling test.",
        publisher="Test Journal",
        published_date=date(2024, 1, 1),
    )
    fake_search = FakeSearchProvider(default_results=[fake_item])
    search_recorder = SearchTelemetryRecorder(target_fn=fake_search.search)
    fake_search.search = search_recorder

    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=fake_search,
    )
    analysis_svc = AnalysisService(
        llm_client=fake_llm,
        evidence_service=evidence_svc,
        analysis_timeout_seconds=60.0,
    )

    deadline = time.monotonic() + 60.0
    timing_recorder = PipelineTimingRecorder(deadline_monotonic=deadline)

    orig_deconstruct = analysis_svc.engine.deconstruct
    def inst_deconstruct(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        res = orig_deconstruct(*args, **kwargs)
        t1 = time.monotonic()
        rem_after = deadline - time.monotonic()
        timing_recorder.record_stage("stage1_decision_framer", t0, t1, rem_before, rem_after)
        return res
    analysis_svc.engine.deconstruct = inst_deconstruct

    orig_build_ev = analysis_svc.evidence_service.build_evidence_package
    def inst_build_ev(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        res = orig_build_ev(*args, **kwargs)
        t1 = time.monotonic()
        rem_after = deadline - time.monotonic()
        timing_recorder.record_stage("stage2_evidence_engine", t0, t1, rem_before, rem_after)
        return res
    analysis_svc.evidence_service.build_evidence_package = inst_build_ev

    orig_build_board = analysis_svc.reasoning_service.build_reasoning_board
    def inst_build_board(*args: Any, **kwargs: Any) -> Any:
        rem_before = deadline - time.monotonic()
        t0 = time.monotonic()
        res = orig_build_board(*args, **kwargs)
        t1 = time.monotonic()
        rem_after = deadline - time.monotonic()
        timing_recorder.record_stage("stage3_ai_boardroom", t0, t1, rem_before, rem_after)
        return res
    analysis_svc.reasoning_service.build_reasoning_board = inst_build_board

    orig_eval_all = analysis_svc.reasoning_service.orchestrator.evaluate_all
    def inst_eval_all(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        res = orig_eval_all(*args, **kwargs)
        t1 = time.monotonic()
        timing_recorder.record_parallel_perspectives(t0, t1)
        return res
    analysis_svc.reasoning_service.orchestrator.evaluate_all = inst_eval_all

    orig_evaluate = analysis_svc.reasoning_service.orchestrator.reasoner.evaluate
    def inst_evaluate(ctx: Any, *args: Any, **kwargs: Any) -> Any:
        ptype = getattr(ctx.perspective.perspective_type, "value", str(ctx.perspective.perspective_type))
        t0 = time.monotonic()
        res = orig_evaluate(ctx, *args, **kwargs)
        t1 = time.monotonic()
        timing_recorder.record_perspective(ptype, t0, t1)
        return res
    analysis_svc.reasoning_service.orchestrator.reasoner.evaluate = inst_evaluate

    orig_detect_disagreements = reasoning_service_module.detect_disagreements
    def inst_detect(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        res = orig_detect_disagreements(*args, **kwargs)
        t1 = time.monotonic()
        timing_recorder.record_disagreements(t0, t1, len(res))
        return res
    reasoning_service_module.detect_disagreements = inst_detect

    orig_synthesize = analysis_svc.reasoning_service.synthesizer.synthesize
    def inst_synth(*args: Any, **kwargs: Any) -> Any:
        t0 = time.monotonic()
        res = orig_synthesize(*args, **kwargs)
        t1 = time.monotonic()
        timing_recorder.record_synthesis(t0, t1)
        return res
    analysis_svc.reasoning_service.synthesizer.synthesize = inst_synth

    try:
        req = AnalysisRequest(question="Offline test inquiry for pipeline timing?")
        resp = analysis_svc.analyze(req, deadline_monotonic=deadline)
        timing_recorder.record_completion(time.monotonic())
    finally:
        reasoning_service_module.detect_disagreements = orig_detect_disagreements

    # Validate timing metrics were captured
    assert "stage1_decision_framer" in timing_recorder.stage_timings
    assert "stage2_evidence_engine" in timing_recorder.stage_timings
    assert "stage3_ai_boardroom" in timing_recorder.stage_timings
    assert timing_recorder.stage_timings["stage1_decision_framer"]["duration"] >= 0.0
    assert timing_recorder.stage_timings["stage2_evidence_engine"]["duration"] >= 0.0
    assert timing_recorder.stage_timings["stage3_ai_boardroom"]["duration"] >= 0.0

    assert timing_recorder.parallel_perspectives_timing is not None
    assert timing_recorder.parallel_perspectives_timing["duration"] >= 0.0

    for ptype in ("growth", "finance", "customer", "risk"):
        assert ptype in timing_recorder.perspective_timings
        assert timing_recorder.perspective_timings[ptype]["duration"] >= 0.0

    assert timing_recorder.disagreement_timing is not None
    assert timing_recorder.synthesis_timing is not None
    assert timing_recorder.completion_remaining_deadline is not None
    assert timing_recorder.completion_remaining_deadline <= 60.0

    # Validate artifact
    assert resp.decision_model is not None
    assert resp.evidence_package is not None
    assert resp.reasoning_board is not None
    assert len(resp.reasoning_board.perspectives) == 4
    validate_reasoning_references(resp.reasoning_board, resp.decision_model, resp.evidence_package)
