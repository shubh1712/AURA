# AURA Development Rules & Engineering Standards

These 10 core engineering rules govern the development, extension, and maintenance of the AURA platform. All contributors and automated agents must adhere to these standards.

---

### Rule 1: Business logic should not live in UI components
UI components (`src/components/`) must focus strictly on layout, user interaction, rendering, and accessibility. 
- **Do not** write data-transformation logic, external network calls, or validation algorithms directly inside React views.
- **Do** isolate state transitions, client-side validation rules, in-flight guards, and lifecycle effects inside reusable custom hooks (`src/hooks/`) or dedicated utilities (`src/lib/`).

---

### Rule 2: API routes should remain thin
FastAPI route controllers (`backend/app/api/routes/`) should act exclusively as HTTP gateways:
- Route handlers parse the request, invoke Pydantic schema validation, and immediately delegate execution to the service layer via dependency injection (`Depends(get_service)`).
- Route handlers must never directly query databases, execute business logic, or instantiate multi-step workflows.

---

### Rule 3: Pydantic validates backend data
All data crossing the network boundary into the backend must be defined as Pydantic models in `backend/app/schemas/`:
- Utilize `Field(...)` definitions, type annotations, and `@field_validator` decorators to enforce strict boundaries.
- Never manually parse or sanitize raw JSON dictionaries inside route handlers or business logic.

---

### Rule 4: TypeScript types represent frontend contracts
The frontend must maintain complete structural parity with backend Pydantic models using TypeScript interfaces in `frontend/src/types/`:
- Data structures passed between hooks, components, and the API client must be strictly typed.
- Avoid using `any`. Use `unknown` with runtime type narrowing or defined interfaces to preserve type safety across the network boundary.

---

### Rule 5: AI-generated code must be tested
Every AI-assisted code change or feature addition must be accompanied by automated validation before acceptance:
- **Backend:** Verify unit logic and API routes with `pytest` (`backend/tests/`).
- **Frontend:** Verify compilation and type integrity via `npm run build` and interactive workflows via automated browser/integration tests.
- Never mark a task as complete based on speculative correctness.

---

### Rule 6: LLM calls should eventually be isolated behind services
As cognitive decision engines are implemented, LLM client invocations must not pollute route controllers or generic utility files:
- All model interactions must reside inside dedicated service wrappers or agent modules (`app/services/` and `app/agents/`).
- Service boundaries must define strict input/output signatures so that model providers (e.g. Gemini, local models) can be swapped or mocked in test suites without altering downstream consumers.

---

### Rule 7: Deterministic calculations must not be delegated to the LLM
Calculations involving resilience boundaries, risk scores, budget limits, scenario parameters, and probability distributions must be executed mathematically using deterministic code:
- LLMs are probabilistic text processors and must not be used as arithmetic or constraint-solving calculators.
- Use Python engines (`app/engines/`) for mathematical evaluations, leveraging LLMs solely for semantic synthesis, qualitative reasoning, and explanation drafting.

---

### Rule 8: New features should be modular
Every new functional capability must be packaged as an isolated module with clear interfaces:
- New cognitive pillars should be implemented in dedicated directories within `app/engines/`.
- New UI views should compose smaller, focused primitives from `src/components/`.
- Modular code allows individual decision engines to be benchmarked, upgraded, or disabled independently.

---

### Rule 9: Avoid unnecessary dependencies
Keep the dependency tree lean and deliberate:
- Do not add external packages for tasks achievable with language primitives (e.g. avoid adding `axios` when native `fetch` suffices; avoid large utility libraries for simple array/string manipulations).
- Every added dependency introduces maintenance overhead, supply-chain attack surface, and bundle-size latency.

---

### Rule 10: Existing functionality must not be broken when adding features
Refactoring and feature additions must maintain non-breaking backward compatibility with existing tests and contracts:
- Run the full test suite (`pytest` and `npm run build`) before and after any change.
- Never modify or remove existing schema fields or test assertions without explicit architectural review.
