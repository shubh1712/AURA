"""Phase 4.41: Single Authorized Live End-to-End Analysis Job Execution.

Executes exactly ONE live analysis job through the asynchronous API pipeline:
- Parent analysis timeout: 180 seconds.
- Framer operation ceiling: 75 seconds.
- Downstream LLM operation ceilings: 60 seconds.
- HTTP attempt timeout: 30 seconds.
- Live Gemini 3.8 Flash on Vertex AI & real Brave Search.

Never logs secrets, credentials, or raw sensitive provider payloads.
"""

import json
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.job import (
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    JobStatus,
    PipelineStage,
)
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningBoard,
    validate_reasoning_references,
)
from app.services.analysis_service import AnalysisService
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.evidence.service import EvidenceService
from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.gemini import GeminiLLMClient
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aura.phase441")


class TelemetryCollector:
    """Collects LLM, search, and pipeline timing telemetry without logging secrets."""

    def __init__(self, deadline_monotonic: float):
        self.deadline_monotonic = deadline_monotonic
        self._lock = threading.Lock()
        self.llm_calls: List[Dict[str, Any]] = []
        self.search_calls: List[Dict[str, Any]] = []
        self.stage_timings: Dict[str, Dict[str, float]] = {}
        self.perspective_timings: Dict[str, float] = {}
        self.disagreements_count: int = 0
        self.disagreement_duration: float = 0.0
        self.synthesis_duration: float = 0.0

    def record_llm(
        self,
        schema_name: str,
        duration: float,
        success: bool,
        error_name: Optional[str] = None,
        diagnostic: Optional[Dict[str, Any]] = None,
    ):
        with self._lock:
            self.llm_calls.append({
                "call_id": len(self.llm_calls) + 1,
                "schema": schema_name,
                "duration": duration,
                "success": success,
                "error": error_name,
                "attempts": diagnostic.get("attempts_count", 1) if diagnostic else 1,
            })

    def record_search(self, duration: float, result_count: int, success: bool):
        with self._lock:
            self.search_calls.append({
                "duration": duration,
                "result_count": result_count,
                "success": success,
            })

    def record_stage(self, stage_name: str, start: float, end: float):
        with self._lock:
            self.stage_timings[stage_name] = {
                "start": start,
                "end": end,
                "duration": end - start,
                "remaining_at_end": self.deadline_monotonic - end,
            }

    def record_perspective(self, ptype: str, duration: float):
        with self._lock:
            self.perspective_timings[ptype] = duration


def run_single_authorized_live_job():
    logger.info("=== Phase 4.41: Single Authorized Live Job Preflight ===")

    # 1. Verify credentials presence (without logging secrets)
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or settings.GOOGLE_CLOUD_PROJECT
    )
    brave_key = (
        os.environ.get("BRAVE_SEARCH_API_KEY")
        or settings.BRAVE_SEARCH_API_KEY
    )
    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or settings.GOOGLE_CLOUD_LOCATION
        or "global"
    )

    if not project or not brave_key:
        logger.error("Missing required credentials in environment. Aborting.")
        sys.exit(1)

    logger.info("Preflight OK: Vertex AI Project and Brave Search configured.")
    logger.info("Configured timeouts: Parent=180s, Framer=75s, Downstream LLM=60s, HTTP Attempt=30s.")

    # 2. Wire Live Providers & Telemetry
    t_global_start = time.monotonic()
    parent_deadline = t_global_start + 180.0
    telemetry = TelemetryCollector(deadline_monotonic=parent_deadline)

    real_llm = GeminiLLMClient(project=project.strip(), location=location.strip())
    orig_generate_structured = real_llm.generate_structured

    def instrumented_generate_structured(prompt: str, response_schema: Any, *args, **kwargs):
        schema_name = getattr(response_schema, "__name__", str(response_schema))
        t0 = time.monotonic()
        success = False
        err_name = None
        diag = None
        try:
            result = orig_generate_structured(prompt, response_schema, *args, **kwargs)
            success = True
            return result
        except Exception as e:
            err_name = type(e).__name__
            raise
        finally:
            t1 = time.monotonic()
            # If the client stored diagnostic on the object, capture it
            diag = getattr(real_llm, "_last_call_diagnostic", None)
            telemetry.record_llm(schema_name, t1 - t0, success, err_name, diag)

    real_llm.generate_structured = instrumented_generate_structured

    real_search = BraveSearchProvider(api_key=brave_key.strip())
    orig_search = real_search.search

    def instrumented_search(query: str, *args, **kwargs):
        t0 = time.monotonic()
        success = False
        res_count = 0
        try:
            results = orig_search(query, *args, **kwargs)
            success = True
            res_count = len(results)
            return results
        finally:
            t1 = time.monotonic()
            telemetry.record_search(t1 - t0, res_count, success)

    real_search.search = instrumented_search

    real_evidence_svc = EvidenceService.create_default(
        llm_client=real_llm,
        search_provider=real_search,
    )

    def service_factory():
        svc = AnalysisService(
            llm_client=real_llm,
            evidence_service=real_evidence_svc,
            analysis_timeout_seconds=180.0,
            framer_operation_timeout_seconds=75.0,
        )
        return svc

    # 3. Initialize SQLite Job Storage & Manager
    db_file = "live_phase441_jobs.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass

    storage = SQLiteJobStorage(db_path=db_file)
    manager = AnalysisJobManager(
        storage=storage,
        service_factory=service_factory,
        max_workers=1,
        default_timeout_seconds=180.0,
    )

    # 4. Submit EXACTLY ONE Live Job
    canonical_question = "Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    job_req = AnalysisJobCreateRequest(
        question=canonical_question,
        timeout_seconds=180.0,
        framer_operation_timeout_seconds=75.0,
    )

    logger.info("Submitting single authorized live job to AnalysisJobManager...")
    job_created: AnalysisJobStatusResponse = manager.submit_job(job_req)
    job_id = job_created.job_id
    logger.info("Job successfully created: job_id=%s, status=%s, stage=%s", job_id, job_created.status.value, job_created.stage.value)

    # 5. Poll Job Lifecycle
    t_start = time.monotonic()
    last_stage = None
    stage_transitions: List[Tuple[float, str, str]] = []
    final_status_resp: Optional[AnalysisJobStatusResponse] = None

    while True:
        elapsed = time.monotonic() - t_start
        status_resp = manager.get_job_status(job_id)

        if status_resp.stage.value != last_stage:
            stage_transitions.append((elapsed, status_resp.status.value, status_resp.stage.value))
            logger.info(
                "[Elapsed %6.2fs] Status: %-9s | Stage: %-25s | Msg: %s",
                elapsed,
                status_resp.status.value,
                status_resp.stage.value,
                status_resp.progress_message or "",
            )
            last_stage = status_resp.stage.value

        if status_resp.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT):
            final_status_resp = status_resp
            break

        if elapsed >= 210.0:  # Hard safety ceiling (parent timeout 180s + 30s buffer)
            logger.error("Polling safety ceiling reached (210s).")
            final_status_resp = status_resp
            break

        time.sleep(2.0)

    t_end = time.monotonic()
    total_duration = t_end - t_start
    logger.info("Job terminal state reached in %.2f seconds.", total_duration)

    # 6. Retrieve Result & Validate
    result_payload: Optional[AnalysisResponse] = None
    retrieval_http_status = 200
    retrieval_error = None

    if final_status_resp and final_status_resp.status == JobStatus.SUCCEEDED:
        try:
            result_payload = manager.get_job_result(job_id)
            retrieval_http_status = 200
        except HTTPException as he:
            retrieval_http_status = he.status_code
            retrieval_error = he.detail
    elif final_status_resp and final_status_resp.status == JobStatus.TIMED_OUT:
        retrieval_http_status = 504
        retrieval_error = final_status_resp.error
    else:
        retrieval_http_status = (final_status_resp.error_status_code if final_status_resp else 500) or 500
        retrieval_error = final_status_resp.error if final_status_resp else "Unknown failure"

    # 7. Print Comprehensive Telemetry & Validation Report
    print("\n" + "=" * 78)
    print("           AURA Phase 4.41: Live Analysis Execution Report")
    print("=" * 78)
    print(f"Job ID:               {job_id}")
    print(f"Final Job Status:     {final_status_resp.status.value if final_status_resp else 'UNKNOWN'}")
    print(f"Final Pipeline Stage: {final_status_resp.stage.value if final_status_resp else 'UNKNOWN'}")
    print(f"Retrieval HTTP Code:  {retrieval_http_status}")
    print(f"Total Wall Time:      {total_duration:.2f}s (Budget: 180.0s)")

    print("\n--- Lifecycle Stage Transitions ---")
    for t_sec, st, stage in stage_transitions:
        print(f"  + {t_sec:6.2f}s -> Status: {st:<9s} | Stage: {stage}")

    print("\n--- LLM Telemetry (Vertex AI Gemini 3.8 Flash) ---")
    print(f"Total LLM Calls: {len(telemetry.llm_calls)}")
    for call in telemetry.llm_calls:
        status_sym = "PASS" if call["success"] else f"FAIL ({call['error']})"
        print(f"  Call #{call['call_id']:2d} | Schema: {call['schema']:<30s} | {call['duration']:6.2f}s | {status_sym} (attempts: {call['attempts']})")

    print("\n--- Brave Search Telemetry ---")
    print(f"Total Search Queries: {len(telemetry.search_calls)}")
    for i, sc in enumerate(telemetry.search_calls, 1):
        print(f"  Search #{i:2d} | Duration: {sc['duration']:5.2f}s | Results: {sc['result_count']}")

    # 8. Schema & Referential Integrity Verification
    validation_passed = False
    ref_integrity_passed = False
    perspectives_found: List[str] = []

    if result_payload:
        print("\n--- Canonical Artifact Validation ---")
        try:
            # Check Pydantic validation
            assert isinstance(result_payload, AnalysisResponse)
            print("  [x] AnalysisResponse root schema: VALID")

            assert result_payload.decision_model is not None
            print(f"  [x] DecisionModel: VALID (id={result_payload.decision_model.id})")

            assert result_payload.evidence_package is not None
            pkg = result_payload.evidence_package
            print(f"  [x] EvidencePackage: VALID (id={pkg.id}, sources={len(pkg.sources)}, items={len(pkg.items)})")

            assert result_payload.reasoning_board is not None
            board = result_payload.reasoning_board
            print(f"  [x] ReasoningBoard: VALID (id={board.id})")

            # Check 4 canonical perspectives
            perspectives_found = [p.perspective_type.value for p in board.perspectives]
            print(f"  [x] Perspectives Present ({len(board.perspectives)}): {', '.join(perspectives_found)}")
            assert set(perspectives_found) == {"growth", "finance", "customer", "risk"}
            assert len(board.perspectives) == 4
            print("  [x] Canonical 4 Perspectives (Growth, Finance, Customer, Risk): EXACT MATCH")

            # Check Disagreements and Synthesis
            print(f"  [x] Disagreements Found: {len(board.disagreements)}")
            for d in board.disagreements:
                print(f"      - [{d.id}] '{d.topic}' ({d.nature.value})")

            print(f"  [x] Board Synthesis: VALID")
            print(f"      - Areas of Agreement: {len(board.synthesis.areas_of_agreement)}")
            print(f"      - Critical Assumptions: {len(board.synthesis.critical_assumption_ids)}")
            print(f"      - Critical Evidence Gaps: {len(board.synthesis.critical_evidence_gap_ids)}")
            print(f"      - Evidence-Sensitive Points: {len(board.synthesis.evidence_sensitive_points)}")
            print(f"      - Unresolved Questions: {len(board.synthesis.unresolved_questions)}")

            # Check cross-artifact referential integrity
            validate_reasoning_references(
                decision_model=result_payload.decision_model,
                evidence_package=result_payload.evidence_package,
                reasoning_board=board,
            )
            print("  [x] Cross-Artifact Referential Integrity (validate_reasoning_references): ZERO ERRORS")
            ref_integrity_passed = True
            validation_passed = True

        except Exception as val_err:
            logger.error("Validation error: %s", val_err, exc_info=True)
            validation_passed = False

    print("\n" + "=" * 78)
    if validation_passed and ref_integrity_passed and retrieval_http_status == 200:
        print("                 FINAL RESULT: LIVE END-TO-END SUCCESS")
    else:
        print(f"                 FINAL RESULT: LIVE EXECUTION FAILED ({retrieval_error})")
    print("=" * 78 + "\n")

    manager.shutdown(wait=True)
    storage.close()

    # Save summary data to json for reporting
    summary_data = {
        "job_id": job_id,
        "status": final_status_resp.status.value if final_status_resp else "UNKNOWN",
        "stage": final_status_resp.stage.value if final_status_resp else "UNKNOWN",
        "http_status": retrieval_http_status,
        "total_duration_seconds": total_duration,
        "validation_passed": validation_passed,
        "ref_integrity_passed": ref_integrity_passed,
        "perspectives": perspectives_found,
        "llm_calls_count": len(telemetry.llm_calls),
        "search_calls_count": len(telemetry.search_calls),
        "error": retrieval_error,
    }
    with open("live_phase441_summary.json", "w") as f:
        json.dump(summary_data, f, indent=2)

    return summary_data


if __name__ == "__main__":
    run_single_authorized_live_job()
