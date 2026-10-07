"""Unit and integration tests for Phase Day 3.1: Bounded Evidence-Mapping Latency.

Verifies:
1. Multiple mapping batches overlap when concurrency is enabled (proven via threading synchronization).
2. Concurrency is bounded to configured worker count N (active simultaneous calls <= N).
3. Deterministic merge ordering (later finishing batches do not alter original batch output order).
4. Shared parent deadline propagation (all workers receive exact parent deadline_monotonic).
5. Expired deadline before scheduling aborts with zero LLM requests.
6. Failure propagation preserves existing typed LLM errors (fail-closed).
7. Deterministic failure selection based on original batch index order (not completion race order).
8. Explicit mapping-work budget ceiling (total batches cannot exceed max_batches).
9. Budget boundary: exactly-at-limit inputs are fully processed.
10. Above-limit behavior: sources beyond budget are bounded deterministically without false completeness.
11. Single-batch execution: runs correctly without concurrency overhead.
12. Empty-source input returns empty mapping result immediately.
13. Grounding and provenance integrity preserved under concurrency.
14. Normal test suite executes 100% offline with zero network calls.
15. GeminiLLMClient diagnostic state is thread-safe and uncorrupted under concurrent execution.
"""

from datetime import date, datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional
import httpx
import pytest

from app.schemas.decision_model import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
)
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidenceRequirement,
    EvidenceStance,
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
    EVIDENCE_MAPPING_BATCH_SIZE,
    EvidenceMapper,
    EvidenceMappingResult,
    EvidenceRequirementEngine,
    EvidenceRetriever,
    EvidenceService,
    FakeSearchProvider,
    MAX_EVIDENCE_MAPPING_BATCHES,
    MAX_EVIDENCE_MAPPING_WORKERS,
    MAX_SOURCE_TEXT_CHARS,
    NormalizedSourceResult,
    SearchResultItem,
    SourceNormalizer,
)
from app.services.evidence.gaps import EvidenceGapDetector
from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    FakeLLMClient,
    LLMAuthenticationError,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Test Fixtures and Helpers
# ------------------------------------------------------------------------------

def _create_decision_model() -> DecisionModel:
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _create_requirement(
    req_id: str = "req_elasticity",
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical B2B SaaS price elasticity benchmarks.",
        status=RequirementStatus.PENDING,
        suggested_queries=["B2B SaaS price elasticity"],
    )


def _create_source(
    idx: int,
    req_id: str = "req_elasticity",
    snippet: str = "Benchmark finding reports 14% customer acquisition increase.",
    raw_content: Optional[str] = None,
) -> NormalizedSourceResult:
    url = f"https://example.com/source_{idx}"
    title = f"Source {idx} Benchmark Study"
    src = Source(
        id=f"src_{idx}",
        url=url,
        title=title,
        publisher="Benchmark Institute",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 1, 1),
    )
    search_item = SearchResultItem(
        url=url,
        title=title,
        snippet=snippet,
        publisher="Benchmark Institute",
        published_date=date(2024, 1, 1),
        raw_content=raw_content,
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query="B2B SaaS price elasticity",
        source=src,
        search_result=search_item,
    )


def _make_candidate_payload(
    source_ref: str = "SOURCE_1",
    target_entity_id: str = "asm_elasticity",
    content: str = "Finding shows 14% customer acquisition increase.",
    numeric_data: Optional[List[CandidateNumericEvidence]] = None,
) -> CandidateBatchEvidenceMappingPayload:
    return CandidateBatchEvidenceMappingPayload(
        findings=[
            CandidateFinding(
                source_ref=source_ref,
                target_entity_id=target_entity_id,
                content=content,
                summary="Empirical evidence finding.",
                stance=EvidenceStance.SUPPORTS,
                reasoning="Empirical observation aligns with assumption.",
                numeric_data=numeric_data or [],
                extraction_confidence=ConfidenceLevel.HIGH,
                relationship_confidence=ConfidenceLevel.MEDIUM,
            )
        ]
    )


# ------------------------------------------------------------------------------
# 1. Multiple Mapping Batches Overlap Under Concurrency
# ------------------------------------------------------------------------------

def test_01_multiple_mapping_batches_overlap_when_concurrent() -> None:
    """Proves that multiple mapping batches overlap in execution using a synchronization barrier."""
    barrier = threading.Barrier(2, timeout=5.0)
    overlap_occurred = threading.Event()

    class OverlappingLLMClient(MockLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            super().generate_structured(*args, **kwargs)
            # When 2 workers arrive at the barrier simultaneously, overlap is verified
            try:
                barrier.wait()
                overlap_occurred.set()
            except threading.BrokenBarrierError:
                pass
            return _make_candidate_payload()

    client = OverlappingLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 2
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1), _create_source(2)]

    result = mapper.map_evidence(dm, [req], sources)

    assert overlap_occurred.is_set(), "Batch workers did not overlap concurrently at the barrier"
    assert len(client.call_history) == 2
    assert len(result.items) == 2


# ------------------------------------------------------------------------------
# 2. Concurrency Is Bounded to Configured Worker Count N
# ------------------------------------------------------------------------------

def test_02_concurrency_is_bounded_to_configured_workers() -> None:
    """Proves that active simultaneous mapping calls never exceed the configured worker count N."""
    configured_workers = 2
    active_calls = 0
    max_active_observed = 0
    lock = threading.Lock()

    class BoundedLLMClient(MockLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal active_calls, max_active_observed
            super().generate_structured(*args, **kwargs)
            with lock:
                active_calls += 1
                if active_calls > max_active_observed:
                    max_active_observed = active_calls

            # Brief real yield to allow other worker threads to execute
            time.sleep(0.01)

            with lock:
                active_calls -= 1

            return _make_candidate_payload()

    client = BoundedLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = configured_workers
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(i) for i in range(1, 7)]  # 6 batches

    mapper.map_evidence(dm, [req], sources)

    assert max_active_observed <= configured_workers, (
        f"Active concurrent workers ({max_active_observed}) exceeded limit ({configured_workers})"
    )
    assert max_active_observed == configured_workers, "Expected concurrency up to worker limit"


# ------------------------------------------------------------------------------
# 3. Deterministic Merge Ordering Independent of Completion Race
# ------------------------------------------------------------------------------

def test_03_deterministic_merge_ordering_independent_of_completion_order() -> None:
    """Forces later batches to finish before earlier ones; proves output order follows original batch index."""
    batch_0_release = threading.Event()

    class InvertedOrderLLMClient(MockLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt") or args[0]
            super().generate_structured(*args, **kwargs)

            if "Source 1 Benchmark" in prompt:
                # Batch 0 delays until Batch 1 has completed
                batch_0_release.wait(timeout=5.0)
                return _make_candidate_payload(
                    content="Batch 0 content: first in original order."
                )
            else:
                # Batch 1 finishes first and signals Batch 0 to release
                payload = _make_candidate_payload(
                    content="Batch 1 content: finished first in wall-clock time."
                )
                batch_0_release.set()
                return payload

    client = InvertedOrderLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 2
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    s1 = _create_source(1, snippet="Source 1 Benchmark data.")
    s2 = _create_source(2, snippet="Source 2 Benchmark data.")

    result = mapper.map_evidence(dm, [req], [s1, s2])

    assert len(result.items) == 2
    # Item 1 must be from Batch 0, Item 2 from Batch 1, regardless of completion order
    assert result.items[0].id == "evi_1"
    assert "Batch 0 content" in result.items[0].content
    assert result.items[1].id == "evi_2"
    assert "Batch 1 content" in result.items[1].content


# ------------------------------------------------------------------------------
# 4. Shared Parent Deadline Propagation
# ------------------------------------------------------------------------------

def test_04_shared_parent_deadline_propagated_to_all_batches() -> None:
    """Proves every mapping call receives the exact same parent monotonic deadline."""
    client = MockLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 3
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1), _create_source(2), _create_source(3)]

    parent_deadline = time.monotonic() + 75.0
    mapper.map_evidence(dm, [req], sources, deadline_monotonic=parent_deadline)

    assert len(client.call_history) == 3
    for call in client.call_history:
        assert call["deadline_monotonic"] == parent_deadline


# ------------------------------------------------------------------------------
# 5. Expired Deadline Before Scheduling Makes Zero Calls
# ------------------------------------------------------------------------------

def test_05_expired_deadline_aborts_with_zero_calls() -> None:
    """Proves that an already-exhausted deadline triggers LLMTimeoutError with zero LLM calls."""
    client = MockLLMClient()
    mapper = EvidenceMapper(llm_client=client)

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1), _create_source(2)]

    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(LLMTimeoutError, match="Operation timed out"):
        mapper.map_evidence(dm, [req], sources, deadline_monotonic=expired_deadline)

    assert len(client.call_history) == 0


# ------------------------------------------------------------------------------
# 6. Failure Propagation Preserves Typed Error
# ------------------------------------------------------------------------------

def test_06_failure_propagation_preserves_typed_llm_error() -> None:
    """Proves that a typed LLM failure inside a worker propagates fail-closed to the caller."""
    client = MockLLMClient()
    client.register_error(LLMAuthenticationError("Invalid Vertex credentials (401)."))
    mapper = EvidenceMapper(llm_client=client)

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1), _create_source(2)]

    with pytest.raises(LLMAuthenticationError, match="Invalid Vertex credentials"):
        mapper.map_evidence(dm, [req], sources)


# ------------------------------------------------------------------------------
# 7. Deterministic Failure Selection Based on Original Batch Index
# ------------------------------------------------------------------------------

def test_07_deterministic_failure_ordering_based_on_batch_index() -> None:
    """If Batch 1 finishes earlier with an error and Batch 0 finishes later with a different error,
    the externally selected failure must strictly be Batch 0's error (lowest original index).
    """
    batch_0_release = threading.Event()

    class DualFailingLLMClient(MockLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt") or args[0]
            super().generate_structured(*args, **kwargs)

            if "Source 1 Benchmark" in prompt:
                # Batch 0 waits for Batch 1 to fail first, then fails with LLMAuthenticationError
                batch_0_release.wait(timeout=5.0)
                raise LLMAuthenticationError("Batch 0 Authentication Error")
            else:
                # Batch 1 fails immediately with LLMRateLimitError and signals Batch 0
                batch_0_release.set()
                raise LLMRateLimitError("Batch 1 Rate Limit Error")

    client = DualFailingLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 2
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    s1 = _create_source(1, snippet="Source 1 Benchmark finding.")
    s2 = _create_source(2, snippet="Source 2 Benchmark finding.")

    with pytest.raises(LLMAuthenticationError, match="Batch 0 Authentication Error"):
        mapper.map_evidence(dm, [req], [s1, s2])


# ------------------------------------------------------------------------------
# 8. Mapping-Work Budget Enforces Ceiling
# ------------------------------------------------------------------------------

def test_08_mapping_work_budget_enforces_ceiling() -> None:
    """Proves that total scheduled mapping work cannot exceed max_batches."""
    client = MockLLMClient()
    client.register_response(
        CandidateBatchEvidenceMappingPayload,
        _make_candidate_payload(),
    )
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_batches = 3
    mapper.batch_size = 5

    dm = _create_decision_model()
    req = _create_requirement()
    # 30 sources would normally produce 6 batches
    sources = [_create_source(i) for i in range(1, 31)]

    result = mapper.map_evidence(dm, [req], sources)

    # Must be bounded strictly to 3 batches
    assert len(client.call_history) == 3
    assert len(result.items) == 3


# ------------------------------------------------------------------------------
# 9. Budget Boundary: Exactly-At-Limit Input Fully Processed
# ------------------------------------------------------------------------------

def test_09_budget_boundary_exactly_at_limit_processed() -> None:
    """Proves that an input exactly matching max_batches is fully processed without truncation."""
    client = MockLLMClient()
    client.register_response(
        CandidateBatchEvidenceMappingPayload,
        _make_candidate_payload(),
    )
    mapper = EvidenceMapper(llm_client=client)
    assert mapper.max_batches == MAX_EVIDENCE_MAPPING_BATCHES  # 6
    assert mapper.batch_size == EVIDENCE_MAPPING_BATCH_SIZE    # 5

    dm = _create_decision_model()
    req = _create_requirement()
    # Exactly 30 sources = exactly 6 batches of 5
    sources = [_create_source(i) for i in range(1, 31)]

    result = mapper.map_evidence(dm, [req], sources)

    assert len(client.call_history) == 6
    assert len(result.items) == 6


# ------------------------------------------------------------------------------
# 10. Above-Limit Behavior: Sources Beyond Budget Are Honestly Bounded
# ------------------------------------------------------------------------------

def test_10_above_limit_sources_bounded_honestly_without_false_completeness() -> None:
    """Proves that when sources exceed max_batches, mapping bounds work to budget and
    downstream gap detection honestly marks unmapped requirements as UNSUPPORTED.
    """
    client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_batches = 2
    mapper.batch_size = 2

    dm = _create_decision_model()
    # Req 1 has sources in batches 1-2; Req 2 only has sources in batch 3 (beyond budget)
    req1 = _create_requirement("req_1", "asm_elasticity", DecisionEntityType.ASSUMPTION)
    req2 = _create_requirement("req_2", "var_monthly_churn", DecisionEntityType.VARIABLE)

    s1 = _create_source(1, req_id="req_1")
    s2 = _create_source(2, req_id="req_1")
    s3 = _create_source(3, req_id="req_1")
    s4 = _create_source(4, req_id="req_1")
    s5 = _create_source(5, req_id="req_2")  # Batch 3: dropped by budget
    s6 = _create_source(6, req_id="req_2")  # Batch 3: dropped by budget

    mapping_res = mapper.map_evidence(dm, [req1, req2], [s1, s2, s3, s4, s5, s6])

    # Exactly 2 batches mapped (4 sources)
    assert len(client.call_history) == 2

    # Verify downstream gap detector honestly detects that req_2 is UNSUPPORTED (no false completeness)
    gap_detector = EvidenceGapDetector()
    gap_res = gap_detector.detect_gaps(dm, [req1, req2], mapping_res)

    req2_evaluated = next(r for r in gap_res.requirements if r.id == "req_2")
    assert req2_evaluated.status == RequirementStatus.UNSUPPORTED
    req2_gaps = [g for g in gap_res.gaps if g.requirement_id == "req_2"]
    assert len(req2_gaps) == 1
    assert req2_gaps[0].gap_type == EvidenceGapType.UNSUPPORTED_CLAIM


# ------------------------------------------------------------------------------
# 11. Single-Batch Behavior Avoids Unnecessary Concurrency Overhead
# ------------------------------------------------------------------------------

def test_11_single_batch_behavior_executes_sequentially() -> None:
    """Single batch inputs should execute directly on caller thread without thread-pool overhead."""
    client = MockLLMClient()
    client.register_response(
        CandidateBatchEvidenceMappingPayload,
        _make_candidate_payload(),
    )
    mapper = EvidenceMapper(llm_client=client)

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1)]  # 1 source = 1 batch

    result = mapper.map_evidence(dm, [req], sources)

    assert len(client.call_history) == 1
    assert len(result.items) == 1
    assert result.items[0].id == "evi_1"
    assert result.claim_links[0].id == "lnk_1"


# ------------------------------------------------------------------------------
# 12. Empty-Source Behavior
# ------------------------------------------------------------------------------

def test_12_empty_sources_returns_empty_mapping_result() -> None:
    """Empty normalized sources list returns empty result immediately with zero calls."""
    client = MockLLMClient()
    mapper = EvidenceMapper(llm_client=client)

    dm = _create_decision_model()
    req = _create_requirement()

    result = mapper.map_evidence(dm, [req], [])

    assert result.items == []
    assert result.claim_links == []
    assert len(client.call_history) == 0


# ------------------------------------------------------------------------------
# 13. Grounding and Provenance Invariants Preserved Under Concurrency
# ------------------------------------------------------------------------------

def test_13_grounding_and_provenance_preserved_under_concurrency() -> None:
    """Verifies that numeric anti-hallucination validation and relational links
    remain strictly enforced per source under concurrent batch execution.
    """
    class ValidatingLLMClient(MockLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt") or args[0]
            if "Source 1" in prompt:
                # Valid grounded number: 14.0% is in snippet
                return _make_candidate_payload(
                    source_ref="SOURCE_1",
                    content="Reports 14% customer acquisition increase.",
                    numeric_data=[
                        CandidateNumericEvidence(metric_name="acquisition_rate", value=14.0, unit="%")
                    ],
                )
            else:
                # Hallucinated number: 99.0% is NOT in snippet
                return _make_candidate_payload(
                    source_ref="SOURCE_1",
                    content="Reports massive growth.",
                    numeric_data=[
                        CandidateNumericEvidence(metric_name="growth_rate", value=99.0, unit="%")
                    ],
                )

    client = ValidatingLLMClient()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 2
    mapper.batch_size = 1

    dm = _create_decision_model()
    req = _create_requirement()
    s1 = _create_source(1, snippet="Source 1: Observed 14% customer acquisition increase.")
    s2 = _create_source(2, snippet="Source 2: Observed steady baseline growth.")

    result = mapper.map_evidence(dm, [req], [s1, s2])

    assert len(result.items) == 2
    # Item 1 has validated NumericEvidence
    assert len(result.items[0].numeric_data) == 1
    assert result.items[0].numeric_data[0].value == 14.0
    # Item 2 has hallucinated number stripped
    assert len(result.items[1].numeric_data) == 0


# ------------------------------------------------------------------------------
# 14. Zero Network Calls During Testing
# ------------------------------------------------------------------------------

def test_14_zero_network_calls_guaranteed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that offline fake LLM operates with zero network socket activity."""
    def guarded_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Prohibited real network call during testing!")

    import socket
    monkeypatch.setattr(socket, "create_connection", guarded_connect)

    client = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=client)

    dm = _create_decision_model()
    req = _create_requirement()
    sources = [_create_source(1), _create_source(2)]

    result = mapper.map_evidence(dm, [req], sources)
    assert len(result.items) >= 1


# ------------------------------------------------------------------------------
# 15. GeminiLLMClient Diagnostic State Is Concurrency-Safe
# ------------------------------------------------------------------------------

def test_15_gemini_client_diagnostic_state_is_concurrency_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that multiple concurrent calls to the same GeminiLLMClient instance
    maintain thread-isolated last_diagnostic entries without cross-thread corruption.
    """
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")

    # Mock interactions.create to simulate concurrent execution with distinct durations
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(
        project="aura-test-project",
        location="us-central1",
        http_client=http_client,
    )

    valid_json = _create_decision_model().model_dump_json()
    barrier = threading.Barrier(2, timeout=5.0)
    thread_diagnostics: Dict[str, Any] = {}

    def custom_create(**kwargs: Any) -> Any:
        barrier.wait()
        prompt_text = str(kwargs.get("input", ""))
        if "worker_slow" in prompt_text:
            time.sleep(0.06)
        else:
            time.sleep(0.01)
        return {"output_text": valid_json}

    client._get_genai_client().interactions.create = custom_create

    def worker_action(worker_name: str) -> None:
        try:
            client.generate_structured(
                prompt=f"Decision prompt from {worker_name}",
                response_schema=DecisionModel,
            )
            # Read diagnostic from the worker thread
            diag = client.last_diagnostic
            if diag:
                thread_diagnostics[worker_name] = dict(diag)
        except Exception as e:
            thread_diagnostics[worker_name] = {"error": str(e)}

    t1 = threading.Thread(target=worker_action, args=("worker_fast",))
    t2 = threading.Thread(target=worker_action, args=("worker_slow",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert "worker_fast" in thread_diagnostics
    assert "worker_slow" in thread_diagnostics

    diag_fast = thread_diagnostics["worker_fast"]
    diag_slow = thread_diagnostics["worker_slow"]

    assert diag_fast.get("status") == "success"
    assert diag_slow.get("status") == "success"
    # User prompt chars recorded in each thread must match that thread's prompt
    assert diag_fast.get("user_prompt_chars") == len("Decision prompt from worker_fast")
    assert diag_slow.get("user_prompt_chars") == len("Decision prompt from worker_slow")
    # Call duration for worker_slow must be strictly greater than worker_fast
    assert diag_slow.get("call_duration_seconds", 0) > diag_fast.get("call_duration_seconds", 0)
