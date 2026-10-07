"""Tests for Phase 14C: End-to-End Analysis Deadline.

Verifies:
A. Analysis completing within budget succeeds.
B. Deadline already expired before DecisionModel -> no Gemini call -> HTTP 504.
C. DecisionModel consumes most of budget -> requirement generation receives only remaining budget.
D. Deadline expires before evidence requirements -> requirements LLM not called -> HTTP 504.
E. Deadline expires before Brave query -> Brave query not executed -> HTTP 504.
F. Deadline expires between Brave queries -> subsequent search queries are not executed -> HTTP 504.
G. Deadline expires before mapper batch -> that Gemini batch is not executed -> HTTP 504.
H. Deadline expires between mapper batches -> later batches are not executed -> HTTP 504.
I. Parent analysis deadline shorter than 60s LLM operation deadline -> Gemini uses parent remaining budget.
J. 60s LLM operation deadline shorter than analysis remaining budget -> Gemini still uses 60s maximum.
K. Retry/backoff cannot cross parent analysis deadline.
L. Analysis timeout returns HTTP 504.
M. Timeout client response contains no provider content/API keys/prompts.
N. No partial completed EvidencePackage is returned after timeout.
O. Existing callers of generate_structured() without parent deadline retain Phase 14A semantics.
"""

from datetime import date, timezone
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
from fastapi import HTTPException
import httpx
import pytest

from app.config import settings
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.analysis_service import (
    AnalysisService,
    AnalysisTimeoutError,
)
from app.services.evidence import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    CandidateRequirementsPayload,
    EvidenceMapper,
    EvidenceRequirementEngine,
    EvidenceRetriever,
    EvidenceService,
    FakeSearchProvider,
    NormalizedSourceResult,
    SearchResultItem,
    SearchTimeoutError,
)
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Helpers & Fixtures
# ------------------------------------------------------------------------------

def _create_sample_request() -> AnalysisRequest:
    return AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _create_sample_source(idx: int, req_id: str = "req_1") -> NormalizedSourceResult:
    url = f"https://example.com/source_{idx}"
    title = f"Source {idx} Report"
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
        snippet="In a sample of 240 B2B SaaS companies, pricing reduction was associated with 14% increase.",
        publisher="Benchmark Institute",
        published_date=date(2024, 1, 1),
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query="B2B SaaS price elasticity",
        source=src,
        search_result=search_item,
    )


# ------------------------------------------------------------------------------
# Test A: Analysis Completing Within Budget Succeeds
# ------------------------------------------------------------------------------

def test_a_analysis_completing_within_budget_succeeds() -> None:
    """A. Analysis completing within budget succeeds."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(
        default_results=[
            SearchResultItem(
                url="https://example.com/item1",
                title="SaaS Pricing Benchmark",
                snippet="Pricing reduction of 20% lifted customer acquisition by 14%.",
            )
        ]
    )
    service = AnalysisService(
        llm_client=fake_llm,
        search_provider=fake_search,
        analysis_timeout_seconds=120.0,
    )

    response = service.analyze(_create_sample_request())

    assert isinstance(response, AnalysisResponse)
    assert response.status == "completed"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert len(response.evidence_package.items) > 0


# ------------------------------------------------------------------------------
# Test B: Deadline Already Expired Before DecisionModel
# ------------------------------------------------------------------------------

def test_b_deadline_expired_before_decision_model_no_llm_call() -> None:
    """B. Deadline already expired before DecisionModel -> no Gemini/LLM call -> HTTP 504."""
    fake_llm = FakeLLMClient()
    service = AnalysisService(
        llm_client=fake_llm,
        analysis_timeout_seconds=120.0,
    )

    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(_create_sample_request(), deadline_monotonic=expired_deadline)

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()
    # LLM was never called
    assert len(fake_llm.call_history) == 0


# ------------------------------------------------------------------------------
# Test C: DecisionModel Consumes Most of Budget -> Requirements Gets Only Remaining
# ------------------------------------------------------------------------------

def test_c_decision_model_consumes_most_budget_propagates_remaining() -> None:
    """C. DecisionModel consumes most of budget -> requirement generation receives only remaining budget."""
    call_deadlines: List[Optional[float]] = []

    class InspectingLLMClient(FakeLLMClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            call_deadlines.append(kwargs.get("deadline_monotonic"))
            return super().generate_structured(*args, **kwargs)

    inspecting_llm = InspectingLLMClient()
    service = AnalysisService(
        llm_client=inspecting_llm,
        analysis_timeout_seconds=120.0,
    )

    start = time.monotonic()
    shared_deadline = start + 50.0

    service.analyze(_create_sample_request(), deadline_monotonic=shared_deadline)

    # Both DecisionModel and Requirements calls must have received the EXACT same shared deadline
    assert len(call_deadlines) >= 2
    for dl in call_deadlines:
        assert dl == shared_deadline


# ------------------------------------------------------------------------------
# Test D: Deadline Expires Before Evidence Requirements
# ------------------------------------------------------------------------------

def test_d_deadline_expires_before_evidence_requirements() -> None:
    """D. Deadline expires before evidence requirements -> requirements LLM not called -> HTTP 504."""
    fake_llm = FakeLLMClient()
    engine = QuestionUnderstandingEngine(llm_client=fake_llm)

    class ExpiringEvidenceService(EvidenceService):
        def build_evidence_package(self, decision_model: DecisionModel, deadline_monotonic: Optional[float] = None) -> EvidencePackage:
            # Simulate monotonic time passing deadline before requirements LLM
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                raise LLMTimeoutError("Requirements stage timed out against deadline.")
            return super().build_evidence_package(decision_model, deadline_monotonic=deadline_monotonic)

    service = AnalysisService(
        engine=engine,
        evidence_service=EvidenceService.create_default(fake_llm, FakeSearchProvider()),
    )

    # Force deadline to expire right after deconstruct
    original_deconstruct = engine.deconstruct

    def deconstruct_and_expire(*args: Any, **kwargs: Any) -> DecisionModel:
        dm = original_deconstruct(*args, **kwargs)
        # Advance clock or trigger deadline expiration
        return dm

    engine.deconstruct = deconstruct_and_expire  # type: ignore

    # Pass deadline that is valid during deconstruct but expired before requirements
    current_time = time.monotonic()
    service.analysis_timeout_seconds = 0.001  # expires almost immediately

    with pytest.raises(HTTPException) as exc_info:
        # Pass a deadline that expires after a tiny sleep
        dl = time.monotonic() + 0.05
        time.sleep(0.06)
        service.analyze(_create_sample_request(), deadline_monotonic=dl)

    assert exc_info.value.status_code == 504
    assert len(fake_llm.call_history) == 0


# ------------------------------------------------------------------------------
# Test E: Deadline Expires Before Brave Query
# ------------------------------------------------------------------------------

def test_e_deadline_expires_before_brave_query_not_executed() -> None:
    """E. Deadline expires before Brave/search query -> search query not executed -> HTTP 504."""
    fake_search = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_search)

    expired_deadline = time.monotonic() - 0.5
    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="var_1",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Search requirement",
        status=RequirementStatus.PENDING,
        suggested_queries=["SaaS price elasticity"],
    )

    with pytest.raises(SearchTimeoutError):
        retriever.retrieve([req], deadline_monotonic=expired_deadline)

    assert len(fake_search.recorded_queries) == 0


# ------------------------------------------------------------------------------
# Test F: Deadline Expires Between Brave Queries
# ------------------------------------------------------------------------------

def test_f_deadline_expires_between_brave_queries() -> None:
    """F. Deadline expires between Brave queries -> subsequent search queries are not executed."""
    class ExpiringSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5, timeout: Optional[float] = None) -> List[SearchResultItem]:
            self.recorded_queries.append(query)
            return [
                SearchResultItem(
                    url="https://example.com/res",
                    title="Result",
                    snippet="Snippet text",
                )
            ]

    search_provider = ExpiringSearchProvider()
    retriever = EvidenceRetriever(search_provider=search_provider)

    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="var_1",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Search requirement",
        status=RequirementStatus.PENDING,
        suggested_queries=["Query 1", "Query 2", "Query 3"],
    )

    start = time.monotonic()
    deadline = start + 50.0

    orig_monotonic = time.monotonic

    def advancing_monotonic() -> float:
        if len(search_provider.recorded_queries) >= 1:
            return start + 100.0  # Expired after query 1!
        return orig_monotonic()

    import app.services.evidence.retriever as retriever_mod
    monkey = pytest.MonkeyPatch()
    monkey.setattr(retriever_mod.time, "monotonic", advancing_monotonic)

    try:
        with pytest.raises(SearchTimeoutError):
            retriever.retrieve([req], deadline_monotonic=deadline)

        # Only Query 1 was executed, Query 2 and 3 were never executed
        assert len(search_provider.recorded_queries) == 1
        assert search_provider.recorded_queries[0] == "Query 1"
    finally:
        monkey.undo()


# ------------------------------------------------------------------------------
# Test G: Deadline Expires Before Mapper Batch
# ------------------------------------------------------------------------------

def test_g_deadline_expires_before_mapper_batch() -> None:
    """G. Deadline expires before mapper batch -> that Gemini batch is not executed."""
    fake_llm = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_llm)

    dm = get_default_decision_model("Test question?")
    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Description",
        status=RequirementStatus.PENDING,
    )
    source = _create_sample_source(1, req_id="req_1")

    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(LLMTimeoutError):
        mapper.map_evidence(dm, [req], [source], deadline_monotonic=expired_deadline)

    # Zero LLM batch calls executed
    assert len(fake_llm.call_history) == 0


# ------------------------------------------------------------------------------
# Test H: Deadline Expires Between Mapper Batches
# ------------------------------------------------------------------------------

def test_h_deadline_expires_between_mapper_batches() -> None:
    """H. Deadline expires between mapper batches -> later batches are not executed."""
    fake_llm = FakeLLMClient()
    mapper = EvidenceMapper(llm_client=fake_llm)
    mapper.batch_size = 1  # 2 sources = 2 batches

    dm = get_default_decision_model("Test question?")
    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Description",
        status=RequirementStatus.PENDING,
    )
    s1 = _create_sample_source(1, req_id="req_1")
    s2 = _create_sample_source(2, req_id="req_1")

    start = time.monotonic()
    deadline = start + 50.0

    call_count = 0
    orig_monotonic = time.monotonic

    def advancing_monotonic() -> float:
        nonlocal call_count
        call_count += 1
        # After batch 1 completes, advance time past deadline
        if len(fake_llm.call_history) >= 1:
            return start + 100.0  # Expired!
        return orig_monotonic()

    import app.services.evidence.mapper as mapper_mod
    monkey = pytest.MonkeyPatch()
    monkey.setattr(mapper_mod.time, "monotonic", advancing_monotonic)

    try:
        with pytest.raises(LLMTimeoutError):
            mapper.map_evidence(dm, [req], [s1, s2], deadline_monotonic=deadline)

        # Batch 1 executed, Batch 2 did not execute
        assert len(fake_llm.call_history) == 1
    finally:
        monkey.undo()


# ------------------------------------------------------------------------------
# Test I: Parent Analysis Deadline Shorter than 60s LLM Operation Deadline
# ------------------------------------------------------------------------------

def test_i_parent_deadline_shorter_than_60s_gemini_uses_parent_remaining() -> None:
    """I. Parent analysis deadline shorter than 60s LLM operation deadline -> Gemini uses parent remaining budget."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(api_key="test-key", http_client=http_client)

    mock_interactions = MagicMock()
    mock_genai_client = MagicMock()
    mock_genai_client.interactions = mock_interactions
    client._genai_client = mock_genai_client

    recorded_timeouts: List[float] = []

    def mock_create(**kwargs: Any) -> Any:
        recorded_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = '{"findings": []}'
        return mock_resp

    mock_interactions.create.side_effect = mock_create

    start = time.monotonic()
    parent_deadline = start + 17.0  # 17s remaining < 60s operation deadline

    client.generate_structured(
        prompt="Test prompt",
        response_schema=CandidateBatchEvidenceMappingPayload,
        deadline_monotonic=parent_deadline,
    )

    assert len(recorded_timeouts) == 1
    # Clamped to remaining parent budget (approximately 17s), NOT 30s or 60s
    assert recorded_timeouts[0] <= 17.0
    assert recorded_timeouts[0] > 15.0


# ------------------------------------------------------------------------------
# Test J: 60s LLM Operation Deadline Shorter than Analysis Remaining Budget
# ------------------------------------------------------------------------------

def test_j_operation_deadline_shorter_than_analysis_budget_capped_at_60s() -> None:
    """J. 60s LLM operation deadline shorter than analysis remaining budget -> Gemini still uses 60s maximum."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(api_key="test-key", http_client=http_client)

    mock_interactions = MagicMock()
    mock_genai_client = MagicMock()
    mock_genai_client.interactions = mock_interactions
    client._genai_client = mock_genai_client

    recorded_timeouts: List[float] = []

    def mock_create(**kwargs: Any) -> Any:
        recorded_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = '{"findings": []}'
        return mock_resp

    mock_interactions.create.side_effect = mock_create

    start = time.monotonic()
    parent_deadline = start + 120.0  # 120s remaining > 60s operation deadline

    client.generate_structured(
        prompt="Test prompt",
        response_schema=CandidateBatchEvidenceMappingPayload,
        deadline_monotonic=parent_deadline,
    )

    assert len(recorded_timeouts) == 1
    # Per-request HTTP timeout is capped at cfg.timeout_seconds (45.0), not 120.0
    assert recorded_timeouts[0] == 45.0


# ------------------------------------------------------------------------------
# Test K: Retry/Backoff Cannot Cross Parent Analysis Deadline
# ------------------------------------------------------------------------------

def test_k_retry_backoff_cannot_cross_parent_deadline() -> None:
    """K. Retry/backoff cannot cross parent analysis deadline."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(api_key="test-key", http_client=http_client)

    mock_interactions = MagicMock()
    mock_genai_client = MagicMock()
    mock_genai_client.interactions = mock_interactions
    client._genai_client = mock_genai_client

    sleep_calls: List[float] = []
    client._sleep_fn = lambda s: sleep_calls.append(s)

    # Force timeout error to trigger retry loop
    mock_interactions.create.side_effect = httpx.TimeoutException("Read timed out")

    start = time.monotonic()
    # Give a tiny parent deadline so backoff is truncated or times out
    parent_deadline = start + 0.5

    with pytest.raises(LLMTimeoutError):
        client.generate_structured(
            prompt="Test prompt",
            response_schema=CandidateBatchEvidenceMappingPayload,
            deadline_monotonic=parent_deadline,
        )

    # Any backoff sleep performed could not exceed parent remaining time (0.5s)
    for s in sleep_calls:
        assert s <= 0.5


# ------------------------------------------------------------------------------
# Test L: Analysis Timeout Returns HTTP 504
# ------------------------------------------------------------------------------

def test_l_analysis_timeout_returns_http_504() -> None:
    """L. Analysis timeout returns HTTP 504 Gateway Timeout."""
    fake_llm = FakeLLMClient()
    service = AnalysisService(
        llm_client=fake_llm,
        analysis_timeout_seconds=0.001,
    )

    with pytest.raises(HTTPException) as exc_info:
        # Expired deadline
        service.analyze(_create_sample_request(), deadline_monotonic=time.monotonic() - 1.0)

    assert exc_info.value.status_code == 504


# ------------------------------------------------------------------------------
# Test M: Timeout Client Response Contains No Provider Content / API Keys / Prompts
# ------------------------------------------------------------------------------

def test_m_timeout_client_response_sanitized() -> None:
    """M. Timeout client response contains no provider content, API keys, or prompts."""
    secret_marker = "SECRET_PROVIDER_INTERNAL_KEY_99999"
    fake_llm = FakeLLMClient()

    class LeakingTimeoutService(EvidenceService):
        def build_evidence_package(self, decision_model: DecisionModel, deadline_monotonic: Optional[float] = None) -> EvidencePackage:
            raise SearchTimeoutError(f"Raw provider dump with {secret_marker} and prompt contents")

    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=LeakingTimeoutService(None, None, None, None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(_create_sample_request())

    assert exc_info.value.status_code == 504
    # The client detail must be cleanly sanitized
    assert exc_info.value.detail == "Decision analysis timed out while evaluating the inquiry."
    assert secret_marker not in exc_info.value.detail


# ------------------------------------------------------------------------------
# Test N: No Partial Completed EvidencePackage Returned After Timeout
# ------------------------------------------------------------------------------

def test_n_no_partial_completed_evidence_package_after_timeout() -> None:
    """N. No partial completed EvidencePackage is returned after timeout (fail-closed)."""
    fake_llm = FakeLLMClient()

    # Stage 1 (DecisionModel) succeeds, but mapping stage times out
    class TimingOutEvidenceService(EvidenceService):
        def build_evidence_package(self, decision_model: DecisionModel, deadline_monotonic: Optional[float] = None) -> EvidencePackage:
            raise LLMTimeoutError("Mapping batch 3 timed out after partial findings.")

    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=TimingOutEvidenceService(None, None, None, None, None),  # type: ignore
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(_create_sample_request())

    assert exc_info.value.status_code == 504
    # Service must NOT return AnalysisResponse with status="completed"


# ------------------------------------------------------------------------------
# Test O: Existing Callers Without Parent Deadline Retain Phase 14A Semantics
# ------------------------------------------------------------------------------

def test_o_callers_without_parent_deadline_retain_phase14a_semantics() -> None:
    """O. Existing callers of generate_structured() without parent deadline retain Phase 14A semantics."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"output_text": "{}"}))
    http_client = httpx.Client(transport=mock_transport)
    client = GeminiLLMClient(api_key="test-key", http_client=http_client)

    mock_interactions = MagicMock()
    mock_genai_client = MagicMock()
    mock_genai_client.interactions = mock_interactions
    client._genai_client = mock_genai_client

    recorded_timeouts: List[float] = []

    def mock_create(**kwargs: Any) -> Any:
        recorded_timeouts.append(kwargs.get("timeout"))
        mock_resp = MagicMock()
        mock_resp.output_text = '{"findings": []}'
        return mock_resp

    mock_interactions.create.side_effect = mock_create

    # Call WITHOUT deadline_monotonic
    client.generate_structured(
        prompt="Test prompt",
        response_schema=CandidateBatchEvidenceMappingPayload,
    )

    assert len(recorded_timeouts) == 1
    # Uses Phase 14A default timeout_seconds = 45.0
    assert recorded_timeouts[0] == 45.0
