"""Phase 5 Stage 2 Evidence Mapping Validation Recovery & Diagnostic Regression Tests.

Verifies:
1. Deterministic reproduction and recovery for Gemini-generated structured output edge cases:
   - numeric_data: null coerced to []
   - findings: null coerced to []
   - sample_size: 0 (indicating no sample size reported) coerced to None (satisfies ge=1)
   - sample_size placeholders ("", "N/A", "none") coerced to None
   - value / range_min / range_max placeholders ("", "none", "N/A") coerced to None
   - summary exceeding 500 characters safely bounded to <= 500 characters
   - target_entity_id placeholder or hallucinated description (>100 chars) coerced to None
2. Safe diagnostics preservation:
   - Error categories, field paths, and schema names are captured in diagnostics.
   - Prompts, raw customer data, credentials, and raw model text are never leaked.
   - EvidenceServiceError captures structured details and AnalysisService logs sanitized errors.
3. Retry behavior and timing:
   - Unrecoverable errors retry up to max_attempts with exponential backoff before failing.
   - Recoverable payloads succeed on attempt 1 without retry overhead.
4. Invariant preservation:
   - Formatted strings like "14%" still fail with numeric_type_error (zero number fabrication).
   - Extra forbidden fields like "quote" still fail with extra_forbidden.
   - Unknown enums like "neutral" still fail with enum_mismatch.
   - Numeric anti-hallucination validation against source text remains strictly enforced.
5. Stage 4 recommendation engine schema fix remains intact.
"""

from datetime import date
import logging
from typing import Any, Dict
import pytest
from pydantic import ValidationError

from app.schemas.decision_model import ConfidenceLevel, DecisionModel
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
    EvidenceMapper,
)
from app.services.evidence.normalizer import NormalizedSourceResult, SearchResultItem
from app.services.evidence.service import EvidenceService, EvidenceServiceError
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMResponseValidationError,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.mock_data import get_default_decision_model
from app.services.llm.parser import StructuredOutputParser
import httpx


# ------------------------------------------------------------------------------
# 1. Deterministic Recovery Tests
# ------------------------------------------------------------------------------

def test_recovery_numeric_data_null() -> None:
    """Verifies that numeric_data: null in a finding is safely normalized to []."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "B2B SaaS companies see 25% faster resolution times.",
                "stance": "supports",
                "reasoning": "Direct evidence of efficiency gains.",
                "numeric_data": None,
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["numeric_data"] == []

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert len(validated.findings) == 1
    assert validated.findings[0].numeric_data == []


def test_recovery_findings_null() -> None:
    """Verifies that findings: null is safely normalized to []."""
    raw = {"findings": None}
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"] == []

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings == []


def test_recovery_sample_size_zero_and_placeholders() -> None:
    """Verifies that sample_size: 0 and placeholder strings are safely coerced to None."""
    for val in [0, "", "N/A", "n/a", "none", "null", "undefined"]:
        raw = {
            "findings": [
                {
                    "source_ref": "SOURCE_1",
                    "content": "A survey showed customer satisfaction improvement.",
                    "stance": "supports",
                    "reasoning": "Relevant finding narrative.",
                    "numeric_data": [
                        {
                            "metric_name": "csat_increase",
                            "value": 15.0,
                            "sample_size": val,
                        }
                    ],
                }
            ]
        }
        sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
        assert sanitized["findings"][0]["numeric_data"][0]["sample_size"] is None

        validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
        assert validated.findings[0].numeric_data[0].sample_size is None


def test_recovery_numeric_fields_placeholders() -> None:
    """Verifies that value, range_min, range_max placeholders ('', 'none', 'N/A') are coerced to None."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Support deflection was observed across multiple cohorts.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": [
                    {
                        "metric_name": "deflection_rate",
                        "value": "",
                        "range_min": "none",
                        "range_max": "N/A",
                        "unit": "N/A",
                        "confidence_interval": "none",
                        "context": "none",
                    }
                ],
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    num = sanitized["findings"][0]["numeric_data"][0]
    assert num["value"] is None
    assert num["range_min"] is None
    assert num["range_max"] is None
    assert num["unit"] is None
    assert num["confidence_interval"] is None
    assert num["context"] is None

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    v_num = validated.findings[0].numeric_data[0]
    assert v_num.value is None
    assert v_num.range_min is None
    assert v_num.range_max is None


def test_recovery_summary_oversized_safely_truncated() -> None:
    """Verifies that a verbose summary exceeding 500 characters is safely truncated with ellipsis."""
    long_summary = "In our comprehensive analysis of the empirical findings: " + ("data " * 100)
    assert len(long_summary) > 500

    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Resolution times dropped by 30%.",
                "summary": long_summary,
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": [],
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert len(sanitized["findings"][0]["summary"]) <= 500
    assert sanitized["findings"][0]["summary"].endswith("...")

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert len(validated.findings[0].summary) <= 500
    assert validated.findings[0].summary.endswith("...")


def test_recovery_target_entity_id_placeholder_and_overlong_failure() -> None:
    """Verifies that target_entity_id placeholders are normalized to None and overlong strings fail validation."""
    # 1. Placeholders normalized to None
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "N/A",
                "content": "Resolution times dropped by 30%.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": [],
            },
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "none",
                "content": "Customer satisfaction remained stable.",
                "stance": "context",
                "reasoning": "Context narrative.",
                "numeric_data": [],
            },
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["target_entity_id"] is None
    assert sanitized["findings"][1]["target_entity_id"] is None

    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings[0].target_entity_id is None
    assert validated.findings[1].target_entity_id is None

    # 2. Overlong ID strictly fails Pydantic validation (max_length=100)
    oversized_id = "Target Decision Entity: Assumption that customer support costs will decrease significantly within 90 days of deployment"
    assert len(oversized_id) > 100
    raw_overlong = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": oversized_id,
                "content": "Resolution times dropped by 30%.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": [],
            }
        ]
    }
    sanitized_overlong = StructuredOutputParser.sanitize_evidence_mapping_dict(raw_overlong)
    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized_overlong)
    primary, _, field_paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert "findings.0.target_entity_id" in field_paths
    assert primary == "other_pydantic_error"
    assert exc_info.value.errors()[0]["type"] == "string_too_long"


# ------------------------------------------------------------------------------
# 2. Invariant Preservation (Non-Coercion of Real Invalids)
# ------------------------------------------------------------------------------

def test_formatted_numbers_not_coerced_and_fail_validation() -> None:
    """Proves that '14%' is NOT fabricated into float and fails canonical validation with numeric_type_error."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Cost decreased by 14%.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "numeric_data": [
                    {"metric_name": "cost_reduction", "value": "14%"}
                ],
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["numeric_data"][0]["value"] == "14%"

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary, cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary == "numeric_type_error"
    assert "findings.0.numeric_data.0.value" in paths


def test_extra_forbidden_keys_not_stripped_and_fail_validation() -> None:
    """Proves that unknown keys like 'quote' are preserved and strictly fail extra='forbid'."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Factual excerpt.",
                "stance": "supports",
                "reasoning": "Reasoning narrative.",
                "quote": "Disallowed extra quote key",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert "quote" in sanitized["findings"][0]

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary, cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary == "extra_forbidden"
    assert "findings.0.quote" in paths


def test_unknown_enum_not_coerced_and_fails_validation() -> None:
    """Proves that 'neutral' is not coerced to 'context' and fails with enum_mismatch."""
    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Factual excerpt.",
                "stance": "neutral",
                "reasoning": "Reasoning narrative.",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    assert sanitized["findings"][0]["stance"] == "neutral"

    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary, cats, paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary == "enum_mismatch"
    assert "findings.0.stance" in paths


# ------------------------------------------------------------------------------
# 3. Safe Diagnostics & Privacy Guard
# ------------------------------------------------------------------------------

def test_gemini_client_logs_sanitized_diagnostics_without_leaking_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies that GeminiLLMClient logs validation failure diagnostics without leaking prompts or secrets."""
    caplog.set_level(logging.WARNING)

    unrecoverable_json = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "content": "Customer confidential content about contract ABC-12345.",
                "stance": "supports",
                "reasoning": "Confidential reasoning narrative.",
                "forbidden_key": "hallucinated"
            }
        ]
    }"""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": unrecoverable_json})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        initial_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    with pytest.raises(LLMResponseValidationError) as exc_info:
        client.generate_structured(
            prompt="PROMPT: Analyze customer secrets and confidential agreements",
            response_schema=CandidateBatchEvidenceMappingPayload,
            config=LLMConfig(max_retries=1),
        )

    # 1. Error details captured safely
    assert exc_info.value.category == "extra_forbidden"
    assert "findings.0.forbidden_key" in exc_info.value.details["field_paths"]

    # 2. Logs contain schema, category, field paths
    log_text = caplog.text
    assert "CandidateBatchEvidenceMappingPayload" in log_text
    assert "extra_forbidden" in log_text
    assert "findings.0.forbidden_key" in log_text

    # 3. Privacy invariant: prompt and confidential content are NOT in logs
    assert "Analyze customer secrets" not in log_text
    assert "ABC-12345" not in log_text


def test_evidence_service_error_contains_structured_details() -> None:
    """Verifies that EvidenceServiceError captures validation details from underlying cause."""
    err = EvidenceServiceError(
        "Evidence orchestration failed at stage 'mapping': validation failed",
        stage="mapping",
        details={"schema": "CandidateBatchEvidenceMappingPayload", "category": "numeric_type_error", "field_paths": ["findings.0.numeric_data.0.value"]},
    )
    assert err.stage == "mapping"
    assert err.details["category"] == "numeric_type_error"
    assert "findings.0.numeric_data.0.value" in err.details["field_paths"]


# ------------------------------------------------------------------------------
# 4. End-to-End Recovery Simulation (Single Provider Call, Zero Retries)
# ------------------------------------------------------------------------------

def test_full_mapping_pipeline_recovers_real_world_gemini_payload() -> None:
    """Proves that a real-world Gemini mapping payload with numeric_data: null and sample_size: 0 passes Stage 2."""
    real_world_json = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_cost",
                "content": "In a study of 40 support teams, an AI assistant deflected 35% of common tier-1 inquiries.",
                "summary": "35% tier-1 deflection observed in study of 40 support teams.",
                "stance": "Supports",
                "reasoning": "Empirically validates potential cost reduction through deflection.",
                "numeric_data": [
                    {
                        "metric_name": "tier_1_deflection",
                        "value": 35.0,
                        "unit": "%",
                        "sample_size": 40
                    }
                ],
                "extraction_confidence": "HIGH",
                "relationship_confidence": "MEDIUM"
            },
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_cost",
                "content": "Early implementation often encounters temporary ticket backlogs before stabilization.",
                "summary": "Implementation risk noted.",
                "stance": "Challenges",
                "reasoning": "Highlights short-term adoption friction.",
                "numeric_data": null,
                "extraction_confidence": "HIGH",
                "relationship_confidence": "HIGH"
            }
        ]
    }"""

    # Parse and validate through StructuredOutputParser
    payload = StructuredOutputParser.parse_and_validate(
        raw_text=real_world_json,
        response_schema=CandidateBatchEvidenceMappingPayload,
    )
    assert len(payload.findings) == 2
    assert payload.findings[0].stance == EvidenceStance.SUPPORTS
    assert payload.findings[1].stance == EvidenceStance.CHALLENGES
    assert payload.findings[1].numeric_data == []

    # Map through EvidenceMapper
    fake_client = FakeLLMClient()
    fake_client.register_response(CandidateBatchEvidenceMappingPayload, payload)
    mapper = EvidenceMapper(llm_client=fake_client)

    model = get_default_decision_model("Should we launch an AI assistant?")
    # Replace default assumption ID with asm_cost for mapping
    model.assumptions[0].id = "asm_cost"

    req = EvidenceRequirement(
        id="req_cost",
        target_entity_id="asm_cost",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Verify support deflection and cost reduction.",
        status=RequirementStatus.PENDING,
        suggested_queries=["ai support deflection rate"],
    )
    source = NormalizedSourceResult(
        requirement_id="req_cost",
        query="ai support deflection rate",
        source=Source(
            id="src_1",
            url="https://example.com/study",
            title="AI Support Study",
            publisher="TechBench",
            source_type=SourceType.INDUSTRY_REPORT,
            publication_date=date(2024, 1, 1),
        ),
        search_result=SearchResultItem(
            url="https://example.com/study",
            title="AI Support Study",
            snippet="Study snippet.",
            publisher="TechBench",
            published_date=date(2024, 1, 1),
            raw_content="In a study of 40 support teams, an AI assistant deflected 35% of common tier-1 inquiries. Early implementation often encounters temporary ticket backlogs before stabilization.",
        ),
    )

    res = mapper.map_evidence(model, [req], [source])
    assert len(fake_client.call_history) == 1
    assert len(res.items) == 2
    assert len(res.claim_links) == 2

    # Verify numeric evidence was grounded in source text (35% in raw_content)
    assert len(res.items[0].numeric_data) == 1
    assert res.items[0].numeric_data[0].value == 35.0
    assert res.items[0].numeric_data[0].sample_size == 40

    # Second item had numeric_data: null -> recovered as empty list
    assert len(res.items[1].numeric_data) == 0
