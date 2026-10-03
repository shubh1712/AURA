"""AURA Structured Output Parser and Validator.

Provides resilient extraction, sanitization, and Pydantic validation for
language model responses. Ensures adherence to canonical schemas, prevents
application crashes from malformed JSON or invalid types, and strictly preserves
epistemic integrity (distinguishing user-stated facts from model inferences).
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

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
from app.services.llm.client import LLMResponseValidationError

T = TypeVar("T", bound=BaseModel)


# ------------------------------------------------------------------------------
# 1. Normalization Helpers for Enums and Scalars
# ------------------------------------------------------------------------------

def _normalize_string_key(val: Any) -> str:
    """Strips whitespace, converts to lowercase, and replaces hyphens/spaces with underscores."""
    if not isinstance(val, str):
        val = str(val)
    return re.sub(r"[\s\-]+", "_", val.strip().lower())


def _safe_enum_lookup(val: Any, enum_cls: Any, fallback: Any) -> Any:
    """Attempts exact and normalized lookup in enum_cls; returns fallback if unresolvable."""
    if val is None:
        return fallback

    normalized = _normalize_string_key(val)
    # Check by value
    for member in enum_cls:
        if member.value == normalized or _normalize_string_key(member.name) == normalized:
            return member

    # Partial substring heuristic for common model shorthand
    for member in enum_cls:
        if normalized in member.value or member.value in normalized:
            return member

    return fallback


def _safe_bool(val: Any, default: bool = False) -> bool:
    """Coerces various truthy/falsy representations to a boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "1", "yes", "y", "t", "primary"):
            return True
        if s in ("false", "0", "no", "n", "f", "secondary"):
            return False
    return default


# ------------------------------------------------------------------------------
# 2. Main StructuredOutputParser Class
# ------------------------------------------------------------------------------

class StructuredOutputParser:
    """Resilient parser and validator for model structured outputs."""

    @staticmethod
    def extract_json_string(raw_text: str) -> str:
        """Extracts JSON string from model response, handling Markdown fences and commentary.

        Args:
            raw_text: Raw textual content returned by the LLM.

        Returns:
            Extracted JSON string candidate.

        Raises:
            LLMResponseValidationError: If no JSON object or array structure can be located.
        """
        if not raw_text or not raw_text.strip():
            raise LLMResponseValidationError("LLM returned empty or whitespace-only response.")

        text = raw_text.strip()

        # 1. Check for standard Markdown code fences: ```json ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            if candidate:
                return candidate

        # 2. Find outermost JSON object bounds: first '{' to last '}'
        start_brace = text.find("{")
        end_brace = text.rfind("}")

        if start_brace != -1:
            if end_brace != -1 and end_brace > start_brace:
                return text[start_brace : end_brace + 1].strip()
            # Truncated JSON starting with '{'
            return text[start_brace:].strip()

        # 3. Find outermost JSON array bounds: first '[' to last ']'
        start_bracket = text.find("[")
        end_bracket = text.rfind("]")
        if start_bracket != -1:
            if end_bracket != -1 and end_bracket > start_bracket:
                return text[start_bracket : end_bracket + 1].strip()
            # Truncated JSON array starting with '['
            return text[start_bracket:].strip()

        raise LLMResponseValidationError(
            f"No valid JSON structure found in LLM output. Raw snippet: {text[:200]!r}",
            details={"raw_output": text[:500]},
        )

    @classmethod
    def safe_parse_json(cls, raw_text: str) -> Any:
        """Extracts and parses JSON, converting JSONDecodeError into typed LLMResponseValidationError.

        Args:
            raw_text: Raw output string from model.

        Returns:
            Parsed JSON data structure (usually dict or list).

        Raises:
            LLMResponseValidationError: On JSON syntax or extraction errors.
        """
        extracted = cls.extract_json_string(raw_text)

        try:
            return json.loads(extracted)
        except json.JSONDecodeError as e:
            # Provide actionable error context including line and column numbers
            error_context = (
                f"Malformed JSON syntax from LLM: {e.msg} at line {e.lineno}, column {e.colno}. "
                f"Error near: {extracted[max(0, e.pos - 30):min(len(extracted), e.pos + 30)]!r}"
            )
            raise LLMResponseValidationError(
                error_context,
                details={
                    "json_error": e.msg,
                    "lineno": e.lineno,
                    "colno": e.colno,
                    "pos": e.pos,
                    "extracted_snippet": extracted[:500],
                },
            ) from e

    @classmethod
    def sanitize_decision_model_dict(
        cls,
        data: Dict[str, Any],
        raw_user_prompt: Optional[str] = None,
        user_constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Sanitizes raw JSON dict for DecisionModel schema conformance.

        Performs defensive normalization:
        - Auto-generates missing collection IDs and top-level ID
        - Normalizes enums across all child entities
        - Ensures primary objective invariant
        - Coerces compatible types
        - Enforces epistemic safety: ensures unstated constraints are tagged
          as 'inferred_operational' rather than 'user_specified'.

        Args:
            data: Raw dictionary parsed from JSON.
            raw_user_prompt: The verbatim user prompt.
            user_constraints: Explicit constraints submitted by the user.

        Returns:
            Sanitized dictionary ready for Pydantic validation.
        """
        sanitized = dict(data)

        # 1. Top-Level ID
        if not sanitized.get("id") or not isinstance(sanitized.get("id"), str):
            sanitized["id"] = f"dec_{uuid.uuid4().hex[:12]}"

        # 2. Decision Section
        decision_raw = sanitized.get("decision")
        if isinstance(decision_raw, dict):
            dec = dict(decision_raw)
            # Ensure raw_prompt is populated with actual user input
            if not dec.get("raw_prompt") or not isinstance(dec.get("raw_prompt"), str):
                dec["raw_prompt"] = raw_user_prompt or dec.get("summary") or "Verbatim prompt unavailable."

            # Normalize decision_type enum
            dec["decision_type"] = _safe_enum_lookup(
                dec.get("decision_type"),
                DecisionType,
                fallback=DecisionType.GENERAL_CHOICE,
            )

            # Normalize time_horizon enum
            dec["time_horizon"] = _safe_enum_lookup(
                dec.get("time_horizon"),
                TimeHorizon,
                fallback=TimeHorizon.MEDIUM_TERM,
            )
            sanitized["decision"] = dec

        # 3. Complexity Section
        complexity_raw = sanitized.get("complexity")
        if isinstance(complexity_raw, dict):
            comp = dict(complexity_raw)
            comp["level"] = _safe_enum_lookup(
                comp.get("level"),
                ComplexityLevel,
                fallback=ComplexityLevel.MEDIUM,
            )
            comp["reversibility"] = _safe_enum_lookup(
                comp.get("reversibility"),
                ReversibilityLevel,
                fallback=ReversibilityLevel.PARTIALLY_REVERSIBLE,
            )
            # Ensure score is numeric if present
            if comp.get("score") is not None:
                try:
                    comp["score"] = float(comp["score"])
                except (ValueError, TypeError):
                    comp["score"] = None
            sanitized["complexity"] = comp

        # 4. Objectives Section
        objectives_raw = sanitized.get("objectives")
        if isinstance(objectives_raw, list):
            clean_objs: List[Dict[str, Any]] = []
            has_primary = False
            for idx, item in enumerate(objectives_raw):
                if isinstance(item, dict):
                    obj = dict(item)
                    if not obj.get("id"):
                        obj["id"] = f"obj_{idx + 1}"
                    obj["is_primary"] = _safe_bool(obj.get("is_primary"), default=False)
                    if obj["is_primary"]:
                        has_primary = True
                    clean_objs.append(obj)
            # Guardrail: Ensure at least one primary objective exists
            if clean_objs and not has_primary:
                clean_objs[0]["is_primary"] = True
            sanitized["objectives"] = clean_objs

        # 5. Variables Section
        variables_raw = sanitized.get("variables")
        valid_variable_ids = set()
        if isinstance(variables_raw, list):
            clean_vars: List[Dict[str, Any]] = []
            for idx, item in enumerate(variables_raw):
                if isinstance(item, dict):
                    var = dict(item)
                    if not var.get("id"):
                        var["id"] = f"var_{idx + 1}"
                    var["variable_type"] = _safe_enum_lookup(
                        var.get("variable_type"),
                        VariableType,
                        fallback=VariableType.QUALITATIVE,
                    )
                    var["is_controllable"] = _safe_bool(var.get("is_controllable"), default=True)
                    valid_variable_ids.add(var["id"])
                    clean_vars.append(var)
            sanitized["variables"] = clean_vars

        # 6. Constraints Section (Epistemic Safety Rule)
        constraints_raw = sanitized.get("constraints")
        if constraints_raw is None:
            sanitized["constraints"] = []
        elif isinstance(constraints_raw, list):
            clean_cnstrs: List[Dict[str, Any]] = []
            user_constraint_texts = [c.strip().lower() for c in (user_constraints or []) if c.strip()]

            for idx, item in enumerate(constraints_raw):
                if isinstance(item, str):
                    # Coerce string item into Constraint dict
                    desc = item.strip()
                    is_user = any(u in desc.lower() for u in user_constraint_texts) if user_constraint_texts else False
                    clean_cnstrs.append({
                        "id": f"cnstr_{idx + 1}",
                        "name": f"Constraint {idx + 1}",
                        "description": desc,
                        "is_hard_constraint": is_user,
                        "source": "user_specified" if is_user else "inferred_operational",
                    })
                elif isinstance(item, dict):
                    cnstr = dict(item)
                    if not cnstr.get("id"):
                        cnstr["id"] = f"cnstr_{idx + 1}"

                    # AI Epistemic Rule: Do not convert fabricated info into facts.
                    # Verify whether constraint truly came from user specifications.
                    desc = str(cnstr.get("description", "")).lower()
                    is_explicit_user = any(u in desc for u in user_constraint_texts) if user_constraint_texts else False

                    # If not explicitly from user, enforce "inferred_operational" tag and is_hard_constraint=False
                    if not is_explicit_user:
                        cnstr["source"] = "inferred_operational"
                        cnstr["is_hard_constraint"] = False
                    else:
                        cnstr["source"] = "user_specified"
                        cnstr["is_hard_constraint"] = _safe_bool(cnstr.get("is_hard_constraint"), default=True)

                    clean_cnstrs.append(cnstr)
            sanitized["constraints"] = clean_cnstrs

        # 7. Stakeholders Section
        stakeholders_raw = sanitized.get("stakeholders")
        if stakeholders_raw is None:
            sanitized["stakeholders"] = []
        elif isinstance(stakeholders_raw, list):
            clean_stks: List[Dict[str, Any]] = []
            for idx, item in enumerate(stakeholders_raw):
                if isinstance(item, dict):
                    stk = dict(item)
                    if not stk.get("id"):
                        stk["id"] = f"stk_{idx + 1}"
                    stk["influence_level"] = _safe_enum_lookup(
                        stk.get("influence_level"),
                        CriticalityLevel,
                        fallback=CriticalityLevel.MEDIUM,
                    )
                    clean_stks.append(stk)
            sanitized["stakeholders"] = clean_stks

        # 8. Tradeoffs Section
        tradeoffs_raw = sanitized.get("tradeoffs")
        if isinstance(tradeoffs_raw, list):
            clean_trds: List[Dict[str, Any]] = []
            for idx, item in enumerate(tradeoffs_raw):
                if isinstance(item, dict):
                    trd = dict(item)
                    if not trd.get("id"):
                        trd["id"] = f"trd_{idx + 1}"
                    # Ensure affected_variable_ids only reference existing variable IDs
                    raw_var_refs = trd.get("affected_variable_ids") or []
                    if isinstance(raw_var_refs, list):
                        trd["affected_variable_ids"] = [
                            vid for vid in raw_var_refs if vid in valid_variable_ids
                        ]
                    else:
                        trd["affected_variable_ids"] = []
                    clean_trds.append(trd)
            sanitized["tradeoffs"] = clean_trds

        # 9. Assumptions Section
        assumptions_raw = sanitized.get("assumptions")
        if assumptions_raw is None:
            sanitized["assumptions"] = []
        elif isinstance(assumptions_raw, list):
            clean_asms: List[Dict[str, Any]] = []
            for idx, item in enumerate(assumptions_raw):
                if isinstance(item, dict):
                    asm = dict(item)
                    if not asm.get("id"):
                        asm["id"] = f"asm_{idx + 1}"
                    asm["confidence"] = _safe_enum_lookup(
                        asm.get("confidence"),
                        ConfidenceLevel,
                        fallback=ConfidenceLevel.UNTESTED,
                    )
                    clean_asms.append(asm)
            sanitized["assumptions"] = clean_asms

        # 10. Unknowns Section
        unknowns_raw = sanitized.get("unknowns")
        if unknowns_raw is None:
            sanitized["unknowns"] = []
        elif isinstance(unknowns_raw, list):
            clean_unks: List[Dict[str, Any]] = []
            for idx, item in enumerate(unknowns_raw):
                if isinstance(item, dict):
                    unk = dict(item)
                    if not unk.get("id"):
                        unk["id"] = f"unk_{idx + 1}"
                    unk["criticality"] = _safe_enum_lookup(
                        unk.get("criticality"),
                        CriticalityLevel,
                        fallback=CriticalityLevel.MEDIUM,
                    )
                    if not isinstance(unk.get("potential_sources"), list):
                        unk["potential_sources"] = []
                    clean_unks.append(unk)
            sanitized["unknowns"] = clean_unks

        # 11. Key Questions Section
        key_questions_raw = sanitized.get("key_questions")
        if isinstance(key_questions_raw, str):
            sanitized["key_questions"] = [key_questions_raw]
        elif isinstance(key_questions_raw, list):
            sanitized["key_questions"] = [str(q) for q in key_questions_raw if str(q).strip()]

        return sanitized

    @classmethod
    def parse_and_validate(
        cls,
        raw_text: str,
        response_schema: Type[T],
        raw_user_prompt: Optional[str] = None,
        user_constraints: Optional[List[str]] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> T:
        """Parses raw LLM text into JSON, sanitizes for schema conformance, and validates with Pydantic.

        Args:
            raw_text: Model text output.
            response_schema: Target Pydantic model class.
            raw_user_prompt: Optional user prompt for populating decision context.
            user_constraints: Optional explicit user constraints for epistemic tagging.
            user_context: Optional background dictionary of operational metrics.

        Returns:
            Instantiated, validated model of type T.

        Raises:
            LLMResponseValidationError: If parsing, extraction, or Pydantic validation fails.
        """
        # Step 1: Safely parse JSON
        parsed_json = cls.safe_parse_json(raw_text)

        if not isinstance(parsed_json, dict):
            raise LLMResponseValidationError(
                f"LLM output must be a JSON object, but got {type(parsed_json).__name__}.",
                details={"parsed_type": type(parsed_json).__name__},
            )

        # Step 2: Apply schema-specific sanitization if target is DecisionModel
        if issubclass(response_schema, DecisionModel):
            sanitized_data = cls.sanitize_decision_model_dict(
                parsed_json,
                raw_user_prompt=raw_user_prompt,
                user_constraints=user_constraints,
            )
        else:
            sanitized_data = parsed_json

        # Step 3: Validate against requested Pydantic schema
        try:
            validated = response_schema.model_validate(sanitized_data)
            if isinstance(validated, DecisionModel):
                from app.engines.provenance import audit_decision_provenance
                validated = audit_decision_provenance(
                    model=validated,
                    raw_prompt=raw_user_prompt or validated.decision.raw_prompt,
                    context=user_context,
                    constraints=user_constraints,
                )
            return validated
        except ValidationError as e:
            formatted_errors = []
            for err in e.errors():
                loc_str = " -> ".join(str(loc) for loc in err["loc"])
                formatted_errors.append(f"- {loc_str}: {err['msg']} (type: {err['type']})")

            error_summary = (
                f"Validation failed for schema {response_schema.__name__}:\n"
                + "\n".join(formatted_errors)
            )
            raise LLMResponseValidationError(
                error_summary,
                details={
                    "schema": response_schema.__name__,
                    "errors": e.errors(),
                    "sanitized_payload": sanitized_data,
                },
            ) from e


def parse_and_validate_structured_output(
    raw_text: str,
    response_schema: Type[T],
    raw_user_prompt: Optional[str] = None,
    user_constraints: Optional[List[str]] = None,
    user_context: Optional[Dict[str, Any]] = None,
) -> T:
    """Convenience function to parse and validate structured model output."""
    return StructuredOutputParser.parse_and_validate(
        raw_text=raw_text,
        response_schema=response_schema,
        raw_user_prompt=raw_user_prompt,
        user_constraints=user_constraints,
        user_context=user_context,
    )

