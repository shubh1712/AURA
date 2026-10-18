"""AURA Deterministic Mock Backend Server for End-to-End Integration & UI Testing.

Runs the real FastAPI application on http://127.0.0.1:8000 with offline fake providers
(FakeLLMClient and FakeSearchProvider) and realistic stage progression timings.
Zero live external API calls are made.
"""

import os
import sys
import time
from typing import Any, Optional
import uvicorn
from fastapi import HTTPException, status

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.evidence import FakeSearchProvider, SearchResultItem
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import FakeLLMClient


def create_deterministic_analysis_service(
    stage_delay_seconds: float = 1.0,
    fail_status: Optional[int] = None,
) -> AnalysisService:
    """Builds an offline AnalysisService using FakeLLMClient and FakeSearchProvider."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(
        default_results=[
            SearchResultItem(
                url="https://example.com/vldb-distributed-sql-2024",
                title="Distributed Transaction Benchmarks at Hyperscale (VLDB 2024)",
                snippet="Multi-Raft storage engines achieve 65,000 write ops/sec across 5 nodes.",
            )
        ]
    )
    svc = AnalysisService(
        llm_client=fake_llm,
        search_provider=fake_search,
        analysis_timeout_seconds=120.0,
    )

    orig_analyze = svc.analyze

    def paced_analyze(request: AnalysisRequest, *args: Any, **kwargs: Any) -> AnalysisResponse:
        stage_cb = kwargs.get("stage_callback")

        if stage_cb:
            stage_cb("stage1_decision_framer")
        time.sleep(stage_delay_seconds)

        if stage_cb:
            stage_cb("stage2_evidence_engine")
        time.sleep(stage_delay_seconds)

        if fail_status:
            if fail_status == 504:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Decision analysis timed out while evaluating inquiry.",
                )
            raise HTTPException(
                status_code=fail_status,
                detail=f"Simulated execution error HTTP {fail_status}",
            )

        if stage_cb:
            stage_cb("stage3_ai_boardroom")
        time.sleep(stage_delay_seconds)

        return orig_analyze(request, *args, **kwargs)

    svc.analyze = paced_analyze
    return svc


def setup_mock_backend():
    storage = SQLiteJobStorage(db_path="mock_dev_jobs.db")
    service_factory = lambda: create_deterministic_analysis_service(stage_delay_seconds=1.2)
    manager = AnalysisJobManager(
        storage=storage,
        service_factory=service_factory,
        max_workers=2,
        default_timeout_seconds=60.0,
    )
    app.dependency_overrides[get_job_manager] = lambda: manager
    return manager


if __name__ == "__main__":
    manager = setup_mock_backend()
    print("Starting AURA Deterministic Mock Backend on http://127.0.0.1:8000...")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    finally:
        manager.shutdown(wait=True)
