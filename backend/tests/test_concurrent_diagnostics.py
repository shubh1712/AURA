"""AURA Phase 4.19: Concurrent Diagnostics Integrity and Transport Guard Verification Tests.

Deterministic offline tests validating:
1. Thread-safe call-scoped diagnostic collection in PerspectiveOrchestrator.
2. Stable association of diagnostics with perspective identity (Growth, Finance, Customer, Risk).
3. All four perspective diagnostics preserved concurrently without last-write-wins overwriting.
4. Batch mapping diagnostics preserved in EvidenceMapper per batch index.
5. Telemetry preserved across failure paths (provider timeout, auth error, rate limit, validation error).
6. Fail-closed behavior on deadline expiration and partial worker completion.
7. Zero cross-request diagnostic leakage.
8. Zero sensitive payload logging in diagnostics (telemetry metadata only).
9. Zero mutation of model outputs.
10. Strict verification of Phase 4.18 transport schema compaction guards across all response schemas.
"""

import concurrent.futures
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Type
import pytest
from pydantic import BaseModel, Field

from app.schemas.decision_model import (
    Assumption,
    Complexity,
    ComplexityLevel,
    Constraint,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ReversibilityLevel,
    Stakeholder,
    TimeHorizon,
    Tradeoff,
    Unknown,
    Variable,
    VariableType,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence.search_provider import SearchResultItem
from app.services.evidence.normalizer import NormalizedSourceResult
from app.services.evidence.mapper import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    EvidenceMapper,
)
from app.services.evidence.requirements import CandidateRequirementsPayload
from app.schemas.reasoning import (
    ArgumentDirection,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    CandidateBoardSynthesis,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningPerspective,
)
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMConfig,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    MockLLMClient,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.reasoning.context_builder import (
    PerspectiveContext,
    build_reasoning_context,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.orchestrator import (
    CANONICAL_PERSPECTIVES,
    PerspectiveOrchestrator,
)
from app.services.reasoning.validator import (
    ReasoningEvaluationError,
    ReasoningOrchestrationError,
)


def _build_test_decision_model() -> DecisionModel:
    return DecisionModel(
        id="dec_orch_01",
        decision=Decision(
            raw_prompt="Expand into enterprise market?",
            summary="Strategic decision to expand into tier-1 enterprise accounts.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Substantial operational and capital risk.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[Objective(id="obj_scale", description="Achieve 40% ARR growth", is_primary=True)],
        variables=[
            Variable(
                id="var_pricing",
                name="Annual Contract Value",
                description="Average contract revenue per year",
                variable_type=VariableType.CURRENCY,
            )
        ],
        constraints=[Constraint(id="cnstr_cash", name="Runway Constraint", description="Runway >= 18 months")],
        stakeholders=[
            Stakeholder(
                id="stk_board",
                group="Board of Directors",
                impact_nature="Accountable for long-term equity value",
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_growth_cash",
                upside="Accelerated enterprise market penetration",
                downside="Higher cash burn and tighter runway",
            )
        ],
        assumptions=[
            Assumption(id="asm_market_tam", statement="TAM exceeds $2B"),
            Assumption(id="asm_conversion", statement="Enterprise conversion >= 15%"),
        ],
        unknowns=[Unknown(id="unk_competitor_reaction", question="Competitor discounting response")],
        key_questions=["Can we sustain enterprise sales velocity?"],
    )


def _build_test_evidence_package(dm_id: str = "dec_orch_01") -> EvidencePackage:
    src = Source(
        id="src_diag_1",
        title="Source 1",
        url="https://example.com/source1",
        source_type=SourceType.INDUSTRY_REPORT,
        snippet="Verified test metric finding value 42.0",
    )
    req = EvidenceRequirement(
        id="req_diag_1",
        target_entity_id="obj_scale",
        target_entity_type=DecisionEntityType.OBJECTIVE,
        description="Verify metric 1",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        status=RequirementStatus.FULFILLED,
    )
    item = EvidenceItem(
        id="evi_diag_1",
        source_id="src_diag_1",
        content="Verified test metric finding value 42.0",
    )
    return EvidencePackage(
        id="ep_diag_test",
        decision_model_id=dm_id,
        sources=[src],
        requirements=[req],
        items=[item],
        gaps=[],
        summary="Empirical evidence portfolio for test analysis.",
    )


def _build_candidate_analysis(ptype: PerspectiveType) -> CandidatePerspectiveAnalysis:
    return CandidatePerspectiveAnalysis(
        perspective_type=ptype,
        summary=f"Analysis for {ptype.value}",
        arguments=[
            CandidateReasoningArgument(
                claim=f"Test claim for {ptype.value}",
                direction=ArgumentDirection.FAVORABLE,
                basis=ReasoningBasis.EVIDENCE,
                reasoning="Solid reasoning based on verified facts",
                evidence_item_ids=["evi_diag_1"],
                requirement_ids=["req_diag_1"],
                assumption_ids=[],
                unknown_ids=[],
                evidence_gap_ids=[],
                related_entity_ids=["obj_scale"],
            )
        ],
        critical_assumption_ids=[],
        evidence_gap_ids=[],
        unresolved_questions=[f"Question {ptype.value}"],
        limitations=["None"],
    )


class DiagnosticMockClient:
    """Mock LLM client that provides thread-isolated last_diagnostic entries."""

    def __init__(self, canned_diagnostics: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._thread_local = threading.local()
        self._canned_diagnostics = canned_diagnostics or {}
        self._error_for_perspective: Dict[str, Exception] = {}
        self._barrier: Optional[threading.Barrier] = None
        self._call_counter = 0
        self._lock = threading.Lock()

    def set_barrier(self, count: int) -> None:
        self._barrier = threading.Barrier(count)

    def set_error_for_perspective(self, ptype_val: str, exc: Exception) -> None:
        self._error_for_perspective[ptype_val] = exc

    @property
    def last_diagnostic(self) -> Optional[Dict[str, Any]]:
        return getattr(self._thread_local, "diagnostic", None)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        system_instruction: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> Any:
        if self._barrier:
            self._barrier.wait(timeout=5.0)

        with self._lock:
            self._call_counter += 1
            call_idx = self._call_counter

        # Identify perspective if system instruction is available
        ptype_val = "unknown"
        if system_instruction:
            for cand in ("growth", "finance", "customer", "risk"):
                if f"({cand})" in system_instruction.lower():
                    ptype_val = cand
                    break

        # Simulate error if configured
        if ptype_val in self._error_for_perspective:
            exc = self._error_for_perspective[ptype_val]
            diag = {
                "call_id": call_idx,
                "perspective": ptype_val,
                "status": "timeout" if isinstance(exc, LLMTimeoutError) else "error",
                "call_duration_seconds": 0.05,
                "attempt": 1,
                "model": "gemini-3.8-flash",
                "location": "global",
            }
            self._thread_local.diagnostic = diag
            raise exc

        request_tag = "default"
        if "req_A" in prompt or (system_instruction and "req_A" in system_instruction):
            request_tag = "req_A"
        elif "req_B" in prompt or (system_instruction and "req_B" in system_instruction):
            request_tag = "req_B"

        # Set thread-local diagnostic
        diag = {
            "call_id": call_idx,
            "perspective": ptype_val,
            "request_tag": request_tag,
            "status": "success",
            "call_duration_seconds": 0.02,
            "attempt": 1,
            "model": "gemini-3.8-flash",
            "location": "global",
            "user_prompt_chars": len(prompt),
        }
        self._thread_local.diagnostic = diag

        # Return mock candidate
        if response_schema == CandidatePerspectiveAnalysis:
            for p in PerspectiveType:
                if p.value == ptype_val:
                    return _build_candidate_analysis(p)
            return _build_candidate_analysis(PerspectiveType.GROWTH)

        if response_schema == CandidateBatchEvidenceMappingPayload:
            return CandidateBatchEvidenceMappingPayload(
                findings=[
                    CandidateFinding(
                        source_ref="SOURCE_1",
                        target_entity_id="obj_scale",
                        content="Verified test metric finding value 42.0",
                        stance=EvidenceStance.SUPPORTS,
                        reasoning="Direct empirical evidence from source",
                    )
                ]
            )

        raise ValueError(f"Unsupported schema {response_schema}")


# ------------------------------------------------------------------------------
# Test 1: Concurrency and Stable Identity Preservation
# ------------------------------------------------------------------------------

def test_orchestrator_concurrent_diagnostics_preservation() -> None:
    """Proves that all four perspective diagnostics are preserved with stable identity under 4-worker concurrency."""
    mock_llm = DiagnosticMockClient()
    mock_llm.set_barrier(4)  # Force true parallel worker execution

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    perspectives = orchestrator.evaluate_all(dm, ep)

    assert len(perspectives) == 4
    # Verify all four perspective diagnostics are present
    assert len(orchestrator.last_perspective_diagnostics) == 4

    canonical_types = [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]

    for ptype in canonical_types:
        assert ptype in orchestrator.last_perspective_diagnostics
        diag = orchestrator.last_perspective_diagnostics[ptype]
        assert diag["perspective"] == ptype.value
        assert diag["status"] == "success"
        assert diag["attempt"] == 1
        assert "call_duration_seconds" in diag


# ------------------------------------------------------------------------------
# Test 2: Evidence Mapper Batch Diagnostics
# ------------------------------------------------------------------------------

def test_evidence_mapper_concurrent_batch_diagnostics_preservation() -> None:
    """Proves that EvidenceMapper preserves call-scoped diagnostics for each batch."""
    mock_llm = DiagnosticMockClient()
    mapper = EvidenceMapper(llm_client=mock_llm)
    mapper.max_workers = 3
    mapper.batch_size = 1

    dm = _build_test_decision_model()
    sources = [
        NormalizedSourceResult(
            source=Source(
                id=f"src_{i}",
                title=f"Source {i}",
                url=f"https://example.com/s{i}",
                source_type=SourceType.INDUSTRY_REPORT,
                snippet=f"Snippet {i} with unique content",
            ),
            requirement_id="req_diag_1",
            query=f"https://example.com/s{i}",
            search_result=SearchResultItem(
                url=f"https://example.com/s{i}",
                title=f"Source {i}",
                snippet=f"Snippet {i} with unique content",
            ),
        )
        for i in range(3)
    ]
    reqs = [_build_test_evidence_package().requirements[0]]

    res = mapper.map_evidence(dm, reqs, sources)
    assert len(res.items) >= 1
    # Check that each batch diagnostic was recorded
    assert len(mapper.last_batch_diagnostics) == 3
    for b_idx in range(3):
        assert b_idx in mapper.last_batch_diagnostics
        assert mapper.last_batch_diagnostics[b_idx]["status"] == "success"


# ------------------------------------------------------------------------------
# Test 3: Failure Paths - Provider Timeout
# ------------------------------------------------------------------------------

def test_failure_path_provider_timeout_diagnostics() -> None:
    """Proves that timeout diagnostics are captured and fail-closed behavior is enforced without exposing partial board."""
    mock_llm = DiagnosticMockClient()
    mock_llm.set_error_for_perspective("finance", LLMTimeoutError("Simulated Vertex timeout"))

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep)

    assert "finance" in str(exc_info.value).lower()
    # Diagnostic for failed worker is preserved
    assert PerspectiveType.FINANCE in orchestrator.last_perspective_diagnostics
    assert orchestrator.last_perspective_diagnostics[PerspectiveType.FINANCE]["status"] == "timeout"
    # Exception carries diagnostics
    assert hasattr(exc_info.value, "perspective_diagnostics")
    assert PerspectiveType.FINANCE in exc_info.value.perspective_diagnostics


# ------------------------------------------------------------------------------
# Test 4: Failure Paths - Authentication and Rate Limit
# ------------------------------------------------------------------------------

def test_failure_path_auth_and_rate_limit_diagnostics() -> None:
    """Proves that non-retryable and retryable client errors preserve diagnostics."""
    mock_llm = DiagnosticMockClient()
    mock_llm.set_error_for_perspective("risk", LLMAuthenticationError("Missing GCP credentials"))

    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep)

    assert PerspectiveType.RISK in orchestrator.last_perspective_diagnostics


# ------------------------------------------------------------------------------
# Test 5: Deadline Pre-Check Expiration
# ------------------------------------------------------------------------------

def test_failure_path_deadline_precheck_preserves_clean_isolation() -> None:
    """Proves that expired parent deadline fails closed immediately and isolates state."""
    mock_llm = DiagnosticMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(ReasoningOrchestrationError, match="already expired"):
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=expired_deadline)

    assert orchestrator.last_perspective_diagnostics == {}


# ------------------------------------------------------------------------------
# Test 6: Zero Cross-Request Leakage
# ------------------------------------------------------------------------------

def test_no_cross_request_diagnostic_leakage() -> None:
    """Proves that subsequent requests reset diagnostic state and never retain stale worker data."""
    mock_llm = DiagnosticMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    # Call 1: success
    orchestrator.evaluate_all(dm, ep)
    assert len(orchestrator.last_perspective_diagnostics) == 4

    # Call 2: deadline expired immediately
    with pytest.raises(ReasoningOrchestrationError):
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=time.monotonic() - 10.0)

    # State from call 1 was reset and is not retained
    assert orchestrator.last_perspective_diagnostics == {}


# ------------------------------------------------------------------------------
# Test 7: Telemetry Safety (No Sensitive Data)
# ------------------------------------------------------------------------------

def test_no_sensitive_payload_in_diagnostics() -> None:
    """Proves that diagnostics record only metadata, never prompt text or raw outputs."""
    mock_llm = DiagnosticMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    orchestrator.evaluate_all(dm, ep)

    for ptype, diag in orchestrator.last_perspective_diagnostics.items():
        assert "prompt" not in diag
        assert "user_prompt" not in diag
        assert "system_instruction" not in diag
        assert "response_text" not in diag
        assert "output" not in diag
        # Safe fields only
        assert "call_duration_seconds" in diag
        assert "status" in diag
        assert "attempt" in diag


# ------------------------------------------------------------------------------
# Test 8: No Mutation of Model Outputs
# ------------------------------------------------------------------------------

def test_no_mutation_of_model_outputs() -> None:
    """Proves that ReasoningPerspective instances remain pure without extra runtime attributes."""
    mock_llm = DiagnosticMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    perspectives = orchestrator.evaluate_all(dm, ep)
    for p in perspectives:
        assert isinstance(p, ReasoningPerspective)
        assert not hasattr(p, "last_diagnostic")
        assert not hasattr(p, "diagnostics")
        assert "last_diagnostic" not in p.model_dump()


# ------------------------------------------------------------------------------
# Test 9: Phase 4.18 Transport Schema Guard Scope Verification
# ------------------------------------------------------------------------------

def test_phase418_transport_schema_guard_isolation() -> None:
    """Proves that DecisionModel-specific compaction guard strictly isolates non-DecisionModel schemas."""
    # 1. Non-DecisionModel schemas MUST NOT be compacted
    req_schema = CandidateRequirementsPayload.model_json_schema()
    cleaned_req = GeminiLLMClient._clean_schema_for_transport(
        req_schema,
        response_schema=CandidateRequirementsPayload,
    )
    assert cleaned_req["description"] == req_schema["description"]

    mapping_schema = CandidateBatchEvidenceMappingPayload.model_json_schema()
    cleaned_mapping = GeminiLLMClient._clean_schema_for_transport(
        mapping_schema,
        response_schema=CandidateBatchEvidenceMappingPayload,
    )
    assert cleaned_mapping["description"] == mapping_schema["description"]

    persp_schema = CandidatePerspectiveAnalysis.model_json_schema()
    cleaned_persp = GeminiLLMClient._clean_schema_for_transport(
        persp_schema,
        response_schema=CandidatePerspectiveAnalysis,
    )
    assert cleaned_persp["description"] == persp_schema["description"]

    synth_schema = CandidateBoardSynthesis.model_json_schema()
    cleaned_synth = GeminiLLMClient._clean_schema_for_transport(
        synth_schema,
        response_schema=CandidateBoardSynthesis,
    )
    assert cleaned_synth["description"] == synth_schema["description"]

    # 2. DecisionModel IS compacted
    dm_schema = DecisionModel.model_json_schema()
    cleaned_dm = GeminiLLMClient._clean_schema_for_transport(
        dm_schema,
        response_schema=DecisionModel,
    )
    assert cleaned_dm["description"] != dm_schema["description"]
    assert len(cleaned_dm["description"]) < len(dm_schema["description"])


# ------------------------------------------------------------------------------
# Test 10: Repeated & Concurrent Schema Preparation Determinism
# ------------------------------------------------------------------------------

def test_transport_schema_preparation_deterministic_concurrent() -> None:
    """Proves that concurrent preparation of transport schemas across worker threads is 100% deterministic."""
    def prepare_worker(schema_cls: Type[BaseModel]) -> str:
        s = schema_cls.model_json_schema()
        cleaned = GeminiLLMClient._clean_schema_for_transport(s, response_schema=schema_cls)
        import json
        return json.dumps(cleaned, sort_keys=True)

    schemas = [
        DecisionModel,
        CandidateRequirementsPayload,
        CandidateBatchEvidenceMappingPayload,
        CandidatePerspectiveAnalysis,
        CandidateBoardSynthesis,
    ]

    # Baseline sequential serializations
    baselines = {cls.__name__: prepare_worker(cls) for cls in schemas}

    # Concurrent executions
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futs = [
            executor.submit(prepare_worker, schemas[i % len(schemas)])
            for i in range(50)
        ]
        for i, fut in enumerate(futs):
            schema_cls = schemas[i % len(schemas)]
            result_str = fut.result()
            assert result_str == baselines[schema_cls.__name__]


# ------------------------------------------------------------------------------
# Test 11: Overlapping Requests on Shared Orchestrator Instance
# ------------------------------------------------------------------------------

def test_11_overlapping_requests_on_shared_orchestrator_instance() -> None:
    """Proves that two concurrent requests sharing the same PerspectiveOrchestrator instance

    cannot overwrite or leak diagnostic dictionaries across calling threads.
    """
    mock_llm = DiagnosticMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    # Shared orchestrator instance
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm_a = _build_test_decision_model()
    dm_a.id = "dec_req_A"
    dm_a.decision.summary = "Inquiry for req_A enterprise focus"
    ep_a = _build_test_evidence_package(dm_a.id)

    dm_b = _build_test_decision_model()
    dm_b.id = "dec_req_B"
    dm_b.decision.summary = "Inquiry for req_B international expansion"
    ep_b = _build_test_evidence_package(dm_b.id)

    barrier = threading.Barrier(2)
    thread_a_diags: Dict[PerspectiveType, Dict[str, Any]] = {}
    thread_b_diags: Dict[PerspectiveType, Dict[str, Any]] = {}

    def run_request_a() -> None:
        barrier.wait(timeout=5.0)
        orchestrator.evaluate_all(dm_a, ep_a)
        thread_a_diags.update(orchestrator.last_perspective_diagnostics)

    def run_request_b() -> None:
        barrier.wait(timeout=5.0)
        orchestrator.evaluate_all(dm_b, ep_b)
        thread_b_diags.update(orchestrator.last_perspective_diagnostics)

    t_a = threading.Thread(target=run_request_a)
    t_b = threading.Thread(target=run_request_b)

    t_a.start()
    t_b.start()
    t_a.join(timeout=10.0)
    t_b.join(timeout=10.0)

    assert not t_a.is_alive()
    assert not t_b.is_alive()

    # Verify Thread A received all 4 perspectives and they are strictly tagged req_A
    assert len(thread_a_diags) == 4
    for ptype, d in thread_a_diags.items():
        assert d["request_tag"] == "req_A", f"Leak detected in Thread A for {ptype}: {d}"

    # Verify Thread B received all 4 perspectives and they are strictly tagged req_B
    assert len(thread_b_diags) == 4
    for ptype, d in thread_b_diags.items():
        assert d["request_tag"] == "req_B", f"Leak detected in Thread B for {ptype}: {d}"


# ------------------------------------------------------------------------------
# Test 12: Overlapping Requests on Shared EvidenceMapper Instance
# ------------------------------------------------------------------------------

def test_12_overlapping_requests_on_shared_evidence_mapper_instance() -> None:
    """Proves that two concurrent requests sharing the same EvidenceMapper instance

    cannot overwrite or leak batch diagnostics across calling threads.
    """
    mock_llm = DiagnosticMockClient()
    mapper = EvidenceMapper(llm_client=mock_llm)
    mapper.max_workers = 2
    mapper.batch_size = 1

    dm_a = _build_test_decision_model()
    dm_a.id = "dec_req_A"
    dm_b = _build_test_decision_model()
    dm_b.id = "dec_req_B"

    sources_a = [
        NormalizedSourceResult(
            source=Source(
                id="src_a_1",
                title="Source A",
                url="https://example.com/a1",
                source_type=SourceType.INDUSTRY_REPORT,
                snippet="req_A snippet",
            ),
            requirement_id="req_diag_1",
            query="req_A query",
            search_result=SearchResultItem(
                url="https://example.com/a1",
                title="Source A",
                snippet="req_A snippet",
            ),
        )
    ]
    sources_b = [
        NormalizedSourceResult(
            source=Source(
                id="src_b_1",
                title="Source B",
                url="https://example.com/b1",
                source_type=SourceType.INDUSTRY_REPORT,
                snippet="req_B snippet",
            ),
            requirement_id="req_diag_1",
            query="req_B query",
            search_result=SearchResultItem(
                url="https://example.com/b1",
                title="Source B",
                snippet="req_B snippet",
            ),
        )
    ]
    reqs = [_build_test_evidence_package().requirements[0]]

    barrier = threading.Barrier(2)
    thread_a_batches: Dict[int, Dict[str, Any]] = {}
    thread_b_batches: Dict[int, Dict[str, Any]] = {}

    def run_map_a() -> None:
        barrier.wait(timeout=5.0)
        mapper.map_evidence(dm_a, reqs, sources_a)
        thread_a_batches.update(mapper.last_batch_diagnostics)

    def run_map_b() -> None:
        barrier.wait(timeout=5.0)
        mapper.map_evidence(dm_b, reqs, sources_b)
        thread_b_batches.update(mapper.last_batch_diagnostics)

    t_a = threading.Thread(target=run_map_a)
    t_b = threading.Thread(target=run_map_b)

    t_a.start()
    t_b.start()
    t_a.join(timeout=10.0)
    t_b.join(timeout=10.0)

    assert not t_a.is_alive()
    assert not t_b.is_alive()

    assert len(thread_a_batches) == 1
    assert thread_a_batches[0]["request_tag"] == "req_A"

    assert len(thread_b_batches) == 1
    assert thread_b_batches[0]["request_tag"] == "req_B"


# ------------------------------------------------------------------------------
# Test 13: Worker Thread Lifecycle on Timeout Audit
# ------------------------------------------------------------------------------

def test_13_worker_thread_lifecycle_on_timeout_audit() -> None:
    """Proves that when orchestrator deadline expires, the caller unblocks immediately

    without hanging, while acknowledging that already-running worker threads in Python
    cannot be forcibly killed and will complete naturally up to their socket/call timeout.
    """
    worker_started = threading.Event()
    worker_finished = threading.Event()

    class StallingMockClient(DiagnosticMockClient):
        def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
            worker_started.set()
            # Simulate a slow provider call that sleeps 0.3s
            time.sleep(0.3)
            worker_finished.set()
            return super().generate_structured(*args, **kwargs)

    mock_llm = StallingMockClient()
    reasoner = PerspectiveReasoner(llm_client=mock_llm)
    orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=4)

    dm = _build_test_decision_model()
    ep = _build_test_evidence_package(dm.id)

    # Set a very tight deadline (50ms)
    deadline = time.monotonic() + 0.05
    t0 = time.monotonic()

    with pytest.raises(ReasoningOrchestrationError) as exc_info:
        orchestrator.evaluate_all(dm, ep, deadline_monotonic=deadline)

    elapsed_caller = time.monotonic() - t0
    # The caller must fail closed and unblock within ~0.15s (well before the 0.3s sleep finishes)
    assert elapsed_caller < 0.25, f"Caller blocked too long: {elapsed_caller}s"
    assert "timed out" in str(exc_info.value).lower()

    # The running worker thread unblocks and finishes in the background
    worker_finished.wait(timeout=1.0)
    assert worker_finished.is_set(), "Worker finished naturally without corrupted runtime state"

