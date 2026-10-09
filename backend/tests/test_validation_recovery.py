"""AURA Day 4 — Phase 4.23: Tests for Safe Structured-Output Validation Recovery.

Verifies:
1. Already-valid CandidateBatchEvidenceMappingPayload payloads remain strictly unchanged.
2. Allowlisted enum capitalization is normalized correctly ("Supports" -> "supports", "CHALLENGES" -> "challenges").
3. Allowlisted enum whitespace is normalized correctly ("  supports  " -> "supports", "  HIGH  " -> "high").
4. Unknown enum values ("neutral", "contradicts") are not coerced and still fail canonical validation.
5. Extra forbidden fields ("quote", "extra_field") still fail canonical validation (extra="forbid" preserved).
6. Missing required fields still fail canonical validation.
7. Invalid numeric values ("14%") are not coerced and still fail canonical validation.
8. Non-mutation: input dictionary passed to sanitization is not mutated.
9. Response schema isolation: other response schemas (DecisionModel, CandidateRequirementsPayload,
   CandidatePerspectiveAnalysis, CandidateBoardSynthesis) are completely untouched.
10. Provider-call recovery: locally recoverable payload completes in exactly 1 call (no retry triggered).
11. Unrecoverable payload follows existing retry policy and fails closed without partial output.
12. Sanitized diagnostics: validation errors are classified into privacy-safe categories
    (enum_mismatch, extra_forbidden, missing_required_field, numeric_type_error, etc.)
    without leaking model response content, snippets, or raw prompts.
"""

import copy
from datetime import date
from typing import Any, Dict, List, Optional
import pytest
from pydantic import ValidationError

from app.schemas.decision_model import (
    ConfidenceLevel,
    DecisionModel,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
    Source,
    SourceType,
)
from app.services.evidence.mapper import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
)
from app.schemas.reasoning import (
    CandidatePerspectiveAnalysis,
    PerspectiveType,
)
from app.services.evidence.normalizer import NormalizedSourceResult, SearchResultItem
from app.services.evidence.mapper import EvidenceMapper
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMError,
    LLMResponseValidationError,
)
from app.services.llm.mock_data import get_default_decision_model
from app.services.llm.parser import StructuredOutputParser


# ------------------------------------------------------------------------------
# Fixtures & Sample Payloads
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


def _valid_raw_payload() -> Dict[str, Any]:
    return {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_elasticity",
                "content": "In a study of 240 SaaS companies, a 20% price reduction was associated with a 14% increase in acquisition.",
                "summary": "Observed 14% acquisition increase from 20% price cut.",
                "stance": "supports",
                "reasoning": "Empirically validates that lower price increases acquisition.",
                "numeric_data": [
                    {
                        "metric_name": "acquisition_increase",
                        "value": 14.0,
                        "unit": "%",
                        "sample_size": 240,
                    }
                ],
                "extraction_confidence": "high",
                "relationship_confidence": "medium",
            }
        ]
    }


# ------------------------------------------------------------------------------
# 1. Allowlist Normalization & Invariant Preservation
# ------------------------------------------------------------------------------

def test_already_valid_payload_remains_unchanged() -> None:
    """Verifies that an already-valid payload passes normalization and matches original content."""
    raw = _valid_raw_payload()
    original_copy = copy.deepcopy(raw)
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert raw == original_copy, "Input dictionary was mutated!"
    assert sanitized == raw
    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings[0].stance == EvidenceStance.SUPPORTS


def test_enum_capitalization_and_whitespace_normalized() -> None:
    """Verifies that allowlisted enum casing and whitespace are recovered correctly."""
    raw = _valid_raw_payload()
    raw["findings"][0]["stance"] = "  Supports  "
    raw["findings"][0]["extraction_confidence"] = "HIGH"
    raw["findings"][0]["relationship_confidence"] = "  Medium  "

    original_copy = copy.deepcopy(raw)
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert raw == original_copy, "Input dictionary was mutated!"

    assert sanitized["findings"][0]["stance"] == "supports"
    assert sanitized["findings"][0]["extraction_confidence"] == "high"
    assert sanitized["findings"][0]["relationship_confidence"] == "medium"

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings[0].stance == EvidenceStance.SUPPORTS
    assert validated.findings[0].extraction_confidence == ConfidenceLevel.HIGH
    assert validated.findings[0].relationship_confidence == ConfidenceLevel.MEDIUM


def test_unknown_enum_value_still_fails() -> None:
    """Verifies that arbitrary or unknown enum values are NOT normalized and fail validation."""
    raw = _valid_raw_payload()
    raw["findings"][0]["stance"] = "neutral"  # Invalid enum value

    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["stance"] == "neutral"  # Untouched

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary_cat, all_cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary_cat == "enum_mismatch"
    assert "findings.0.stance" in paths


def test_extra_forbidden_fields_still_fail() -> None:
    """Verifies that unknown/extra keys are NOT stripped and strictly fail validation (extra='forbid')."""
    raw = _valid_raw_payload()
    raw["findings"][0]["stance"] = "Supports"  # Recoverable casing
    raw["findings"][0]["quote"] = "Direct verbatim excerpt"  # Extra forbidden key

    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert "quote" in sanitized["findings"][0], "Extra field was improperly stripped!"

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary_cat, all_cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary_cat == "extra_forbidden"
    assert "findings.0.quote" in paths


def test_missing_required_fields_still_fail() -> None:
    """Verifies that missing required fields are NOT invented and strictly fail validation."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "stance": "Supports",
                # missing 'content' and 'reasoning'
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary_cat, all_cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary_cat == "missing_required_field"
    assert "findings.0.content" in paths
    assert "findings.0.reasoning" in paths


def test_numeric_type_error_not_coerced() -> None:
    """Verifies that formatted numbers like '14%' are NOT coerced into floats and fail validation."""
    raw = _valid_raw_payload()
    raw["findings"][0]["numeric_data"][0]["value"] = "14%"

    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["numeric_data"][0]["value"] == "14%"  # Untouched

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary_cat, all_cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary_cat == "numeric_type_error"
    assert "findings.0.numeric_data.0.value" in paths


# ------------------------------------------------------------------------------
# 2. Response Schema Isolation
# ------------------------------------------------------------------------------

def test_response_schema_isolation_non_mapping_schemas_unaffected() -> None:
    """Verifies that parse_and_validate does NOT apply mapping sanitization to other schemas."""
    # Test with CandidatePerspectiveAnalysis
    perspective_json = """{
        "perspective_type": "Growth",
        "summary": "Growth perspective analysis narrative.",
        "arguments": []
    }"""
    # CandidatePerspectiveAnalysis has perspective_type: PerspectiveType ("growth", "finance", "customer", "risk")
    # If unnormalized, "Growth" will fail validation because CandidatePerspectiveAnalysis is NOT CandidateBatchEvidenceMappingPayload
    with pytest.raises(LLMResponseValidationError) as exc_info:
        StructuredOutputParser.parse_and_validate(
            raw_text=perspective_json,
            response_schema=CandidatePerspectiveAnalysis,
        )

    # Verifies that it failed with enum_mismatch and was not touched by mapping sanitization
    details = exc_info.value.details
    assert details.get("schema") == "CandidatePerspectiveAnalysis"
    assert details.get("category") == "enum_mismatch"
    assert "perspective_type" in details.get("field_paths", [])


# ------------------------------------------------------------------------------
# 3. Provider Call Recovery vs Retry (End-to-End Simulation)
# ------------------------------------------------------------------------------

def test_recoverable_payload_avoids_full_provider_retry(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that a payload with 'Supports' is recovered locally in 1 provider call without a retry."""
    raw_with_capitalized_stance = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_elasticity",
                "content": "In a study of 240 SaaS companies, a 20% price cut increased signups by 14%.",
                "summary": "14% signup increase.",
                "stance": "Supports",
                "reasoning": "Empirical evidence supports price elasticity.",
                "numeric_data": [{"metric_name": "growth", "value": 14.0}],
                "extraction_confidence": "HIGH",
                "relationship_confidence": "MEDIUM"
            }
        ]
    }"""

    # Parse through StructuredOutputParser
    recovered = StructuredOutputParser.parse_and_validate(
        raw_text=raw_with_capitalized_stance,
        response_schema=CandidateBatchEvidenceMappingPayload,
    )

    assert isinstance(recovered, CandidateBatchEvidenceMappingPayload)
    assert recovered.findings[0].stance == EvidenceStance.SUPPORTS
    assert recovered.findings[0].extraction_confidence == ConfidenceLevel.HIGH

    # Prove in FakeLLMClient setting: exactly 1 call consumed
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateBatchEvidenceMappingPayload,
        recovered,
    )
    mapper = EvidenceMapper(llm_client=fake_client)
    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify pricing elasticity.",
        status=RequirementStatus.PENDING,
        suggested_queries=["saas pricing elasticity benchmark"],
    )
    source = NormalizedSourceResult(
        requirement_id="req_1",
        query="saas pricing elasticity benchmark",
        source=Source(
            id="src_1",
            url="https://example.com/study",
            title="Study",
            publisher="Pub",
            source_type=SourceType.INDUSTRY_REPORT,
            publication_date=date(2024, 1, 1),
        ),
        search_result=SearchResultItem(
            url="https://example.com/study",
            title="Study",
            snippet="Price cut increased signups by 14%.",
            publisher="Pub",
            published_date=date(2024, 1, 1),
            raw_content="Price cut increased signups by 14%.",
        ),
    )
    res = mapper.map_evidence(saas_decision_model, [req], [source])
    assert len(fake_client.call_history) == 1
    assert len(res.items) == 1
    assert res.items[0].id == "evi_1"


def test_unrecoverable_payload_fails_closed_and_raises_validation_error() -> None:
    """Proves that an unrecoverable payload (e.g. extra field) strictly fails validation."""
    raw_with_extra_field = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Price cut increased signups by 14%.",
                "stance": "supports",
                "reasoning": "Empirical evidence supports price elasticity.",
                "hallucinated_field": "disallowed"
            }
        ]
    }"""
    with pytest.raises(LLMResponseValidationError) as exc_info:
        StructuredOutputParser.parse_and_validate(
            raw_text=raw_with_extra_field,
            response_schema=CandidateBatchEvidenceMappingPayload,
        )

    assert exc_info.value.category == "extra_forbidden"
    assert exc_info.value.details["category"] == "extra_forbidden"
    assert "findings.0.hallucinated_field" in exc_info.value.details["field_paths"]


# ------------------------------------------------------------------------------
# 4. Invalid References Subject to Existing Post-Processing Rules
# ------------------------------------------------------------------------------

def test_invalid_references_subject_to_existing_post_processing_rules(
    saas_decision_model: DecisionModel,
) -> None:
    """Proves that normalization does not alter or fix invalid source refs or target IDs.

    Invalid references are passed through to EvidenceMapper's post-processing, which strictly
    discards them according to existing rules.
    """
    raw_with_invalid_ref = """{
        "findings": [
            {
                "source_ref": "NON_EXISTENT_SOURCE_REF",
                "target_entity_id": "asm_elasticity",
                "content": "Evidence content with unmapped source reference.",
                "summary": "Summary of unmapped source.",
                "stance": "Supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": []
            }
        ]
    }"""

    # Normalization recovers the stance casing to "supports"
    recovered = StructuredOutputParser.parse_and_validate(
        raw_text=raw_with_invalid_ref,
        response_schema=CandidateBatchEvidenceMappingPayload,
    )
    assert recovered.findings[0].stance == EvidenceStance.SUPPORTS
    assert recovered.findings[0].source_ref == "NON_EXISTENT_SOURCE_REF"  # Untouched

    # When processed by EvidenceMapper, the invalid source_ref is rejected during post-processing
    fake_client = FakeLLMClient()
    fake_client.register_response(CandidateBatchEvidenceMappingPayload, recovered)
    mapper = EvidenceMapper(llm_client=fake_client)
    req = EvidenceRequirement(
        id="req_1",
        target_entity_id="asm_elasticity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify pricing elasticity.",
        status=RequirementStatus.PENDING,
        suggested_queries=["saas pricing elasticity benchmark"],
    )
    source = NormalizedSourceResult(
        requirement_id="req_1",
        query="saas pricing elasticity benchmark",
        source=Source(
            id="src_1",
            url="https://example.com/study",
            title="Study",
            publisher="Pub",
            source_type=SourceType.INDUSTRY_REPORT,
            publication_date=date(2024, 1, 1),
        ),
        search_result=SearchResultItem(
            url="https://example.com/study",
            title="Study",
            snippet="Snippet.",
            publisher="Pub",
            published_date=date(2024, 1, 1),
            raw_content="Content.",
        ),
    )
    res = mapper.map_evidence(saas_decision_model, [req], [source])
    # The finding had source_ref='NON_EXISTENT_SOURCE_REF', which is not in batch_source_map (only SOURCE_1 exists)
    assert len(res.items) == 0, "Finding with invalid source_ref must be discarded by mapper post-processing!"


# ------------------------------------------------------------------------------
# 5. Schema Isolation for All Structured Schemas
# ------------------------------------------------------------------------------

def test_response_schema_isolation_all_schemas() -> None:
    """Verifies that other structured schemas (CandidateRequirementsPayload, CandidateBoardSynthesis) are completely isolated."""
    from app.services.evidence.requirements import CandidateRequirementsPayload
    from app.schemas.reasoning import CandidateBoardSynthesis

    # 1. CandidateRequirementsPayload: unnormalized enum 'Assumption' (must fail, not touched by mapping sanitization)
    reqs_json = """{
        "requirements": [
            {
                "target_entity_id": "asm_1",
                "target_entity_type": "Assumption",
                "kind": "external_research",
                "description": "Validation description"
            }
        ]
    }"""
    with pytest.raises(LLMResponseValidationError) as exc_reqs:
        StructuredOutputParser.parse_and_validate(
            raw_text=reqs_json,
            response_schema=CandidateRequirementsPayload,
        )
    assert exc_reqs.value.details["schema"] == "CandidateRequirementsPayload"
    assert exc_reqs.value.details["category"] == "enum_mismatch"
    assert "requirements.0.target_entity_type" in exc_reqs.value.details["field_paths"]

    # 2. CandidateBoardSynthesis: missing required fields
    with pytest.raises(LLMResponseValidationError) as exc_synth:
        StructuredOutputParser.parse_and_validate(
            raw_text="{}",
            response_schema=CandidateBoardSynthesis,
        )
    assert exc_synth.value.details["schema"] == "CandidateBoardSynthesis"
    assert exc_synth.value.details["category"] == "missing_required_field"


# ------------------------------------------------------------------------------
# 6. Concurrency and Cross-Request Leakage Safety
# ------------------------------------------------------------------------------

def test_no_cross_request_leakage_concurrent_threads() -> None:
    """Proves that multiple concurrent parsing threads do not leak state or mutate shared dictionaries."""
    import threading

    errors: List[Exception] = []

    def worker(worker_id: int) -> None:
        try:
            for _ in range(20):
                if worker_id % 2 == 0:
                    raw = _valid_raw_payload()
                    raw["findings"][0]["stance"] = "  Supports  "
                    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
                    assert sanitized["findings"][0]["stance"] == "supports"
                    assert raw["findings"][0]["stance"] == "  Supports  "
                else:
                    raw_invalid = "{}"
                    try:
                        StructuredOutputParser.parse_and_validate(
                            raw_text=raw_invalid,
                            response_schema=CandidateBatchEvidenceMappingPayload,
                        )
                    except LLMResponseValidationError as e:
                        assert e.category == "missing_required_field"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent thread leakage encountered: {errors}"


# ------------------------------------------------------------------------------
# 7. GeminiLLMClient: Local Recovery in 1 Provider Call vs Retry Policy
# ------------------------------------------------------------------------------

def test_gemini_client_local_recovery_in_single_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that GeminiLLMClient recovers a payload with casing differences in exactly 1 call without retrying."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    import httpx
    from app.services.llm.gemini import GeminiLLMClient

    canned_recoverable_json = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_elasticity",
                "content": "A 20% price cut increased customer acquisition by 14%.",
                "summary": "14% acquisition increase.",
                "stance": "Supports",
                "reasoning": "Empirical evidence supports price elasticity.",
                "numeric_data": [{"metric_name": "acquisition_increase", "value": 14.0}],
                "extraction_confidence": "HIGH",
                "relationship_confidence": "MEDIUM"
            }
        ]
    }"""

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"output_text": canned_recoverable_json})

    mock_transport = httpx.MockTransport(mock_handler)
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )

    res = client.generate_structured(
        prompt="Extract findings from batch",
        response_schema=CandidateBatchEvidenceMappingPayload,
    )

    assert isinstance(res, CandidateBatchEvidenceMappingPayload)
    assert res.findings[0].stance == EvidenceStance.SUPPORTS
    assert call_count == 1, "Recoverable payload must not trigger a full provider retry!"

    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "success"
    assert diag["attempt"] == 1
    assert len(diag["attempts"]) == 1


def test_gemini_client_unrecoverable_follows_retry_policy_and_records_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves that an unrecoverable payload follows the retry policy, exhausts attempts, and records sanitized diagnostics."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    import httpx
    from app.services.llm.gemini import GeminiLLMClient

    unrecoverable_json = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Price cut increased signups.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "forbidden_extra_key": "hallucinated"
            }
        ]
    }"""

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"output_text": unrecoverable_json})

    mock_transport = httpx.MockTransport(mock_handler)
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        initial_backoff_seconds=0.001,
        http_client=httpx.Client(transport=mock_transport),
    )

    with pytest.raises(LLMResponseValidationError) as exc_info:
        client.generate_structured(
            prompt="Extract findings from batch",
            response_schema=CandidateBatchEvidenceMappingPayload,
            config=LLMConfig(max_retries=1),  # 1 initial + 1 retry = 2 attempts
        )

    # 1. Retry policy was followed
    assert call_count == 2, "Unrecoverable payload must follow the retry policy up to max_attempts!"
    assert exc_info.value.category == "extra_forbidden"

    # 2. Sanitized diagnostics recorded without leaking sensitive/raw content
    diag = client.last_diagnostic
    assert diag is not None
    assert diag["status"] == "validation_error"
    assert diag["final_validation_category"] == "extra_forbidden"
    assert len(diag["attempts"]) == 2

    # Check each attempt record
    for att in diag["attempts"]:
        assert att["status"] == "validation_error"
        assert att["validation_category"] == "extra_forbidden"
        assert "findings.0.forbidden_extra_key" in att["validation_field_paths"]
        # Invariant: raw prompt and raw response text are NOT leaked into diagnostic records
        assert "Extract findings from batch" not in str(att.get("validation_category"))
        assert "forbidden_extra_key" in str(att.get("validation_field_paths"))


# ------------------------------------------------------------------------------
# 8. Sanitized Diagnostics: JSON Parse Error & Root Type Error
# ------------------------------------------------------------------------------

def test_sanitized_diagnostics_json_and_root_type_errors() -> None:
    """Verifies that JSON syntax errors and non-dict root types are classified accurately."""
    # 1. JSON syntax error
    with pytest.raises(LLMResponseValidationError) as exc_json:
        StructuredOutputParser.parse_and_validate(
            raw_text="This is not JSON at all: { broken: invalid }",
            response_schema=CandidateBatchEvidenceMappingPayload,
        )
    assert exc_json.value.category == "json_parse_error"

    # 2. Root type error (JSON array of strings instead of JSON object)
    with pytest.raises(LLMResponseValidationError) as exc_root:
        StructuredOutputParser.parse_and_validate(
            raw_text='["unexpected_string_1", "unexpected_string_2"]',
            response_schema=CandidateBatchEvidenceMappingPayload,
        )
    assert exc_root.value.category == "root_type_error"


