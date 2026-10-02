"""Tests for Gemini Structured Output Handling & Resilience.

Validates that:
1. Gemini responses conform to the canonical DecisionModel schema.
2. Pydantic validation is strictly enforced.
3. Malformed JSON is handled safely without unhandled crashes.
4. Missing required fields raise structured LLMResponseValidationError.
5. Invalid or non-standard enum strings are safely normalized.
6. Incorrect data types are coerced or safely validated.
7. Epistemic integrity is maintained (inferred constraints are not marked as user facts).
8. GeminiLLMClient encapsulates transport and maps HTTP errors accurately.
"""

import json
from typing import Any, Dict
import httpx
import pytest

from app.schemas.decision_model import (
    ComplexityLevel,
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
    DecisionType,
    ReversibilityLevel,
    TimeHorizon,
    VariableType,
)
from app.services.llm.client import (
    LLMAuthenticationError,
    LLMConfig,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.parser import (
    StructuredOutputParser,
    parse_and_validate_structured_output,
)


# ------------------------------------------------------------------------------
# Fixtures & Sample Payloads
# ------------------------------------------------------------------------------

@pytest.fixture
def valid_decision_dict() -> Dict[str, Any]:
    """Returns a canonical dictionary that perfectly satisfies DecisionModel."""
    return {
        "id": "dec_sample_001",
        "decision": {
            "raw_prompt": "Should our SaaS startup reduce pricing by 20% to acquire more customers?",
            "summary": "Evaluate reducing SaaS subscription pricing by 20% to accelerate customer acquisition.",
            "decision_type": "strategic_direction",
            "time_horizon": "medium_term",
        },
        "complexity": {
            "level": "medium",
            "reasoning": "Interactions between pricing, churn, customer acquisition, and unit economics.",
            "reversibility": "partially_reversible",
            "score": 45.0,
        },
        "objectives": [
            {
                "id": "obj_acq",
                "description": "Increase monthly active customer acquisition by 35%.",
                "is_primary": True,
                "target_metric": "+35% MoM new accounts",
            },
            {
                "id": "obj_arr",
                "description": "Protect gross annual recurring revenue from declining.",
                "is_primary": False,
                "target_metric": ">= $2.5M ARR",
            },
        ],
        "variables": [
            {
                "id": "var_price",
                "name": "Subscription Price Discount",
                "description": "Percentage discount applied to standard tier.",
                "variable_type": "percentage",
                "baseline_value": 0.0,
                "proposed_value": -20.0,
                "unit": "%",
                "is_controllable": True,
            },
            {
                "id": "var_churn",
                "name": "Monthly Churn Rate",
                "description": "Expected rate of customer cancellations.",
                "variable_type": "percentage",
                "baseline_value": 3.5,
                "proposed_value": 4.0,
                "unit": "%",
                "is_controllable": False,
            },
        ],
        "constraints": [
            {
                "id": "cnstr_margin",
                "name": "Gross Margin Threshold",
                "description": "Gross margin must not fall below 70%.",
                "is_hard_constraint": True,
                "threshold_expression": "gross_margin >= 0.70",
                "source": "user_specified",
            }
        ],
        "stakeholders": [
            {
                "id": "stk_leadership",
                "group": "Executive Leadership",
                "impact_nature": "Accountable for runway and investor expectations.",
                "influence_level": "high",
            }
        ],
        "tradeoffs": [
            {
                "id": "trd_volume_vs_margin",
                "upside": "Higher volume of top-of-funnel customer signups.",
                "downside": "Compressed revenue per account and potentially longer payback period.",
                "affected_variable_ids": ["var_price"],
            }
        ],
        "assumptions": [
            {
                "id": "asm_elasticity",
                "statement": "Price elasticity of demand is sufficiently high that volume offsets price cuts.",
                "confidence": "untested",
                "falsification_condition": "Customer signup rate increases by less than 15% after 60 days.",
            }
        ],
        "unknowns": [
            {
                "id": "unk_competitor",
                "question": "How will the primary market competitor respond to our discounted tier?",
                "criticality": "high",
                "potential_sources": ["Competitor pricing telemetry", "Customer exit interviews"],
            }
        ],
        "key_questions": [
            "What is our estimated CAC payback period under the 20% discount?",
            "Will existing cohort customers demand retroactive price matching?",
        ],
    }


# ------------------------------------------------------------------------------
# 1. Valid Parsing & Markdown Fence Handling
# ------------------------------------------------------------------------------

def test_parse_valid_decision_model(valid_decision_dict: Dict[str, Any]):
    """Tests that a clean JSON string matching DecisionModel parses into a validated model."""
    raw_json = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_json, DecisionModel)

    assert isinstance(model, DecisionModel)
    assert model.id == "dec_sample_001"
    assert model.decision.decision_type == DecisionType.STRATEGIC_DIRECTION
    assert model.decision.time_horizon == TimeHorizon.MEDIUM_TERM
    assert len(model.objectives) == 2
    assert model.objectives[0].is_primary is True
    assert len(model.variables) == 2
    assert len(model.tradeoffs) == 1
    assert model.tradeoffs[0].affected_variable_ids == ["var_price"]


def test_parse_markdown_code_fences(valid_decision_dict: Dict[str, Any]):
    """Tests extraction from markdown ```json fences with surrounding commentary."""
    raw_text = (
        "Here is the analyzed decision model:\n\n"
        "```json\n"
        f"{json.dumps(valid_decision_dict, indent=2)}\n"
        "```\n\n"
        "Let me know if you would like me to unpack any section further."
    )
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert isinstance(model, DecisionModel)
    assert model.id == "dec_sample_001"
    assert model.decision.summary.startswith("Evaluate reducing SaaS")


def test_parse_unlabeled_code_fences(valid_decision_dict: Dict[str, Any]):
    """Tests extraction from markdown fences without the 'json' tag."""
    raw_text = f"```\n{json.dumps(valid_decision_dict)}\n```"
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert isinstance(model, DecisionModel)
    assert model.id == "dec_sample_001"


# ------------------------------------------------------------------------------
# 2. Malformed JSON Safety
# ------------------------------------------------------------------------------

def test_malformed_truncated_json_raises_validation_error():
    """Tests that truncated/cut-off JSON raises LLMResponseValidationError safely."""
    truncated = '{"id": "dec_1", "decision": {"summary": "Pricing choice", "decision_type":'

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(truncated, DecisionModel)

    assert "Malformed JSON syntax from LLM" in str(exc_info.value)
    assert exc_info.value.details.get("json_error") is not None


def test_malformed_syntax_raises_validation_error():
    """Tests that JSON with syntax errors (trailing comma, unquoted identifiers) raises safely."""
    syntax_error_json = '{"decision": {"summary": "test",}, "objectives": []}'

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(syntax_error_json, DecisionModel)

    assert "Malformed JSON syntax" in str(exc_info.value)


def test_empty_or_whitespace_output_raises_validation_error():
    """Tests that empty or whitespace strings raise LLMResponseValidationError."""
    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output("   \n\t  ", DecisionModel)

    assert "empty or whitespace-only" in str(exc_info.value)


def test_non_json_conversational_text_raises_validation_error():
    """Tests that a model refusing to return JSON raises LLMResponseValidationError."""
    conversational = "I am sorry, but I cannot assist with this business decision."

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(conversational, DecisionModel)

    assert "No valid JSON structure found" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 3. Missing Fields & Defensive Normalization
# ------------------------------------------------------------------------------

def test_missing_required_decision_raises_validation_error(valid_decision_dict: Dict[str, Any]):
    """Tests that missing 'decision' section raises clear schema validation error."""
    del valid_decision_dict["decision"]
    raw_text = json.dumps(valid_decision_dict)

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(raw_text, DecisionModel)

    assert "Validation failed for schema DecisionModel" in str(exc_info.value)
    assert "decision" in str(exc_info.value)


def test_missing_variables_raises_validation_error(valid_decision_dict: Dict[str, Any]):
    """Tests that omitting 'variables' raises validation error."""
    del valid_decision_dict["variables"]
    raw_text = json.dumps(valid_decision_dict)

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(raw_text, DecisionModel)

    assert "variables" in str(exc_info.value)


def test_auto_generates_missing_top_level_id(valid_decision_dict: Dict[str, Any]):
    """Tests that if the model omits top-level 'id', a UUID-based ID is safely generated."""
    del valid_decision_dict["id"]
    raw_text = json.dumps(valid_decision_dict)

    model = parse_and_validate_structured_output(raw_text, DecisionModel)
    assert model.id.startswith("dec_")
    assert len(model.id) > 5


def test_auto_generates_missing_collection_ids(valid_decision_dict: Dict[str, Any]):
    """Tests that if child items lack 'id', sequential IDs are safely generated."""
    del valid_decision_dict["objectives"][0]["id"]
    del valid_decision_dict["variables"][0]["id"]
    # Update tradeoff reference to match the generated id
    valid_decision_dict["tradeoffs"][0]["affected_variable_ids"] = ["var_1"]

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.objectives[0].id == "obj_1"
    assert model.variables[0].id == "var_1"


def test_enforces_primary_objective_if_model_omits_flag(valid_decision_dict: Dict[str, Any]):
    """Tests that if all objectives have is_primary=False, the first is safely flagged True."""
    for obj in valid_decision_dict["objectives"]:
        obj["is_primary"] = False

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.objectives[0].is_primary is True


def test_filters_hallucinated_tradeoff_variable_references(valid_decision_dict: Dict[str, Any]):
    """Tests that hallucinated variable references in tradeoffs are pruned rather than crashing validation."""
    valid_decision_dict["tradeoffs"][0]["affected_variable_ids"] = ["var_price", "non_existent_var_99"]

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.tradeoffs[0].affected_variable_ids == ["var_price"]


# ------------------------------------------------------------------------------
# 4. Enum Normalization & Safe Fallbacks
# ------------------------------------------------------------------------------

def test_enum_normalization_case_and_formatting(valid_decision_dict: Dict[str, Any]):
    """Tests that uppercase, hyphenated, and space-separated enum values are safely normalized."""
    valid_decision_dict["decision"]["decision_type"] = "STRATEGIC-DIRECTION"
    valid_decision_dict["decision"]["time_horizon"] = "Short-Term"
    valid_decision_dict["complexity"]["level"] = "HIGH"
    valid_decision_dict["complexity"]["reversibility"] = "IRREVERSIBLE"
    valid_decision_dict["variables"][0]["variable_type"] = "PERCENTAGE"
    valid_decision_dict["stakeholders"][0]["influence_level"] = "High"
    valid_decision_dict["assumptions"][0]["confidence"] = "Untested"
    valid_decision_dict["unknowns"][0]["criticality"] = "HIGH"

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.decision.decision_type == DecisionType.STRATEGIC_DIRECTION
    assert model.decision.time_horizon == TimeHorizon.SHORT_TERM
    assert model.complexity.level == ComplexityLevel.HIGH
    assert model.complexity.reversibility == ReversibilityLevel.IRREVERSIBLE
    assert model.variables[0].variable_type == VariableType.PERCENTAGE
    assert model.stakeholders[0].influence_level == CriticalityLevel.HIGH
    assert model.assumptions[0].confidence == ConfidenceLevel.UNTESTED
    assert model.unknowns[0].criticality == CriticalityLevel.HIGH


def test_unknown_enum_safely_falls_back(valid_decision_dict: Dict[str, Any]):
    """Tests that a completely unrecognized enum string safely falls back rather than crashing."""
    valid_decision_dict["decision"]["decision_type"] = "completely_unknown_domain_type"
    valid_decision_dict["decision"]["time_horizon"] = "unprecedented_future"

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.decision.decision_type == DecisionType.GENERAL_CHOICE
    assert model.decision.time_horizon == TimeHorizon.MEDIUM_TERM


# ------------------------------------------------------------------------------
# 5. Type Coercion Safety
# ------------------------------------------------------------------------------

def test_coerces_compatible_data_types(valid_decision_dict: Dict[str, Any]):
    """Tests that string booleans, string floats, and single string questions are safely coerced."""
    valid_decision_dict["objectives"][0]["is_primary"] = "true"
    valid_decision_dict["complexity"]["score"] = "45.5"
    valid_decision_dict["key_questions"] = "Will existing cohort customers churn if we cut prices?"

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert model.objectives[0].is_primary is True
    assert model.complexity.score == 45.5
    assert model.key_questions == ["Will existing cohort customers churn if we cut prices?"]


def test_coerces_string_constraints_to_objects(valid_decision_dict: Dict[str, Any]):
    """Tests that a list of constraint strings is converted into structured Constraint models."""
    valid_decision_dict["constraints"] = [
        "Budget must not exceed $10,000",
        "Must be launched within Q2",
    ]

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(raw_text, DecisionModel)

    assert len(model.constraints) == 2
    assert model.constraints[0].id == "cnstr_1"
    assert model.constraints[0].description == "Budget must not exceed $10,000"
    assert model.constraints[1].id == "cnstr_2"
    assert model.constraints[1].description == "Must be launched within Q2"


# ------------------------------------------------------------------------------
# 6. Epistemic Safety: Never Convert Fabrications into Facts
# ------------------------------------------------------------------------------

def test_epistemic_safety_tags_inferred_constraints(valid_decision_dict: Dict[str, Any]):
    """Tests that model-invented constraints not stated by the user are marked 'inferred_operational'."""
    # User only specified margin constraint
    user_constraints = ["Gross margin must not fall below 70%"]

    # Model returns user's constraint plus an invented regulatory constraint tagged as user_specified
    valid_decision_dict["constraints"] = [
        {
            "id": "cnstr_1",
            "name": "Margin",
            "description": "Gross margin must not fall below 70%",
            "source": "user_specified",
        },
        {
            "id": "cnstr_2",
            "name": "GDPR Compliance",
            "description": "Must ensure full GDPR data residency in Frankfurt.",
            "source": "user_specified",  # Model claims this was user specified!
        },
    ]

    raw_text = json.dumps(valid_decision_dict)
    model = parse_and_validate_structured_output(
        raw_text=raw_text,
        response_schema=DecisionModel,
        user_constraints=user_constraints,
    )

    # First constraint matches user constraint -> source remains user_specified
    assert model.constraints[0].source == "user_specified"
    # Second constraint was invented by model -> source coerced to inferred_operational
    assert model.constraints[1].source == "inferred_operational"


# ------------------------------------------------------------------------------
# 7. GeminiLLMClient HTTP & Transport Handling
# ------------------------------------------------------------------------------

def test_gemini_client_missing_api_key_raises_auth_error():
    """Tests that invoking GeminiLLMClient without an API key raises LLMAuthenticationError."""
    client = GeminiLLMClient(api_key="")

    with pytest.raises(LLMAuthenticationError) as exc_info:
        client.generate_structured(
            prompt="Should we expand into Europe?",
            response_schema=DecisionModel,
        )

    assert "Gemini API key is not configured" in str(exc_info.value)


def test_gemini_client_successful_generation(valid_decision_dict: Dict[str, Any]):
    """Tests GeminiLLMClient successful flow using an injected mock transport."""
    gemini_api_response = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(valid_decision_dict)}],
                },
                "finishReason": "STOP",
            }
        ]
    }

    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=gemini_api_response)
    )
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(api_key="test-api-key-123", http_client=http_client)
    result = client.generate_structured(
        prompt="Should our startup discount pricing?",
        response_schema=DecisionModel,
    )

    assert isinstance(result, DecisionModel)
    assert result.id == "dec_sample_001"
    assert result.decision.decision_type == DecisionType.STRATEGIC_DIRECTION


def test_gemini_client_rate_limit_error():
    """Tests that HTTP 429 is mapped to LLMRateLimitError."""
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(429, text="Resource has been exhausted (e.g. check quota).")
    )
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(api_key="test-api-key", http_client=http_client)

    with pytest.raises(LLMRateLimitError) as exc_info:
        client.generate_structured(
            prompt="Should we scale nodes?",
            response_schema=DecisionModel,
        )

    assert "Gemini rate limit or quota exceeded" in str(exc_info.value)


def test_gemini_client_provider_500_error():
    """Tests that HTTP 500 is mapped to LLMProviderError."""
    mock_transport = httpx.MockTransport(
        lambda request: httpx.Response(503, text="Service Unavailable")
    )
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(api_key="test-api-key", http_client=http_client)

    with pytest.raises(LLMProviderError) as exc_info:
        client.generate_structured(
            prompt="Should we launch?",
            response_schema=DecisionModel,
        )

    assert "Gemini upstream server error" in str(exc_info.value)


def test_gemini_client_timeout_error():
    """Tests that an HTTP timeout maps to LLMTimeoutError."""
    def timeout_handler(request):
        raise httpx.ReadTimeout("Read timed out")

    mock_transport = httpx.MockTransport(timeout_handler)
    http_client = httpx.Client(transport=mock_transport)

    client = GeminiLLMClient(api_key="test-api-key", http_client=http_client)

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate_structured(
            prompt="Should we refactor the monolith?",
            response_schema=DecisionModel,
            config=LLMConfig(timeout_seconds=5.0),
        )

    assert "Gemini API request timed out" in str(exc_info.value)
