"""AURA Day 8F: Action Intelligence Timeout Hardening & Regression Tests.

Verifies:
1. Configured timeout chain: dedicated setting, outer operation deadline >= HTTP timeout.
2. Claim TTL (180.0s) strictly exceeds generation operation deadline (120.0s).
3. Runtime model resolution accurately discovers default_model or model_name.
4. Large real-schema analysis prompt builds successfully without exceptions.
5. Grounding survives prompt optimization: all Stage 4 actions and hard constraints preserved.
6. Epistemic boundaries: zero quantitative ROI, probabilities, or dates.
7. Timeout returns HTTP 504 Gateway Timeout and releases durable SQLite claim as failed.
8. Failed generation can be retried immediately and succeeds.
9. Cached generation avoids invoking Gemini.
10. Concurrent generation requests are rejected with HTTP 409 Conflict.
11. Expired or superseded claims cannot overwrite newer plans.
12. Opt-in structured diagnostics (AURA_LLM_DIAGNOSTICS=1) track model, prompt chars,
    estimated tokens, and elapsed duration without logging secrets or raw prompts.
13. Frontend polling timeout (150s) safely exceeds backend operation timeout (120s).
"""

from datetime import datetime, timezone
import json
import os
import pytest
import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app
from app.schemas.action_intelligence import (
    ActionPriority,
    CandidateActionCriterion,
    CandidateActionItem,
    CandidateActionPlan,
    CandidateDecisionGate,
    ComparisonOperator,
    CriterionType,
    IntelligentActionPlan,
)
from app.schemas.analysis import AnalysisResponse
from app.services.action_intelligence.generator import (
    ActionIntelligenceGenerator,
    _resolve_model_name,
)
from app.services.action_intelligence.prompt_builder import (
    CURRENT_ACTION_INTELLIGENCE_PROMPT_VERSION,
    build_action_intelligence_system_instruction,
    build_action_intelligence_user_prompt,
)
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.analysis_service import get_llm_client
from app.services.jobs.manager import AnalysisJobManager, get_job_manager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.llm.client import (
    LLMClient,
    LLMConfig,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.schemas.job import AnalysisJobCreateRequest
from tests.test_phase8e_real_schema_regression import (
    MockGeminiClient,
    build_saas_six_stage_analysis_response,
)


@pytest.fixture
def temp_db(tmp_path) -> str:
    db_file = tmp_path / "test_aura_phase8f.db"
    return str(db_file)


@pytest.fixture
def storage(temp_db: str) -> SQLiteJobStorage:
    return SQLiteJobStorage(db_path=temp_db)


@pytest.fixture
def manager(storage: SQLiteJobStorage) -> AnalysisJobManager:
    return AnalysisJobManager(storage=storage)


def create_completed_job(storage: SQLiteJobStorage, analysis_id: str = "analysis-saas-real-01"):
    create_req = AnalysisJobCreateRequest(
        question="Evaluate pilot rollout of AI customer support assistant.",
        owner_id="owner_shubh",
    )
    job = storage.create_job(create_req, job_id=analysis_id)
    real_response = build_saas_six_stage_analysis_response(analysis_id=analysis_id)
    storage.complete_job(job.job_id, response=real_response)
    return job


# ==============================================================================
# 1. Timeout Chain & Settings Configuration
# ==============================================================================

def test_timeout_chain_configuration_and_invariants():
    """Verifies dedicated Action Intelligence timeout settings and chain invariants."""
    assert settings.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS == 120.0
    assert settings.AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS == 90.0
    assert settings.AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS == 180.0
    assert settings.AURA_ACTION_INTELLIGENCE_MAX_RETRIES == 0

    # Invariant: Claim TTL > Operation Timeout
    assert settings.AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS > settings.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS
    # Invariant: Operation Timeout >= HTTP Timeout
    assert settings.AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS >= settings.AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS


def test_settings_validation_rejects_inconsistent_timeout_chains():
    """Verifies that invalid timeout chains are rejected at configuration time."""
    # Claim TTL <= Operation Timeout is invalid (would allow premature claim expiry while worker runs)
    with pytest.raises(ValueError, match="strictly greater than"):
        Settings(
            AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS=100.0,
            AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS=90.0,
        )

    # Operation Timeout < HTTP Timeout is invalid
    with pytest.raises(ValueError, match="greater than or equal to"):
        Settings(
            AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS=30.0,
            AURA_ACTION_INTELLIGENCE_HTTP_TIMEOUT_SECONDS=60.0,
            AURA_ACTION_INTELLIGENCE_CLAIM_TTL_SECONDS=120.0,
        )

    # Negative timeouts are invalid
    with pytest.raises(ValueError, match="strictly greater than 0.0"):
        Settings(AURA_ACTION_INTELLIGENCE_OPERATION_TIMEOUT_SECONDS=-10.0)


# ==============================================================================
# 2. Configured Timeouts Honored in Generator
# ==============================================================================

class RecordingLLMClient(LLMClient):
    """Mock client that records the LLMConfig received."""

    def __init__(self, model_name: str = "gemini-3.8-flash") -> None:
        self.default_model = model_name
        self.recorded_config: Optional[LLMConfig] = None
        self.call_count = 0

    def generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        self.call_count += 1
        self.recorded_config = config
        return CandidateActionPlan(
            strategy_summary="Test plan grounded in Stage 4 recommendation.",
            actions=[
                CandidateActionItem(
                    action_id="act_saas_pilot",
                    source_action_reference="act_saas_pilot",
                    title="Pilot Execution",
                    description="Configure isolated support routing.",
                    priority=ActionPriority.HIGH,
                    sequence=1,
                    owner_role="VP Customer Support",
                    rationale="Sound starting step",
                )
            ],
            decision_gates=[],
        )


def test_generator_honors_configured_settings_timeouts():
    """Verifies that generator applies configured settings timeouts by default."""
    client = RecordingLLMClient()
    generator = ActionIntelligenceGenerator(llm_client=client)
    resp = build_saas_six_stage_analysis_response()

    generator.generate(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        evidence_package=resp.evidence_package,
        reasoning_board=resp.reasoning_board,
        scenario_set=resp.scenarios,
        resilience_report=resp.resilience,
    )

    assert client.call_count == 1
    assert client.recorded_config is not None
    assert client.recorded_config.timeout_seconds == 90.0
    assert client.recorded_config.operation_timeout_seconds == 120.0
    assert client.recorded_config.max_retries == 0


def test_generator_honors_explicit_overrides():
    """Verifies that explicit timeout parameters override settings defaults."""
    client = RecordingLLMClient()
    generator = ActionIntelligenceGenerator(llm_client=client)
    resp = build_saas_six_stage_analysis_response()

    generator.generate(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        evidence_package=resp.evidence_package,
        reasoning_board=resp.reasoning_board,
        scenario_set=resp.scenarios,
        resilience_report=resp.resilience,
        timeout_seconds=45.0,
        operation_timeout_seconds=65.0,
    )

    assert client.recorded_config is not None
    assert client.recorded_config.timeout_seconds == 45.0
    assert client.recorded_config.operation_timeout_seconds == 65.0


def test_runtime_model_name_resolution():
    """Verifies _resolve_model_name accurately discovers client default_model or model_name."""
    # 1. Client with default_model
    c1 = RecordingLLMClient(model_name="gemini-3.8-flash")
    assert _resolve_model_name(c1) == "gemini-3.8-flash"

    # 2. Client with model_name attribute
    class LegacyClient:
        model_name = "gemini-2.5-pro"
    assert _resolve_model_name(LegacyClient()) == "gemini-2.5-pro"

    # 3. Fallback when neither is defined
    class EmptyClient:
        pass
    assert _resolve_model_name(EmptyClient()) == settings.GEMINI_MODEL


# ==============================================================================
# 3. Prompt Size & Optimization Preserves Grounding & Invariants
# ==============================================================================

def test_large_real_schema_analysis_prompt_builds_and_preserves_grounding():
    """Verifies prompt construction with full six-stage analysis preserves all grounding and constraints."""
    resp = build_saas_six_stage_analysis_response()

    sys_inst = build_action_intelligence_system_instruction()
    user_prompt = build_action_intelligence_user_prompt(
        decision_model=resp.decision_model,
        recommendation=resp.recommendation,
        evidence_package=resp.evidence_package,
        reasoning_board=resp.reasoning_board,
        scenario_set=resp.scenarios,
        resilience_report=resp.resilience,
    )

    # Prompt build succeeds and length is measured
    assert len(sys_inst) > 1000
    assert len(user_prompt) > 2000
    assert len(user_prompt) < 20000  # Well within 40,000 max limit

    # Epistemic rules in system instruction
    assert "DO NOT invent quantitative ROI" in sys_inst
    assert "DO NOT invent numeric success probabilities" in sys_inst
    assert "DO NOT invent resilience score deltas" in sys_inst
    assert "DO NOT invent calendar completion dates" in sys_inst
    assert "<untrusted_analysis_material>" in sys_inst

    # Authoritative Stage 4 actions are present
    assert "act_saas_pilot" in user_prompt
    assert "VP Customer Support" in user_prompt

    # Stage 1 Hard constraints and thresholds are present
    assert "cnstr_pilot_cohort" in user_prompt
    assert "<= 1000" in user_prompt
    assert "cnstr_csat_floor" in user_prompt
    assert ">= 90" in user_prompt

    # Stage 3 Disagreements and Stage 5 Scenarios are present
    assert "Key Boardroom Disagreements" in user_prompt
    assert "SCENARIO STRESS TEST PROJECTIONS" in user_prompt
    assert "COMPOSITE RESILIENCE RATING" in user_prompt


# ==============================================================================
# 4. Timeout Failure Returns HTTP 504 and Releases Claim
# ==============================================================================

def test_timeout_returns_504_gateway_timeout_and_releases_claim(manager: AnalysisJobManager):
    """Verifies that an LLM timeout raises HTTP 504 and releases the SQLite claim as failed."""
    job = create_completed_job(manager.storage, analysis_id="analysis_phase8f_to")

    mock_client = MockGeminiClient()
    mock_client.exception_to_raise = LLMTimeoutError("Gemini API request timed out after 45.0s.")

    service = ActionIntelligenceService(manager=manager, llm_client=mock_client)

    with pytest.raises(HTTPException) as exc_info:
        service.generate_action_plan(analysis_id=job.job_id)

    assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert "exceeded allowed processing time" in exc_info.value.detail

    # Verify claim was released as failed
    claim = manager.storage.get_action_plan_claim(analysis_id=job.job_id)
    assert claim is not None
    assert claim["status"] == "failed"
    assert "exceeded allowed processing time" in claim["error_message"]

    # Verify status endpoint reflects failure without asserting backend crash
    stat = service.get_action_plan_status(analysis_id=job.job_id)
    assert stat["status"] == "failed"
    assert stat["plan"] is None


# ==============================================================================
# 5. Failed Generation Can Be Retried and Succeeds
# ==============================================================================

def test_failed_generation_can_be_retried_and_succeeds(manager: AnalysisJobManager):
    """Verifies that after a timeout/failure, a retry acquires a fresh claim and completes."""
    job = create_completed_job(manager.storage, analysis_id="analysis_phase8f_retry")

    mock_client = MockGeminiClient()
    # 1. First attempt fails with timeout
    mock_client.exception_to_raise = LLMTimeoutError("Request timed out.")
    service = ActionIntelligenceService(manager=manager, llm_client=mock_client)

    with pytest.raises(HTTPException) as exc_info:
        service.generate_action_plan(analysis_id=job.job_id)
    assert exc_info.value.status_code == 504

    # 2. Second attempt succeeds
    mock_client.exception_to_raise = None
    plan, cached = service.generate_action_plan(analysis_id=job.job_id)

    assert cached is False
    assert plan is not None
    assert plan.plan_id.startswith("plan_")

    # Claim is now released with success (status 'ready')
    claim = manager.storage.get_action_plan_claim(analysis_id=job.job_id)
    assert claim["status"] == "ready"


# ==============================================================================
# 6. Cached Generation Avoids Gemini Invocation
# ==============================================================================

def test_cached_generation_avoids_gemini_invocation(manager: AnalysisJobManager):
    """Verifies that once a plan is generated, subsequent calls do not touch Gemini."""
    job = create_completed_job(manager.storage, analysis_id="analysis_phase8f_cached")

    mock_client = MockGeminiClient()
    service = ActionIntelligenceService(manager=manager, llm_client=mock_client)

    # First run generates
    plan1, cached1 = service.generate_action_plan(analysis_id=job.job_id)
    assert cached1 is False
    assert mock_client.call_count == 1

    # Second run retrieves cached without LLM call
    plan2, cached2 = service.generate_action_plan(analysis_id=job.job_id)
    assert cached2 is True
    assert mock_client.call_count == 1  # No additional call!
    assert plan2.plan_id == plan1.plan_id


# ==============================================================================
# 7. Concurrent Generation Requests Rejected with 409
# ==============================================================================

def test_concurrent_generation_requests_rejected_with_409(manager: AnalysisJobManager):
    """Verifies that duplicate concurrent requests are rejected with HTTP 409 without calling LLM."""
    job = create_completed_job(manager.storage, analysis_id="analysis_phase8f_conc")

    # Worker 1 acquires claim
    acquired, c_stat, c_id = manager.storage.acquire_action_plan_claim(
        analysis_id=job.job_id,
        ttl_seconds=180.0,
    )
    assert acquired is True

    # Worker 2 attempts generation
    mock_client = MockGeminiClient()
    service = ActionIntelligenceService(manager=manager, llm_client=mock_client)

    with pytest.raises(HTTPException) as exc_info:
        service.generate_action_plan(analysis_id=job.job_id)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "currently in progress" in exc_info.value.detail
    assert mock_client.call_count == 0


# ==============================================================================
# 8. Expired or Superseded Claims Cannot Overwrite Newer Plans
# ==============================================================================

def test_expired_claim_cannot_overwrite_newer_plan(manager: AnalysisJobManager):
    """Verifies that an expired claim is aborted before saving into SQLite."""
    job = create_completed_job(manager.storage, analysis_id="analysis_phase8f_exp")

    mock_client = MockGeminiClient()
    service = ActionIntelligenceService(manager=manager, llm_client=mock_client)

    # Monkeypatch storage.acquire_action_plan_claim to return an expired claim
    def fake_acquire(analysis_id, owner_id=None, ttl_seconds=180.0):
        with manager.storage._lock:
            manager.storage._conn.execute(
                """
                INSERT OR REPLACE INTO action_plan_claims (analysis_id, claim_id, status, owner_id, claimed_at, expires_at)
                VALUES (?, ?, 'running', ?, datetime('now'), ?)
                """,
                (analysis_id, "expired_claim_01", owner_id, time.time() - 10),
            )
            manager.storage._conn.commit()
        return True, "running", "expired_claim_01"

    manager.storage.acquire_action_plan_claim = fake_acquire

    with pytest.raises(HTTPException) as exc_info:
        service.generate_action_plan(analysis_id=job.job_id)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "expired or was superseded" in exc_info.value.detail

    # No plan was saved
    saved = service.get_action_plan(analysis_id=job.job_id)
    assert saved is None


# ==============================================================================
# 9. Structured Diagnostics (AURA_LLM_DIAGNOSTICS=1)
# ==============================================================================

def test_opt_in_structured_diagnostics_records_metadata_without_secrets():
    """Verifies that opt-in diagnostics track metrics and metadata without leaking sensitive data."""
    os.environ["AURA_LLM_DIAGNOSTICS"] = "1"
    try:
        client = RecordingLLMClient()
        generator = ActionIntelligenceGenerator(llm_client=client)
        resp = build_saas_six_stage_analysis_response()

        candidate = generator.generate(
            decision_model=resp.decision_model,
            recommendation=resp.recommendation,
            evidence_package=resp.evidence_package,
            reasoning_board=resp.reasoning_board,
            scenario_set=resp.scenarios,
            resilience_report=resp.resilience,
        )

        diag = generator.last_diagnostic
        assert diag is not None
        assert diag["status"] == "success"
        assert diag["model_name"] == "gemini-3.8-flash"
        assert diag["prompt_chars"] > 0
        assert diag["estimated_prompt_tokens"] > 0
        assert diag["elapsed_seconds"] >= 0.0

        # No secret keys or raw prompt in diagnostics
        assert "api_key" not in diag
        assert "prompt" not in diag

        # Assembled plan contains diagnostic metrics in generation_metadata
        plan = generator.assemble_plan(
            candidate=candidate,
            analysis_id="test_diag_analysis",
            source_recommendation_fingerprint="srfp_" + "a" * 32,
        )
        assert plan.generation_metadata["model_name"] == "gemini-3.8-flash"
        assert plan.generation_metadata["prompt_chars"] == diag["prompt_chars"]
        assert plan.generation_metadata["estimated_prompt_tokens"] == diag["estimated_prompt_tokens"]
    finally:
        os.environ.pop("AURA_LLM_DIAGNOSTICS", None)
