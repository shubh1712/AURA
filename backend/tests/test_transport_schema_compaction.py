"""Deterministic offline test suite for AURA Phase 4.18: Safe Transport Schema Description Compaction.

Validates:
1. All original required fields are retained across root and $defs.
2. All enum values across the 8 domain enums are retained.
3. All schema $ref definitions and references remain valid and resolvable.
4. All nested types, properties, and validation constraints are structurally identical.
5. Essential epistemic descriptions (provenance, hard/soft constraints, units, tradeoffs) are retained.
6. DecisionModel.model_json_schema() is never mutated by transport cleaning.
7. Other response schemas (Evidence, Reasoning, test schemas) remain completely untouched.
8. Concurrent multi-threaded schema preparation is deterministic and thread-safe.
9. Fake/mock GeminiLLMClient structured generation operates seamlessly with compacted schema.
10. Invalid model responses continue to fail closed with strict typed validation.
"""

import copy
import json
import threading
from typing import Any, Dict, List, Set
import httpx
import pytest
from pydantic import BaseModel

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidenceRequirement
from app.services.evidence.requirements import CandidateRequirementsPayload
from app.services.llm.client import LLMResponseValidationError
from app.services.llm.gemini import GeminiLLMClient
from app.services.llm.mock_data import get_default_decision_model
from app.services.llm.transport_schema import (
    DECISION_MODEL_COMPACT_DESCRIPTIONS,
    IMMUTABLE_DESCRIPTIONS,
    compact_decision_model_schema_for_transport,
)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _strip_descriptions(schema: Any) -> Any:
    """Recursively removes 'description' keys to isolate structural schema properties."""
    if isinstance(schema, dict):
        return {
            k: _strip_descriptions(v)
            for k, v in schema.items()
            if k != "description"
        }
    if isinstance(schema, list):
        return [_strip_descriptions(item) for item in schema]
    return schema


def _extract_all_required(schema: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extracts required field lists keyed by subschema path."""
    req_map: Dict[str, List[str]] = {}
    if "required" in schema and isinstance(schema["required"], list):
        req_map["root"] = list(schema["required"])
    for def_name, def_schema in schema.get("$defs", {}).items():
        if isinstance(def_schema, dict) and "required" in def_schema:
            req_map[def_name] = list(def_schema["required"])
    return req_map


# ------------------------------------------------------------------------------
# 1. Required Fields Retained
# ------------------------------------------------------------------------------

def test_01_all_original_required_fields_retained() -> None:
    """Proves that every required field in DecisionModel root and $defs is strictly retained."""
    raw = DecisionModel.model_json_schema()
    cleaned_orig = GeminiLLMClient._clean_schema_for_transport(raw)
    compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)

    req_orig = _extract_all_required(cleaned_orig)
    req_compacted = _extract_all_required(compacted)

    assert req_orig == req_compacted
    # Verify canonical root required fields are intact
    assert set(req_compacted["root"]) == {
        "id",
        "decision",
        "complexity",
        "objectives",
        "variables",
        "tradeoffs",
        "key_questions",
    }


# ------------------------------------------------------------------------------
# 2. Enum Values Retained
# ------------------------------------------------------------------------------

def test_02_all_enum_values_retained() -> None:
    """Proves that all 8 domain enum definition values remain identical."""
    raw = DecisionModel.model_json_schema()
    cleaned_orig = GeminiLLMClient._clean_schema_for_transport(raw)
    compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)

    defs_orig = cleaned_orig.get("$defs", {})
    defs_compacted = compacted.get("$defs", {})

    enum_names = [
        "ComplexityLevel",
        "ConfidenceLevel",
        "CriticalityLevel",
        "DecisionType",
        "ProvenanceType",
        "ReversibilityLevel",
        "TimeHorizon",
        "VariableType",
    ]

    for en in enum_names:
        assert en in defs_compacted, f"Enum {en} missing from compacted schema"
        orig_enum_vals = defs_orig[en].get("enum")
        comp_enum_vals = defs_compacted[en].get("enum")
        assert orig_enum_vals is not None
        assert orig_enum_vals == comp_enum_vals


# ------------------------------------------------------------------------------
# 3. References and Definitions Valid
# ------------------------------------------------------------------------------

def test_03_all_references_valid() -> None:
    """Proves that all $ref pointers in the compacted schema resolve to valid $defs."""
    raw = DecisionModel.model_json_schema()
    compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)

    defs = compacted.get("$defs", {})
    ref_targets: Set[str] = set()

    def collect_refs(d: Any) -> None:
        if isinstance(d, dict):
            if "$ref" in d and isinstance(d["$ref"], str):
                ref_targets.add(d["$ref"])
            for v in d.values():
                collect_refs(v)
        elif isinstance(d, list):
            for item in d:
                collect_refs(item)

    collect_refs(compacted)
    assert len(ref_targets) > 0

    prefix = "#/$defs/"
    for ref in ref_targets:
        assert ref.startswith(prefix), f"Unexpected ref format: {ref}"
        def_key = ref[len(prefix):]
        assert def_key in defs, f"Dangling reference: {ref} target not found in $defs"


# ------------------------------------------------------------------------------
# 4. Structural Non-Description Equivalence
# ------------------------------------------------------------------------------

def test_04_all_nested_types_and_constraints_retained() -> None:
    """Proves that all non-description attributes (types, constraints, properties) are 100% identical."""
    raw = DecisionModel.model_json_schema()
    cleaned_orig = GeminiLLMClient._clean_schema_for_transport(raw)
    compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)

    stripped_orig = _strip_descriptions(cleaned_orig)
    stripped_compacted = _strip_descriptions(compacted)

    assert stripped_orig == stripped_compacted


# ------------------------------------------------------------------------------
# 5. Essential Epistemic Descriptions Retained
# ------------------------------------------------------------------------------

def test_05_essential_epistemic_descriptions_retained() -> None:
    """Proves that essential semantic guidance is preserved across epistemic boundaries."""
    raw = DecisionModel.model_json_schema()
    compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)
    defs = compacted["$defs"]

    # 1. Epistemic provenance distinctions
    prov_desc = defs["Objective"]["properties"]["provenance"]["description"]
    assert "user_provided" in prov_desc and "inferred" in prov_desc and "unknown" in prov_desc

    # 2. Hard vs soft constraints
    hard_cnstr_desc = defs["Constraint"]["properties"]["is_hard_constraint"]["description"]
    assert "hard boundary" in hard_cnstr_desc.lower() and "soft" in hard_cnstr_desc.lower()

    # 3. Source attribution origin
    source_desc = defs["Constraint"]["properties"]["source"]["description"]
    assert "user_specified" in source_desc and "inferred_operational" in source_desc

    # 4. Variable units
    unit_desc = defs["Variable"]["properties"]["unit"]["description"]
    assert "unit symbol" in unit_desc.lower()

    # 5. Tradeoff relationships
    trd_vars_desc = defs["Tradeoff"]["properties"]["affected_variable_ids"]["description"]
    assert "variables" in trd_vars_desc.lower()

    # 6. Assumptions and Unknowns
    asm_desc = defs["Assumption"]["description"]
    assert "unverified" in asm_desc.lower()
    unk_desc = defs["Unknown"]["description"]
    assert "empirical gap" in unk_desc.lower() or "investigation" in unk_desc.lower()


# ------------------------------------------------------------------------------
# 6. No Mutation of Underlying Pydantic Schema
# ------------------------------------------------------------------------------

def test_06_no_mutation_of_decision_model_json_schema() -> None:
    """Proves that DecisionModel.model_json_schema() is never mutated."""
    baseline_schema = DecisionModel.model_json_schema()
    baseline_json = json.dumps(baseline_schema, sort_keys=True)

    # Perform multiple compaction runs
    for _ in range(5):
        raw = DecisionModel.model_json_schema()
        _ = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)

    current_schema = DecisionModel.model_json_schema()
    current_json = json.dumps(current_schema, sort_keys=True)

    assert baseline_json == current_json


# ------------------------------------------------------------------------------
# 7. Other Response Schemas Unchanged
# ------------------------------------------------------------------------------

def test_07_other_response_schemas_unchanged() -> None:
    """Proves that non-DecisionModel schemas undergo standard title stripping with zero description compaction."""
    raw_ev = EvidenceRequirement.model_json_schema()
    clean_ev_no_cls = GeminiLLMClient._clean_schema_for_transport(raw_ev)
    clean_ev_with_cls = GeminiLLMClient._clean_schema_for_transport(raw_ev, response_schema=EvidenceRequirement)

    assert clean_ev_no_cls == clean_ev_with_cls

    raw_reqs = CandidateRequirementsPayload.model_json_schema()
    clean_reqs_no_cls = GeminiLLMClient._clean_schema_for_transport(raw_reqs)
    clean_reqs_with_cls = GeminiLLMClient._clean_schema_for_transport(raw_reqs, response_schema=CandidateRequirementsPayload)

    assert clean_reqs_no_cls == clean_reqs_with_cls


# ------------------------------------------------------------------------------
# 8. Concurrent Schema Preparation Safe
# ------------------------------------------------------------------------------

def test_08_concurrent_schema_preparation_safe() -> None:
    """Proves that concurrent threads calling schema preparation produce deterministic equivalent outputs."""
    raw = DecisionModel.model_json_schema()
    results: List[str] = []
    errors: List[Exception] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            compacted = GeminiLLMClient._clean_schema_for_transport(raw, response_schema=DecisionModel)
            serialized = json.dumps(compacted, sort_keys=True)
            with lock:
                results.append(serialized)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 10
    # Every thread produced the exact same serialized schema
    first = results[0]
    for r in results[1:]:
        assert r == first


# ------------------------------------------------------------------------------
# 9. Fake Gemini Structured Generation Compatible
# ------------------------------------------------------------------------------

def test_09_fake_gemini_calls_remain_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves that GeminiLLMClient.generate_structured operates seamlessly with compacted schema."""
    monkeypatch.setenv("AURA_LLM_DIAGNOSTICS", "1")
    sample_model = get_default_decision_model()
    canned_json = sample_model.model_dump_json()

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"output_text": canned_json})
    )
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )

    result = client.generate_structured(
        prompt="Analyze decision problem",
        response_schema=DecisionModel,
    )

    assert isinstance(result, DecisionModel)
    assert result.decision.summary == sample_model.decision.summary

    diag = client.last_diagnostic
    assert diag is not None
    # Telemetry records compacted schema length (~10,567 chars)
    assert diag["schema_chars"] < 11000
    assert diag["schema_chars"] > 10000


# ------------------------------------------------------------------------------
# 10. Invalid Responses Still Fail Closed
# ------------------------------------------------------------------------------

def test_10_invalid_decision_model_responses_still_fail_closed() -> None:
    """Proves that malformed or incomplete outputs fail closed with strict validation error."""
    # Omit required 'decision' and 'objectives'
    invalid_json = '{"id": "dec_broken", "variables": []}'

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"output_text": invalid_json})
    )
    client = GeminiLLMClient(
        project="aura-test-project",
        location="global",
        http_client=httpx.Client(transport=mock_transport),
    )

    with pytest.raises(LLMResponseValidationError):
        client.generate_structured(
            prompt="Analyze decision problem",
            response_schema=DecisionModel,
        )
