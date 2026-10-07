"""Unit and regression tests for AURA Day 3 Phase 6 EvidenceRequirementEngine.

Verifies:
1. Valid EXTERNAL_RESEARCH requirement with suggested search queries.
2. EXTERNAL_RESEARCH queries are preserved and bounded.
3. INTERNAL_DATA produces no search queries (wiped deterministically).
4. USER_CLARIFICATION produces no search queries.
5. DETERMINISTIC_CALCULATION produces no search queries.
6. New requirements always start status=PENDING.
7. Valid target entity references are accepted.
8. Nonexistent target_entity_id is rejected with ValueError.
9. Mismatched target_entity_type is rejected with ValueError.
10. User-provided 20% variable does not generate a requirement to verify that 20%.
11. Unknown internal CAC can become INTERNAL_DATA.
12. Unknown organization-specific churn can become INTERNAL_DATA.
13. Missing decision-maker preference can become USER_CLARIFICATION.
14. Industry pricing elasticity can become EXTERNAL_RESEARCH.
15. Break-even arithmetic can become DETERMINISTIC_CALCULATION.
16. No recommendation is generated (output is strictly List[EvidenceRequirement]).
17. No EvidencePackage is generated.
18. Duplicate requirement IDs are prevented and all generated IDs are strictly unique.
19. Malformed LLM output is handled according to existing conventions (LLMResponseValidationError).
20. Normal tests require no GEMINI_API_KEY and perform zero external calls.
21. SaaS scenario regression case.
"""

import pytest

from app.schemas.decision_model import (
    Assumption,
    CriticalityLevel,
    DecisionModel,
    ProvenanceType,
    Unknown,
    Variable,
    VariableType,
)
from app.schemas.evidence import (
    DecisionEntityType,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    RequirementStatus,
)
from app.services.evidence.requirements import (
    CandidateEvidenceRequirement,
    CandidateRequirementsPayload,
    EvidenceRequirementEngine,
    validate_target_reference,
)
from app.services.llm.client import FakeLLMClient, LLMResponseValidationError
from app.services.llm.mock_data import get_default_decision_model


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def saas_decision_model() -> DecisionModel:
    """Provides canonical DecisionModel for the SaaS 20% price reduction inquiry."""
    return get_default_decision_model(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )


# ------------------------------------------------------------------------------
# 1-6: EvidenceKind and Query Policy Tests
# ------------------------------------------------------------------------------

def test_external_research_requirement_and_queries(saas_decision_model: DecisionModel) -> None:
    """Verifies EXTERNAL_RESEARCH retains suggested_queries and starts PENDING."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Public market studies on B2B software price elasticity.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=[
                        "B2B SaaS price elasticity customer acquisition",
                        "SaaS discount conversion rate benchmark",
                    ],
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) == 1
    req = reqs[0]
    assert req.kind == EvidenceKind.EXTERNAL_RESEARCH
    assert req.status == RequirementStatus.PENDING
    assert len(req.suggested_queries) == 2
    assert "B2B SaaS price elasticity" in req.suggested_queries[0]


def test_internal_data_wipes_search_queries(saas_decision_model: DecisionModel) -> None:
    """Verifies INTERNAL_DATA requirements have suggested_queries deterministically forced to []."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="var_monthly_churn",
                    target_entity_type=DecisionEntityType.VARIABLE,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Current monthly churn rate from internal subscription telemetry.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["accidental internal churn query that should be stripped"],
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) == 1
    assert reqs[0].kind == EvidenceKind.INTERNAL_DATA
    assert reqs[0].suggested_queries == []  # Deterministically wiped


def test_user_clarification_produces_no_queries(saas_decision_model: DecisionModel) -> None:
    """Verifies USER_CLARIFICATION requirements have suggested_queries deterministically forced to []."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="stk_prospects",
                    target_entity_type=DecisionEntityType.STAKEHOLDER,
                    kind=EvidenceKind.USER_CLARIFICATION,
                    description="Clarification on target prospect risk tolerance and purchasing tier.",
                    priority=CriticalityLevel.MEDIUM,
                    suggested_queries=["clarification query that must be wiped"],
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) == 1
    assert reqs[0].kind == EvidenceKind.USER_CLARIFICATION
    assert reqs[0].suggested_queries == []


def test_deterministic_calculation_produces_no_queries(saas_decision_model: DecisionModel) -> None:
    """Verifies DETERMINISTIC_CALCULATION produces no search queries."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="trd_volume_vs_arpu",
                    target_entity_type=DecisionEntityType.TRADEOFF,
                    kind=EvidenceKind.DETERMINISTIC_CALCULATION,
                    description="Compute break-even volume increase required to balance 20% ARPU reduction.",
                    priority=CriticalityLevel.HIGH,
                    suggested_queries=["math search query that must be wiped"],
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) == 1
    assert reqs[0].kind == EvidenceKind.DETERMINISTIC_CALCULATION
    assert reqs[0].suggested_queries == []


def test_new_requirements_always_start_pending(saas_decision_model: DecisionModel) -> None:
    """Verifies that newly generated requirements always start with status=PENDING."""
    fake_client = FakeLLMClient()
    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) >= 1
    for r in reqs:
        assert r.status == RequirementStatus.PENDING
        assert r.status != RequirementStatus.FULFILLED
        assert r.status != RequirementStatus.CONTESTED
        assert r.status != RequirementStatus.UNSUPPORTED


# ------------------------------------------------------------------------------
# 7-9: Target Entity Validation Tests
# ------------------------------------------------------------------------------

def test_valid_target_entity_reference_accepted(saas_decision_model: DecisionModel) -> None:
    """Verifies validate_target_reference accepts valid entity ID and type."""
    # asm_elasticity is an ASSUMPTION
    validate_target_reference(saas_decision_model, "asm_elasticity", DecisionEntityType.ASSUMPTION)
    # var_discount_percentage is a VARIABLE
    validate_target_reference(saas_decision_model, "var_discount_percentage", DecisionEntityType.VARIABLE)
    # unk_competitor_pricing is an UNKNOWN
    validate_target_reference(saas_decision_model, "unk_competitor_pricing", DecisionEntityType.UNKNOWN)


def test_nonexistent_target_entity_id_rejected(saas_decision_model: DecisionModel) -> None:
    """Verifies that a nonexistent target_entity_id is rejected with ValueError."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="nonexistent_entity_999",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Inquiry targeting a non-existent entity.",
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    with pytest.raises(ValueError) as exc_info:
        engine.generate_requirements(saas_decision_model)

    assert "does not exist in DecisionModel" in str(exc_info.value)
    assert "nonexistent_entity_999" in str(exc_info.value)


def test_mismatched_target_entity_type_rejected(saas_decision_model: DecisionModel) -> None:
    """Verifies that a mismatched target_entity_type is rejected with ValueError."""
    # asm_elasticity is an ASSUMPTION, not a VARIABLE
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.VARIABLE,  # Mismatched!
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Mismatched type inquiry.",
                )
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    with pytest.raises(ValueError) as exc_info:
        engine.generate_requirements(saas_decision_model)

    assert "Mismatched target_entity_type" in str(exc_info.value)
    assert "asm_elasticity" in str(exc_info.value)


# ------------------------------------------------------------------------------
# 10: Provenance Guard: User-Provided 20% Fact
# ------------------------------------------------------------------------------

def test_user_provided_value_does_not_generate_verification_requirement(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies user-provided 20% variable does not generate a requirement to verify that the value is 20%."""
    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                # Invalid: Attempting to verify user-provided 20% fact
                CandidateEvidenceRequirement(
                    target_entity_id="var_discount_percentage",
                    target_entity_type=DecisionEntityType.VARIABLE,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Verify that the proposed value is 20% for pricing reduction.",
                    priority=CriticalityLevel.LOW,
                ),
                # Valid: Validating market reaction to the discount
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="Empirical customer reaction to SaaS price cuts.",
                    priority=CriticalityLevel.HIGH,
                ),
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    # The redundant requirement targeting the 20% fact was dropped
    assert len(reqs) == 1
    assert reqs[0].target_entity_id == "asm_elasticity"
    assert "20%" not in reqs[0].description


# ------------------------------------------------------------------------------
# 11-15: Domain Classification Tests
# ------------------------------------------------------------------------------

def test_domain_classification_scenarios(saas_decision_model: DecisionModel) -> None:
    """Verifies classification of various factual needs into appropriate EvidenceKinds."""
    # Add an explicit unknown CAC to the model
    saas_decision_model.unknowns.append(
        Unknown(
            id="unk_cac",
            question="What is our startup's current blended customer acquisition cost?",
            criticality=CriticalityLevel.HIGH,
            potential_sources=["Internal marketing telemetry"],
            provenance=ProvenanceType.UNKNOWN,
        )
    )

    fake_client = FakeLLMClient()
    fake_client.register_response(
        CandidateRequirementsPayload,
        CandidateRequirementsPayload(
            requirements=[
                # 11. Unknown internal CAC -> INTERNAL_DATA
                CandidateEvidenceRequirement(
                    target_entity_id="unk_cac",
                    target_entity_type=DecisionEntityType.UNKNOWN,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Current blended customer acquisition cost from marketing spend records.",
                ),
                # 12. Unknown internal churn -> INTERNAL_DATA
                CandidateEvidenceRequirement(
                    target_entity_id="var_monthly_churn",
                    target_entity_type=DecisionEntityType.VARIABLE,
                    kind=EvidenceKind.INTERNAL_DATA,
                    description="Historical cohort customer attrition rates.",
                ),
                # 13. Missing decision-maker preference -> USER_CLARIFICATION
                CandidateEvidenceRequirement(
                    target_entity_id="stk_prospects",
                    target_entity_type=DecisionEntityType.STAKEHOLDER,
                    kind=EvidenceKind.USER_CLARIFICATION,
                    description="Executive risk tolerance for temporary gross margin compression.",
                ),
                # 14. Industry pricing elasticity -> EXTERNAL_RESEARCH
                CandidateEvidenceRequirement(
                    target_entity_id="asm_elasticity",
                    target_entity_type=DecisionEntityType.ASSUMPTION,
                    kind=EvidenceKind.EXTERNAL_RESEARCH,
                    description="B2B software price elasticity benchmarks.",
                    suggested_queries=["B2B SaaS price elasticity benchmark"],
                ),
                # 15. Break-even arithmetic -> DETERMINISTIC_CALCULATION
                CandidateEvidenceRequirement(
                    target_entity_id="trd_volume_vs_arpu",
                    target_entity_type=DecisionEntityType.TRADEOFF,
                    kind=EvidenceKind.DETERMINISTIC_CALCULATION,
                    description="Compute break-even percentage volume surge needed to balance 20% discount.",
                ),
            ]
        ),
    )

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    assert len(reqs) == 5
    by_kind = {r.kind: r for r in reqs}

    assert EvidenceKind.INTERNAL_DATA in by_kind
    assert by_kind[EvidenceKind.INTERNAL_DATA].suggested_queries == []

    assert EvidenceKind.USER_CLARIFICATION in by_kind
    assert by_kind[EvidenceKind.USER_CLARIFICATION].suggested_queries == []

    assert EvidenceKind.EXTERNAL_RESEARCH in by_kind
    assert len(by_kind[EvidenceKind.EXTERNAL_RESEARCH].suggested_queries) == 1

    assert EvidenceKind.DETERMINISTIC_CALCULATION in by_kind
    assert by_kind[EvidenceKind.DETERMINISTIC_CALCULATION].suggested_queries == []


# ------------------------------------------------------------------------------
# 16-18: Output Scope & Deduplication Tests
# ------------------------------------------------------------------------------

def test_no_recommendation_and_no_evidence_package_generated(
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies output is strictly List[EvidenceRequirement], NOT EvidencePackage or recommendation."""
    fake_client = FakeLLMClient()
    engine = EvidenceRequirementEngine(llm_client=fake_client)
    result = engine.generate_requirements(saas_decision_model)

    # 1. Must be a list of EvidenceRequirement
    assert isinstance(result, list)
    assert not isinstance(result, EvidencePackage)
    for item in result:
        assert isinstance(item, EvidenceRequirement)
        # Ensure no prescriptive recommendation text
        assert "recommend" not in item.description.lower()
        assert "you should" not in item.description.lower()


def test_duplicate_requirement_ids_prevented(saas_decision_model: DecisionModel) -> None:
    """Verifies all generated requirements have distinct, unique IDs."""
    fake_client = FakeLLMClient()
    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    ids = [r.id for r in reqs]
    assert len(ids) == len(set(ids)), f"Duplicate IDs found in requirements: {ids}"


# ------------------------------------------------------------------------------
# 19-20: Error Handling & Credential Independence Tests
# ------------------------------------------------------------------------------

def test_malformed_llm_output_handled(saas_decision_model: DecisionModel) -> None:
    """Verifies malformed structured output raises LLMResponseValidationError."""
    fake_client = FakeLLMClient()
    fake_client.register_error(LLMResponseValidationError("Malformed JSON schema"))

    engine = EvidenceRequirementEngine(llm_client=fake_client)
    with pytest.raises(LLMResponseValidationError):
        engine.generate_requirements(saas_decision_model)


def test_normal_execution_without_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
    saas_decision_model: DecisionModel,
) -> None:
    """Verifies engine execution succeeds with zero Gemini API key dependencies."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_client = FakeLLMClient()
    engine = EvidenceRequirementEngine(llm_client=fake_client)

    reqs = engine.generate_requirements(saas_decision_model)
    assert len(reqs) >= 1


# ------------------------------------------------------------------------------
# 21: Full SaaS Scenario Regression Test
# ------------------------------------------------------------------------------

def test_saas_scenario_regression_end_to_end(saas_decision_model: DecisionModel) -> None:
    """Verifies end-to-end requirement generation for SaaS 20% discount scenario.

    Ensures:
    - User-provided 20% discount produces NO requirement to verify the 20%.
    - Inferred assumption (elasticity) produces EXTERNAL_RESEARCH.
    - Unresolved churn produces INTERNAL_DATA.
    - Unknown competitor response produces EXTERNAL_RESEARCH.
    - Trade-off volume vs ARPU produces DETERMINISTIC_CALCULATION.
    """
    fake_client = FakeLLMClient()
    engine = EvidenceRequirementEngine(llm_client=fake_client)
    reqs = engine.generate_requirements(saas_decision_model)

    # 1. No requirement merely verifying user's 20%
    price_reqs = [
        r for r in reqs
        if r.target_entity_id == "var_discount_percentage" and "20" in r.description
    ]
    assert price_reqs == []

    # 2. Check kind coverage in default generation
    kinds = {r.kind for r in reqs}
    assert EvidenceKind.EXTERNAL_RESEARCH in kinds
    assert EvidenceKind.INTERNAL_DATA in kinds
    assert EvidenceKind.DETERMINISTIC_CALCULATION in kinds

    # 3. Check query policy on all generated items
    for r in reqs:
        if r.kind == EvidenceKind.EXTERNAL_RESEARCH:
            assert len(r.suggested_queries) >= 1
        else:
            assert r.suggested_queries == []
