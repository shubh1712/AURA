"""Regression test suite for AURA Day 2 correctness and testing safety.

Verifies:
A) Explicit numerical values from the user's question are preserved with USER_PROVIDED provenance.
B) Malformed LLM response containing an excessively long Variable.unit fails validation, triggers retry, and cannot silently enter DecisionModel.
C) Inferred LTV:CAC consideration without an explicit threshold is not automatically treated as a hard constraint.
D) Normal test execution cannot instantiate/call the real Gemini provider.
E) Tests pass when GEMINI_API_KEY is completely absent.
"""

import json
import httpx
import pytest
from pydantic import ValidationError

from app.engines.provenance import audit_decision_provenance
from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.analysis import AnalysisRequest
from app.schemas.decision_model import (
    Constraint,
    DecisionModel,
    ProvenanceType,
    Variable,
    VariableType,
)
from app.services.analysis_service import AnalysisService
from app.services.llm.client import (
    FakeLLMClient,
    LLMConfig,
    LLMResponseValidationError,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.mock_data import get_default_decision_model
from app.services.llm.parser import parse_and_validate_structured_output


# ------------------------------------------------------------------------------
# Regression Test A: Explicit Numerical Value Preserved
# ------------------------------------------------------------------------------

def test_regression_explicit_numerical_value_preserved() -> None:
    """Regression 9A: Explicit 20% price reduction is preserved with USER_PROVIDED provenance."""
    question = "Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    fake_client = FakeLLMClient()
    engine = QuestionUnderstandingEngine(llm_client=fake_client)

    model = engine.deconstruct(question=question)

    price_vars = [
        v for v in model.variables
        if "price" in v.name.lower() or "discount" in v.name.lower()
    ]
    assert len(price_vars) >= 1, f"No pricing variable found in {model.variables}"
    var = price_vars[0]

    assert var.proposed_value in (20, 20.0)
    assert var.unit == "%"
    assert var.proposed_provenance == ProvenanceType.USER_PROVIDED
    assert var.baseline_value is None
    assert var.baseline_provenance == ProvenanceType.UNKNOWN
    assert var.provenance == ProvenanceType.USER_PROVIDED


# ------------------------------------------------------------------------------
# Regression Test B: Malformed Variable.unit Schema Validation & Retry
# ------------------------------------------------------------------------------

def test_regression_malformed_variable_unit_rejected_and_retried() -> None:
    """Regression 9B: Malformed unit fails validation, triggers retry, cannot silently enter DecisionModel."""
    long_unit = "% elasticity discount factor / baseline fraction that is way too long to be a unit label"

    # 1. Direct Pydantic validation rejects excessive string length
    with pytest.raises(ValidationError) as exc_info:
        Variable(
            id="var_invalid",
            name="Price Discount",
            description="Discount on subscription tier",
            variable_type=VariableType.PERCENTAGE,
            unit=long_unit,
        )
    assert "unit" in str(exc_info.value)

    # 2. Parser rejects malformed payload and raises LLMResponseValidationError
    sample_dict = get_default_decision_model().model_dump()
    sample_dict["variables"][0]["unit"] = long_unit
    malformed_json = json.dumps(sample_dict)

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(malformed_json, DecisionModel)
    assert "unit" in str(exc_info.value) or "Validation failed" in str(exc_info.value)

    # 3. Existing repair/retry path is triggered in GeminiLLMClient
    valid_dict = get_default_decision_model().model_dump()
    valid_dict["variables"][0]["unit"] = "%"

    responses = [
        httpx.Response(200, json={"output_text": malformed_json}),
        httpx.Response(200, json={"output_text": json.dumps(valid_dict)}),
    ]
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return responses.pop(0)

    http_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = GeminiLLMClient(api_key="test-api-key", http_client=http_client)

    result = client.generate_structured(
        prompt="Test prompt",
        response_schema=DecisionModel,
        config=LLMConfig(max_retries=1),
    )
    # Verification: retry occurred and valid model was ingested
    assert call_count == 2
    assert result.variables[0].unit == "%"
    assert result.variables[0].unit != long_unit


# ------------------------------------------------------------------------------
# Regression Test C: Inferred LTV:CAC Not Hard Constraint
# ------------------------------------------------------------------------------

def test_regression_inferred_ltv_cac_not_hard_constraint() -> None:
    """Regression 9C: Inferred LTV:CAC consideration without explicit threshold is not a hard constraint."""
    raw_prompt = "Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    model = get_default_decision_model(question=raw_prompt)
    model.constraints.append(
        Constraint(
            id="cnstr_ltv_cac",
            name="LTV to CAC Ratio Viability",
            description="Maintain healthy LTV to CAC ratio above 3.0",
            is_hard_constraint=True,  # Model inferred and marked True
            threshold_expression=None,
            source="user_specified",  # Model claimed user specified
        )
    )

    audited = audit_decision_provenance(
        model=model,
        raw_prompt=raw_prompt,
        constraints=[],  # User provided no constraint
    )

    ltv_cnstr = next(c for c in audited.constraints if c.id == "cnstr_ltv_cac")
    assert ltv_cnstr.is_hard_constraint is False
    assert ltv_cnstr.provenance == ProvenanceType.INFERRED
    assert ltv_cnstr.source == "inferred_operational"


# ------------------------------------------------------------------------------
# Regression Test D: Normal Test Execution Cannot Call Real Gemini Provider
# ------------------------------------------------------------------------------

def test_regression_normal_test_cannot_call_real_gemini() -> None:
    """Regression 9D: Normal test execution cannot instantiate/call unmocked Gemini provider."""
    client = GeminiLLMClient(api_key="AIzaSy-fake-unmocked-key")
    with pytest.raises(RuntimeError) as exc_info:
        client.generate_structured(
            prompt="Should we cut prices?",
            response_schema=DecisionModel,
        )
    assert "Fail-closed safety violation" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Regression Test E: Tests Pass When GEMINI_API_KEY is Completely Absent
# ------------------------------------------------------------------------------

def test_regression_tests_pass_without_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
    client: httpx.Client,
) -> None:
    """Regression 9E: Normal tests pass when GEMINI_API_KEY is completely absent."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.config import settings
    if hasattr(settings, "GEMINI_API_KEY"):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", None, raising=False)

    # 1. Direct AnalysisService works
    service = AnalysisService()
    req = AnalysisRequest(question="Should we migrate to serverless?")
    res = service.analyze(req)
    assert res.status == "completed"
    assert res.decision_model is not None

    # 2. HTTP POST /api/analyze works
    http_res = client.post("/api/analyze", json={"question": "Should we migrate to serverless?"})
    assert http_res.status_code == 200
    data = http_res.json()
    assert data["status"] == "completed"
    assert data["decision_model"] is not None
