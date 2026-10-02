import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.analysis import AnalysisRequest, AnalysisResponse


# ------------------------------------------------------------------------------
# 1. API Route Integration Tests (via TestClient)
# ------------------------------------------------------------------------------


def test_analyze_valid_full_payload(client: TestClient) -> None:
    """Test POST /api/analyze with all fields provided."""
    payload = {
        "question": "Should we migrate from a monolithic database to a distributed architecture?",
        "context": {
            "current_db": "PostgreSQL",
            "daily_active_users": 100000,
            "budget_usd": 30000,
        },
        "constraints": [
            "Zero downtime during transition",
            "Target completion in Q4",
        ],
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "analysis_id" in data
    assert isinstance(data["analysis_id"], str)
    assert len(data["analysis_id"]) > 0
    assert data["status"] == "completed"
    assert "decision_model" in data
    assert data["decision_model"] is not None
    assert (
        data["question"]
        == "Should we migrate from a monolithic database to a distributed architecture?"
    )
    assert "message" in data
    assert isinstance(data["message"], str)


def test_analyze_valid_minimal_payload(client: TestClient) -> None:
    """Test POST /api/analyze with only the required question field."""
    payload = {
        "question": "Should we adopt Rust for our high-throughput data processing engine?",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["question"] == payload["question"]
    assert data["status"] == "completed"
    assert "decision_model" in data
    assert "analysis_id" in data


def test_analyze_empty_question(client: TestClient) -> None:
    """Test POST /api/analyze fails with 422 when question is an empty string."""
    payload = {
        "question": "",
        "constraints": ["Constraint 1"],
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422

    body = response.json()
    errors = body.get("detail", [])
    assert any("Question cannot be empty or contain only whitespace" in str(err) for err in errors)


def test_analyze_whitespace_question(client: TestClient) -> None:
    """Test POST /api/analyze fails with 422 when question contains only whitespace."""
    payload = {
        "question": "      ",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422

    body = response.json()
    errors = body.get("detail", [])
    assert any("Question cannot be empty or contain only whitespace" in str(err) for err in errors)


def test_analyze_missing_question_field(client: TestClient) -> None:
    """Test POST /api/analyze fails with 422 when question key is omitted."""
    payload = {
        "context": {"key": "val"},
        "constraints": ["Constraint 1"],
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422

    body = response.json()
    errors = body.get("detail", [])
    assert any(err.get("loc") == ["body", "question"] for err in errors)


def test_analyze_invalid_context_type(client: TestClient) -> None:
    """Test POST /api/analyze fails with 422 when context is not a dictionary."""
    payload = {
        "question": "Valid decision question?",
        "context": "this-should-be-a-dictionary",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_invalid_constraints_type(client: TestClient) -> None:
    """Test POST /api/analyze fails with 422 when constraints is not a list."""
    payload = {
        "question": "Valid decision question?",
        "constraints": "not-a-list",
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 422


# ------------------------------------------------------------------------------
# 2. Direct Pydantic Model Unit Tests
# ------------------------------------------------------------------------------


def test_analysis_request_model_direct() -> None:
    """Directly test AnalysisRequest validation, defaults, and trimming."""
    req = AnalysisRequest(
        question="   Should we expand to multi-region?   ",
        context={"primary_region": "us-east-1"},
    )
    # Verifies whitespace trimming
    assert req.question == "Should we expand to multi-region?"
    assert req.context == {"primary_region": "us-east-1"}
    # Verifies default constraints list
    assert req.constraints == []


def test_analysis_request_model_empty_raises() -> None:
    """Directly test that empty or whitespace strings raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        AnalysisRequest(question="")
    assert "Question cannot be empty or contain only whitespace" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        AnalysisRequest(question="     \t \n  ")
    assert "Question cannot be empty or contain only whitespace" in str(exc_info.value)


def test_analysis_response_model_direct() -> None:
    """Directly test AnalysisResponse validation and serialization."""
    res = AnalysisResponse(
        analysis_id="test-1234",
        status="pending",
        question="Should we adopt GraphQL?",
        message="Queued for analysis",
    )
    assert res.analysis_id == "test-1234"
    assert res.status == "pending"
    assert res.question == "Should we adopt GraphQL?"
    assert res.message == "Queued for analysis"
