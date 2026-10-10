"""Unit and regression tests for Boardroom Perspective Schema Validation and Timeout Recovery.

Verifies:
1. Exact reproduction of live failure: CandidatePerspectiveAnalysis with uncited basis='evidence'
   at arguments.0 and arguments.3 fails Pydantic validation with value_error.
2. StructuredOutputParser.sanitize_perspective_analysis_dict deterministically reconciles uncited
   arguments to basis='inference' without dropping arguments or fabricating fake IDs.
3. Enhanced diagnostics report specific error_types ('value_error') and nested field_paths
   ('arguments.0.evidence_item_ids') without leaking prompts, raw model responses, credentials, or customer data.
4. Genuinely invalid arguments (e.g. empty claims, invalid directions) strictly fail validation.
5. Perspective prompt builder explicitly instructs the LLM on basis enum values and ID dependencies.
6. Boardroom perspective evaluation and synthesis succeed deterministically with reconciled arguments
   on attempt 1, avoiding retry timeout.
"""

import json
import pytest
from pydantic import ValidationError

from datetime import datetime, timezone

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
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGap,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import (
    BoardSynthesis,
    CandidatePerspectiveAnalysis,
    CandidateReasoningArgument,
    PerspectiveType,
    ReasoningBasis,
    ReasoningBoard,
    ArgumentDirection,
    ReasoningPerspective,
    validate_reasoning_references,
)
from app.services.llm.client import FakeLLMClient
from app.services.llm.parser import (
    LLMResponseValidationError,
    StructuredOutputParser,
    parse_and_validate_structured_output,
)
from app.services.reasoning.context_builder import (
    PerspectiveContext,
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.orchestrator import CANONICAL_PERSPECTIVES
from app.services.reasoning.prompt_builder import build_perspective_prompt
from app.services.reasoning.service import ReasoningService
from app.services.reasoning.validator import (
    ReasoningValidationError,
    validate_and_reconcile_candidate_perspective,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _create_minimal_decision_model() -> DecisionModel:
    return DecisionModel(
        id="dm_test_001",
        decision=Decision(
            raw_prompt="Should we enter the enterprise SaaS market?",
            summary="Evaluate enterprise market entry.",
            decision_type=DecisionType.RESOURCE_ALLOCATION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="High uncertainty regarding sales cycle and churn.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_1",
                description="Maximize ARR growth",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        variables=[
            Variable(
                id="var_1",
                name="Pricing",
                description="Annual contract value",
                variable_type=VariableType.CURRENCY,
                baseline_value=10000.0,
                proposed_value=25000.0,
                unit="USD",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        constraints=[
            Constraint(
                id="con_1",
                name="Gross Margin",
                description="Maintain 80% gross margins",
                is_hard_constraint=True,
                threshold_expression="margin >= 0.8",
                source="policy",
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        stakeholders=[
            Stakeholder(
                id="stk_1",
                group="Executive Leadership",
                impact_nature="Cash flow impact",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_1",
                upside="High ARR per logo",
                downside="Higher sales friction",
                affected_variable_ids=["var_1"],
                provenance=ProvenanceType.INFERRED,
            )
        ],
        assumptions=[
            Assumption(
                id="asm_1",
                statement="Churn remains below 5%",
                confidence=ConfidenceLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        unknowns=[
            Unknown(
                id="unk_1",
                question="Enterprise sales cycle length",
                criticality=CriticalityLevel.HIGH,
                provenance=ProvenanceType.UNKNOWN,
            )
        ],
        key_questions=["What is the average enterprise sales cycle?"],
    )


def _create_minimal_evidence_package() -> EvidencePackage:
    src = Source(
        id="src_1",
        title="2026 SaaS Benchmarks",
        publisher="Gartner",
        source_type=SourceType.INDUSTRY_REPORT,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    evi_1 = EvidenceItem(
        id="evi_1",
        source_id="src_1",
        content="Enterprise sales cycles average 6 months.",
        summary="Sales cycle average: 6 months",
        numeric_data=[NumericEvidence(metric_name="cycle_months", value=6.0, unit="months")],
        extraction_confidence=ConfidenceLevel.HIGH,
        retrieval_timestamp=datetime(2026, 10, 1, 10, 5, 0, tzinfo=timezone.utc),
    )
    req_1 = EvidenceRequirement(
        id="req_1",
        target_entity_id="unk_1",
        target_entity_type=DecisionEntityType.UNKNOWN,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Determine average enterprise sales cycle duration",
        status=RequirementStatus.FULFILLED,
        linked_evidence_ids=["evi_1"],
    )
    lnk_1 = ClaimEvidenceLink(
        id="lnk_1",
        evidence_item_id="evi_1",
        target_entity_id="unk_1",
        target_entity_type=DecisionEntityType.UNKNOWN,
        stance=EvidenceStance.SUPPORTS,
        reasoning="Benchmarking data confirms enterprise sales cycles average 6 months.",
        relationship_confidence=ConfidenceLevel.HIGH,
        requirement_id="req_1",
    )
    return EvidencePackage(
        id="evp_test_001",
        decision_model_id="dm_test_001",
        summary="Enterprise sales cycle research package.",
        sources=[src],
        items=[evi_1],
        claim_links=[lnk_1],
        requirements=[req_1],
        gaps=[],
        generated_at=datetime(2026, 10, 1, 10, 10, 0, tzinfo=timezone.utc),
    )


def _create_live_failure_payload() -> str:
    """Raw JSON payload reproducing the exact live failure pattern observed in Day 5 Phase 4D.

    arguments.0 and arguments.3 have basis='evidence' but evidence_item_ids=[]
    because Gemini followed prompt instruction 'provide an empty array []' when no specific evidence applied.
    """
    data = {
        "perspective_type": "growth",
        "summary": "Executive growth evaluation indicating substantial potential ARR expansion.",
        "arguments": [
            {
                "id": "arg_0",
                "claim": "Market demand for enterprise tier is expanding rapidly.",
                "direction": "favorable",
                "basis": "evidence",
                "reasoning": "Macro industry dynamics show enterprise SaaS spend increasing by 18% YoY.",
                "evidence_item_ids": [],
                "requirement_ids": [],
                "assumption_ids": [],
                "unknown_ids": [],
                "evidence_gap_ids": [],
                "related_entity_ids": ["obj_1"],
                "caveat": "none",
            },
            {
                "id": "arg_1",
                "claim": "Sales cycle duration may delay near-term revenue recognition.",
                "direction": "unfavorable",
                "basis": "evidence",
                "reasoning": "Benchmarking data confirms enterprise sales cycles average 6 months.",
                "evidence_item_ids": ["evi_1"],
                "requirement_ids": ["req_1"],
                "assumption_ids": [],
                "unknown_ids": [],
                "evidence_gap_ids": [],
                "related_entity_ids": ["unk_1"],
                "caveat": "null",
            },
            {
                "id": "arg_2",
                "claim": "Low churn assumption is vital for lifetime value realization.",
                "direction": "neutral",
                "basis": "assumption",
                "reasoning": "Models rely on churn remaining below 5%.",
                "evidence_item_ids": [],
                "requirement_ids": [],
                "assumption_ids": ["asm_1"],
                "unknown_ids": [],
                "evidence_gap_ids": [],
                "related_entity_ids": ["asm_1"],
                "caveat": None,
            },
            {
                "id": "arg_3",
                "claim": "Direct sales expansion unlocks strategic partner distribution.",
                "direction": "favorable",
                "basis": "evidence",
                "reasoning": "Enterprise tier allows reseller agreements and channel partnerships.",
                "evidence_item_ids": [],
                "requirement_ids": [],
                "assumption_ids": [],
                "unknown_ids": [],
                "evidence_gap_ids": [],
                "related_entity_ids": ["obj_1"],
                "caveat": "N/A",
            },
        ],
        "critical_assumption_ids": ["asm_1"],
        "evidence_gap_ids": [],
        "opportunities": ["Capture early market share in enterprise segment"],
        "key_vulnerabilities": ["Extended sales runway"],
    }
    return json.dumps(data)


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------

def test_01_exact_live_failure_reproduction_in_raw_pydantic():
    """Confirms the exact Pydantic validation failure on raw un-sanitized payload at arguments.0 and arguments.3."""
    raw_dict = json.loads(_create_live_failure_payload())

    with pytest.raises(ValidationError) as exc_info:
        CandidatePerspectiveAnalysis.model_validate(raw_dict)

    errs = exc_info.value.errors()
    assert len(errs) == 2

    # Verify failing locations
    locs = [e["loc"] for e in errs]
    assert ("arguments", 0) in locs
    assert ("arguments", 3) in locs

    # Verify error types and messages
    for e in errs:
        assert e["type"] == "value_error"
        assert "Candidate argument with basis 'evidence' must reference at least one evidence_item_id." in e["msg"]


def test_02_structured_output_parser_sanitizes_uncited_arguments_to_inference():
    """Proves StructuredOutputParser safely reconciles uncited basis='evidence' to 'inference' without losing arguments or data."""
    raw_json = _create_live_failure_payload()

    parsed = parse_and_validate_structured_output(
        raw_text=raw_json,
        response_schema=CandidatePerspectiveAnalysis,
        raw_user_prompt="Evaluate growth perspective",
    )

    assert isinstance(parsed, CandidatePerspectiveAnalysis)
    assert parsed.perspective_type == PerspectiveType.GROWTH
    assert len(parsed.arguments) == 4

    # arguments.0 was reconciled from 'evidence' to 'inference'
    arg0 = parsed.arguments[0]
    assert "Market demand" in arg0.claim
    assert arg0.basis == ReasoningBasis.INFERENCE
    assert arg0.direction == ArgumentDirection.FAVORABLE
    assert arg0.evidence_item_ids == []
    assert arg0.caveat is None  # string 'none' normalized to None

    # arguments.1 had valid evidence_item_ids ['evi_1'], remained 'evidence'
    arg1 = parsed.arguments[1]
    assert "Sales cycle duration" in arg1.claim
    assert arg1.basis == ReasoningBasis.EVIDENCE
    assert arg1.evidence_item_ids == ["evi_1"]

    # arguments.2 had assumption_ids ['asm_1'], remained 'assumption'
    arg2 = parsed.arguments[2]
    assert "Low churn assumption" in arg2.claim
    assert arg2.basis == ReasoningBasis.ASSUMPTION
    assert arg2.assumption_ids == ["asm_1"]

    # arguments.3 was reconciled from 'evidence' to 'inference'
    arg3 = parsed.arguments[3]
    assert "Direct sales expansion" in arg3.claim
    assert arg3.basis == ReasoningBasis.INFERENCE
    assert arg3.direction == ArgumentDirection.FAVORABLE
    assert arg3.evidence_item_ids == []
    assert arg3.caveat is None  # string 'N/A' normalized to None


def test_03_enhanced_diagnostics_report_specific_error_types_and_nested_field_paths():
    """Proves classify_validation_error produces precise nested paths and error_types without raw text leaks."""
    raw_dict = json.loads(_create_live_failure_payload())

    try:
        CandidatePerspectiveAnalysis.model_validate(raw_dict)
        pytest.fail("Expected ValidationError")
    except ValidationError as val_err:
        primary_cat, all_cats, field_paths = StructuredOutputParser.classify_validation_error(val_err)

        assert primary_cat == "value_error"
        assert "value_error" in all_cats
        # Nested field paths explicitly report .evidence_item_ids rather than bare index
        assert field_paths == [
            "arguments.0.evidence_item_ids",
            "arguments.3.evidence_item_ids",
        ]


def test_04_genuinely_invalid_arguments_strictly_rejected():
    """Proves that genuine validation errors (empty claim, invalid direction) are NOT suppressed."""
    # 1. Invalid direction
    invalid_direction_json = json.dumps({
        "perspective_type": "growth",
        "summary": "Summary",
        "arguments": [
            {
                "id": "arg_0",
                "claim": "Claim text",
                "direction": "super_positive",  # Invalid enum value
                "basis": "inference",
                "reasoning": "Valid reasoning",
                "evidence_item_ids": [],
            }
        ],
        "critical_assumption_ids": [],
        "evidence_gap_ids": [],
        "opportunities": [],
        "key_vulnerabilities": [],
    })

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(
            raw_text=invalid_direction_json,
            response_schema=CandidatePerspectiveAnalysis,
        )

    details = exc_info.value.details
    assert details["category"] == "enum_mismatch"
    assert any("direction" in p for p in details["field_paths"])

    # 2. Empty claim
    empty_claim_json = json.dumps({
        "perspective_type": "growth",
        "summary": "Summary",
        "arguments": [
            {
                "id": "arg_0",
                "claim": "",  # Empty claim (min_length=1 violated)
                "direction": "favorable",
                "basis": "inference",
                "reasoning": "Valid reasoning",
                "evidence_item_ids": [],
            }
        ],
        "critical_assumption_ids": [],
        "evidence_gap_ids": [],
        "opportunities": [],
        "key_vulnerabilities": [],
    })

    with pytest.raises(LLMResponseValidationError) as exc_info_empty:
        parse_and_validate_structured_output(
            raw_text=empty_claim_json,
            response_schema=CandidatePerspectiveAnalysis,
        )

    details_empty = exc_info_empty.value.details
    assert any("claim" in p for p in details_empty["field_paths"])


def test_05_perspective_prompt_builder_explicitly_specifies_basis_definitions():
    """Proves the perspective prompt builder provides clear epistemic basis instructions to prevent LLM ambiguity."""
    dm = _create_minimal_decision_model()
    ep = _create_minimal_evidence_package()
    ctx = build_reasoning_context(dm, ep)
    p_ctx = build_perspective_context(CANONICAL_PERSPECTIVES[0], ctx)

    prompt = build_perspective_prompt(p_ctx)
    up = prompt.user_prompt

    # Check for basis enum guidelines
    assert "'evidence': Grounded directly in empirical findings" in up
    assert "Requires at least one valid 'evi_...' ID in evidence_item_ids" in up
    assert "DO NOT use 'evidence' — use 'inference'" in up
    assert "'inference': Logical projection, deductive reasoning, or analytical assessment" in up
    assert "Does NOT require empirical IDs (leave evidence_item_ids as [])" in up
    assert "'assumption': Premised upon unverified assumptions" in up
    assert "'unresolved': Hinges on empirical unknowns, gaps, or pending requirements" in up
    assert "'mixed': Combines multiple distinct categories" in up


def test_06_grounding_validation_and_end_to_end_synthesis_compatibility():
    """Proves that a sanitized CandidatePerspectiveAnalysis passes strict grounding validation and boardroom synthesis."""
    dm = _create_minimal_decision_model()
    ep = _create_minimal_evidence_package()
    ctx = build_reasoning_context(dm, ep)
    p_ctx = build_perspective_context(CANONICAL_PERSPECTIVES[0], ctx)

    raw_json = _create_live_failure_payload()
    candidate = parse_and_validate_structured_output(
        raw_text=raw_json,
        response_schema=CandidatePerspectiveAnalysis,
    )

    # 1. Grounding and lineage validation passes
    validated_persp = validate_and_reconcile_candidate_perspective(
        candidate=candidate,
        context=p_ctx,
    )

    assert isinstance(validated_persp, ReasoningPerspective)
    assert validated_persp.perspective_type == PerspectiveType.GROWTH
    assert len(validated_persp.arguments) == 4

    # 2. End-to-end Boardroom synthesis & reference validation compatibility
    perspectives = [validated_persp]
    for p_def in CANONICAL_PERSPECTIVES[1:]:
        p_sub_ctx = build_perspective_context(p_def, ctx)
        cand_sub = CandidatePerspectiveAnalysis(
            perspective_type=p_def.perspective_type,
            summary=f"{p_def.perspective_type.value} perspective summary.",
            arguments=[
                CandidateReasoningArgument(
                    claim=f"{p_def.perspective_type.value} evaluation argument.",
                    direction=ArgumentDirection.NEUTRAL,
                    basis=ReasoningBasis.INFERENCE,
                    reasoning="Deductive reasoning from perspective mandate.",
                    related_entity_ids=["obj_1"],
                )
            ],
            critical_assumption_ids=[],
            evidence_gap_ids=[],
            opportunities=[],
            key_vulnerabilities=[],
        )
        perspectives.append(validate_and_reconcile_candidate_perspective(cand_sub, p_sub_ctx))

    synthesis = BoardSynthesis(
        summary="Board synthesis across evaluated perspectives.",
        areas_of_agreement=["Enterprise expansion offers strategic growth."],
        disagreement_ids=[],
        critical_assumption_ids=["asm_1"],
        critical_evidence_gap_ids=[],
        evidence_sensitive_points=["Sales cycle duration benchmark"],
        unresolved_questions=[],
    )
    board = ReasoningBoard(
        id="rbd_test_reconciled_board",
        decision_model_id=dm.id,
        evidence_package_id=ep.id,
        perspectives=perspectives,
        disagreements=[],
        synthesis=synthesis,
    )

    # Referential validation and epistemic grounding must pass cleanly
    validate_reasoning_references(board, dm, ep)
    assert len(board.perspectives) == 4
    assert board.perspectives[0].arguments[0].basis == ReasoningBasis.INFERENCE
    assert board.perspectives[0].arguments[1].basis == ReasoningBasis.EVIDENCE
    assert board.perspectives[0].arguments[2].basis == ReasoningBasis.ASSUMPTION
    assert board.perspectives[0].arguments[3].basis == ReasoningBasis.INFERENCE


def test_07_diagnostics_contain_zero_data_leaks_or_prompt_text():
    """Verifies that LLMResponseValidationError details contain no prompt or payload text."""
    bad_json = json.dumps({
        "perspective_type": "growth",
        "summary": "Confidential customer strategy and secret pricing details",
        "arguments": "not_a_list",
    })

    with pytest.raises(LLMResponseValidationError) as exc_info:
        parse_and_validate_structured_output(
            raw_text=bad_json,
            response_schema=CandidatePerspectiveAnalysis,
            raw_user_prompt="Super secret prompt with confidential customer question",
        )

    details = exc_info.value.details
    details_str = json.dumps(details)

    # Ensure zero sensitive terms appear in structured diagnostics
    assert "Confidential" not in details_str
    assert "secret pricing" not in details_str
    assert "Super secret prompt" not in details_str
    assert "confidential customer question" not in details_str

    # Only schema metadata and paths
    assert details["schema"] == "CandidatePerspectiveAnalysis"
    assert "arguments" in details["field_paths"]
