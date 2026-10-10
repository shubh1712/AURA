"""Deterministic tests reproducing EvidenceMapper scheduling dynamics under Phase 4.26 audit."""

import concurrent.futures
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

class FakeSchedulerProbe:
    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def record_call(self, batch_idx: int, worker_name: str, start_t: float, end_t: float, status: str):
        with self.lock:
            self.call_history.append({
                "batch_idx": batch_idx,
                "worker": worker_name,
                "start": start_t,
                "end": end_t,
                "duration": end_t - start_t,
                "status": status,
            })

def test_four_batches_three_workers_simulation():
    """Simulates 4 batches with max_workers=3 where batch 0 stalls, and batches 1, 2, 3 are fast."""
    probe = FakeSchedulerProbe()
    t_start = time.monotonic()

    # Batch behavior:
    # Batch 0: stalls for 0.60s (simulating 60s)
    # Batch 1: fast 0.15s (simulating 15s)
    # Batch 2: fast 0.18s (simulating 18s)
    # Batch 3: fast 0.24s (simulating 24s)
    durations = {0: 0.60, 1: 0.15, 2: 0.18, 3: 0.24}
    statuses = {0: "timeout", 1: "success", 2: "success", 3: "success"}

    def worker_job(batch_idx: int):
        thread_name = threading.current_thread().name
        t0 = time.monotonic()
        time.sleep(durations[batch_idx])
        t1 = time.monotonic()
        status = statuses[batch_idx]
        probe.record_call(batch_idx, thread_name, t0 - t_start, t1 - t_start, status)
        if status == "timeout":
            raise TimeoutError(f"Batch {batch_idx} timed out")
        return f"result_{batch_idx}"

    max_workers = 3
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    try:
        for idx in range(4):
            fut = executor.submit(worker_job, idx)
            futures[fut] = idx

        done, not_done = concurrent.futures.wait(
            futures.keys(),
            timeout=1.20,
            return_when=concurrent.futures.ALL_COMPLETED,
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    print("--- 4 Batches / 3 Workers Simulation Results ---")
    for call in sorted(probe.call_history, key=lambda x: x["end"]):
        print(f"Batch {call['batch_idx']}: start={call['start']:.3f}s | end={call['end']:.3f}s | dur={call['duration']:.3f}s | worker={call['worker']} | status={call['status']}")

    # Assertions
    assert len(done) == 4
    # Batch 3 should start around when the fastest batch (Batch 1, 0.15s) finishes
    b1 = next(c for c in probe.call_history if c["batch_idx"] == 1)
    b3 = next(c for c in probe.call_history if c["batch_idx"] == 3)
    print(f"Batch 1 ended at {b1['end']:.3f}s; Batch 3 started at {b3['start']:.3f}s")
    assert abs(b3["start"] - b1["end"]) < 0.05, "Batch 3 should start immediately after Batch 1 frees a worker!"
    print("Verification passed successfully!")

if __name__ == "__main__":
    test_four_batches_three_workers_simulation()
