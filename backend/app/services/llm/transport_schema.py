"""AURA Transport Schema Optimization.

Provides narrow, DecisionModel-specific description compaction for structured-output
wire schemas transmitted to Google Gemini. Preserves all field names, types, required
properties, enums, array structures, references, and validation constraints while
reducing wire schema size by eliminating verbose narrative descriptions.
"""

from typing import Any, Dict
from types import MappingProxyType


DECISION_MODEL_COMPACT_DESCRIPTIONS: Dict[str, str] = {
    "": "Decomposed decision problem model.",
    "properties.id": "Unique model identifier.",
    "properties.decision": "Core decision details.",
    "properties.complexity": "Complexity and reversibility.",
    "properties.objectives": "Target goals with at least one primary objective.",
    "properties.variables": "Key levers and governing factors.",
    "properties.constraints": "Hard boundaries and soft limits.",
    "properties.stakeholders": "Affected groups and roles.",
    "properties.tradeoffs": "Core trade-offs between alternatives.",
    "properties.assumptions": "Unverified premises held.",
    "properties.unknowns": "Empirical gaps requiring investigation.",
    "properties.key_questions": "Sub-questions needed for resolution.",

    "$defs.Decision": "Core decision details.",
    "$defs.Decision.properties.raw_prompt": "Verbatim user inquiry prompt.",
    "$defs.Decision.properties.summary": "Unambiguous central decision focus.",
    "$defs.Decision.properties.decision_type": "Domain decision categorization.",
    "$defs.Decision.properties.time_horizon": "Operational timeframe of consequences.",

    "$defs.Complexity": "Structural difficulty assessment.",
    "$defs.Complexity.properties.level": "Complexity level assessment.",
    "$defs.Complexity.properties.reasoning": "Rationale for complexity rating.",
    "$defs.Complexity.properties.reversibility": "Ease and cost of unwinding (reversibility door).",
    "$defs.Complexity.properties.score": "Deterministic complexity score (0.0-100.0).",

    "$defs.Objective": "Target goal or desired outcome.",
    "$defs.Objective.properties.id": "Unique objective identifier.",
    "$defs.Objective.properties.description": "Objective statement and definition.",
    "$defs.Objective.properties.is_primary": "True if primary foundational goal; False if secondary.",
    "$defs.Objective.properties.target_metric": "Quantifiable success target metric if known.",
    "$defs.Objective.properties.provenance": "Epistemic origin (user_provided/inferred/unknown).",

    "$defs.Variable": "Governing decision parameter or lever.",
    "$defs.Variable.properties.id": "Unique variable identifier.",
    "$defs.Variable.properties.name": "Short variable label.",
    "$defs.Variable.properties.description": "Role of variable in decision context.",
    "$defs.Variable.properties.variable_type": "Variable data type class.",
    "$defs.Variable.properties.baseline_value": "Status-quo baseline value if known.",
    "$defs.Variable.properties.proposed_value": "Candidate value considered.",
    "$defs.Variable.properties.unit": "Unit symbol only (e.g. %, USD, ms).",
    "$defs.Variable.properties.is_controllable": "True if internal controllable lever; False if external factor.",
    "$defs.Variable.properties.provenance": "Epistemic origin (user_provided/inferred/unknown).",
    "$defs.Variable.properties.baseline_provenance": "Provenance of baseline (user/inferred/unk).",
    "$defs.Variable.properties.proposed_provenance": "Provenance of proposed (user/inferred/unk).",

    "$defs.Constraint": "Boundary or threshold options must satisfy.",
    "$defs.Constraint.properties.id": "Unique constraint identifier.",
    "$defs.Constraint.properties.name": "Short constraint label.",
    "$defs.Constraint.properties.description": "Constraint condition statement.",
    "$defs.Constraint.properties.is_hard_constraint": "True if non-negotiable hard boundary; False if soft limit.",
    "$defs.Constraint.properties.threshold_expression": "Mathematical bound expression (e.g. margin >= 0.65).",
    "$defs.Constraint.properties.source": "Constraint origin: user_specified/inferred_operational/reg.",
    "$defs.Constraint.properties.provenance": "Epistemic origin (user_provided/inferred/unknown).",

    "$defs.Stakeholder": "Party or role affected by decision.",
    "$defs.Stakeholder.properties.id": "Unique stakeholder identifier.",
    "$defs.Stakeholder.properties.group": "Stakeholder group or role name.",
    "$defs.Stakeholder.properties.impact_nature": "Nature of impact on group.",
    "$defs.Stakeholder.properties.influence_level": "Stakeholder decision influence level.",
    "$defs.Stakeholder.properties.provenance": "Epistemic origin (user_provided/inferred/unknown).",

    "$defs.Tradeoff": "Tension between competing advantages.",
    "$defs.Tradeoff.properties.id": "Unique tradeoff identifier.",
    "$defs.Tradeoff.properties.upside": "Gain or advantage of alternative.",
    "$defs.Tradeoff.properties.downside": "Sacrifice or risk of alternative.",
    "$defs.Tradeoff.properties.affected_variable_ids": "IDs of declared Variables involved in tension.",
    "$defs.Tradeoff.properties.provenance": "Epistemic origin (user_provided/inferred/unknown).",

    "$defs.Unknown": "Critical empirical gap to resolve.",
    "$defs.Unknown.properties.id": "Unique unknown identifier.",
    "$defs.Unknown.properties.question": "Empirical question needing inquiry.",
    "$defs.Unknown.properties.criticality": "Criticality of resolving gap early.",
    "$defs.Unknown.properties.potential_sources": "Evidence or data sources to consult.",
    "$defs.Unknown.properties.provenance": "Epistemic origin (always unknown for gaps).",

    "$defs.Assumption": "Unverified belief held as true.",
    "$defs.Assumption.properties.id": "Unique assumption identifier.",
    "$defs.Assumption.properties.statement": "The assumed premise.",
    "$defs.Assumption.properties.confidence": "Confidence level in this premise.",
    "$defs.Assumption.properties.falsification_condition": "Metric or event proving premise false if known.",
    "$defs.Assumption.properties.provenance": "Epistemic origin (unverified, always inferred).",

    "$defs.ComplexityLevel": "Overall decision complexity.",
    "$defs.ConfidenceLevel": "Empirical certainty in assumption.",
    "$defs.CriticalityLevel": "Importance or severity classification.",
    "$defs.DecisionType": "Categorical decision domain.",
    "$defs.ProvenanceType": "Epistemic origin classification of facts.",
    "$defs.ReversibilityLevel": "Ease and cost of unwinding decision.",
    "$defs.TimeHorizon": "Timeframe over which consequences occur.",
    "$defs.VariableType": "Data type for decision parameter.",
}

# Immutable mapping proxy to guarantee thread safety and prevent runtime mutations
IMMUTABLE_DESCRIPTIONS: MappingProxyType = MappingProxyType(DECISION_MODEL_COMPACT_DESCRIPTIONS)


def compact_decision_model_schema_for_transport(schema: Any, path: str = "") -> Any:
    """Recursively produces a compacted copy of DecisionModel JSON schema.

    Replaces verbose descriptions with concise equivalents from the registered override map.
    Guarantees that input schema is never mutated and that non-description properties remain
    structurally identical.
    """
    if isinstance(schema, dict):
        res: Dict[str, Any] = {}
        for k, v in schema.items():
            subpath = f"{path}.{k}" if path else k
            res[k] = compact_decision_model_schema_for_transport(v, subpath)
        if path in IMMUTABLE_DESCRIPTIONS and "description" in res:
            res["description"] = IMMUTABLE_DESCRIPTIONS[path]
        return res
    elif isinstance(schema, list):
        return [
            compact_decision_model_schema_for_transport(item, f"{path}[{idx}]")
            for idx, item in enumerate(schema)
        ]
    return schema
