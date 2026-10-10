"""Tests for Stage 2 Evidence Mapping Entity ID Validation, Reconciliation, and Diagnostics.

Phase 4F Regression Test Suite:
1. Exact 'string_too_long' validation failure for overlong un-reconcilable strings.
2. Clean bare canonical entity IDs pass unchanged.
3. Canonical IDs followed by explanatory prose, labels, or formatting deterministically reconcile.
4. Extremely long invalid strings without canonical IDs fail without truncation.
5. Multiple or ambiguous canonical IDs are not guessed and remain unreconciled.
6. Nonexistent, partial, or malformed prefixes do not match.
7. Cross-namespace ID misuse (e.g. 'req_...', 'evi_...') is rejected.
8. Sanitized diagnostics reporting captures constraint metadata safely without leaking data.
9. Retry and timeout behavior respects deadline budgets.
10. End-to-end compatibility with EvidenceMapper.map_evidence.
"""

import time
from typing import Any, Dict, List
import httpx
import pytest
from pydantic import ValidationError

from app.schemas.decision_model import (
    Assumption,
    ComplexityLevel,
    ConfidenceLevel,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ReversibilityLevel,
    TimeHorizon,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidenceRequirement,
    EvidenceStance,
    Source,
    SourceType,
)
from app.services.evidence.mapper import (
    CandidateBatchEvidenceMappingPayload,
    CandidateFinding,
    EvidenceMapper,
    reconcile_target_entity_id,
)
from app.services.evidence.normalizer import NormalizedSourceResult
from app.services.llm.client import FakeLLMClient, LLMConfig, LLMResponseValidationError, LLMTimeoutError
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.parser import StructuredOutputParser


# ------------------------------------------------------------------------------
# Test Fixtures & Helpers
# ------------------------------------------------------------------------------

def _create_minimal_decision_model() -> DecisionModel:
    from app.services.llm.mock_data import get_default_decision_model
    model = get_default_decision_model("Should we offer a 20% price discount?")
    model.id = "1299e1ac-9473-4f60-b9ec-06a53c145336"
    model.assumptions[0].id = "asm_elasticity"
    return model


def _create_requirement(
    req_id: str,
    target_id: str,
    target_type: DecisionEntityType = DecisionEntityType.ASSUMPTION,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        target_entity_id=target_id,
        target_entity_type=target_type,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description=f"Empirical validation question for {target_id}.",
    )


def _create_normalized_source(
    req_id: str,
    src_id: str,
    text: str,
) -> NormalizedSourceResult:
    source = Source(
        id=src_id,
        title=f"Source {src_id}",
        publisher="Test Publisher",
        source_type=SourceType.ACADEMIC,
        url="https://example.com/source",
    )
    from app.services.evidence.normalizer import SearchResultItem
    sr = SearchResultItem(
        title=source.title,
        url=source.url or "https://example.com/source",
        snippet=text,
        raw_content=text,
        publisher="Test Publisher",
    )
    return NormalizedSourceResult(
        requirement_id=req_id,
        query="test query",
        source=source,
        search_result=sr,
    )


# ------------------------------------------------------------------------------
# 1. Exact string_too_long Failure
# ------------------------------------------------------------------------------

def test_exact_string_too_long_failure():
    """An overlong string (>100 chars) lacking any canonical ID strictly fails Pydantic validation."""
    oversized_text = "Target Decision Entity: Assumption that customer support costs will decrease significantly within 90 days of deployment"
    assert len(oversized_text) > 100

    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": oversized_text,
                "content": "Empirical excerpt showing support costs decreased.",
                "stance": "supports",
                "reasoning": "Supports cost reduction assumption.",
            }
        ]
    }

    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)

    primary, all_cats, field_paths = StructuredOutputParser.classify_validation_error(exc_info.value)
    assert primary == "other_pydantic_error"
    assert "findings.0.target_entity_id" in field_paths
    assert exc_info.value.errors()[0]["type"] == "string_too_long"


# ------------------------------------------------------------------------------
# 2. Valid Canonical Entity IDs
# ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "valid_id",
    [
        "asm_elasticity",
        "unk_churn",
        "var_price_discount",
        "obj_arr_growth",
        "con_runway_limit",
        "trd_growth_vs_profit",
        "stk_enterprise_buyers",
        "dec_root_choice",
        "dm_strategic_pricing",
        "1299e1ac-9473-4f60-b9ec-06a53c145336",
    ],
)
def test_valid_canonical_entity_ids_pass_unchanged(valid_id: str):
    """Clean canonical entity IDs pass reconciliation and validation completely intact."""
    assert reconcile_target_entity_id(valid_id) == valid_id

    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": valid_id,
                "content": "Valid empirical excerpt.",
                "stance": "supports",
                "reasoning": "Grounds the decision entity directly.",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings[0].target_entity_id == valid_id


def test_target_entity_id_none_and_placeholders():
    """Empty and placeholder target_entity_id values coerce to None."""
    for placeholder in [None, "", "none", "null", "N/A", "undefined", "  "]:
        assert reconcile_target_entity_id(placeholder) is None


# ------------------------------------------------------------------------------
# 3. Canonical IDs with Explanatory Prose, Labels, and Formatting
# ------------------------------------------------------------------------------

def test_canonical_id_with_explanatory_prose_reconciles():
    """A canonical ID accompanied by verbose explanation (>100 chars) reconciles to the exact bare ID."""
    overlong_with_id = (
        "asm_elasticity: Price elasticity of demand in B2B SaaS under 20% discount "
        "will lead to net positive gross revenue acceleration over 12 months."
    )
    assert len(overlong_with_id) > 100

    reconciled = reconcile_target_entity_id(overlong_with_id)
    assert reconciled == "asm_elasticity"

    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": overlong_with_id,
                "content": "Price reductions resulted in a 35% conversion lift across SaaS tiers.",
                "stance": "supports",
                "reasoning": "Validates price elasticity assumption empirically.",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    validated = CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert validated.findings[0].target_entity_id == "asm_elasticity"


def test_canonical_id_with_prompt_header_and_markdown_formatting():
    """Canonical IDs embedded in prompt headers, parentheses, or markdown delimiters reconcile cleanly."""
    variations = [
        ("Target Decision Entity - ID: asm_elasticity - Description: Elasticity assumption", "asm_elasticity"),
        ("(asm_elasticity) Price elasticity assumption under discount", "asm_elasticity"),
        ('"asm_elasticity"', "asm_elasticity"),
        ("'asm_elasticity'", "asm_elasticity"),
        ("`asm_elasticity`", "asm_elasticity"),
        ("Target: unk_churn (Unresolved enterprise churn risk)", "unk_churn"),
        ("var_discount - Proposed price reduction percentage", "var_discount"),
    ]
    for raw_val, expected in variations:
        assert reconcile_target_entity_id(raw_val) == expected


# ------------------------------------------------------------------------------
# 4. Extremely Long Invalid Strings
# ------------------------------------------------------------------------------

def test_extremely_long_invalid_string_not_truncated():
    """An extremely long invalid string is never silently truncated to 100 chars; it fails validation."""
    long_invalid = "Arbitrary non-canonical text " * 20
    assert len(long_invalid) > 100

    # Reconciliation does not touch it because no canonical ID is present
    assert reconcile_target_entity_id(long_invalid) == long_invalid.strip()

    raw = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": long_invalid,
                "content": "Empirical content excerpt.",
                "stance": "supports",
                "reasoning": "Some reasoning.",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw)
    with pytest.raises(ValidationError) as exc_info:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert exc_info.value.errors()[0]["type"] == "string_too_long"


# ------------------------------------------------------------------------------
# 5. Multiple or Ambiguous IDs
# ------------------------------------------------------------------------------

def test_multiple_competing_canonical_ids_are_not_reconciled():
    """Strings containing multiple competing canonical IDs are ambiguous and must NOT be guessed."""
    ambiguous_inputs = [
        "asm_elasticity and unk_churn",
        "asm_elasticity vs asm_retention",
        "Related to obj_growth and con_runway",
        "Target is asm_1 or asm_2 depending on tier",
    ]
    for amb in ambiguous_inputs:
        # Returns the original string without guessing
        assert reconcile_target_entity_id(amb) == amb


def test_repeated_identical_canonical_id_reconciles_cleanly():
    """A string repeating the exact same canonical ID without competing IDs reconciles safely."""
    repeated = "asm_elasticity (confirming asm_elasticity from DecisionModel)"
    assert reconcile_target_entity_id(repeated) == "asm_elasticity"


# ------------------------------------------------------------------------------
# 6. Nonexistent and Partial IDs
# ------------------------------------------------------------------------------

def test_partial_or_nonexistent_prefixes_are_rejected():
    """Partial prefixes without a valid token name or with invalid prefixes are never coerced."""
    invalid_inputs = [
        "asm",
        "asm_",
        "asm_ ",
        "unk",
        "unk_",
        "foo_bar",
        "custom_entity_123",
        "assumption_elasticity",
    ]
    for inv in invalid_inputs:
        assert reconcile_target_entity_id(inv) == inv.strip()


# ------------------------------------------------------------------------------
# 7. Cross-Namespace ID Misuse
# ------------------------------------------------------------------------------

def test_cross_namespace_id_misuse_is_rejected():
    """Using non-decision namespaces (such as 'req_...' or 'evi_...') in target_entity_id is rejected."""
    # 1. Overlong requirement ID description does not reconcile to a decision entity
    overlong_req = "req_saas_pricing_proof: Requirement hypothesis to prove enterprise willingness to pay beyond baseline thresholds"
    assert len(overlong_req) > 100
    assert reconcile_target_entity_id(overlong_req) == overlong_req

    raw_overlong = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": overlong_req,
                "content": "Valid excerpt.",
                "stance": "supports",
                "reasoning": "Valid reasoning.",
            }
        ]
    }
    sanitized = StructuredOutputParser.sanitize_evidence_mapping_dict(raw_overlong)
    with pytest.raises(ValidationError) as exc:
        CandidateBatchEvidenceMappingPayload.model_validate(sanitized)
    assert exc.value.errors()[0]["type"] == "string_too_long"

    # 2. Cross-namespace mixed string (e.g. req_1 for asm_1) is ambiguous and not reconciled
    mixed = "req_1 for asm_elasticity"
    assert reconcile_target_entity_id(mixed) == mixed


# ------------------------------------------------------------------------------
# 8. Safe Diagnostic Reporting
# ------------------------------------------------------------------------------

def test_safe_diagnostic_reporting_on_validation_failure():
    """Sanitized validation failures include constraint metadata without leaking raw prompts or secrets."""
    raw_overlong_secret = {
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "SECRET_CONFIDENTIAL_KEY_XYZ_" + ("X" * 120),
                "content": "Confidential internal report on pricing secrets.",
                "stance": "supports",
                "reasoning": "Grounding reasoning.",
            }
        ]
    }
    raw_text = str(raw_overlong_secret).replace("'", '"')

    with pytest.raises(LLMResponseValidationError) as exc_info:
        StructuredOutputParser.parse_and_validate(
            raw_text=raw_text,
            response_schema=CandidateBatchEvidenceMappingPayload,
            raw_user_prompt="USER_PROMPT_SECRET_DO_NOT_LEAK",
        )

    err_details = exc_info.value.details
    assert err_details["schema"] == "CandidateBatchEvidenceMappingPayload"
    assert "findings.0.target_entity_id" in err_details["field_paths"]
    assert "string_too_long" in err_details["error_types"]

    # Constraint metadata safely extracted
    constraints = err_details.get("constraints", [])
    assert len(constraints) >= 1
    c0 = next(c for c in constraints if c["field"] == "findings.0.target_entity_id")
    assert c0["type"] == "string_too_long"
    assert c0["max_length"] == 100

    # Privacy preservation: Secret tokens are not in constraint metadata
    assert "SECRET_CONFIDENTIAL_KEY_XYZ_" not in str(constraints)
    assert "USER_PROMPT_SECRET_DO_NOT_LEAK" not in str(constraints)


# ------------------------------------------------------------------------------
# 9. Retry and Timeout Behavior
# ------------------------------------------------------------------------------

def test_gemini_client_respects_deadline_budget_on_validation_error(caplog):
    """GeminiLLMClient terminates cleanly without infinite retries when deadline budget expires."""
    unrecoverable_overlong = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "Arbitrary overlong text without canonical ID that exceeds the schema limit of one hundred characters completely",
                "content": "Some content",
                "stance": "supports",
                "reasoning": "Some reasoning"
            }
        ]
    }"""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": unrecoverable_overlong})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        initial_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    # Set deadline already expired or 0 budget
    expired_deadline = time.monotonic() - 1.0

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Evaluate evidence mapping",
            response_schema=CandidateBatchEvidenceMappingPayload,
            deadline_monotonic=expired_deadline,
        )

    assert "timed out" in str(exc_info.value).lower()


def test_reconciled_response_succeeds_on_first_attempt_without_retry():
    """A response containing canonical ID with prose succeeds immediately on attempt 1 with zero retries."""
    response_with_prose = """{
        "findings": [
            {
                "source_ref": "SOURCE_1",
                "target_entity_id": "asm_elasticity: Price elasticity assumption for B2B SaaS under 20% discount exceeding 100 characters in length easily",
                "content": "Price reductions resulted in a 35% conversion lift across SaaS tiers.",
                "stance": "supports",
                "reasoning": "Direct empirical proof of price elasticity."
            }
        ]
    }"""

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"output_text": response_with_prose})

    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        initial_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    result = client.generate_structured(
        prompt="Evaluate evidence mapping",
        response_schema=CandidateBatchEvidenceMappingPayload,
        config=LLMConfig(max_retries=2),
    )

    # Reconciled on first attempt: exactly 1 HTTP call made, 0 retries
    assert call_count == 1
    assert isinstance(result, CandidateBatchEvidenceMappingPayload)
    assert len(result.findings) == 1
    assert result.findings[0].target_entity_id == "asm_elasticity"


# ------------------------------------------------------------------------------
# 10. Compatibility with Existing EvidenceMapper
# ------------------------------------------------------------------------------

def test_evidence_mapper_end_to_end_with_reconciled_finding():
    """EvidenceMapper.map_evidence correctly links reconciled candidate findings to DecisionModel entities."""
    model = _create_minimal_decision_model()
    req = _create_requirement("req_1", "asm_elasticity")
    source_result = _create_normalized_source(
        req_id="req_1",
        src_id="src_study_1",
        text="A rigorous study found conversion rates increased by 25% when offering 20% discounts.",
    )

    fake_client = FakeLLMClient()
    # Simulate LLM returning a finding with verbose target_entity_id
    payload = CandidateBatchEvidenceMappingPayload(
        findings=[
            CandidateFinding(
                source_ref="SOURCE_1",
                target_entity_id="asm_elasticity: Customer willingness to pay under 20% discount",
                content="A rigorous study found conversion rates increased by 25% when offering 20% discounts.",
                summary="Empirical evidence of price elasticity.",
                stance=EvidenceStance.SUPPORTS,
                reasoning="Demonstrates clear volume elasticity following price discount.",
                extraction_confidence=ConfidenceLevel.HIGH,
                relationship_confidence=ConfidenceLevel.HIGH,
            )
        ]
    )
    fake_client.register_response(CandidateBatchEvidenceMappingPayload, payload)

    mapper = EvidenceMapper(llm_client=fake_client)
    mapping_result = mapper.map_evidence(
        decision_model=model,
        requirements=[req],
        normalized_sources=[source_result],
    )

    assert len(mapping_result.items) == 1
    assert len(mapping_result.claim_links) == 1
    link = mapping_result.claim_links[0]
    assert link.target_entity_id == "asm_elasticity"
    assert link.stance == EvidenceStance.SUPPORTS
    assert link.requirement_id == "req_1"
