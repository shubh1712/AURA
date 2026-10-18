"""Deterministic measurement script for Phase 4.30 source-excerpt deduplication."""

from datetime import date, datetime, timezone
from typing import List, Tuple

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
    EvidenceGapType,
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
from app.services.reasoning.context_builder import (
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.perspectives import (
    CANONICAL_PERSPECTIVES,
    CUSTOMER,
    FINANCE,
    GROWTH,
    RISK,
)
from app.services.reasoning.prompt_builder import (
    PerspectivePrompt,
    build_perspective_prompt,
    build_perspective_system_instruction,
    truncate_narrative,
)


def _build_original_prompt_before_phase430(context) -> PerspectivePrompt:
    """Reconstructs the exact Phase 4.29 / Phase 4.28 prompt format before Phase 4.30 deduplication."""
    system_instruction = build_perspective_system_instruction(context)

    p = context.perspective
    dec = context.decision_context
    evi = context.evidence_context

    sections: List[str] = []

    # 1. Perspective Lens & Mandate
    focus_list = "\n".join(f"  - {f}" for f in p.focus_areas)
    prohib_list = "\n".join(f"  - {pr}" for pr in p.prohibitions)
    rules_list = "\n".join(f"  - {r}" for r in p.epistemic_rules)

    sections.append(
        f"=== ASSIGNED PERSPECTIVE MANDATE: {p.title.upper()} ===\n"
        f"Perspective Title: {p.title}\n"
        f"Type: {p.perspective_type.value}\n"
        f"Mandate: {p.mandate}\n\n"
        f"Focus Areas:\n{focus_list}\n\n"
        f"Strict Prohibitions:\n{prohib_list}\n\n"
        f"Common Epistemic Rules:\n{rules_list}"
    )

    # 2. Decision Problem Specification
    sections.append(
        f"=== DECISION PROBLEM CONTEXT ===\n"
        f"Decision ID: {dec.decision_id}\n"
        f"Summary: {truncate_narrative(dec.summary, 1000)}\n"
        f"Decision Type: {dec.decision_type.value}\n"
        f"Time Horizon: {dec.time_horizon.value}\n"
        f"Complexity: {dec.complexity_level.value} (Reasoning: {truncate_narrative(dec.complexity_reasoning, 1000)})\n"
        f"Reversibility: {dec.reversibility.value}"
    )

    # 3. Objectives
    obj_lines = [
        f"  - ID: {o.id} | Primary: {o.is_primary} | Provenance: {o.provenance.value} | "
        f"Description: {truncate_narrative(o.description, 1000)}"
        for o in dec.objectives
    ]
    sections.append("Objectives:\n" + ("\n".join(obj_lines) if obj_lines else "  None"))

    # 4. Variables
    var_lines = [
        f"  - ID: {v.id} | Name: {v.name} | Type: {v.variable_type.value} | Controllable: {v.is_controllable} | "
        f"Baseline: {v.baseline_value} | Proposed: {v.proposed_value} | Unit: {v.unit or 'N/A'} | Provenance: {v.provenance.value} | "
        f"Description: {truncate_narrative(v.description, 1000)}"
        for v in dec.variables
    ]
    sections.append("Variables:\n" + ("\n".join(var_lines) if var_lines else "  None"))

    # 5. Constraints
    con_lines = [
        f"  - ID: {c.id} | Name: {c.name} | Hard: {c.is_hard_constraint} | Source: {c.source} | Provenance: {c.provenance.value} | "
        f"Threshold: {c.threshold_expression or 'N/A'} | Description: {truncate_narrative(c.description, 1000)}"
        for c in dec.constraints
    ]
    sections.append("Constraints:\n" + ("\n".join(con_lines) if con_lines else "  None"))

    # 6. Stakeholders
    stk_lines = [
        f"  - ID: {s.id} | Group: {s.group} | Influence: {s.influence_level.value} | Provenance: {s.provenance.value} | "
        f"Impact: {truncate_narrative(s.impact_nature, 1000)}"
        for s in dec.stakeholders
    ]
    sections.append("Stakeholders:\n" + ("\n".join(stk_lines) if stk_lines else "  None"))

    # 7. Trade-offs
    trd_lines = [
        f"  - ID: {t.id} | Upside: {truncate_narrative(t.upside, 1000)} | "
        f"Downside: {truncate_narrative(t.downside, 1000)} | "
        f"Variables: {t.affected_variable_ids} | Provenance: {t.provenance.value}"
        for t in dec.tradeoffs
    ]
    sections.append("Trade-offs:\n" + ("\n".join(trd_lines) if trd_lines else "  None"))

    # 8. Assumptions
    asm_lines = [
        f"  - ID: {a.id} | Confidence: {a.confidence.value} | Provenance: {a.provenance.value} | "
        f"Statement: {truncate_narrative(a.statement, 1000)} | "
        f"Falsification: {truncate_narrative(a.falsification_condition, 1000)}"
        for a in dec.assumptions
    ]
    sections.append("Assumptions:\n" + ("\n".join(asm_lines) if asm_lines else "  None"))

    # 9. Unknowns
    unk_lines = [
        f"  - ID: {u.id} | Criticality: {u.criticality.value} | Provenance: {u.provenance.value} | "
        f"Question: {truncate_narrative(u.question, 1000)} | Sources: {u.potential_sources}"
        for u in dec.unknowns
    ]
    sections.append("Unknowns:\n" + ("\n".join(unk_lines) if unk_lines else "  None"))

    # 10. Key Questions
    kq_lines = [f"  - {truncate_narrative(q, 1000)}" for q in dec.key_questions]
    sections.append("Key Questions:\n" + ("\n".join(kq_lines) if kq_lines else "  None"))

    # 11. Evidence Requirements
    req_lines = [
        f"  - ID: {r.id} | Target: {r.target_entity_id} ({r.target_entity_type.value}) | "
        f"Kind: {r.kind.value} | Status: {r.status.value} | Priority: {r.priority.value} | "
        f"Description: {truncate_narrative(r.description, 1000)}"
        for r in evi.requirements
    ]
    sections.append("=== EVIDENCE REQUIREMENTS ===\n" + ("\n".join(req_lines) if req_lines else "  None"))

    # 12. Sources (Original without excerpts)
    src_lines = [
        f"  - ID: {s.id} | Type: {s.source_type.value} | Title: {truncate_narrative(s.title, 200)} | "
        f"Publisher: {s.publisher or 'N/A'} | Date: {s.publication_date or 'N/A'} | "
        f"Reliability: {s.reliability_score if s.reliability_score is not None else 'None (unassessed)'}"
        for s in evi.sources
    ]
    sections.append("=== SOURCES ===\n" + ("\n".join(src_lines) if src_lines else "  None"))

    # 13. Evidence Items (Original repeating raw excerpts per item)
    item_lines: List[str] = []
    for item in evi.items:
        bounded_content = truncate_narrative(item.content.raw_text, 4000)
        safe_xml = f"<untrusted_source_material>\n{bounded_content}\n</untrusted_source_material>"
        nums = [f"{n.metric_name}={n.value} {n.unit or ''}".strip() for n in item.numeric_data]
        item_lines.append(
            f"  - ID: {item.id} | Source: {item.source_id} | Confidence: {item.extraction_confidence.value}\n"
            f"    Numeric Data: {nums if nums else 'None'}\n"
            f"    Content Excerpt:\n{safe_xml}"
        )
    sections.append("=== EVIDENCE ITEMS ===\n" + ("\n".join(item_lines) if item_lines else "  None"))

    # 14. Claim-to-Evidence Links
    link_lines = [
        f"  - ID: {cl.id} | Evidence Item: {cl.evidence_item_id} | Target: {cl.target_entity_id} ({cl.target_entity_type.value}) | "
        f"Stance: {cl.stance.value} | Confidence: {cl.relationship_confidence.value} | Requirement Lineage: {cl.requirement_id or 'None'} | "
        f"Reasoning: {truncate_narrative(cl.reasoning, 1000)}"
        for cl in evi.claim_links
    ]
    sections.append("=== CLAIM EVIDENCE LINKS ===\n" + ("\n".join(link_lines) if link_lines else "  None"))

    # 15. Evidence Gaps & Contradictions
    gap_lines = [
        f"  - ID: {g.id} | Target: {g.target_entity_id} ({g.target_entity_type.value}) | "
        f"Gap Type: {g.gap_type.value} | Impact: {g.impact.value} | Conflicting Items: {g.conflicting_evidence_ids} | "
        f"Description: {truncate_narrative(g.description, 1000)}"
        for g in evi.gaps
    ]
    sections.append("=== EVIDENCE Gaps & CONTRADICTIONS ===\n" + ("\n".join(gap_lines) if gap_lines else "  None"))

    # 16. Instructions
    sections.append(
        "=== ANALYSIS TASK ===\n"
        "Formulate a structured analysis strictly from the assigned perspective.\n"
        "Requirements:\n"
        "1. Provide a comprehensive executive summary from this perspective's mandate.\n"
        "2. Formulate discrete arguments. Each argument must specify claim, direction, basis, reasoning, "
        "and reference only legitimate existing IDs from the context above.\n"
        "3. Explicitly cite any critical assumptions, evidence gaps, unresolved questions, and analytical limitations.\n"
        "4. Do NOT make a final recommendation, declare a vote, calculate a score, or formulate scenarios."
    )

    user_prompt = "\n\n".join(sections)
    return PerspectivePrompt(system_instruction=system_instruction, user_prompt=user_prompt)


def create_representative_workload():
    """Workload representative of Phase 4.28 where multiple evidence items cite common source documents."""
    dm = DecisionModel(
        id="dec_pricing_01",
        decision=Decision(
            raw_prompt="Evaluate shifting B2B SaaS pricing from per-seat to usage-based.",
            summary="Shift core B2B SaaS pricing from fixed seat to consumption model.",
            decision_type=DecisionType.STRATEGIC_DIRECTION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.HIGH,
            reasoning="Significant revenue model change affecting all customers.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
        ),
        objectives=[
            Objective(
                id="obj_growth",
                description="Increase net revenue retention from 105% to 125%.",
                is_primary=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        variables=[
            Variable(
                id="var_discount_percentage",
                name="Volume Discount Percentage",
                description="Discount tier.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=0.0,
                proposed_value=20.0,
                unit="%",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
            Variable(
                id="var_monthly_churn",
                name="Monthly Churn Rate",
                description="Gross monthly customer logo churn.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=1.5,
                proposed_value=2.8,
                unit="%",
                is_controllable=False,
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        constraints=[
            Constraint(
                id="cnstr_min_margin",
                name="Gross Margin Floor",
                description="Gross profit margin must not fall below 70%.",
                is_hard_constraint=True,
                threshold_expression="margin >= 0.70",
                source="Executive Board Mandate",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        stakeholders=[
            Stakeholder(
                id="stk_finance",
                group="Finance & Treasury",
                impact_nature="Cashflow seasonality and ARR recognition timing.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.USER_PROVIDED,
            ),
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_pricing_tradeoff",
                upside="Higher acquisition volume from low entry friction.",
                downside="Margin contraction and potential downsell churn.",
                affected_variable_ids=["var_discount_percentage", "var_monthly_churn"],
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        assumptions=[
            Assumption(
                id="asm_price_sensitivity",
                statement="Enterprise buyers have high elasticity to usage tiers.",
                confidence=ConfidenceLevel.MEDIUM,
                falsification_condition="Enterprise churn increases by > 200 bps.",
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        unknowns=[
            Unknown(
                id="unk_expansion_speed",
                question="How fast do cohorts expand usage in the first 6 months?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Cohort usage analytics"],
                provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        key_questions=["Will net retention improvement exceed customer churn degradation?"],
    )

    s1 = Source(id="src_openview_2024", url="https://openview.com/pricing-report", title="2024 SaaS Pricing Benchmark Report", publisher="OpenView Labs", source_type=SourceType.INDUSTRY_REPORT, publication_date=date(2024, 9, 1))
    s2 = Source(id="src_mckinsey_b2b", url="https://mckinsey.com/b2b-elasticity", title="B2B Software Price Elasticity & Value Metric Study", publisher="McKinsey & Company", source_type=SourceType.INDUSTRY_REPORT, publication_date=date(2024, 5, 12))
    s3 = Source(id="src_internal_billing", url="https://internal.aura/billing-analysis", title="Internal Cohort Expansion & Billing Telemetry", publisher="Internal Finance", source_type=SourceType.INTERNAL_DATA, publication_date=date(2024, 11, 1))

    # Real-world representative retrieved texts (~1,200 chars each)
    source_text_openview = (
        "In a survey of 450 B2B SaaS companies with ARR between $1M and $20M, reducing headline pricing by 15-20% "
        "yielded an average increase in new logo acquisition volume of 18.4% across the subsequent two quarters. "
        "However, companies serving mid-market buyers saw higher elasticity (1.42) compared to enterprise tiers (0.65). "
        "The median sales cycle contracted by 12 days for lower-tier packages, whereas enterprise evaluation timelines remained unchanged. "
        "Furthermore, cohorts acquired under aggressive introductory discounting experienced higher second-year churn rates (31% vs 14% benchmark)."
    ) * 2

    source_text_mckinsey = (
        "Enterprise software price elasticity is heavily asymmetric. While price increases above 10% consistently trigger vendor audits, "
        "price cuts of 20% failed to alter purchase decisions in 68% of evaluated deals where security, integration, and compliance were primary criteria. "
        "For SMB segments, elasticity was measured at -1.8, showing significant conversion sensitivity to upfront price points. "
        "Gross margins for consumption-based models compress by 400-600 basis points in year one due to cloud infrastructure overhead."
    ) * 2

    source_text_internal = (
        "Historical expansion telemetry across 1,200 accounts reveals that usage-driven customers expand ARR at 122% NRR over 24 months. "
        "However, cash collection cycles lengthen from 30 days upfront to 60 days in arrears, requiring an additional $3.5M in working capital runway."
    ) * 2

    r1 = EvidenceRequirement(id="req_elasticity", target_entity_id="var_discount_percentage", target_entity_type=DecisionEntityType.VARIABLE, kind=EvidenceKind.EXTERNAL_RESEARCH, description="Price elasticity benchmark.", status=RequirementStatus.FULFILLED, priority=CriticalityLevel.HIGH)
    r2 = EvidenceRequirement(id="req_churn", target_entity_id="var_monthly_churn", target_entity_type=DecisionEntityType.VARIABLE, kind=EvidenceKind.EXTERNAL_RESEARCH, description="Churn correlation benchmark.", status=RequirementStatus.CONTESTED, priority=CriticalityLevel.HIGH)
    r3 = EvidenceRequirement(id="req_margin", target_entity_id="cnstr_min_margin", target_entity_type=DecisionEntityType.CONSTRAINT, kind=EvidenceKind.EXTERNAL_RESEARCH, description="Gross margin floor impact.", status=RequirementStatus.FULFILLED, priority=CriticalityLevel.HIGH)

    # 10 Evidence Items citing the 3 sources (repeating source excerpts 3-4 times each)
    items = [
        # Source 1 items (4 items share source_text_openview)
        EvidenceItem(id="evi_ov_01", source_id="src_openview_2024", content=source_text_openview, summary="18.4% logo acquisition lift.", numeric_data=[NumericEvidence(metric_name="acquisition_lift", value=18.4, unit="%")]),
        EvidenceItem(id="evi_ov_02", source_id="src_openview_2024", content=source_text_openview, summary="Mid-market elasticity measured at 1.42.", numeric_data=[NumericEvidence(metric_name="elasticity_midmarket", value=1.42, unit="ratio")]),
        EvidenceItem(id="evi_ov_03", source_id="src_openview_2024", content=source_text_openview, summary="Sales cycle contracted by 12 days.", numeric_data=[NumericEvidence(metric_name="sales_cycle_days", value=-12.0, unit="days")]),
        EvidenceItem(id="evi_ov_04", source_id="src_openview_2024", content=source_text_openview, summary="Second-year churn elevated at 31% for discounted cohorts.", numeric_data=[NumericEvidence(metric_name="churn_discounted", value=31.0, unit="%")]),

        # Source 2 items (3 items share source_text_mckinsey)
        EvidenceItem(id="evi_mck_01", source_id="src_mckinsey_b2b", content=source_text_mckinsey, summary="68% of enterprise buyers insensitive to 20% discount.", numeric_data=[NumericEvidence(metric_name="enterprise_insensitivity", value=68.0, unit="%")]),
        EvidenceItem(id="evi_mck_02", source_id="src_mckinsey_b2b", content=source_text_mckinsey, summary="SMB elasticity strong at -1.8.", numeric_data=[NumericEvidence(metric_name="smb_elasticity", value=-1.8, unit="ratio")]),
        EvidenceItem(id="evi_mck_03", source_id="src_mckinsey_b2b", content=source_text_mckinsey, summary="Gross margin compression of 400-600 bps.", numeric_data=[NumericEvidence(metric_name="margin_compression_bps", value=500.0, unit="bps")]),

        # Source 3 items (3 items share source_text_internal)
        EvidenceItem(id="evi_int_01", source_id="src_internal_billing", content=source_text_internal, summary="Usage customers achieve 122% NRR over 24 months.", numeric_data=[NumericEvidence(metric_name="nrr_24mo", value=122.0, unit="%")]),
        EvidenceItem(id="evi_int_02", source_id="src_internal_billing", content=source_text_internal, summary="Collection lag expands to 60 days.", numeric_data=[NumericEvidence(metric_name="dso_days", value=60.0, unit="days")]),
        EvidenceItem(id="evi_int_03", source_id="src_internal_billing", content=source_text_internal, summary="Requires $3.5M working capital buffer.", numeric_data=[NumericEvidence(metric_name="capital_buffer", value=3500000.0, unit="USD")]),
    ]

    links = [
        ClaimEvidenceLink(id=f"lnk_{i+1:02d}", evidence_item_id=items[i].id, target_entity_id="var_discount_percentage" if i < 3 else ("var_monthly_churn" if i < 6 else "cnstr_min_margin"), target_entity_type=DecisionEntityType.VARIABLE if i < 6 else DecisionEntityType.CONSTRAINT, stance=EvidenceStance.SUPPORTS if i not in (3, 6) else EvidenceStance.CHALLENGES, relationship_confidence=ConfidenceLevel.HIGH, requirement_id=r1.id if i < 3 else (r2.id if i < 6 else r3.id), reasoning="Empirical link validation.")
        for i in range(10)
    ]

    gaps = [
        EvidenceGap(id="gap_01", target_entity_id="var_monthly_churn", target_entity_type=DecisionEntityType.VARIABLE, gap_type=EvidenceGapType.CONFLICTING_EVIDENCE, description="Acquisition volume vs long-term churn trade-off.", impact=CriticalityLevel.HIGH, conflicting_evidence_ids=["evi_ov_01", "evi_ov_04"]),
    ]

    ep = EvidencePackage(
        id="evpkg_pricing_workload",
        decision_model_id=dm.id,
        sources=[s1, s2, s3],
        items=items,
        requirements=[r1, r2, r3],
        claim_links=links,
        gaps=gaps,
        summary="Pricing workload with realistic source repetition.",
    )
    return dm, ep


def run_measurements():
    dm, ep = create_representative_workload()
    rctx = build_reasoning_context(dm, ep)

    schema_persp_chars = 4159  # from CandidatePerspectiveAnalysis schema audit

    print("==========================================================================================")
    print("PHASE 4.30 BEFORE VS AFTER LOSSLESS EXCERPT DEDUPLICATION MEASUREMENT")
    print("==========================================================================================")
    print(f"Number of Evidence Items:                  {len(ep.items)}")
    print(f"Number of Distinct Sources:                {len(ep.sources)}")
    distinct_pairs = set((item.source_id, item.content) for item in ep.items)
    print(f"Number of Distinct (source, excerpt) Pairs:{len(distinct_pairs)}")
    print(f"Duplicate Excerpt Occurrences Removed:     {len(ep.items) - len(distinct_pairs)}")
    print("-" * 90)

    print(f"{'Perspective':<10} | {'Before User':<12} | {'After User':<12} | {'Reduction Chars':<16} | {'Reduction %':<12} | {'Total Load (Sys+User+Schema)':<28}")
    print("-" * 105)

    for pdef in CANONICAL_PERSPECTIVES:
        pctx = build_perspective_context(pdef, rctx)
        prompt_before = _build_original_prompt_before_phase430(pctx)
        prompt_after = build_perspective_prompt(pctx)

        before_user = len(prompt_before.user_prompt)
        after_user = len(prompt_after.user_prompt)
        diff = before_user - after_user
        pct = (diff / before_user) * 100.0

        sys_len = len(prompt_after.system_instruction)
        total_wire_after = sys_len + after_user + schema_persp_chars

        pname = pdef.perspective_type.value.upper()
        print(f"{pname:<10} | {before_user:>10,d} c | {after_user:>10,d} c | -{diff:>14,d} c | {pct:>10.2f}% | {total_wire_after:>12,d} c (sys:{sys_len}, schema:{schema_persp_chars})")


if __name__ == "__main__":
    run_measurements()
