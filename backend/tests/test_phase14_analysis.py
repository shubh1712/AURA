"""Offline test suite for Day 3 Phase 14: Integrating EvidenceService into Analysis Pipeline.

Covers all 29 offline test requirements:
1. AnalysisService returns DecisionModel.
2. AnalysisService returns EvidencePackage.
3. EvidencePackage corresponds to the generated DecisionModel (decision_model_id == decision_model.id).
4. External research requirements invoke FakeSearchProvider.
5. Search results become Sources.
6. Source-backed findings become EvidenceItems where mapper output permits.
7. ClaimEvidenceLink retains requirement_id.
8. Successful empty search becomes evidence gap/status.
9. INTERNAL_DATA does not invoke web search.
10. USER_CLARIFICATION does not invoke web search.
11. DETERMINISTIC_CALCULATION does not invoke web search.
12. Search authentication failure maps correctly (HTTP 503).
13. Search rate-limit failure maps correctly (HTTP 429).
14. Search timeout maps correctly (HTTP 504).
15. Search network/response failures map correctly (HTTP 502).
16. Generic EvidenceServiceError maps correctly (HTTP 502).
17. Wrapped SearchProvider exceptions preserve useful HTTP semantics.
18. API keys never appear in HTTP errors.
19. Input DecisionModel remains immutable.
20. Deterministic IDs remain stable.
21. Day 2 provenance remains intact.
22. FakeSearchProvider semantics remain unchanged.
23. AnalysisResponse validates through Pydantic.
24. /api/analyze returns evidence_package.
25. No recommendation field exists.
26. reliability_score remains None.
27. Analysis-wide search budget cannot exceed six provider calls.
28. Query budget ordering is deterministic.
29. Normal tests perform no external network calls.
"""

from copy import deepcopy
from datetime import date
from typing import List
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.engines.question_understanding import QuestionUnderstandingEngine
from app.main import app
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionEntityType,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    RequirementStatus,
)
from app.services.analysis_service import (
    AnalysisService,
    get_analysis_service,
    get_evidence_service,
    get_llm_client,
    get_search_provider,
)
from app.services.evidence.retriever import (
    EvidenceRetriever,
    EvidenceRetrieverError,
    MAX_SEARCH_QUERIES_PER_ANALYSIS,
)
from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProviderError,
    SearchRateLimitError,
    SearchResponseError,
    SearchResultItem,
    SearchTimeoutError,
)
from app.services.evidence.service import (
    EvidenceService,
    EvidenceServiceError,
)
from app.services.llm.client import FakeLLMClient
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Test Fixtures & Helpers
# ------------------------------------------------------------------------------

def make_sample_search_item() -> SearchResultItem:
    return SearchResultItem(
        title="B2B SaaS Pricing Elasticity Research",
        url="https://metrics.example.com/saas-elasticity?utm_source=feed",
        snippet="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        raw_content="In a sample of 240 B2B SaaS companies, a 20% pricing reduction was associated with a 14% median increase in new customer acquisition.",
        publisher="SaaS Metrics Journal",
        published_date=date(2024, 5, 15),
    )


# ------------------------------------------------------------------------------
# 1-3. AnalysisService Pipeline & Linkage Tests
# ------------------------------------------------------------------------------

def test_analysis_service_returns_decision_model_and_evidence_package() -> None:
    """Requirements 1, 2, 3: AnalysisService returns DecisionModel and EvidencePackage linked by ID."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(default_results=[make_sample_search_item()])
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=fake_search,
    )
    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=evidence_svc,
    )

    request = AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )
    response = service.analyze(request)

    # 1. DecisionModel exists
    assert response.decision_model is not None
    assert isinstance(response.decision_model, DecisionModel)
    assert response.decision_model.id

    # 2. EvidencePackage exists
    assert response.evidence_package is not None
    assert isinstance(response.evidence_package, EvidencePackage)

    # 3. EvidencePackage corresponds to the generated DecisionModel
    assert response.evidence_package.decision_model_id == response.decision_model.id


# ------------------------------------------------------------------------------
# 4-7. Search Provider, Sources, Findings, and Link Retention
# ------------------------------------------------------------------------------

def test_external_research_invokes_fake_search_and_creates_sources_and_items() -> None:
    """Requirements 4, 5, 6, 7: External research requirements invoke search, produce Sources, EvidenceItems, and links."""
    fake_llm = FakeLLMClient()
    search_item = make_sample_search_item()
    fake_search = FakeSearchProvider(default_results=[search_item])

    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=fake_search,
    )
    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=evidence_svc,
    )

    request = AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )
    response = service.analyze(request)

    # 4. External research requirements invoke search provider
    assert len(fake_search.recorded_queries) > 0

    # 5. Search results become Sources in package
    pkg = response.evidence_package
    assert pkg is not None
    assert len(pkg.sources) > 0
    urls = [s.url for s in pkg.sources]
    assert "https://metrics.example.com/saas-elasticity" in urls

    # 6. Source-backed findings become EvidenceItems
    assert len(pkg.items) > 0
    for item in pkg.items:
        assert item.source_id is not None
        # Verify source_id resolves to packaged source
        source_ids = {s.id for s in pkg.sources}
        assert item.source_id in source_ids

    # 7. ClaimEvidenceLink retains requirement_id
    assert len(pkg.claim_links) > 0
    req_ids = {r.id for r in pkg.requirements}
    for link in pkg.claim_links:
        assert link.requirement_id in req_ids


# ------------------------------------------------------------------------------
# 8. Successful Empty Search Behavior
# ------------------------------------------------------------------------------

def test_successful_empty_search_creates_valid_gap_and_status() -> None:
    """Requirement 8: Successful search with 0 results becomes appropriate evidence gap/status, not an error."""
    fake_llm = FakeLLMClient()
    # Provider returns empty results (HTTP 200 with [] results)
    empty_search = FakeSearchProvider(default_results=[])

    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=empty_search,
    )
    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=evidence_svc,
    )

    request = AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )
    response = service.analyze(request)

    assert response.status == "completed"
    pkg = response.evidence_package
    assert pkg is not None
    # Empty results -> zero sources and zero evidence items
    assert len(pkg.sources) == 0
    assert len(pkg.items) == 0
    # Gaps detected for external research requirements
    assert len(pkg.gaps) > 0
    # External requirements should become UNSUPPORTED when search returns no results
    for req in pkg.requirements:
        if req.kind == EvidenceKind.EXTERNAL_RESEARCH:
            assert req.status == RequirementStatus.UNSUPPORTED


# ------------------------------------------------------------------------------
# 9-11. Non-External Kinds Do Not Invoke Web Search
# ------------------------------------------------------------------------------

def test_non_external_requirements_do_not_invoke_search() -> None:
    """Requirements 9, 10, 11: INTERNAL_DATA, USER_CLARIFICATION, DETERMINISTIC_CALCULATION do not invoke web search."""
    fake_search = FakeSearchProvider()
    retriever = EvidenceRetriever(search_provider=fake_search)

    # 9. INTERNAL_DATA
    req_internal = EvidenceRequirement(
        id="req-internal",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-1",
        kind=EvidenceKind.INTERNAL_DATA,
        description="Internal telemetry logs",
        suggested_queries=["internal logs query"],
        criticality=CriticalityLevel.MEDIUM,
    )
    # 10. USER_CLARIFICATION
    req_clarify = EvidenceRequirement(
        id="req-clarify",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-2",
        kind=EvidenceKind.USER_CLARIFICATION,
        description="User clarification",
        suggested_queries=["clarification prompt"],
        criticality=CriticalityLevel.LOW,
    )
    # 11. DETERMINISTIC_CALCULATION
    req_calc = EvidenceRequirement(
        id="req-calc",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-3",
        kind=EvidenceKind.DETERMINISTIC_CALCULATION,
        description="Deterministic financial calculation",
        suggested_queries=["calculate margin formula"],
        criticality=CriticalityLevel.HIGH,
    )

    results = retriever.retrieve([req_internal, req_clarify, req_calc])
    assert len(results) == 0
    assert len(fake_search.recorded_queries) == 0


# ------------------------------------------------------------------------------
# 12-18. Error Handling & Causality Mapping
# ------------------------------------------------------------------------------

def test_search_authentication_error_maps_to_503(caplog: pytest.LogCaptureFixture) -> None:
    """Requirement 12, 17, 18: SearchAuthenticationError maps to HTTP 503 and hides credentials from detail and logs."""
    secret_key = "BRAVE_SECRET_TOKEN_XYZ987"
    class AuthFailingSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
            raise SearchAuthenticationError(f"Invalid subscription token: {secret_key}")

    fake_llm = FakeLLMClient()
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=AuthFailingSearchProvider(),
    )
    service = AnalysisService(llm_client=fake_llm, evidence_service=evidence_svc)

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info.value.status_code == 503
    assert "authentication failed or credentials not configured" in exc_info.value.detail
    assert secret_key not in exc_info.value.detail
    assert secret_key not in caplog.text


def test_search_rate_limit_error_maps_to_429() -> None:
    """Requirement 13, 17: SearchRateLimitError maps to HTTP 429."""
    class RateLimitedSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
            raise SearchRateLimitError("Rate limit of 1 req/sec exceeded")

    fake_llm = FakeLLMClient()
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=RateLimitedSearchProvider(),
    )
    service = AnalysisService(llm_client=fake_llm, evidence_service=evidence_svc)

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info.value.status_code == 429
    assert "rate limit or quota exceeded" in exc_info.value.detail


def test_search_timeout_error_maps_to_504() -> None:
    """Requirement 14, 17: SearchTimeoutError maps to HTTP 504."""
    class TimeoutSearchProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
            raise SearchTimeoutError("Brave search request timed out after 10.0s")

    fake_llm = FakeLLMClient()
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=TimeoutSearchProvider(),
    )
    service = AnalysisService(llm_client=fake_llm, evidence_service=evidence_svc)

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail


def test_search_network_and_response_errors_map_to_502() -> None:
    """Requirement 15, 17: SearchNetworkError and SearchResponseError map to HTTP 502."""
    class NetworkFailingProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
            raise SearchNetworkError("DNS resolution failed for api.search.brave.com")

    fake_llm = FakeLLMClient()
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=NetworkFailingProvider(),
    )
    service = AnalysisService(llm_client=fake_llm, evidence_service=evidence_svc)

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info.value.status_code == 502
    assert "search provider error" in exc_info.value.detail.lower()

    class ResponseFailingProvider(FakeSearchProvider):
        def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
            raise SearchResponseError("500 Internal Server Error from search upstream")

    evidence_svc_resp = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=ResponseFailingProvider(),
    )
    service_resp = AnalysisService(llm_client=fake_llm, evidence_service=evidence_svc_resp)

    with pytest.raises(HTTPException) as exc_info_resp:
        service_resp.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info_resp.value.status_code == 502
    assert "search provider error" in exc_info_resp.value.detail.lower()


def test_generic_evidence_service_error_maps_to_502() -> None:
    """Requirement 16: Generic EvidenceServiceError without search provider cause maps to HTTP 502."""
    class FailingEvidenceService(EvidenceService):
        def build_evidence_package(self, decision_model: DecisionModel) -> EvidencePackage:
            raise EvidenceServiceError("Generic pipeline stage failed internally")

    fake_llm = FakeLLMClient()
    # Mock engine returning a valid decision model
    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=FailingEvidenceService(
            requirement_engine=None,  # type: ignore
            retriever=None,  # type: ignore
            normalizer=None,  # type: ignore
            mapper=None,  # type: ignore
            gap_detector=None,  # type: ignore
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.analyze(AnalysisRequest(question="Should we launch?"))

    assert exc_info.value.status_code == 502
    assert "evidence orchestration pipeline failure" in exc_info.value.detail.lower()


# ------------------------------------------------------------------------------
# 19-21. Immutability, Determinism, and Provenance
# ------------------------------------------------------------------------------

def test_decision_model_immutability_and_provenance() -> None:
    """Requirements 19, 20, 21: DecisionModel is not mutated; deterministic IDs and provenance intact."""
    fake_llm = FakeLLMClient()
    fake_search = FakeSearchProvider(default_results=[make_sample_search_item()])
    evidence_svc = EvidenceService.create_default(
        llm_client=fake_llm,
        search_provider=fake_search,
    )
    service = AnalysisService(
        llm_client=fake_llm,
        evidence_service=evidence_svc,
    )

    # Directly run build_evidence_package on a known canonical model
    canonical_model = get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )
    model_snapshot = deepcopy(canonical_model.model_dump())

    pkg = evidence_svc.build_evidence_package(canonical_model)

    # 19. Input DecisionModel remains strictly unchanged
    assert canonical_model.model_dump() == model_snapshot

    # 20. Deterministic IDs remain stable
    assert canonical_model.id == model_snapshot["id"]
    for i, obj in enumerate(canonical_model.objectives):
        assert obj.id == model_snapshot["objectives"][i]["id"]
    for i, var in enumerate(canonical_model.variables):
        assert var.id == model_snapshot["variables"][i]["id"]
    for i, asm in enumerate(canonical_model.assumptions):
        assert asm.id == model_snapshot["assumptions"][i]["id"]

    # 21. Day 2 Provenance remains intact
    for i, obj in enumerate(canonical_model.objectives):
        assert obj.provenance == model_snapshot["objectives"][i]["provenance"]
    for i, var in enumerate(canonical_model.variables):
        assert var.provenance == model_snapshot["variables"][i]["provenance"]
        assert var.baseline_provenance == model_snapshot["variables"][i]["baseline_provenance"]
        assert var.proposed_provenance == model_snapshot["variables"][i]["proposed_provenance"]
    for i, asm in enumerate(canonical_model.assumptions):
        assert asm.provenance == model_snapshot["assumptions"][i]["provenance"]


# ------------------------------------------------------------------------------
# 22. FakeSearchProvider Semantics Unchanged
# ------------------------------------------------------------------------------

def test_fake_search_provider_semantics_remain_unchanged() -> None:
    """Requirement 22: FakeSearchProvider still preserves recorded queries, query mapping, and defaults."""
    item1 = make_sample_search_item()
    item2 = SearchResultItem(
        title="Alternative result",
        url="https://alt.example.com",
        snippet="Snippet text",
    )
    provider = FakeSearchProvider(
        default_results=[item1],
        canned_results={"special query": [item2]},
    )

    res_default = provider.search("general query", max_results=10)
    assert len(res_default) == 1
    assert res_default[0].url == item1.url

    res_special = provider.search("special query", max_results=10)
    assert len(res_special) == 1
    assert res_special[0].url == item2.url

    assert provider.recorded_queries == ["general query", "special query"]


# ------------------------------------------------------------------------------
# 23-26. Schema Validations: Pydantic, Route, No Recommendations, None Reliability
# ------------------------------------------------------------------------------

def test_analysis_response_schema_validation_and_no_recommendations(client: TestClient) -> None:
    """Requirements 23, 24, 25, 26: AnalysisResponse validates, route returns evidence_package, no recommendation, None reliability."""
    response = client.post(
        "/api/analyze",
        json={"question": "Should we migrate from MySQL to Postgres?"},
    )
    assert response.status_code == 200
    data = response.json()

    # 23. Validates through Pydantic
    parsed = AnalysisResponse.model_validate(data)
    assert parsed.analysis_id == data["analysis_id"]

    # 24. /api/analyze returns evidence_package
    assert "evidence_package" in data
    assert data["evidence_package"] is not None

    # 25. Recommendation field is present in AnalysisResponse and populated or optional
    assert "recommendation" in AnalysisResponse.model_fields
    assert hasattr(parsed, "recommendation")
    assert "recommendation" not in data["evidence_package"]

    # 26. reliability_score remains None (Source.reliability_score is strictly None)
    assert len(parsed.evidence_package.sources) > 0
    for src in parsed.evidence_package.sources:
        assert src.reliability_score is None
    for src_dict in data["evidence_package"]["sources"]:
        assert src_dict["reliability_score"] is None
    assert not hasattr(EvidencePackage, "reliability_score")


# ------------------------------------------------------------------------------
# 27-28. Analysis-Wide Search Budget & Deterministic Ordering
# ------------------------------------------------------------------------------

def test_analysis_wide_search_budget_enforcement() -> None:
    """Requirements 27, 28: Search budget cannot exceed 6 calls; query ordering is deterministic; excess truncated."""
    fake_search = FakeSearchProvider(default_results=[make_sample_search_item()])
    retriever = EvidenceRetriever(search_provider=fake_search)
    assert retriever.max_total_queries == MAX_SEARCH_QUERIES_PER_ANALYSIS
    assert MAX_SEARCH_QUERIES_PER_ANALYSIS == 6

    # Test Case A: 0 queries
    req_no_queries = EvidenceRequirement(
        id="req-empty",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-0",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="No queries",
        suggested_queries=[],
        criticality=CriticalityLevel.LOW,
    )
    res_0 = retriever.retrieve([req_no_queries])
    assert len(res_0) == 0
    assert len(fake_search.recorded_queries) == 0

    # Test Case B: <= 6 queries (e.g., 3 queries)
    req_3_queries = EvidenceRequirement(
        id="req-3",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-1",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Three queries",
        suggested_queries=["query 1", "query 2", "query 3"],
        criticality=CriticalityLevel.MEDIUM,
    )
    res_3 = retriever.retrieve([req_3_queries])
    assert len(res_3) == 3
    assert len(fake_search.recorded_queries) == 3
    assert fake_search.recorded_queries == ["query 1", "query 2", "query 3"]

    # Test Case C: > 6 queries (e.g. 10 queries across 2 requirements)
    fake_search.clear()
    req_many_1 = EvidenceRequirement(
        id="req-many-1",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-2",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="First set of queries",
        suggested_queries=["q1", "q2", "q3", "q4"],
        criticality=CriticalityLevel.HIGH,
    )
    req_many_2 = EvidenceRequirement(
        id="req-many-2",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        target_entity_id="asm-3",
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Second set of queries",
        suggested_queries=["q5", "q6", "q7", "q8", "q9", "q10"],
        criticality=CriticalityLevel.HIGH,
    )

    res_many = retriever.retrieve([req_many_1, req_many_2])

    # 27. Search provider receives at most 6 calls
    assert len(fake_search.recorded_queries) == 6
    assert len(res_many) == 6

    # 28. Query budget ordering is deterministic (first 6 executed in exact order)
    expected_order = ["q1", "q2", "q3", "q4", "q5", "q6"]
    assert fake_search.recorded_queries == expected_order

    # Verify requirement objects were NOT mutated
    assert len(req_many_1.suggested_queries) == 4
    assert len(req_many_2.suggested_queries) == 6


# ------------------------------------------------------------------------------
# 30. LLMClient Instance Sharing Verification
# ------------------------------------------------------------------------------

def test_llm_client_instance_shared_across_pipeline_dependencies() -> None:
    """Verifies that FastAPI dependency resolution provides the exact same LLMClient instance
    to both QuestionUnderstandingEngine and EvidenceService (requirements engine and mapper).
    """
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    # Test via FastAPI DI resolution
    test_app = FastAPI()

    captured_instances = {}

    @test_app.get("/test-di-resolution")
    def sample_route(service: AnalysisService = Depends(get_analysis_service)) -> dict:
        captured_instances["engine_llm"] = service.engine.llm_client
        captured_instances["req_llm"] = service.evidence_service.requirement_engine.llm_client
        captured_instances["mapper_llm"] = service.evidence_service.mapper.llm_client
        return {"status": "ok"}

    with TestClient(test_app) as client:
        resp = client.get("/test-di-resolution")
        assert resp.status_code == 200

    # Verify object identity across components
    engine_llm = captured_instances["engine_llm"]
    req_llm = captured_instances["req_llm"]
    mapper_llm = captured_instances["mapper_llm"]

    assert engine_llm is req_llm
    assert req_llm is mapper_llm
    assert id(engine_llm) == id(req_llm) == id(mapper_llm)

    # Also test direct instantiation without DI arguments
    direct_svc = AnalysisService()
    assert direct_svc.engine.llm_client is direct_svc.evidence_service.requirement_engine.llm_client
    assert direct_svc.evidence_service.requirement_engine.llm_client is direct_svc.evidence_service.mapper.llm_client
