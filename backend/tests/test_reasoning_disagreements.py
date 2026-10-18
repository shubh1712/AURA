"""Tests for AURA Deterministic Disagreement Detection (Phase 4.4).

Covers all requirements from Section 14:
1. favorable vs unfavorable with shared entity -> disagreement
2. favorable vs unfavorable with no shared scope -> no disagreement
3. favorable vs favorable -> no disagreement
4. unfavorable vs unfavorable -> no disagreement
5. neutral vs favorable -> no automatic disagreement
6. neutral vs unfavorable -> no automatic disagreement
7. mixed vs favorable -> no automatic disagreement
8. mixed vs unfavorable -> no automatic disagreement
9. shared evidence conflict -> EVIDENCE_DEPENDENT
10. shared requirement conflict -> EVIDENCE_DEPENDENT
11. shared assumption conflict -> ASSUMPTION_DEPENDENT
12. unresolved structural conflict -> UNRESOLVED where defensible
13. entity-only directional conflict -> INTERPRETATION
14. shared gap alone does not invent same proposition unless allowed by the exact implemented structural rule
15. unrelated arguments -> no disagreement
16. arguments from same perspective are never compared as board disagreement
17. deterministic result across perspective input order
18. deterministic result across argument input order
19. reverse pair not duplicated
20. deterministic disagreement ID stable
21. adding unrelated argument does not change existing disagreement ID
22. no built-in hash/random/UUID dependence
23. evidence references preserved
24. assumption references preserved
25. gap references preserved where relevant
26. perspective IDs preserved
27. argument IDs preserved
28. challenging evidence is not suppressed
29. contested dependencies remain represented
30. duplicate perspective IDs rejected
31. duplicate argument IDs rejected
32. input ReasoningPerspective objects remain unchanged
33. detector emits no recommendation fields
34. detector emits no voting/scoring fields
35. zero LLM/network/search calls
Plus edge cases: empty list, single perspective, multiple perspectives.
"""

from typing import List, Optional
import copy
import pytest

from app.schemas.reasoning import (
    ArgumentDirection,
    DisagreementNature,
    PerspectiveType,
    ReasoningArgument,
    ReasoningBasis,
    ReasoningDisagreement,
    ReasoningPerspective,
)
from app.services.reasoning.disagreements import (
    classify_disagreement_nature,
    detect_disagreements,
    generate_deterministic_disagreement_id,
)
from app.services.reasoning.validator import ReasoningValidationError


# ------------------------------------------------------------------------------
# Test Fixture Helpers
# ------------------------------------------------------------------------------

def make_arg(
    arg_id: str,
    direction: ArgumentDirection,
    basis: ReasoningBasis = ReasoningBasis.INFERENCE,
    claim: str = "Test claim about strategic trade-offs.",
    reasoning: str = "Detailed analytical justification of the claim.",
    evidence_item_ids: Optional[List[str]] = None,
    requirement_ids: Optional[List[str]] = None,
    assumption_ids: Optional[List[str]] = None,
    unknown_ids: Optional[List[str]] = None,
    evidence_gap_ids: Optional[List[str]] = None,
    related_entity_ids: Optional[List[str]] = None,
) -> ReasoningArgument:
    ev_ids = evidence_item_ids or []
    req_ids = requirement_ids or []
    as_ids = assumption_ids or []
    unk_ids = unknown_ids or []
    gap_ids = evidence_gap_ids or []
    ent_ids = related_entity_ids or []

    # Satisfy epistemic basis constraints in ReasoningArgument validator
    if basis == ReasoningBasis.EVIDENCE and not ev_ids:
        ev_ids = ["evi_default_01"]
    elif basis == ReasoningBasis.ASSUMPTION and not as_ids:
        as_ids = ["asm_default_01"]
    elif basis == ReasoningBasis.UNRESOLVED and not (unk_ids or gap_ids or req_ids):
        unk_ids = ["unk_default_01"]
    elif basis == ReasoningBasis.MIXED:
        categories = sum([bool(ev_ids), bool(as_ids), bool(unk_ids or gap_ids or req_ids)])
        if categories < 2:
            if not ev_ids:
                ev_ids = ["evi_default_01"]
            if not as_ids:
                as_ids = ["asm_default_01"]

    return ReasoningArgument(
        id=arg_id,
        claim=claim,
        direction=direction,
        basis=basis,
        reasoning=reasoning,
        evidence_item_ids=ev_ids,
        requirement_ids=req_ids,
        assumption_ids=as_ids,
        unknown_ids=unk_ids,
        evidence_gap_ids=gap_ids,
        related_entity_ids=ent_ids,
    )


def make_persp(
    persp_id: str,
    ptype: PerspectiveType,
    arguments: Optional[List[ReasoningArgument]] = None,
    summary: str = "Evaluation from this perspective lens.",
) -> ReasoningPerspective:
    return ReasoningPerspective(
        id=persp_id,
        perspective_type=ptype,
        summary=summary,
        arguments=arguments or [],
    )


# ------------------------------------------------------------------------------
# 1–8. Directional Conflict & Shared Scope Rules
# ------------------------------------------------------------------------------

def test_01_favorable_vs_unfavorable_with_shared_entity_yields_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 1
    d = disagreements[0]
    assert d.perspective_ids == ["persp_growth", "persp_risk"]
    assert d.argument_ids == ["arg_g1", "arg_r1"]
    assert "ent_scale" in d.topic


def test_02_favorable_vs_unfavorable_with_no_shared_scope_yields_no_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_revenue"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_compliance"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 0


def test_03_favorable_vs_favorable_yields_no_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_finance = make_arg("arg_f1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_finance = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_finance])

    disagreements = detect_disagreements([p_growth, p_finance])
    assert len(disagreements) == 0


def test_04_unfavorable_vs_unfavorable_yields_no_disagreement():
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])
    arg_finance = make_arg("arg_f1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])
    p_finance = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_finance])

    disagreements = detect_disagreements([p_risk, p_finance])
    assert len(disagreements) == 0


def test_05_neutral_vs_favorable_yields_no_automatic_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.NEUTRAL, related_entity_ids=["ent_scale"])
    arg_finance = make_arg("arg_f1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_finance = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_finance])

    disagreements = detect_disagreements([p_growth, p_finance])
    assert len(disagreements) == 0


def test_06_neutral_vs_unfavorable_yields_no_automatic_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.NEUTRAL, related_entity_ids=["ent_scale"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 0


def test_07_mixed_vs_favorable_yields_no_automatic_disagreement():
    arg_customer = make_arg("arg_c1", ArgumentDirection.MIXED, related_entity_ids=["ent_pricing"])
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_pricing"])

    p_customer = make_persp("persp_customer", PerspectiveType.CUSTOMER, [arg_customer])
    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])

    disagreements = detect_disagreements([p_customer, p_growth])
    assert len(disagreements) == 0


def test_08_mixed_vs_unfavorable_yields_no_automatic_disagreement():
    arg_customer = make_arg("arg_c1", ArgumentDirection.MIXED, related_entity_ids=["ent_pricing"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_pricing"])

    p_customer = make_persp("persp_customer", PerspectiveType.CUSTOMER, [arg_customer])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_customer, p_risk])
    assert len(disagreements) == 0


# ------------------------------------------------------------------------------
# 9–14. Disagreement Nature Classification & Precedence
# ------------------------------------------------------------------------------

def test_09_shared_evidence_conflict_yields_evidence_dependent():
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_market_data_01"],
    )
    arg_finance = make_arg(
        "arg_f1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_market_data_01"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_finance = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_finance])

    disagreements = detect_disagreements([p_growth, p_finance])
    assert len(disagreements) == 1
    assert disagreements[0].nature == DisagreementNature.EVIDENCE_DEPENDENT
    assert "evi_market_data_01" in disagreements[0].evidence_item_ids


def test_10_shared_requirement_conflict_yields_evidence_dependent():
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_1"],
        requirement_ids=["req_runway"],
    )
    arg_risk = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_2"],
        requirement_ids=["req_runway"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 1
    assert disagreements[0].nature == DisagreementNature.EVIDENCE_DEPENDENT
    assert set(disagreements[0].evidence_item_ids) == {"evi_1", "evi_2"}


def test_11_shared_assumption_conflict_yields_assumption_dependent():
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        assumption_ids=["asm_churn_rate"],
    )
    arg_customer = make_arg(
        "arg_c1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        assumption_ids=["asm_churn_rate"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_customer = make_persp("persp_customer", PerspectiveType.CUSTOMER, [arg_customer])

    disagreements = detect_disagreements([p_growth, p_customer])
    assert len(disagreements) == 1
    assert disagreements[0].nature == DisagreementNature.ASSUMPTION_DEPENDENT
    assert "asm_churn_rate" in disagreements[0].assumption_ids


def test_12_unresolved_structural_conflict_yields_unresolved_nature():
    # Both arguments share an entity and share an unresolved unknown
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        unknown_ids=["unk_regulatory_approval"],
        related_entity_ids=["ent_expansion"],
    )
    arg_risk = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        unknown_ids=["unk_regulatory_approval"],
        related_entity_ids=["ent_expansion"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 1
    assert disagreements[0].nature == DisagreementNature.UNRESOLVED


def test_13_entity_only_directional_conflict_yields_interpretation():
    # Only shared entity exists; no shared evidence, req, assumption, or unknown
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.INFERENCE,
        related_entity_ids=["ent_tier2_market"],
    )
    arg_finance = make_arg(
        "arg_f1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.INFERENCE,
        related_entity_ids=["ent_tier2_market"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_finance = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_finance])

    disagreements = detect_disagreements([p_growth, p_finance])
    assert len(disagreements) == 1
    assert disagreements[0].nature == DisagreementNature.INTERPRETATION


def test_14_shared_gap_alone_does_not_invent_shared_scope():
    # Arguments share ONLY a gap, with no shared entity, requirement, evidence, or assumption
    arg_growth = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        evidence_gap_ids=["gap_unverified_metric"],
    )
    arg_risk = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        evidence_gap_ids=["gap_unverified_metric"],
    )

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 0


def test_15_unrelated_arguments_yield_no_disagreement():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, basis=ReasoningBasis.INFERENCE)
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, basis=ReasoningBasis.INFERENCE)

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 0


# ------------------------------------------------------------------------------
# 16–22. Determinism, Ordering Invariance & Deduplication
# ------------------------------------------------------------------------------

def test_16_arguments_from_same_perspective_are_never_compared():
    # Inside the same perspective, two arguments oppose each other
    arg_g1 = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_g2 = make_arg("arg_g2", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g1, arg_g2])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 0


def test_17_deterministic_result_across_perspective_input_order():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    res1 = detect_disagreements([p_growth, p_risk])
    res2 = detect_disagreements([p_risk, p_growth])

    assert len(res1) == 1
    assert len(res2) == 1
    assert res1[0].id == res2[0].id
    assert res1[0].perspective_ids == res2[0].perspective_ids
    assert res1[0].argument_ids == res2[0].argument_ids
    assert res1[0].positions == res2[0].positions


def test_18_deterministic_result_across_argument_input_order():
    arg_g1 = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_g2 = make_arg("arg_g2", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_cost"])
    arg_r1 = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])
    arg_r2 = make_arg("arg_r2", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_cost"])

    p_growth_order_a = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g1, arg_g2])
    p_growth_order_b = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g2, arg_g1])

    p_risk_order_a = make_persp("persp_risk", PerspectiveType.RISK, [arg_r1, arg_r2])
    p_risk_order_b = make_persp("persp_risk", PerspectiveType.RISK, [arg_r2, arg_r1])

    res_a = detect_disagreements([p_growth_order_a, p_risk_order_a])
    res_b = detect_disagreements([p_growth_order_b, p_risk_order_b])

    assert len(res_a) == 2
    assert len(res_b) == 2
    assert [d.id for d in res_a] == [d.id for d in res_b]


def test_19_reverse_pair_not_duplicated():
    arg_growth = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_risk = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_growth])
    p_risk = make_persp("persp_risk", PerspectiveType.RISK, [arg_risk])

    disagreements = detect_disagreements([p_growth, p_risk])
    assert len(disagreements) == 1
    # Check that there is no reverse (arg_r1, arg_g1) duplicate
    seen_arg_tuples = [tuple(d.argument_ids) for d in disagreements]
    assert len(seen_arg_tuples) == len(set(seen_arg_tuples))


def test_20_deterministic_disagreement_id_stable():
    arg_g = make_arg("arg_growth_01", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_f = make_arg("arg_finance_01", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_f = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_f])

    id1 = generate_deterministic_disagreement_id(p_g, arg_g, p_f, arg_f)
    id2 = generate_deterministic_disagreement_id(p_f, arg_f, p_g, arg_g)

    assert id1 == id2
    assert id1.startswith("dis_growth_finance_")
    assert len(id1) <= 64


def test_21_adding_unrelated_argument_does_not_change_existing_disagreement_id():
    arg_g1 = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_f1 = make_arg("arg_f1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g_small = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g1])
    p_f_small = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_f1])

    dis_small = detect_disagreements([p_g_small, p_f_small])
    assert len(dis_small) == 1
    baseline_id = dis_small[0].id

    # Now add unrelated argument to growth
    arg_g_unrelated = make_arg("arg_g_unrelated", ArgumentDirection.NEUTRAL)
    p_g_large = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g1, arg_g_unrelated])

    dis_large = detect_disagreements([p_g_large, p_f_small])
    assert len(dis_large) == 1
    assert dis_large[0].id == baseline_id


def test_22_no_builtin_hash_or_random_or_uuid_dependence():
    arg_g = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    ids = [detect_disagreements([p_g, p_r])[0].id for _ in range(50)]
    assert len(set(ids)) == 1


# ------------------------------------------------------------------------------
# 23–29. Epistemic Reference Preservation & Structural Integrity
# ------------------------------------------------------------------------------

def test_23_evidence_references_preserved_as_union():
    arg_g = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_1", "evi_2"],
        related_entity_ids=["ent_scale"],
    )
    arg_r = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_2", "evi_3"],
        related_entity_ids=["ent_scale"],
    )

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    assert d.evidence_item_ids == ["evi_1", "evi_2", "evi_3"]


def test_24_assumption_references_preserved_as_union():
    arg_g = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        assumption_ids=["asm_1"],
    )
    arg_f = make_arg(
        "arg_f1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.ASSUMPTION,
        assumption_ids=["asm_1", "asm_2"],
    )

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_f = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_f])

    d = detect_disagreements([p_g, p_f])[0]
    assert d.assumption_ids == ["asm_1", "asm_2"]


def test_25_gap_references_preserved_where_relevant():
    arg_g = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        evidence_gap_ids=["gap_1"],
        related_entity_ids=["ent_scale"],
    )
    arg_r = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.UNRESOLVED,
        evidence_gap_ids=["gap_2"],
        related_entity_ids=["ent_scale"],
    )

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    assert d.evidence_gap_ids == ["gap_1", "gap_2"]


def test_26_perspective_ids_preserved_in_canonical_order():
    arg_c = make_arg("arg_c1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_g = make_arg("arg_g1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_customer = make_persp("persp_customer", PerspectiveType.CUSTOMER, [arg_c])
    p_growth = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])

    # Growth comes before customer in canonical order
    d = detect_disagreements([p_customer, p_growth])[0]
    assert d.perspective_ids == ["persp_growth", "persp_customer"]


def test_27_argument_ids_preserved():
    arg_g = make_arg("arg_growth_alpha", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_f = make_arg("arg_finance_beta", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_f = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_f])

    d = detect_disagreements([p_g, p_f])[0]
    assert d.argument_ids == ["arg_growth_alpha", "arg_finance_beta"]


def test_28_challenging_evidence_is_not_suppressed():
    # Growth uses supporting evidence, Risk uses challenging evidence on same requirement
    arg_g = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_supporting_01"],
        requirement_ids=["req_shared_market"],
    )
    arg_r = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.EVIDENCE,
        evidence_item_ids=["evi_challenging_01"],
        requirement_ids=["req_shared_market"],
    )

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    assert "evi_challenging_01" in d.evidence_item_ids
    assert "evi_supporting_01" in d.evidence_item_ids


def test_29_contested_dependencies_remain_represented():
    arg_g = make_arg(
        "arg_g1",
        ArgumentDirection.FAVORABLE,
        basis=ReasoningBasis.MIXED,
        evidence_item_ids=["evi_pro"],
        assumption_ids=["asm_contested"],
        requirement_ids=["req_contested"],
    )
    arg_r = make_arg(
        "arg_r1",
        ArgumentDirection.UNFAVORABLE,
        basis=ReasoningBasis.MIXED,
        evidence_item_ids=["evi_con"],
        assumption_ids=["asm_contested"],
        requirement_ids=["req_contested"],
    )

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    assert "asm_contested" in d.assumption_ids
    assert set(d.evidence_item_ids) == {"evi_con", "evi_pro"}


# ------------------------------------------------------------------------------
# 30–35. Fail-Closed Validation & Non-Goals Invariants
# ------------------------------------------------------------------------------

def test_30_duplicate_perspective_ids_rejected():
    p1 = make_persp("persp_dup", PerspectiveType.GROWTH)
    p2 = make_persp("persp_dup", PerspectiveType.RISK)

    with pytest.raises(ReasoningValidationError, match="Duplicate perspective IDs"):
        detect_disagreements([p1, p2])


def test_31_duplicate_argument_ids_rejected():
    arg_dup_1 = make_arg("arg_collision", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_dup_2 = make_arg("arg_collision", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_dup_1])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_dup_2])

    with pytest.raises(ReasoningValidationError, match="Duplicate argument ID"):
        detect_disagreements([p_g, p_r])


def test_32_input_reasoning_perspective_objects_remain_unchanged():
    arg_g = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    p_g_dict_before = p_g.model_dump()
    p_r_dict_before = p_r.model_dump()

    _ = detect_disagreements([p_g, p_r])

    assert p_g.model_dump() == p_g_dict_before
    assert p_r.model_dump() == p_r_dict_before


def test_33_detector_emits_no_recommendation_fields():
    arg_g = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    data = d.model_dump()
    forbidden = ["recommendation", "recommended_action", "decision", "verdict"]
    for field in forbidden:
        assert field not in data


def test_34_detector_emits_no_voting_or_scoring_fields():
    arg_g = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    d = detect_disagreements([p_g, p_r])[0]
    data = d.model_dump()
    forbidden = [
        "vote", "votes", "tally", "majority", "minority", "score",
        "agreement_score", "disagreement_score", "consensus_score",
        "alignment_score", "probability", "confidence_score"
    ]
    for field in forbidden:
        assert field not in data


def test_35_zero_llm_network_or_search_calls(monkeypatch):
    # Ensure no network socket or LLM call could possibly execute
    import socket
    def forbidden_network(*args, **kwargs):
        raise RuntimeError("Network calls strictly forbidden during disagreement detection.")
    monkeypatch.setattr(socket, "socket", forbidden_network)

    arg_g = make_arg("arg_g1", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r1", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    disagreements = detect_disagreements([p_g, p_r])
    assert len(disagreements) == 1


# ------------------------------------------------------------------------------
# Edge Cases: Collection Cardinality & Validation
# ------------------------------------------------------------------------------

def test_36_empty_perspectives_returns_empty_list():
    assert detect_disagreements([]) == []


def test_37_single_perspective_returns_empty_list():
    p = make_persp("persp_growth", PerspectiveType.GROWTH)
    assert detect_disagreements([p]) == []


def test_38_non_sequence_input_raises_validation_error():
    with pytest.raises(ReasoningValidationError, match="Expected Sequence"):
        detect_disagreements("not_a_sequence")  # type: ignore


def test_39_non_perspective_element_raises_validation_error():
    p = make_persp("persp_growth", PerspectiveType.GROWTH)
    with pytest.raises(ReasoningValidationError, match="not an instance of ReasoningPerspective"):
        detect_disagreements([p, "invalid_item"])  # type: ignore


def test_40_all_four_perspectives_detects_multiple_pairwise_disagreements():
    # Growth vs Risk on ent_scale
    # Finance vs Customer on ent_price
    arg_g = make_arg("arg_g", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_scale"])
    arg_r = make_arg("arg_r", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_scale"])
    arg_f = make_arg("arg_f", ArgumentDirection.FAVORABLE, related_entity_ids=["ent_price"])
    arg_c = make_arg("arg_c", ArgumentDirection.UNFAVORABLE, related_entity_ids=["ent_price"])

    p_g = make_persp("persp_growth", PerspectiveType.GROWTH, [arg_g])
    p_f = make_persp("persp_finance", PerspectiveType.FINANCE, [arg_f])
    p_c = make_persp("persp_customer", PerspectiveType.CUSTOMER, [arg_c])
    p_r = make_persp("persp_risk", PerspectiveType.RISK, [arg_r])

    disagreements = detect_disagreements([p_g, p_f, p_c, p_r])
    assert len(disagreements) == 2

    # Verify both tensions are identified
    dis_topics = [d.topic for d in disagreements]
    assert any("ent_scale" in t for t in dis_topics)
    assert any("ent_price" in t for t in dis_topics)
