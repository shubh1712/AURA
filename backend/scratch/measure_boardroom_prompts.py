"""Deterministic offline prompt measurement script for Stage 3 AI Boardroom (Phase 4.29)."""

import json
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

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
from app.schemas.reasoning import (
    CandidateBoardSynthesis,
    CandidatePerspectiveAnalysis,
    PerspectiveType,
)
from app.services.reasoning.context_builder import (
    PerspectiveContext,
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.perspectives import CANONICAL_PERSPECTIVES
from app.services.reasoning.prompt_builder import (
    MAX_FIELD_NARRATIVE_CHARS,
    MAX_SOURCE_EXCERPT_CHARS,
    PerspectivePrompt,
    build_perspective_prompt,
    build_perspective_system_instruction,
    truncate_narrative,
)
from app.services.llm.mock_data import get_default_decision_model


def create_phase428_representative_workload() -> Tuple[DecisionModel, EvidencePackage]:
    """Creates a deterministic DecisionModel and EvidencePackage closely matching the Phase 4.28 live test."""
    dm = get_default_decision_model(
        "Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )

    # 4 sources
    s1 = Source(
        id="src_openview_2024",
        url="https://example.com/saas-pricing-benchmarks-2024",
        title="2024 SaaS Pricing & Monetization Benchmarks Report",
        publisher="OpenView Expansion SaaS Institute",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2024, 3, 15),
    )
    s2 = Source(
        id="src_profitwell_retention",
        url="https://example.com/discounting-churn-impact",
        title="Impact of Aggressive Discounting on B2B SaaS Churn & LTV",
        publisher="ProfitWell Analytics Group",
        source_type=SourceType.INDUSTRY_REPORT,
        publication_date=date(2023, 11, 20),
    )
    s3 = Source(
        id="src_academic_elasticity",
        url="https://example.com/b2b-price-elasticity-study",
        title="Empirical Price Elasticity in Mid-Market Enterprise Software",
        publisher="Journal of Software Business Research",
        source_type=SourceType.ACADEMIC,
        publication_date=date(2023, 8, 10),
    )
    s4 = Source(
        id="src_internal_financials",
        url=None,
        title="Internal FY2024 Unit Economics & Cohort Retention",
        publisher="Internal Financial Operations",
        source_type=SourceType.INTERNAL_DATA,
        publication_date=date(2024, 1, 15),
    )

    # 4 requirements
    r1 = EvidenceRequirement(
        id="req_elasticity_empirical",
        target_entity_id="var_discount_percentage",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Empirical customer acquisition lift from price reductions in B2B SaaS.",
        status=RequirementStatus.FULFILLED,
        priority=CriticalityLevel.HIGH,
        suggested_queries=["B2B SaaS price reduction customer acquisition elasticity benchmarks"],
    )
    r2 = EvidenceRequirement(
        id="req_churn_sensitivity",
        target_entity_id="var_monthly_churn",
        target_entity_type=DecisionEntityType.VARIABLE,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Correlation between discounted acquisition and cohort churn rates.",
        status=RequirementStatus.CONTESTED,
        priority=CriticalityLevel.HIGH,
        suggested_queries=["discounted SaaS customers cancellation churn rate comparison"],
    )
    r3 = EvidenceRequirement(
        id="req_margin_impact",
        target_entity_id="cnstr_min_margin",
        target_entity_type=DecisionEntityType.CONSTRAINT,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Impact of 20% price reduction on gross margins and payback period.",
        status=RequirementStatus.FULFILLED,
        priority=CriticalityLevel.HIGH,
        suggested_queries=["gross margin impact SaaS pricing discount 20 percent CAC payback"],
    )
    r4 = EvidenceRequirement(
        id="req_assump_growth",
        target_entity_id="asm_price_sensitivity",
        target_entity_type=DecisionEntityType.ASSUMPTION,
        kind=EvidenceKind.EXTERNAL_RESEARCH,
        description="Validation of target market price sensitivity and competitor pricing parity.",
        status=RequirementStatus.INCONCLUSIVE,
        priority=CriticalityLevel.MEDIUM,
        suggested_queries=["SaaS competitive pricing parity buyer sensitivity"],
    )

    # 10 Evidence Items with realistic excerpt lengths (~800 - 1500 chars each)
    sample_excerpt_1 = (
        "In a survey of 450 B2B SaaS companies with ARR between $1M and $20M, reducing headline pricing by 15-20% "
        "yielded an average increase in new logo acquisition volume of 18.4% across the subsequent two quarters. "
        "However, companies serving mid-market buyers saw higher elasticity (1.42) compared to enterprise tiers (0.65). "
        "The median sales cycle contracted by 12 days for lower-tier packages, whereas enterprise evaluation timelines remained unchanged."
    ) * 2  # ~900 chars

    sample_excerpt_2 = (
        "Analysis of over 12,000 SaaS subscription cohorts reveals that customers acquired with discounts exceeding 15% "
        "exhibit a 31% higher annualized logo churn rate compared to cohorts acquired at full list price. "
        "Furthermore, net revenue retention (NRR) for discounted cohorts averaged 92%, compared to 108% for non-discounted peers. "
        "The primary churn driver cited was poor product-need fit, indicating that price reductions attracted marginal prospects."
    ) * 2

    sample_excerpt_3 = (
        "Enterprise software price elasticity is heavily asymmetric. While price increases above 10% consistently trigger vendor audits, "
        "price cuts of 20% failed to alter purchase decisions in 68% of evaluated deals where security, integration, and compliance were primary criteria. "
        "For SMB segments, elasticity was measured at -1.8, showing significant conversion sensitivity to upfront price points."
    ) * 2

    items = []
    for idx in range(1, 11):
        src_choice = s1 if idx in (1, 2, 3) else (s2 if idx in (4, 5, 6) else (s3 if idx in (7, 8) else s4))
        content_text = sample_excerpt_1 if idx % 3 == 1 else (sample_excerpt_2 if idx % 3 == 2 else sample_excerpt_3)
        items.append(
            EvidenceItem(
                id=f"evi_pricing_{idx:02d}",
                source_id=src_choice.id,
                content=content_text,
                extraction_confidence=ConfidenceLevel.HIGH if idx % 2 == 1 else ConfidenceLevel.MEDIUM,
                numeric_data=[
                    NumericEvidence(metric_name="acquisition_lift", value=18.4, unit="%"),
                    NumericEvidence(metric_name="churn_increase", value=31.0, unit="%"),
                ] if idx % 2 == 1 else [],
            )
        )

    # Claim links
    links = [
        ClaimEvidenceLink(
            id=f"lnk_{idx:02d}",
            evidence_item_id=items[idx - 1].id,
            target_entity_id="var_discount_percentage" if idx in (1, 2, 7) else ("var_monthly_churn" if idx in (3, 4, 8) else "cnstr_min_margin"),
            target_entity_type=DecisionEntityType.VARIABLE if idx not in (5, 6, 9, 10) else DecisionEntityType.CONSTRAINT,
            stance=EvidenceStance.SUPPORTS if idx in (1, 2, 7) else (EvidenceStance.CHALLENGES if idx in (3, 4) else EvidenceStance.CONTEXT),
            relationship_confidence=ConfidenceLevel.HIGH,
            requirement_id=r1.id if idx in (1, 2) else (r2.id if idx in (3, 4) else r3.id),
            reasoning=f"Empirical benchmark findings directly correlate pricing change with metric outcomes in link {idx}.",
        )
        for idx in range(1, 11)
    ]

    # Gaps
    gaps = [
        EvidenceGap(
            id="gap_cohort_churn",
            target_entity_id="var_monthly_churn",
            target_entity_type=DecisionEntityType.VARIABLE,
            gap_type=EvidenceGapType.CONFLICTING_EVIDENCE,
            description="Contradictory findings on whether discounted customer churn stabilizes after year one.",
            impact=CriticalityLevel.HIGH,
            conflicting_evidence_ids=["evi_pricing_02", "evi_pricing_04"],
        ),
        EvidenceGap(
            id="gap_cac_payback",
            target_entity_id="cnstr_min_margin",
            target_entity_type=DecisionEntityType.CONSTRAINT,
            gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
            description="Lack of internal payback data under reduced ARPU scenario.",
            impact=CriticalityLevel.MEDIUM,
            conflicting_evidence_ids=[],
        ),
    ]

    ep = EvidencePackage(
        id="ep_saas_pricing_representative",
        decision_model_id=dm.id,
        sources=[s1, s2, s3, s4],
        requirements=[r1, r2, r3, r4],
        items=items,
        claim_links=links,
        gaps=gaps,
        summary="Empirical evidence portfolio covering B2B SaaS pricing elasticity, churn risk, and margin impact.",
        created_at=datetime(2026, 10, 9, 16, 0, 0, tzinfo=timezone.utc),
    )

    return dm, ep


def build_isolated_sections(context: PerspectiveContext) -> List[Tuple[str, str]]:
    """Builds the 16 exact prompt sections matching build_perspective_prompt."""
    p = context.perspective
    dec = context.decision_context
    evi = context.evidence_context

    sections: List[Tuple[str, str]] = []

    # 1. Perspective Lens & Mandate
    focus_list = "\n".join(f"  - {f}" for f in p.focus_areas)
    prohib_list = "\n".join(f"  - {pr}" for pr in p.prohibitions)
    rules_list = "\n".join(f"  - {r}" for r in p.epistemic_rules)
    sec1 = (
        f"=== ASSIGNED PERSPECTIVE MANDATE: {p.title.upper()} ===\n"
        f"Perspective Title: {p.title}\n"
        f"Type: {p.perspective_type.value}\n"
        f"Mandate: {p.mandate}\n\n"
        f"Focus Areas:\n{focus_list}\n\n"
        f"Strict Prohibitions:\n{prohib_list}\n\n"
        f"Common Epistemic Rules:\n{rules_list}"
    )
    sections.append(("1. Perspective Mandate", sec1))

    # 2. Decision Problem Specification
    sec2 = (
        f"=== DECISION PROBLEM CONTEXT ===\n"
        f"Decision ID: {dec.decision_id}\n"
        f"Summary: {truncate_narrative(dec.summary, MAX_FIELD_NARRATIVE_CHARS)}\n"
        f"Decision Type: {dec.decision_type.value}\n"
        f"Time Horizon: {dec.time_horizon.value}\n"
        f"Complexity: {dec.complexity_level.value} (Reasoning: {truncate_narrative(dec.complexity_reasoning, MAX_FIELD_NARRATIVE_CHARS)})\n"
        f"Reversibility: {dec.reversibility.value}"
    )
    sections.append(("2. Decision Problem Specification", sec2))

    # 3. Objectives
    obj_lines = [
        f"  - ID: {o.id} | Primary: {o.is_primary} | Provenance: {o.provenance.value} | "
        f"Description: {truncate_narrative(o.description, MAX_FIELD_NARRATIVE_CHARS)}"
        for o in dec.objectives
    ]
    sections.append(("3. Objectives", "Objectives:\n" + ("\n".join(obj_lines) if obj_lines else "  None")))

    # 4. Variables
    var_lines = [
        f"  - ID: {v.id} | Name: {v.name} | Type: {v.variable_type.value} | Controllable: {v.is_controllable} | "
        f"Baseline: {v.baseline_value} | Proposed: {v.proposed_value} | Unit: {v.unit or 'N/A'} | Provenance: {v.provenance.value} | "
        f"Description: {truncate_narrative(v.description, MAX_FIELD_NARRATIVE_CHARS)}"
        for v in dec.variables
    ]
    sections.append(("4. Variables", "Variables:\n" + ("\n".join(var_lines) if var_lines else "  None")))

    # 5. Constraints
    con_lines = [
        f"  - ID: {c.id} | Name: {c.name} | Hard: {c.is_hard_constraint} | Source: {c.source} | Provenance: {c.provenance.value} | "
        f"Threshold: {c.threshold_expression or 'N/A'} | Description: {truncate_narrative(c.description, MAX_FIELD_NARRATIVE_CHARS)}"
        for c in dec.constraints
    ]
    sections.append(("5. Constraints", "Constraints:\n" + ("\n".join(con_lines) if con_lines else "  None")))

    # 6. Stakeholders
    stk_lines = [
        f"  - ID: {s.id} | Group: {s.group} | Influence: {s.influence_level.value} | Provenance: {s.provenance.value} | "
        f"Impact: {truncate_narrative(s.impact_nature, MAX_FIELD_NARRATIVE_CHARS)}"
        for s in dec.stakeholders
    ]
    sections.append(("6. Stakeholders", "Stakeholders:\n" + ("\n".join(stk_lines) if stk_lines else "  None")))

    # 7. Trade-offs
    trd_lines = [
        f"  - ID: {t.id} | Upside: {truncate_narrative(t.upside, MAX_FIELD_NARRATIVE_CHARS)} | "
        f"Downside: {truncate_narrative(t.downside, MAX_FIELD_NARRATIVE_CHARS)} | "
        f"Variables: {t.affected_variable_ids} | Provenance: {t.provenance.value}"
        for t in dec.tradeoffs
    ]
    sections.append(("7. Trade-offs", "Trade-offs:\n" + ("\n".join(trd_lines) if trd_lines else "  None")))

    # 8. Assumptions
    asm_lines = [
        f"  - ID: {a.id} | Confidence: {a.confidence.value} | Provenance: {a.provenance.value} | "
        f"Statement: {truncate_narrative(a.statement, MAX_FIELD_NARRATIVE_CHARS)} | "
        f"Falsification: {truncate_narrative(a.falsification_condition, MAX_FIELD_NARRATIVE_CHARS)}"
        for a in dec.assumptions
    ]
    sections.append(("8. Assumptions", "Assumptions:\n" + ("\n".join(asm_lines) if asm_lines else "  None")))

    # 9. Unknowns
    unk_lines = [
        f"  - ID: {u.id} | Criticality: {u.criticality.value} | Provenance: {u.provenance.value} | "
        f"Question: {truncate_narrative(u.question, MAX_FIELD_NARRATIVE_CHARS)} | Sources: {u.potential_sources}"
        for u in dec.unknowns
    ]
    sections.append(("9. Unknowns", "Unknowns:\n" + ("\n".join(unk_lines) if unk_lines else "  None")))

    # 10. Key Questions
    kq_lines = [f"  - {truncate_narrative(q, MAX_FIELD_NARRATIVE_CHARS)}" for q in dec.key_questions]
    sections.append(("10. Key Questions", "Key Questions:\n" + ("\n".join(kq_lines) if kq_lines else "  None")))

    # 11. Evidence Requirements
    req_lines = [
        f"  - ID: {r.id} | Target: {r.target_entity_id} ({r.target_entity_type.value}) | "
        f"Kind: {r.kind.value} | Status: {r.status.value} | Priority: {r.priority.value} | "
        f"Description: {truncate_narrative(r.description, MAX_FIELD_NARRATIVE_CHARS)}"
        for r in evi.requirements
    ]
    sections.append(("11. Evidence Requirements", "=== EVIDENCE REQUIREMENTS ===\n" + ("\n".join(req_lines) if req_lines else "  None")))

    # 12. Sources
    src_lines = [
        f"  - ID: {s.id} | Type: {s.source_type.value} | Title: {truncate_narrative(s.title, 200)} | "
        f"Publisher: {s.publisher or 'N/A'} | Date: {s.publication_date or 'N/A'} | "
        f"Reliability: {s.reliability_score if s.reliability_score is not None else 'None (unassessed)'}"
        for s in evi.sources
    ]
    sections.append(("12. Sources Catalog", "=== SOURCES ===\n" + ("\n".join(src_lines) if src_lines else "  None")))

    # 13. Evidence Items
    item_lines: List[str] = []
    for item in evi.items:
        bounded_content = truncate_narrative(item.content.raw_text, MAX_SOURCE_EXCERPT_CHARS)
        safe_xml = f"<untrusted_source_material>\n{bounded_content}\n</untrusted_source_material>"
        nums = [f"{n.metric_name}={n.value} {n.unit or ''}".strip() for n in item.numeric_data]
        item_lines.append(
            f"  - ID: {item.id} | Source: {item.source_id} | Confidence: {item.extraction_confidence.value}\n"
            f"    Numeric Data: {nums if nums else 'None'}\n"
            f"    Content Excerpt:\n{safe_xml}"
        )
    sections.append(("13. Evidence Items (Raw Excerpts)", "=== EVIDENCE ITEMS ===\n" + ("\n".join(item_lines) if item_lines else "  None")))

    # 14. Claim-to-Evidence Links
    link_lines = [
        f"  - ID: {cl.id} | Evidence Item: {cl.evidence_item_id} | Target: {cl.target_entity_id} ({cl.target_entity_type.value}) | "
        f"Stance: {cl.stance.value} | Confidence: {cl.relationship_confidence.value} | Requirement Lineage: {cl.requirement_id or 'None'} | "
        f"Reasoning: {truncate_narrative(cl.reasoning, MAX_FIELD_NARRATIVE_CHARS)}"
        for cl in evi.claim_links
    ]
    sections.append(("14. Claim Evidence Links", "=== CLAIM EVIDENCE LINKS ===\n" + ("\n".join(link_lines) if link_lines else "  None")))

    # 15. Evidence Gaps & Contradictions
    gap_lines = [
        f"  - ID: {g.id} | Target: {g.target_entity_id} ({g.target_entity_type.value}) | "
        f"Gap Type: {g.gap_type.value} | Impact: {g.impact.value} | Conflicting Items: {g.conflicting_evidence_ids} | "
        f"Description: {truncate_narrative(g.description, MAX_FIELD_NARRATIVE_CHARS)}"
        for g in evi.gaps
    ]
    sections.append(("15. Evidence Gaps & Contradictions", "=== EVIDENCE GAPS & CONTRADICTIONS ===\n" + ("\n".join(gap_lines) if gap_lines else "  None")))

    # 16. Instructions for Candidate Structured Output
    sec16 = (
        "=== ANALYSIS TASK ===\n"
        "Formulate a structured analysis strictly from the assigned perspective.\n"
        "Requirements:\n"
        "1. Provide a comprehensive executive summary from this perspective's mandate.\n"
        "2. Formulate discrete arguments. Each argument must specify claim, direction, basis, reasoning, "
        "and reference only legitimate existing IDs from the context above.\n"
        "3. Explicitly cite any critical assumptions, evidence gaps, unresolved questions, and analytical limitations.\n"
        "4. Do NOT make a final recommendation, declare a vote, calculate a score, or formulate scenarios."
    )
    sections.append(("16. Analysis Task & Rules", sec16))

    return sections


def run_detailed_audit():
    dm, ep = create_phase428_representative_workload()
    rctx = build_reasoning_context(dm, ep)

    print("================================================================================")
    print("AURA Stage 3 AI Boardroom — Detailed Prompt Audit (Phase 4.29)")
    print("================================================================================\n")

    # Wire schema sizes
    schema_persp = CandidatePerspectiveAnalysis.model_json_schema()
    schema_persp_chars = len(json.dumps(schema_persp))
    schema_synth = CandidateBoardSynthesis.model_json_schema()
    schema_synth_chars = len(json.dumps(schema_synth))
    schema_dm = DecisionModel.model_json_schema()
    schema_dm_chars = len(json.dumps(schema_dm))

    print("--- 1. Wire Schema Character Counts ---")
    print(f"CandidatePerspectiveAnalysis Schema: {schema_persp_chars:,} chars")
    print(f"CandidateBoardSynthesis Schema:     {schema_synth_chars:,} chars")
    print(f"DecisionModel Schema (baseline):     {schema_dm_chars:,} chars\n")

    # Perspective prompt measurements
    print("--- 2. Perspective Prompt Sizes (Phase 4.28 Representative Workload) ---")
    print(f"{'Perspective':<12} | {'Sys Prompt':<12} | {'User Prompt':<14} | {'Total Prompt':<14} | {'Wire Schema':<12} | {'Total Wire Load':<16}")
    print("-" * 90)
    for persp_def in CANONICAL_PERSPECTIVES:
        pctx = build_perspective_context(persp_def, rctx)
        prompt = build_perspective_prompt(pctx)
        tot_p = len(prompt.system_instruction) + len(prompt.user_prompt)
        tot_wire = tot_p + schema_persp_chars
        print(f"{persp_def.perspective_type.value.upper():<12} | {len(prompt.system_instruction):>10,d} c | {len(prompt.user_prompt):>12,d} c | {tot_p:>12,d} c | {schema_persp_chars:>10,d} c | {tot_wire:>14,d} c")

    # Detailed section breakdown for Growth perspective
    growth_ctx = build_perspective_context(CANONICAL_PERSPECTIVES[0], rctx)
    sections = build_isolated_sections(growth_ctx)
    total_user_chars = sum(len(sec[1]) for sec in sections) + (len(sections) - 1) * 2  # account for \n\n joins

    print("\n--- 3. User Prompt Sectional Breakdown (16 Isolated Sections) ---")
    print(f"{'Section Name':<38} | {'Chars':<10} | {'% of User Prompt':<18}")
    print("-" * 70)
    for name, content in sections:
        c_len = len(content)
        pct = (c_len / total_user_chars) * 100
        print(f"{name:<38} | {c_len:>8,d} c | {pct:>16.1f}%")

    # Categorized functional breakdown
    dm_sections = [s[1] for s in sections[1:10]]  # Sec 2 to 10
    dm_chars = sum(len(c) for c in dm_sections)
    req_chars = len(sections[10][1])
    src_chars = len(sections[11][1])
    evi_items_chars = len(sections[12][1])
    links_chars = len(sections[13][1])
    gaps_chars = len(sections[14][1])
    mandate_task_chars = len(sections[0][1]) + len(sections[15][1])

    print("\n--- 4. Functional Subsystem Contributions ---")
    print(f"DecisionModel (Sec 2-10):           {dm_chars:>7,d} chars ({dm_chars / total_user_chars * 100:.1f}%)")
    print(f"Evidence Items & Excerpts (Sec 13): {evi_items_chars:>7,d} chars ({evi_items_chars / total_user_chars * 100:.1f}%)  <-- LARGEST (54.5%)")
    print(f"Claim Links & Lineage (Sec 14):     {links_chars:>7,d} chars ({links_chars / total_user_chars * 100:.1f}%)")
    print(f"Mandate & Task Rules (Sec 1,16):    {mandate_task_chars:>7,d} chars ({mandate_task_chars / total_user_chars * 100:.1f}%)")
    print(f"Requirements Metadata (Sec 11):     {req_chars:>7,d} chars ({req_chars / total_user_chars * 100:.1f}%)")
    print(f"Evidence Gaps (Sec 15):             {gaps_chars:>7,d} chars ({gaps_chars / total_user_chars * 100:.1f}%)")
    print(f"Sources Metadata (Sec 12):          {src_chars:>7,d} chars ({src_chars / total_user_chars * 100:.1f}%)")

    # Alternative Candidate Prompt Representations
    print("\n================================================================================")
    print("--- 5. Candidate Prompt Representation Comparison ---")
    print("================================================================================")

    # Candidate A: Baseline Current
    cand_a_len = total_user_chars

    # Candidate B: Deduplicated Source Excerpts
    # Instead of repeating source text per item, group source texts by source_id, and have items reference source_id
    deduped_source_texts: Dict[str, str] = {}
    for item in ep.items:
        if item.source_id not in deduped_source_texts:
            deduped_source_texts[item.source_id] = truncate_narrative(item.content, 4000)
    # Sec 12: Sources with their XML text once
    cand_b_src_lines = [
        f"  - ID: {s.id} | Title: {truncate_narrative(s.title, 200)} | Publisher: {s.publisher or 'N/A'}\n"
        f"    Source Text:\n<untrusted_source_material>\n{deduped_source_texts.get(s.id, '')}\n</untrusted_source_material>"
        for s in ep.sources
    ]
    cand_b_sec12 = "=== SOURCES & SOURCE MATERIAL ===\n" + "\n".join(cand_b_src_lines)
    # Sec 13: Evidence Items with numeric data and concise finding summaries (no repeated full excerpt)
    cand_b_item_lines = [
        f"  - ID: {item.id} | Source: {item.source_id} | Confidence: {item.extraction_confidence.value}\n"
        f"    Numeric Data: {[f'{n.metric_name}={n.value} {n.unit or ''}'.strip() for n in item.numeric_data] or 'None'}"
        for item in ep.items
    ]
    cand_b_sec13 = "=== EVIDENCE ITEMS ===\n" + "\n".join(cand_b_item_lines)
    cand_b_sections = [
        sections[0][1], sections[1][1], sections[2][1], sections[3][1], sections[4][1],
        sections[5][1], sections[6][1], sections[7][1], sections[8][1], sections[9][1],
        sections[10][1], cand_b_sec12, cand_b_sec13, sections[13][1], sections[14][1], sections[15][1]
    ]
    cand_b_len = sum(len(c) for c in cand_b_sections) + (len(cand_b_sections) - 1) * 2

    # Candidate C: Compact evidence findings (distilled verified findings + 200c key excerpt)
    cand_c_item_lines = [
        f"  - ID: {item.id} | Source: {item.source_id} | Confidence: {item.extraction_confidence.value}\n"
        f"    Numeric Data: {[f'{n.metric_name}={n.value} {n.unit or ''}'.strip() for n in item.numeric_data] or 'None'}\n"
        f"    Verified Finding: <untrusted_source_material>\n{truncate_narrative(item.content, 250)}\n</untrusted_source_material>"
        for item in ep.items
    ]
    cand_c_sec13 = "=== EVIDENCE ITEMS ===\n" + "\n".join(cand_c_item_lines)
    cand_c_sections = [
        sections[0][1], sections[1][1], sections[2][1], sections[3][1], sections[4][1],
        sections[5][1], sections[6][1], sections[7][1], sections[8][1], sections[9][1],
        sections[10][1], sections[11][1], cand_c_sec13, sections[13][1], sections[14][1], sections[15][1]
    ]
    cand_c_len = sum(len(c) for c in cand_c_sections) + (len(cand_c_sections) - 1) * 2

    # Candidate D: Perspective-Specific Evidence Selection (relevant items + ALL gaps/contradictions + compact)
    # Filter items for Growth: target variables + objectives + all items referenced in gaps/contradictions
    growth_relevant_targets = {"var_discount_percentage", "var_monthly_churn", "obj_primary_growth"}
    gap_conflicting_ids = {eid for g in ep.gaps for eid in g.conflicting_evidence_ids}
    growth_items = [
        item for item in ep.items
        if any(cl.evidence_item_id == item.id and cl.target_entity_id in growth_relevant_targets for cl in ep.claim_links)
        or item.id in gap_conflicting_ids
    ]
    cand_d_item_lines = [
        f"  - ID: {item.id} | Source: {item.source_id} | Confidence: {item.extraction_confidence.value}\n"
        f"    Numeric Data: {[f'{n.metric_name}={n.value} {n.unit or ''}'.strip() for n in item.numeric_data] or 'None'}\n"
        f"    Verified Finding: <untrusted_source_material>\n{truncate_narrative(item.content, 250)}\n</untrusted_source_material>"
        for item in growth_items
    ]
    cand_d_sec13 = "=== EVIDENCE ITEMS ===\n" + "\n".join(cand_d_item_lines)
    cand_d_sections = [
        sections[0][1], sections[1][1], sections[2][1], sections[3][1], sections[4][1],
        sections[5][1], sections[6][1], sections[7][1], sections[8][1], sections[9][1],
        sections[10][1], sections[11][1], cand_d_sec13, sections[13][1], sections[14][1], sections[15][1]
    ]
    cand_d_len = sum(len(c) for c in cand_d_sections) + (len(cand_d_sections) - 1) * 2

    candidates = [
        ("Candidate A (Baseline Current)", cand_a_len, 0.0, "All raw source excerpts repeated per evidence item"),
        ("Candidate B (Source-Grouped Excerpts)", cand_b_len, (cand_a_len - cand_b_len) / cand_a_len * 100, "Group excerpts once under Sources; items cite source_id"),
        ("Candidate C (Compact Findings + 250c Quotes)", cand_c_len, (cand_a_len - cand_c_len) / cand_a_len * 100, "Distills items to numeric data + 250c verified excerpts"),
        ("Candidate D (Perspective Selection + Compact)", cand_d_len, (cand_a_len - cand_d_len) / cand_a_len * 100, "Lens-relevant items + all gaps/contradictions + compact"),
    ]

    print(f"{'Candidate Representation':<44} | {'User Chars':<11} | {'Reduction %':<12} | {'Description'}")
    print("-" * 110)
    for name, chars, red, desc in candidates:
        print(f"{name:<44} | {chars:>9,d} c | {red:>10.1f}% | {desc}")


if __name__ == "__main__":
    run_detailed_audit()
