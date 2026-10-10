"""Deterministic regression tests for AURA Day 5 Phase 4A:
Diagnose and Fix Gemini HTTP 400 in Recommendation Engine.

Tests:
1. Root-cause schema reproduction: CandidateActionItem.title stripped vs preserved.
2. Safe transport cleaning across all system schemas.
3. Sanitized Gemini HTTP 400 diagnostics without leaking secrets or prompts.
4. Error classification: HTTP 400 invalid request vs actual timeout vs validation failure.
5. End-to-end successful recommendation generation with clean schema transport.
6. Stage 4 partial-success fallback preserves Stages 1-3 with accurate non-timeout error report.
7. Historical response and schema serialization compatibility.
"""

import json
from typing import Any, Dict
import httpx
import pytest
from pydantic import BaseModel, Field

from app.schemas.analysis import AnalysisRequest
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import (
    CandidateBoardSynthesis,
    CandidatePerspectiveAnalysis,
    ReasoningBoard,
)
from app.schemas.recommendation import (
    CandidateActionItem,
    CandidateDecisionRecommendation,
    DecisionRecommendation,
)
from app.services.analysis_service import AnalysisService, _is_timeout_error
from app.services.evidence.mapper import CandidateEvidenceMappingPayload
from app.services.evidence.requirements import CandidateRequirementsPayload
from app.services.llm.client import (
    LLMConfig,
    LLMError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.recommendation.generator import RecommendationGenerator
from app.services.recommendation.service import RecommendationService
from app.services.recommendation.validator import (
    RecommendationEvaluationError,
    RecommendationServiceError,
    RecommendationValidationError,
)
from tests.test_recommendation_engine import (
    MockLLMClient,
    build_test_upstream_artifacts,
    build_valid_candidate,
)
from tests.test_phase5_integration import FakeLLMClient


# ------------------------------------------------------------------------------
# Test 1: Deterministic Root-Cause Schema Reproduction
# ------------------------------------------------------------------------------

def test_01_root_cause_reproduction_title_property_retention():
    """Reproduces the exact bug and proves the fix:
    - Pre-fix: _strip_titles stripped properties['title'] because key was 'title'.
      Result: 'title' was present in 'required', but absent from 'properties'.
      Gemini returned HTTP 400: 'Invalid JSON schema: required property title is not present in properties'.
    - Post-fix: properties['title'] is preserved; only metadata titles are stripped.
    """
    raw_schema = CandidateDecisionRecommendation.model_json_schema()

    # Pre-fix simulation: stripped every key named 'title'
    def buggy_strip_titles(s: Any) -> Any:
        if isinstance(s, dict):
            return {k: buggy_strip_titles(v) for k, v in s.items() if k != "title"}
        if isinstance(s, list):
            return [buggy_strip_titles(item) for item in s]
        return s

    buggy_cleaned = buggy_strip_titles(raw_schema)
    action_item_buggy = buggy_cleaned.get("$defs", {}).get("CandidateActionItem", {})
    # Under the bug, 'title' was in required, but MISSING from properties
    assert "title" in action_item_buggy.get("required", [])
    assert "title" not in action_item_buggy.get("properties", {})

    # Post-fix: using production GeminiLLMClient._clean_schema_for_transport
    fixed_cleaned = GeminiLLMClient._clean_schema_for_transport(
        raw_schema, response_schema=CandidateDecisionRecommendation
    )
    action_item_fixed = fixed_cleaned.get("$defs", {}).get("CandidateActionItem", {})
    # In the fix: 'title' is strictly retained in properties AND required
    assert "title" in action_item_fixed.get("properties", {})
    assert "title" in action_item_fixed.get("required", [])
    assert action_item_fixed["properties"]["title"]["type"] == "string"

    # Verify that metadata titles were cleanly stripped
    assert "title" not in fixed_cleaned  # root metadata title stripped
    assert "title" not in action_item_fixed  # schema metadata title stripped


# ------------------------------------------------------------------------------
# Test 2: Safe Transport Schema Validity Across All System Schemas
# ------------------------------------------------------------------------------

def test_02_all_system_schemas_have_consistent_required_and_properties():
    """Validates that for all 6 system schemas, every item in 'required' strictly exists in 'properties'."""
    system_schemas = [
        ("CandidateDecisionRecommendation", CandidateDecisionRecommendation),
        ("DecisionModel", DecisionModel),
        ("CandidatePerspectiveAnalysis", CandidatePerspectiveAnalysis),
        ("CandidateBoardSynthesis", CandidateBoardSynthesis),
        ("CandidateRequirementsPayload", CandidateRequirementsPayload),
        ("CandidateEvidenceMappingPayload", CandidateEvidenceMappingPayload),
    ]

    for schema_name, model_cls in system_schemas:
        raw = model_cls.model_json_schema()
        cleaned = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=model_cls)

        def verify_schema(node: Any, path: str = "") -> None:
            if isinstance(node, dict):
                if "properties" in node and "required" in node:
                    props = node["properties"]
                    reqs = node["required"]
                    for req in reqs:
                        assert req in props, (
                            f"Schema {schema_name} at {path}: required field '{req}' "
                            f"missing from properties: {list(props.keys())}"
                        )
                for k, v in node.items():
                    verify_schema(v, f"{path}.{k}" if path else k)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    verify_schema(item, f"{path}[{i}]")

        verify_schema(cleaned)


# ------------------------------------------------------------------------------
# Test 3: Gemini HTTP 400 Sanitized Diagnostics
# ------------------------------------------------------------------------------

def test_03_gemini_http_400_captures_sanitized_diagnostics(monkeypatch):
    """Verifies that an HTTP 400 client error captures complete sanitized diagnostics
    in LLMError.details and never leaks authorization headers, API keys, or raw prompts.
    """
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")

    secret_key = "AIzaSySecretApiKey123456789"
    auth_header = "Bearer ya29.SecretOauthToken98765"

    def mock_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "message": f"Invalid JSON schema: required property 'title' is not present in properties. Key: key={secret_key} and auth={auth_header}",
                    "status": "INVALID_ARGUMENT",
                }
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = GeminiLLMClient(
        api_key="fake-test-key",
        http_client=http_client,
        default_model="gemini-2.5-flash",
    )

    with pytest.raises(LLMError) as exc_info:
        client.generate_structured(
            prompt="Confidential customer strategy prompt text",
            response_schema=CandidateDecisionRecommendation,
            config=LLMConfig(model_name="gemini-2.5-flash", temperature=0.3, max_output_tokens=2048, stage="recommendation"),
        )

    err = exc_info.value
    details = err.details

    # Status code and model name
    assert details["status_code"] == 400
    assert details["model"] == "gemini-2.5-flash"
    assert details["stage"] == "recommendation"
    assert details["is_structured"] is True
    assert details["schema_name"] == "CandidateDecisionRecommendation"

    # Generation configuration
    assert details["generation_config"]["temperature"] == 0.3
    assert details["generation_config"]["max_output_tokens"] == 2048

    # Payload size without printing content
    assert details["payload_size_chars"] > 0
    assert "Confidential customer strategy prompt text" not in str(details)

    # Gemini status and message
    assert details["gemini_status"] == "INVALID_ARGUMENT"
    assert "Invalid JSON schema" in details["gemini_message"]

    # Security check: secrets must be redacted
    assert secret_key not in details["gemini_message"]
    assert auth_header not in details["gemini_message"]
    assert secret_key not in str(err)
    assert auth_header not in str(err)
    assert "REDACTED" in details["gemini_message"]


# ------------------------------------------------------------------------------
# Test 4: Error Classification Distinguishes HTTP 400 vs Timeout vs Validation
# ------------------------------------------------------------------------------

def test_04_error_classification_distinguishes_400_from_timeout():
    """Verifies that an HTTP 400 error is classified as 'client_error' / 'invalid request'
    and NOT misclassified as a timeout.
    """
    dm, ep, rb = build_test_upstream_artifacts()

    # Case A: HTTP 400 Client Error
    client_400 = MockLLMClient()
    client_400.raise_exc = LLMError(
        "Gemini API client error (400): Invalid JSON schema",
        details={
            "status_code": 400,
            "gemini_status": "INVALID_ARGUMENT",
            "gemini_message": "Invalid JSON schema: required property 'title' is not present in properties",
        },
    )
    generator_400 = RecommendationGenerator(llm_client=client_400)
    service_400 = RecommendationService(generator=generator_400)

    with pytest.raises(RecommendationServiceError) as exc_400:
        service_400.generate_recommendation(decision_model=dm, evidence_package=ep, reasoning_board=rb)

    assert "invalid request" in str(exc_400.value).lower()
    assert "timed out" not in str(exc_400.value).lower()
    assert not _is_timeout_error(exc_400.value)

    # Case B: Real Timeout Error
    client_timeout = MockLLMClient()
    client_timeout.raise_exc = LLMTimeoutError("Gemini request timed out after 30.0s")
    generator_timeout = RecommendationGenerator(llm_client=client_timeout)
    service_timeout = RecommendationService(generator=generator_timeout)

    with pytest.raises(RecommendationServiceError) as exc_to:
        service_timeout.generate_recommendation(decision_model=dm, evidence_package=ep, reasoning_board=rb)

    assert "timed out" in str(exc_to.value).lower()
    assert _is_timeout_error(exc_to.value)

    # Case C: Candidate Output Validation Failure
    client_val = MockLLMClient()
    client_val.raise_exc = LLMResponseValidationError("Missing required field")
    generator_val = RecommendationGenerator(llm_client=client_val)
    service_val = RecommendationService(generator=generator_val)

    with pytest.raises(RecommendationServiceError) as exc_v:
        service_val.generate_recommendation(decision_model=dm, evidence_package=ep, reasoning_board=rb)

    assert "validation failed" in str(exc_v.value).lower()
    assert "timed out" not in str(exc_v.value).lower()
    assert not _is_timeout_error(exc_v.value)


# ------------------------------------------------------------------------------
# Test 5: Successful Recommendation Generation with Validated Schema
# ------------------------------------------------------------------------------

def test_05_successful_recommendation_generation_retains_all_fields():
    """Verifies that recommendation generation succeeds completely when LLM client
    returns valid candidate, ensuring action plan titles, priorities, and gates remain intact.
    """
    dm, ep, rb = build_test_upstream_artifacts()
    cand = build_valid_candidate()

    mock_client = MockLLMClient()
    mock_client.return_candidate = cand

    service = RecommendationService.create_default(llm_client=mock_client)
    rec = service.generate_recommendation(decision_model=dm, evidence_package=ep, reasoning_board=rb)

    assert isinstance(rec, DecisionRecommendation)
    assert rec.id.startswith("rec_")
    assert rec.decision_status.value == "proceed"
    assert rec.action_plan is not None
    assert len(rec.action_plan.actions) >= 1
    # CandidateActionItem title is retained in authoritative ActionItem
    assert rec.action_plan.actions[0].title == "Enterprise Pilot Validation"
    assert len(rec.action_plan.actions[0].decision_gates) >= 1


# ------------------------------------------------------------------------------
# Test 6: Stage 4 Partial-Success Fallback with Accurate Error Classification
# ------------------------------------------------------------------------------

def test_06_stage4_400_preserves_stages_1_to_3_with_accurate_error():
    """Proves that when Stage 4 encounters an HTTP 400 client error:
    1. Stages 1-3 (DecisionModel, EvidencePackage, ReasoningBoard) are preserved intact.
    2. AnalysisResponse.status is 'partial_success'.
    3. recommendation_status is 'unavailable'.
    4. recommendation_error accurately identifies 'invalid request' and NOT 'timed out'.
    """
    fake_llm = FakeLLMClient()
    mock_client = MockLLMClient()
    mock_client.raise_exc = LLMError(
        "Gemini API client error (400): Invalid JSON schema",
        details={
            "status_code": 400,
            "gemini_status": "INVALID_ARGUMENT",
            "gemini_message": "Invalid JSON schema: required property 'title' is not present in properties",
        },
    )

    rec_service = RecommendationService(generator=RecommendationGenerator(llm_client=mock_client))
    analysis_service = AnalysisService(llm_client=fake_llm, recommendation_service=rec_service)

    req = AnalysisRequest(question="Strategic evaluation of expansion")
    response = analysis_service.analyze(req)

    # Partial success verification
    assert response.status == "partial_success"
    assert response.decision_model is not None
    assert response.evidence_package is not None
    assert response.reasoning_board is not None
    assert response.recommendation is None
    assert response.recommendation_status == "unavailable"

    # Crucial classification check: NOT falsely labeled as a timeout
    assert response.recommendation_error is not None
    assert "invalid request" in response.recommendation_error.lower()
    assert "timed out" not in response.recommendation_error.lower()


# ------------------------------------------------------------------------------
# Test 7: Historical Compatibility
# ------------------------------------------------------------------------------

def test_07_historical_day4_response_compatibility():
    """Ensures AnalysisResponse serializes cleanly and remains 100% backward compatible
    with Day 4 clients that do not parse recommendation objects.
    """
    fake_llm = FakeLLMClient()
    rec_service = RecommendationService.create_default(llm_client=fake_llm)
    analysis_service = AnalysisService(llm_client=fake_llm, recommendation_service=rec_service)

    req = AnalysisRequest(question="Expansion inquiry")
    response = analysis_service.analyze(req)

    dumped = response.model_dump(mode="json")
    assert "analysis_id" in dumped
    assert "decision_model" in dumped
    assert "evidence_package" in dumped
    assert "reasoning_board" in dumped
    assert "recommendation" in dumped
    assert "recommendation_status" in dumped
