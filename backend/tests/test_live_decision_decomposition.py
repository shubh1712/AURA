"""Opt-in live benchmark test for DecisionModel structured generation latency.

Measures whether DecisionModel deconstruction alone succeeds within production
timeout constraints (45.0s per-request, 60.0s operation deadline) on Vertex AI
without running Brave Search or the full analysis pipeline.

Excluded by default from normal test runs. To execute explicitly:
    RUN_LIVE_DECOMPOSITION_TEST=1 pytest tests/test_live_decision_decomposition.py -m live_decomposition -v -s

Requirements:
    RUN_LIVE_DECOMPOSITION_TEST=1
    GOOGLE_CLOUD_PROJECT (configured via environment, .env, or ADC)

Properties:
- Production GeminiLLMClient initialization (enterprise=True, ADC, location="global").
- Same question as test_live_analysis.py.
- Same DecisionModel response schema.
- Same DECOMPOSITION_SYSTEM_PROMPT instruction.
- Strictly ONE attempt (max_retries=0) to isolate single-call latency.
- Strict production 45s request timeout and 60s operation deadline.
- Zero Brave Search or EvidenceService dependencies.
- Never prints credentials or authorization headers.
"""

import os
import time
import pytest

from app.config import settings
from app.schemas.decision_model import DecisionModel
from app.services.llm.client import LLMConfig
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
    build_decomposition_prompt,
)


@pytest.mark.live_decomposition
def test_live_decision_decomposition_latency() -> None:
    """Benchmark single-request live DecisionModel structured generation on Vertex AI."""
    run_flag = os.environ.get("RUN_LIVE_DECOMPOSITION_TEST", "").strip() == "1"
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or getattr(settings, "GOOGLE_CLOUD_PROJECT", None)
        or os.environ.get("GCP_PROJECT")
    )
    if not run_flag or not project or not str(project).strip():
        pytest.skip(
            "RUN_LIVE_DECOMPOSITION_TEST=1 and GOOGLE_CLOUD_PROJECT are required for live decomposition benchmark."
        )

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or getattr(settings, "GOOGLE_CLOUD_LOCATION", None)
        or "global"
    )

    client = GeminiLLMClient(
        project=str(project).strip(),
        location=str(location).strip(),
    )

    prompt = build_decomposition_prompt(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )

    # Strictly 1 attempt, existing 45s per-request limit, 60s operation deadline
    benchmark_config = LLMConfig(
        timeout_seconds=45.0,
        operation_timeout_seconds=60.0,
        max_retries=0,
    )

    start_time = time.monotonic()
    result = client.generate_structured(
        prompt=prompt,
        response_schema=DecisionModel,
        system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
        config=benchmark_config,
    )
    duration = time.monotonic() - start_time

    # Diagnostic reporting (lengths, timings, model, location only - zero credentials or complete prompts)
    diag = getattr(client, "last_diagnostic", None)
    if diag:
        print(f"\n--- Live DecisionModel Decomposition Benchmark Report ---")
        print(f"Model: {diag.get('model')}")
        print(f"Location: {diag.get('location')}")
        print(f"Schema Build Duration: {diag.get('schema_build_seconds', 0.0):.4f}s")
        print(f"Serialized Schema Chars: {diag.get('schema_chars')}")
        print(f"System Prompt Chars: {diag.get('system_prompt_chars')}")
        print(f"User Prompt Chars: {diag.get('user_prompt_chars')}")
        print(f"Vertex interactions.create Duration: {diag.get('call_duration_seconds', 0.0):.3f}s")
        print(f"Parse & Validation Duration: {diag.get('parse_duration_seconds', 0.0):.4f}s")
        print(f"Total Duration: {diag.get('total_duration_seconds', 0.0):.3f}s")
        print(f"Attempt: {diag.get('attempt')}")
        print(f"----------------------------------------------------------")

    assert isinstance(result, DecisionModel)
    assert len(result.objectives) >= 1
    assert any(o.is_primary for o in result.objectives)
    assert len(result.variables) >= 1
    assert len(result.tradeoffs) >= 1
    assert len(result.key_questions) >= 1
    assert duration <= 45.0, f"Deconstruction exceeded 45.0s per-request timeout: {duration:.2f}s"

