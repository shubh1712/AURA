"""AURA Day 4 — Phase 4.22: Tests for Evidence Mapping Batch-Size Tuning (batch_size=3).

Verifies:
1. Deterministic partitioning for item counts 0 through 12 with batch_size=3.
   Expected partition shapes:
   - 0 -> []
   - 1 -> [1]
   - 2 -> [2]
   - 3 -> [3]
   - 4 -> [3, 1]
   - 5 -> [3, 2]
   - 6 -> [3, 3]
   - 7 -> [3, 3, 1]
   - 8 -> [3, 3, 2]
   - 9 -> [3, 3, 3]
   - 10 -> [3, 3, 3, 1]
   - 11 -> [3, 3, 3, 2]
   - 12 -> [3, 3, 3, 3]
2. All scheduled items processed exactly once without loss or duplication.
3. Concurrency verification for 8 items across 3 concurrent batches using a deterministic threading.Barrier.
4. Stable final sequential ordering (evi_1, evi_2, ..., lnk_1, lnk_2, ...) independent of thread completion.
5. Correct batch-index diagnostics and thread-local isolation (no cross-request leakage).
6. Shared parent deadline propagation and fail-closed timeout behavior (no partial EvidencePackage).
"""

from datetime import date, datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional
import pytest

from app.schemas.decision_model import (
    ConfidenceLevel,
    DecisionModel,
)
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    EvidenceMapper,
    EvidenceMappingResult,
    EvidenceService,
    EVIDENCE_MAPPING_BATCH_SIZE,
    NormalizedSourceResult,
    SearchResultItem,
)
from app.services.llm.client import FakeLLMClient, LLMTimeoutError
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Test Fixtures & Helpers
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _create_requirement(
    req_id: str = "req_1",
    target_id: str = "asm_elasticity",
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
    description: str = "Empirical validation requirement for pricing elasticity.",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description=description,
        status=RequirementStatus.PENDING,
        suggested_queries=["saas pricing elasticity benchmark"],
    )


def _create_unique_source(
    idx: int,
    req_id: str = "req_1",
) -> NormalizedSourceResult:
    url = f"https://research.saasbenchmarks.com/study-{idx}"
    src = Source(
        id=f"src_{idx}",
        url=url,
        title=f"SaaS Study #{idx}",
        publisher="Benchmark Institute",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 1, 1),
    )
    search_item = SearchResultItem(
        url=url,
        title=f"SaaS Study #{idx}",
        snippet=f"Empirical study #{idx} found 14% customer acquisition increase from pricing discounts.",
        publisher="Benchmark Institute",
        published_date=date(2024, 1, 1),
        raw_content=f"Report #{idx}: Detailed findings indicate customer acquisition increased 14% with 20% discount.",
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query="saas pricing elasticity benchmark",
        source=src,
        search_result=search_item,
    )


# ------------------------------------------------------------------------------
# 1. Deterministic Partitioning Tests (0 through 12 items)
# ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "item_count,expected_shapes",
    [
        (0, []),
        (1, [1]),
        (2, [2]),
        (3, [3]),
        (4, [3, 1]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [3, 3, 1]),
        (8, [3, 3, 2]),
        (9, [3, 3, 3]),
        (10, [3, 3, 3, 1]),
        (11, [3, 3, 3, 2]),
        (12, [3, 3, 3, 3]),
    ],
)
def test_partitioning_counts_0_through_12(
    saas_decision_model: DecisionModel,
    item_count: int,
    expected_shapes: List[int],
) -> None:
    """Proves that EvidenceMapper with batch_size=3 partitions item counts 0..12 into expected shapes."""
    captured_prompts: List[str] = []

    class ShapeTrackingFakeLLM(FakeLLMClient):
        def generate_structured(self, prompt: str, response_schema: Any, **kwargs: Any) -> Any:
            captured_prompts.append(prompt)
            return super().generate_structured(prompt=prompt, response_schema=response_schema, **kwargs)

    fake_client = ShapeTrackingFakeLLM()
    mapper = EvidenceMapper(llm_client=fake_client)
    assert mapper.batch_size == 3

    req = _create_requirement()
    sources = [_create_unique_source(i) for i in range(1, item_count + 1)]

    res = mapper.map_evidence(saas_decision_model, [req], sources)

    assert len(captured_prompts) == len(expected_shapes)

    # Inspect source count in each prompt via actual <source ref="SOURCE_X"> blocks
    import re

    def _first_study_idx(p: str) -> int:
        m = re.search(r"study-(\d+)", p)
        return int(m.group(1)) if m else 0

    sorted_prompts = sorted(captured_prompts, key=_first_study_idx)
    actual_shapes = [len(re.findall(r'<source ref="SOURCE_\d+">', prompt)) for prompt in sorted_prompts]
    assert actual_shapes == expected_shapes

    # All items processed exactly once after deduplication
    assert len(res.items) == item_count
    assert len(res.claim_links) == item_count

    # Deterministic sequential IDs
    expected_evi_ids = [f"evi_{i}" for i in range(1, item_count + 1)]
    assert [item.id for item in res.items] == expected_evi_ids
    expected_lnk_ids = [f"lnk_{i}" for i in range(1, item_count + 1)]
    assert [link.id for link in res.claim_links] == expected_lnk_ids


# ------------------------------------------------------------------------------
# 2. Concurrency Verification for 8 Items (Barrier-Proven Synchronization)
# ------------------------------------------------------------------------------

def test_eight_items_three_batches_concurrent_barrier(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that 8 items partition into 3 batches [3, 3, 2] and execute concurrently on 3 workers.

    Uses a deterministic threading.Barrier(3) inside generate_structured to prove that all 3
    worker threads reach the barrier concurrently before any worker completes.
    """
    barrier = threading.Barrier(3, timeout=5.0)
    worker_threads_seen: set = set()
    lock = threading.Lock()

    class BarrierVerifyingLLM(FakeLLMClient):
        def generate_structured(self, prompt: str, response_schema: Any, **kwargs: Any) -> Any:
            with lock:
                worker_threads_seen.add(threading.current_thread().name)
            # All 3 worker threads must arrive at this barrier simultaneously
            barrier.wait()
            return super().generate_structured(prompt=prompt, response_schema=response_schema, **kwargs)

    client = BarrierVerifyingLLM()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 3
    assert mapper.batch_size == 3

    req = _create_requirement()
    sources = [_create_unique_source(i) for i in range(1, 9)]  # 8 items

    res = mapper.map_evidence(saas_decision_model, [req], sources)

    # Proves 3 distinct concurrent worker threads participated and rendezvoused at the barrier
    assert len(worker_threads_seen) == 3
    assert len(client.call_history) == 3

    # Confirm all 8 items and claim links are preserved in strict sequential order
    assert len(res.items) == 8
    assert len(res.claim_links) == 8
    assert [it.id for it in res.items] == [f"evi_{i}" for i in range(1, 9)]
    assert [lnk.id for lnk in res.claim_links] == [f"lnk_{i}" for i in range(1, 9)]

    # Confirm source-to-requirement lineage is completely preserved
    for i, it in enumerate(res.items, start=1):
        assert it.source_id == f"src_{i}"
        link = res.claim_links[i - 1]
        assert link.evidence_item_id == it.id
        assert link.target_entity_id == "asm_elasticity"
        assert link.requirement_id == "req_1"


# ------------------------------------------------------------------------------
# 3. Stable Ordering Across Non-Deterministic Thread Completion Order
# ------------------------------------------------------------------------------

def test_stable_ordering_with_out_of_order_completion(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that even if batch 2 finishes before batch 1 and batch 0, output order remains strictly sequential."""
    # Slower sleep for batch 0, medium for batch 1, fastest for batch 2
    delays = {
        "SOURCE_1": 0.04,  # In batch 0 (items 1..3)
        "SOURCE_4": 0.02,  # In batch 1 (items 4..6)
        "SOURCE_7": 0.001, # In batch 2 (items 7..8)
    }

    class DelayedFakeLLM(FakeLLMClient):
        def generate_structured(self, prompt: str, response_schema: Any, **kwargs: Any) -> Any:
            for s_ref, d in delays.items():
                if f'<source ref="{s_ref}">' in prompt:
                    time.sleep(d)
                    break
            return super().generate_structured(prompt=prompt, response_schema=response_schema, **kwargs)

    client = DelayedFakeLLM()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 3

    req = _create_requirement()
    sources = [_create_unique_source(i) for i in range(1, 9)]

    res = mapper.map_evidence(saas_decision_model, [req], sources)

    # Order must remain deterministic regardless of thread completion timing
    assert [it.id for it in res.items] == [f"evi_{i}" for i in range(1, 9)]
    assert [it.source_id for it in res.items] == [f"src_{i}" for i in range(1, 9)]
    assert [lnk.id for lnk in res.claim_links] == [f"lnk_{i}" for i in range(1, 9)]


# ------------------------------------------------------------------------------
# 4. Correct Batch-Index Diagnostics & Thread-Local Isolation
# ------------------------------------------------------------------------------

def test_batch_diagnostics_correctness_and_isolation(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that call-scoped batch diagnostics correctly index all batches and maintain thread isolation."""
    class DiagFakeLLM(FakeLLMClient):
        def generate_structured(self, prompt: str, response_schema: Any, **kwargs: Any) -> Any:
            # Emulate GeminiLLMClient diagnostic update
            self.last_diagnostic = {
                "status": "success",
                "attempt": 1,
                "prompt_len": len(prompt),
                "model": "gemini-3.8-flash",
            }
            return super().generate_structured(prompt=prompt, response_schema=response_schema, **kwargs)

    client = DiagFakeLLM()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 3

    req = _create_requirement()
    sources = [_create_unique_source(i) for i in range(1, 9)]

    mapper.map_evidence(saas_decision_model, [req], sources)

    diags = mapper.last_batch_diagnostics
    assert len(diags) == 3
    assert set(diags.keys()) == {0, 1, 2}
    for b_idx in (0, 1, 2):
        assert diags[b_idx]["status"] == "success"
        assert diags[b_idx]["attempt"] == 1
        assert diags[b_idx]["prompt_len"] > 0


# ------------------------------------------------------------------------------
# 5. Shared Parent Deadline & Fail-Closed Behavior (No Partial EvidencePackage)
# ------------------------------------------------------------------------------

def test_fail_closed_on_batch_timeout_no_partial_package(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that if any batch times out against the shared parent deadline, the operation fails closed without partial output."""
    class TimeoutOnBatch1FakeLLM(FakeLLMClient):
        def generate_structured(self, prompt: str, response_schema: Any, **kwargs: Any) -> Any:
            # Fail closed on batch index 1 (contains items 4, 5, 6)
            if "study-4" in prompt:
                raise LLMTimeoutError("Batch 1 timed out against parent analysis deadline.")
            return super().generate_structured(prompt=prompt, response_schema=response_schema, **kwargs)

    client = TimeoutOnBatch1FakeLLM()
    mapper = EvidenceMapper(llm_client=client)
    mapper.max_workers = 3

    req = _create_requirement()
    sources = [_create_unique_source(i) for i in range(1, 9)]

    with pytest.raises(LLMTimeoutError, match="Batch 1 timed out"):
        mapper.map_evidence(saas_decision_model, [req], sources)
