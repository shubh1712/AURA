"""Deterministic offline test suite for AURA Phase 4.17: Safe Decision Framer Output Optimization.

Validates:
1. System prompt contains refined bounded granularity, conciseness, and constraint preservation guidance.
2. Simple decision produces compact valid DecisionModel output.
3. Complex decision with more than two genuinely relevant variables is preserved without truncation.
4. Multiple explicit user constraints are all preserved as hard user-specified constraints.
5. Multiple distinct unknowns and empirical gaps are retained.
6. No unsupported numbers are introduced; ungrounded numbers are quarantined as UNKNOWN.
7. Stable entity IDs and tradeoff variable referential integrity are enforced.
8. Existing canonical DecisionModel validation invariants remain strictly unchanged.
9. Downstream Evidence Engine compatibility is 100% preserved.
"""

import json
from typing import Any, Dict, List
import pytest
from pydantic import ValidationError

from app.engines.question_understanding import QuestionUnderstandingEngine
from app.schemas.decision_model import (
    Assumption,
    Complexity,
    ComplexityLevel,
    ConfidenceLevel,
    Constraint,
    CriticalityLevel,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    ProvenanceType,
    ReversibilityLevel,
    Stakeholder,
    TimeHorizon,
    Tradeoff,
    Unknown,
    Variable,
    VariableType,
)
from app.schemas.evidence import DecisionEntityType
from app.services.evidence.requirements import EvidenceRequirementEngine
from app.services.llm.client import MockLLMClient
from app.services.llm.parser import StructuredOutputParser
from app.services.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
    build_decomposition_prompt,
)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _create_minimal_valid_decision_dict() -> Dict[str, Any]:
    """Creates a raw dict for a simple, compact decision."""
    return {
        "id": "dec_simple_01",
        "decision": {
            "raw_prompt": "Should we switch our caching layer from Redis to Dragonfly?",
            "summary": "Evaluate switching caching layer from Redis to Dragonfly to reduce memory costs.",
            "decision_type": "architecture_technology",
            "time_horizon": "short_term",
        },
        "complexity": {
            "level": "low",
            "reasoning": "Localized infrastructure change with straightforward fallback.",
            "reversibility": "reversible",
        },
        "objectives": [
            {
                "id": "obj_primary_mem",
                "description": "Reduce infrastructure memory consumption by 30%.",
                "is_primary": True,
                "target_metric": "-30% RAM",
                "provenance": "user_provided",
            }
        ],
        "variables": [
            {
                "id": "var_cache_engine",
                "name": "Cache Engine Choice",
                "description": "Selected caching technology.",
                "variable_type": "categorical",
                "baseline_value": "Redis",
                "proposed_value": "Dragonfly",
                "is_controllable": True,
                "provenance": "user_provided",
            }
        ],
        "constraints": [
            {
                "id": "cnstr_zero_downtime",
                "name": "Zero Downtime",
                "description": "Migration must incur zero API downtime.",
                "is_hard_constraint": True,
                "source": "user_specified",
                "provenance": "user_provided",
            }
        ],
        "stakeholders": [
            {
                "id": "stk_devops",
                "group": "Platform Engineering",
                "impact_nature": "Maintains and operates the cache cluster.",
                "influence_level": "high",
                "provenance": "inferred",
            }
        ],
        "tradeoffs": [
            {
                "id": "trd_efficiency_vs_maturity",
                "upside": "Lower memory footprint and multi-threaded throughput.",
                "downside": "Dragonfly has shorter production track record than Redis.",
                "affected_variable_ids": ["var_cache_engine"],
                "provenance": "inferred",
            }
        ],
        "assumptions": [
            {
                "id": "asm_compatibility",
                "statement": "Dragonfly maintains full wire compatibility with existing Redis clients.",
                "confidence": "high",
                "provenance": "inferred",
            }
        ],
        "unknowns": [
            {
                "id": "unk_edge_behavior",
                "question": "Does Dragonfly reproduce identical replication semantics under network partitions?",
                "criticality": "high",
                "potential_sources": ["Load testing benchmarks", "Documentation"],
                "provenance": "unknown",
            }
        ],
        "key_questions": [
            "Are all Redis commands used by our backend 100% compatible with Dragonfly?"
        ],
    }


# ------------------------------------------------------------------------------
# 1. System Prompt Guidance Semantics
# ------------------------------------------------------------------------------

def test_01_system_prompt_bounded_granularity_and_conciseness() -> None:
    """Verifies that DECOMPOSITION_SYSTEM_PROMPT reflects updated guidance."""
    prompt = DECOMPOSITION_SYSTEM_PROMPT

    # 1. Encourages concise descriptions without conversational filler
    assert "concise" in prompt.lower()
    assert "without conversational filler" in prompt.lower()

    # 2. Prefers high-impact, non-redundant entities
    assert "high-impact" in prompt.lower() or "high-priority" in prompt.lower()
    assert "nonredundant" in prompt.lower() or "non-redundant" in prompt.lower()

    # 3. Discourages duplicate or speculative items
    assert "duplicate or speculative" in prompt.lower()

    # 4. Preserves all materially distinct user-stated boundaries as hard constraints
    assert "all materially distinct user-stated boundaries must be preserved as hard constraints" in prompt.lower()

    # 5. Preserves decision-critical assumptions and unknowns
    assert "assumptions" in prompt.lower()
    assert "unknowns" in prompt.lower()

    # 6. Does NOT mandate a rigid hard cap; allows entities necessary for completeness
    assert "completeness" in prompt.lower()
    assert "typically 1–3" in prompt or "typically 1-3" in prompt


# ------------------------------------------------------------------------------
# 2. Simple Decision Compact Valid Output
# ------------------------------------------------------------------------------

def test_02_simple_decision_produces_compact_valid_model() -> None:
    """Verifies that a focused inquiry produces a compact, strictly valid DecisionModel."""
    raw_data = _create_minimal_valid_decision_dict()
    model = DecisionModel.model_validate(raw_data)

    mock_llm = MockLLMClient()
    mock_llm.register_response(DecisionModel, model)

    engine = QuestionUnderstandingEngine(llm_client=mock_llm)
    question = "Should we switch our caching layer from Redis to Dragonfly to reduce memory consumption by 30%?"
    result = engine.deconstruct(
        question=question,
        constraints=["Migration must incur zero API downtime."],
    )

    assert isinstance(result, DecisionModel)
    assert result.decision.decision_type == DecisionType.ARCHITECTURE_TECH
    assert len(result.objectives) == 1
    assert result.objectives[0].is_primary is True
    assert len(result.variables) == 1
    assert len(result.constraints) == 1
    assert result.constraints[0].is_hard_constraint is True
    assert len(result.tradeoffs) == 1
    assert len(result.unknowns) >= 1


    # Verify compact serialized output JSON
    compact_json = result.model_dump_json()
    assert len(compact_json) < 2500
    assert result.complexity.score is not None
    assert result.complexity.level in (ComplexityLevel.LOW, ComplexityLevel.MEDIUM)


# ------------------------------------------------------------------------------
# 3. Complex Decision with More Than Two Variables Preserved
# ------------------------------------------------------------------------------

def test_03_complex_decision_preserves_multiple_variables() -> None:
    """Proves that a complex decision with 4 genuinely distinct variables retains all 4."""
    raw_data = _create_minimal_valid_decision_dict()
    raw_data["variables"] = [
        {
            "id": "var_price_discount",
            "name": "Discount Rate",
            "description": "Percentage discount off standard SaaS tier.",
            "variable_type": "percentage",
            "proposed_value": 20.0,
            "unit": "%",
            "is_controllable": True,
            "provenance": "user_provided",
        },
        {
            "id": "var_sales_commission",
            "name": "Sales Rep Commission",
            "description": "Commission rate paid on closed annual contracts.",
            "variable_type": "percentage",
            "proposed_value": 12.0,
            "unit": "%",
            "is_controllable": True,
            "provenance": "inferred",
        },
        {
            "id": "var_marketing_cac",
            "name": "Paid Acquisition Spend",
            "description": "Monthly performance marketing budget.",
            "variable_type": "currency",
            "proposed_value": 50000,
            "unit": "USD",
            "is_controllable": True,
            "provenance": "inferred",
        },
        {
            "id": "var_gross_margin",
            "name": "Net Gross Margin",
            "description": "Gross margin percentage after hosting and support COGS.",
            "variable_type": "percentage",
            "proposed_value": 68.0,
            "unit": "%",
            "is_controllable": False,
            "provenance": "inferred",
        },
    ]
    # Update tradeoff to reference two of these variables
    raw_data["tradeoffs"][0]["affected_variable_ids"] = [
        "var_price_discount",
        "var_gross_margin",
    ]

    model = DecisionModel.model_validate(raw_data)
    assert len(model.variables) == 4
    var_ids = [v.id for v in model.variables]
    assert var_ids == [
        "var_price_discount",
        "var_sales_commission",
        "var_marketing_cac",
        "var_gross_margin",
    ]
    # Referential integrity holds
    assert model.tradeoffs[0].affected_variable_ids == [
        "var_price_discount",
        "var_gross_margin",
    ]


# ------------------------------------------------------------------------------
# 4. Multiple Explicit User Constraints All Preserved
# ------------------------------------------------------------------------------

def test_04_multiple_explicit_user_constraints_all_preserved() -> None:
    """Proves that multiple distinct user-stated constraints are all preserved as hard constraints."""
    raw_data = _create_minimal_valid_decision_dict()
    raw_data["constraints"] = [
        {
            "id": "cnstr_margin",
            "name": "Margin Floor",
            "description": "Gross margin must not fall below 65%.",
            "is_hard_constraint": True,
            "source": "user_specified",
            "provenance": "user_provided",
        },
        {
            "id": "cnstr_sla",
            "name": "SLA Floor",
            "description": "Enterprise uptime SLA must remain 99.99%.",
            "is_hard_constraint": True,
            "source": "user_specified",
            "provenance": "user_provided",
        },
        {
            "id": "cnstr_headcount",
            "name": "Zero Layoffs",
            "description": "No headcount reductions permitted during restructuring.",
            "is_hard_constraint": True,
            "source": "user_specified",
            "provenance": "user_provided",
        },
    ]

    user_constraints = [
        "Gross margin must not fall below 65%.",
        "Enterprise uptime SLA must remain 99.99%.",
        "No headcount reductions permitted during restructuring.",
    ]

    sanitized = StructuredOutputParser.sanitize_decision_model_dict(
        data=raw_data,
        raw_user_prompt="Evaluate cost restructuring",
        user_constraints=user_constraints,
    )
    validated = DecisionModel.model_validate(sanitized)

    assert len(validated.constraints) == 3
    for c in validated.constraints:
        assert c.is_hard_constraint is True
        assert c.source == "user_specified"
        assert c.provenance == ProvenanceType.USER_PROVIDED


# ------------------------------------------------------------------------------
# 5. Multiple Distinct Unknowns Retained
# ------------------------------------------------------------------------------

def test_05_multiple_distinct_unknowns_retained() -> None:
    """Proves that multiple critical information gaps are retained as distinct Unknowns."""
    raw_data = _create_minimal_valid_decision_dict()
    raw_data["unknowns"] = [
        {
            "id": "unk_competitor_reaction",
            "question": "How rapidly will incumbent competitors match a 20% price cut?",
            "criticality": "high",
            "potential_sources": ["Win/loss reports", "Competitor press releases"],
            "provenance": "unknown",
        },
        {
            "id": "unk_churn_elasticity",
            "question": "What is the measured price elasticity of our existing cohort churn?",
            "criticality": "high",
            "potential_sources": ["Historical cohort billing data"],
            "provenance": "unknown",
        },
        {
            "id": "unk_sales_cycle",
            "question": "Does lower pricing compress enterprise sales cycle duration?",
            "criticality": "medium",
            "potential_sources": ["CRM pipeline duration logs"],
            "provenance": "unknown",
        },
    ]

    model = DecisionModel.model_validate(raw_data)
    assert len(model.unknowns) == 3
    for unk in model.unknowns:
        assert unk.provenance == ProvenanceType.UNKNOWN
        assert unk.id.startswith("unk_")
        assert len(unk.potential_sources) > 0


# ------------------------------------------------------------------------------
# 6. No Unsupported Numbers Introduced (Epistemic Grounding)
# ------------------------------------------------------------------------------

def test_06_no_unsupported_numbers_introduced() -> None:
    """Proves that hallucinated numbers are purged and converted to Unknown gaps."""
    raw_data = _create_minimal_valid_decision_dict()
    # Model generates a variable with an ungrounded baseline value of 95000 USD
    raw_data["variables"][0]["baseline_value"] = 95000
    raw_data["variables"][0]["baseline_provenance"] = "inferred"

    question = "Should we switch our caching layer from Redis to Dragonfly?"
    parsed = StructuredOutputParser.parse_and_validate(
        raw_text=json.dumps(raw_data),
        response_schema=DecisionModel,
        raw_user_prompt=question,
    )

    # The 95000 number was NOT in the user prompt -> must be purged from variable
    var = parsed.variables[0]
    assert var.baseline_value is None
    assert var.baseline_provenance == ProvenanceType.UNKNOWN

    # A corresponding Unknown should have been quarantined for the missing empirical baseline
    quarantined_unknowns = [
        u for u in parsed.unknowns if "Cache Engine Choice" in u.question or "baseline value" in u.question
    ]
    assert len(quarantined_unknowns) >= 1


# ------------------------------------------------------------------------------
# 7. Stable IDs and Tradeoff Referential Integrity
# ------------------------------------------------------------------------------

def test_07_stable_ids_and_tradeoff_references() -> None:
    """Proves referential integrity and safe pruning of phantom tradeoff variable IDs."""
    raw_data = _create_minimal_valid_decision_dict()
    # Insert phantom variable reference in tradeoff
    raw_data["tradeoffs"][0]["affected_variable_ids"] = [
        "var_cache_engine",
        "var_phantom_nonexistent",
    ]

    sanitized = StructuredOutputParser.sanitize_decision_model_dict(raw_data)
    validated = DecisionModel.model_validate(sanitized)

    # Phantom ID is stripped by sanitization; valid ID is preserved
    assert validated.tradeoffs[0].affected_variable_ids == ["var_cache_engine"]


# ------------------------------------------------------------------------------
# 8. Existing DecisionModel Validation Unchanged
# ------------------------------------------------------------------------------

def test_08_existing_decision_model_validation_unchanged() -> None:
    """Verifies that canonical schema validators remain strict and fail-closed."""
    raw_data = _create_minimal_valid_decision_dict()

    # Invariant 1: Missing primary objective raises ValueError
    raw_data_no_primary = dict(raw_data)
    raw_data_no_primary["objectives"] = [
        {
            "id": "obj_sec",
            "description": "Secondary goal",
            "is_primary": False,
        }
    ]
    with pytest.raises(ValidationError, match="at least one primary objective"):
        DecisionModel.model_validate(raw_data_no_primary)

    # Invariant 2: Duplicate IDs in a collection raise ValueError
    raw_data_dupe = dict(raw_data)
    raw_data_dupe["objectives"] = [
        {"id": "obj_1", "description": "Goal 1", "is_primary": True},
        {"id": "obj_1", "description": "Goal 2", "is_primary": False},
    ]
    with pytest.raises(ValidationError, match="Duplicate ID 'obj_1'"):
        DecisionModel.model_validate(raw_data_dupe)

    # Invariant 3: Empty variables list raises ValidationError
    raw_data_empty_vars = dict(raw_data)
    raw_data_empty_vars["variables"] = []
    with pytest.raises(ValidationError):
        DecisionModel.model_validate(raw_data_empty_vars)


# ------------------------------------------------------------------------------
# 9. Downstream Evidence Engine Compatibility
# ------------------------------------------------------------------------------

def test_09_downstream_evidence_engine_compatibility() -> None:
    """Proves that both compact and multi-variable DecisionModels integrate seamlessly with Stage 2."""
    from app.services.evidence.requirements import (
        CandidateEvidenceRequirement,
        CandidateRequirementsPayload,
    )
    from app.schemas.evidence import DecisionEntityType, EvidenceKind

    raw_data = _create_minimal_valid_decision_dict()
    compact_model = DecisionModel.model_validate(raw_data)

    mock_llm = MockLLMClient()
    mock_payload = CandidateRequirementsPayload(
        requirements=[
            CandidateEvidenceRequirement(
                target_entity_id="var_cache_engine",
                target_entity_type=DecisionEntityType.VARIABLE,
                kind=EvidenceKind.EXTERNAL_RESEARCH,
                description="Benchmark comparison of Dragonfly vs Redis memory usage.",
                priority=CriticalityLevel.HIGH,
                suggested_queries=["Dragonfly vs Redis memory footprint"],
            )
        ]
    )
    mock_llm.register_response(CandidateRequirementsPayload, mock_payload)

    engine = EvidenceRequirementEngine(llm_client=mock_llm)
    compact_reqs = engine.generate_requirements(compact_model)

    assert len(compact_reqs) == 1
    assert compact_reqs[0].target_entity_id == "var_cache_engine"
    assert compact_reqs[0].target_entity_type == DecisionEntityType.VARIABLE

    # Test with multi-variable model
    raw_data["variables"].append({
        "id": "var_backup_schedule",
        "name": "Snapshot Interval",
        "description": "Interval for Redis RDB snapshots.",
        "variable_type": "numeric",
        "proposed_value": 300,
        "unit": "s",
        "is_controllable": True,
        "provenance": "inferred",
    })
    multi_model = DecisionModel.model_validate(raw_data)
    multi_payload = CandidateRequirementsPayload(
        requirements=[
            CandidateEvidenceRequirement(
                target_entity_id="var_cache_engine",
                target_entity_type=DecisionEntityType.VARIABLE,
                kind=EvidenceKind.EXTERNAL_RESEARCH,
                description="Benchmark comparison of Dragonfly vs Redis memory usage.",
                priority=CriticalityLevel.HIGH,
                suggested_queries=["Dragonfly vs Redis memory footprint"],
            ),
            CandidateEvidenceRequirement(
                target_entity_id="var_backup_schedule",
                target_entity_type=DecisionEntityType.VARIABLE,
                kind=EvidenceKind.INTERNAL_DATA,
                description="Production snapshot frequency telemetry.",
                priority=CriticalityLevel.MEDIUM,
                suggested_queries=[],
            ),
        ]
    )
    mock_llm.register_response(CandidateRequirementsPayload, multi_payload)
    multi_reqs = engine.generate_requirements(multi_model)
    assert len(multi_reqs) == 2
    req_targets = {r.target_entity_id for r in multi_reqs}
    assert req_targets == {"var_cache_engine", "var_backup_schedule"}

