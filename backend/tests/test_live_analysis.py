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
from app.services.analysis_service import AnalysisService
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.evidence.service import EvidenceService
from app.services.llm.gemini import GeminiLLMClient


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

                call_info: Dict[str, Any] = {
                    "call_id": call_id,
                    "call_index": call_id,
                    "schema_name": schema_name,
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

        with self._print_lock:
            if call_info["success"]:
                print(f"\n--- [LLM Call #{call_id}: {schema_name}] ---")
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
                else:
                    print("Diagnostic Vertex API Call Duration: N/A")
                    print("Diagnostic Attempt Number: N/A")
                print("-" * 45)
            else:
                print(f"\n--- [LLM Call #{call_id}: {schema_name} (FAILED)] ---")
                print(f"Total generate_structured Wall Time: {duration:.3f}s")
                if diag:
                    vertex_dur = diag.get("call_duration_seconds")
                    vertex_str = f"{vertex_dur:.3f}s" if isinstance(vertex_dur, (int, float)) else "N/A"
                    print(f"Final Diagnostic Vertex API Call Duration: {vertex_str}")
                    print(f"Final Diagnostic Attempt Number: {diag.get('attempt', 'N/A')}")
                    raw_status = str(diag.get("status", "unknown"))
                    sanitized_status = raw_status.split("\n")[0][:100]
                    print(f"Final Diagnostic Status: {sanitized_status}")
                else:
                    print("Final Diagnostic Vertex API Call Duration: N/A")
                    print("Final Diagnostic Attempt Number: N/A")
                    print("Final Diagnostic Status: N/A")
                print("-" * 45)


@pytest.mark.live_analysis
def test_live_end_to_end_analysis() -> None:
    """Performs a live, real end-to-end analysis using Gemini on Vertex AI and Brave Search.

    Validates structural invariants without asserting non-deterministic wording or rankings:
    - DecisionModel exists and is valid.
    - EvidencePackage exists and is valid.
    - Source IDs are unique.
    - EvidenceItem.source_id references resolve to Sources in the package.
    - ClaimEvidenceLink.evidence_item_id references resolve to EvidenceItems in the package.
    - ClaimEvidenceLink.requirement_id references resolve to Requirements in the package.
    - Source.reliability_score remains strictly None.
    - No recommendation field exists anywhere in schemas or responses.
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
    response = analysis_svc.analyze(
        request,
        deadline_monotonic=t_analysis_start + analysis_timeout,
    )
    total_analysis_duration = time.monotonic() - t_analysis_start

    if diagnostics_enabled:
        print("\n" + "=" * 65)
        print("--- AURA Live End-to-End Analysis Diagnostic Summary ---")
        print("=" * 65)
        print(f"Total Analysis Wall Time: {total_analysis_duration:.2f}s")
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
        # Clamp only tiny floating-point precision negatives to 0.0; do not mask genuine accounting errors.
        if -1e-4 <= raw_non_llm < 0.0:
            non_llm_wall_time = 0.0
        else:
            non_llm_wall_time = raw_non_llm
        print(f"Non-LLM/Inter-Stage Wall Time: {non_llm_wall_time:.2f}s")

        print("\nPer-Call Breakdown:")
        sorted_calls = sorted(recorded_llm_calls, key=lambda c: c.get("call_id", c.get("call_index", 0)))
        for c in sorted_calls:
            d = c.get("diagnostic") or {}
            print(
                f"  Call #{c.get('call_id', c.get('call_index', '?'))} [{c['schema_name']}]: "
                f"wall_duration={c['duration']:.3f}s | "
                f"vertex={d.get('call_duration_seconds', c['duration']):.3f}s | "
                f"schema_build={d.get('schema_build_seconds', 0.0):.4f}s | "
                f"parse={d.get('parse_duration_seconds', 0.0):.4f}s | "
                f"total={d.get('total_duration_seconds', c['duration']):.3f}s | "
                f"attempt={d.get('attempt', 'N/A')} | "
                f"status={d.get('status', 'unknown')}"
            )
        print("=" * 65 + "\n")

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
        # evidence_item_id resolves to an EvidenceItem in the package
        assert link.evidence_item_id in item_id_set
        # requirement_id resolves to an EvidenceRequirement in the package if present
        if link.requirement_id:
            assert link.requirement_id in req_id_set

    # 6. Source reliability_score remains strictly None in Day 3
    for s in pkg.sources:
        assert s.reliability_score is None
    assert not hasattr(EvidencePackage, "reliability_score")

    # 7. No recommendation field exists
    assert "recommendation" not in AnalysisResponse.model_fields
    assert not hasattr(response, "recommendation")
    response_dict = response.model_dump()
    assert "recommendation" not in response_dict
    assert "recommendation" not in response_dict["evidence_package"]


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
    import random
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

    def mock_generate_structured(prompt: str, response_schema: Any, **kwargs: Any) -> Any:
        # Simulate varying thread runtime and slight interleaving
        call_sleep = random.uniform(0.005, 0.02)
        time.sleep(call_sleep)
        thread_local.diag = {
            "call_duration_seconds": call_sleep,
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
        assert record["duration"] >= 0.004
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
