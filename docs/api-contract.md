# AURA API Contract: Day 1 Specification

> **Base URL:** `http://127.0.0.1:8000` (configurable via `NEXT_PUBLIC_API_BASE_URL`)  
> **API Version:** `0.0.1-pre-alpha`  
> **Prefix:** `/api` for resource routes, `/` for root system utilities.

---

## 1. Endpoints

### 1.1 `POST /api/analyze`
Submits a natural-language decision question along with optional context and constraints for staging in the analysis engine.

- **URL:** `/api/analyze`
- **Method:** `POST`
- **Headers:**
  - `Content-Type: application/json`
  - `Accept: application/json`

#### Request Payload
| Field | Type | Required | Description | Constraints / Validation |
|---|---|---|---|---|
| `question` | `string` | **Yes** | The core decision problem statement to evaluate. | Must be non-empty; whitespace is trimmed; empty string rejected with HTTP 422. |
| `context` | `object` or `null` | No | Operational background, parameters, or scope. | Optional dictionary. Defaults to `null`. |
| `constraints` | `array[string]` | No | Non-negotiable boundaries, deadlines, or budget limits. | Optional list of strings. Defaults to `[]`. |

##### Request Example (Minimal)
```json
{
  "question": "Should we migrate from our monolithic database to a distributed SQL cluster?"
}
```

##### Request Example (Full)
```json
{
  "question": "Should we migrate from our monolithic database to a distributed SQL cluster?",
  "context": {
    "current_db": "PostgreSQL",
    "scale": "100k daily active users",
    "budget_usd": 40000
  },
  "constraints": [
    "Zero downtime migration",
    "Must complete in Q4"
  ]
}
```

#### Response Payload (HTTP 200 OK)
| Field | Type | Description |
|---|---|---|
| `analysis_id` | `string` (UUID4) | Globally unique identifier assigned to the staged decision analysis. |
| `status` | `string` | Current lifecycle status of the analysis session (`"pending"` in Day 1). |
| `question` | `string` | The validated, trimmed decision question submitted for analysis. |
| `message` | `string` | Informational status message acknowledging intake. |

##### Response Example
```json
{
  "analysis_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "status": "pending",
  "question": "Should we migrate from our monolithic database to a distributed SQL cluster?",
  "message": "Decision analysis request accepted and queued for processing (Day 1 Stub)."
}
```

---

### 1.2 `GET /health`
System liveness and readiness probe for the AURA FastAPI backend.

- **URL:** `/health`
- **Method:** `GET`
- **Headers:**
  - `Accept: application/json`

#### Response Payload (HTTP 200 OK)
| Field | Type | Description |
|---|---|---|
| `status` | `string` | Operational state (`"ok"`). |
| `service` | `string` | Service identifier (`"aura-backend"`). |
| `version` | `string` | Current backend version (`"0.0.1-pre-alpha"`). |
| `timestamp` | `string` (ISO 8601) | Current UTC timestamp. |

##### Response Example
```json
{
  "status": "ok",
  "service": "aura-backend",
  "version": "0.0.1-pre-alpha",
  "timestamp": "2026-10-02T06:30:00.000000Z"
}
```

---

## 2. Schema Type Parity

To prevent interface drift, backend Pydantic models in [`backend/app/schemas/analysis.py`](file:///d:/AURA/AURA/backend/app/schemas/analysis.py) match frontend TypeScript interfaces in [`frontend/src/types/api.ts`](file:///d:/AURA/AURA/frontend/src/types/api.ts):

### Python (Pydantic v2)
```python
class AnalysisRequest(BaseModel):
    question: str = Field(..., description="Core decision question.")
    context: Optional[Dict[str, Any]] = Field(default=None)
    constraints: List[str] = Field(default_factory=list)

class AnalysisResponse(BaseModel):
    analysis_id: str
    status: str
    question: str
    message: str
```

### TypeScript (Interface)
```typescript
export interface AnalysisRequest {
  question: string;
  context?: Record<string, unknown> | null;
  constraints?: string[];
}

export interface AnalysisResponse {
  analysis_id: string;
  status: string;
  question: string;
  message: string;
}
```

---

## 3. Error Responses

### 3.1 HTTP 422 Unprocessable Entity
Returned by FastAPI when input validation fails (e.g., empty or whitespace question, non-dict context, or non-list constraints).

#### Error Example
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "question"],
      "msg": "Value error, Question cannot be empty or contain only whitespace.",
      "input": "",
      "ctx": {
        "error": {}
      }
    }
  ]
}
```

### 3.2 HTTP 500 Internal Server Error
Returned when an unexpected runtime exception occurs inside the service layer.

#### Error Example
```json
{
  "detail": "Internal Server Error"
}
```

### 3.3 Network / Connectivity Errors
Handled client-side by [`ApiClientError`](file:///d:/AURA/AURA/frontend/src/lib/api.ts#L7-L18) when:
- The backend server is not running on port 8000.
- A CORS origin check fails in the browser.
- The returned response payload is malformed or missing required schema keys.
