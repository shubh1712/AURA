"""AURA Authoritative PDF Report Generator (Day 8G-C).

Generates high-fidelity executive Summary (2-4 pages) and complete Detailed Audit PDFs
using ReportLab vector formatting. Strictly adheres to AURA design aesthetics:
- Primary Navy (#0F172A) & Deep Slate (#1E293B)
- Accent Cyan (#0284C7) & Emerald (#10B981) & Amber (#F59E0B) & Rose (#E11D48)
- Zero Gemini calls. Uses normalized SharedReportModel facts exclusively.
- Clean page breaks, wrapping tables, and no clipped content.
"""

from io import BytesIO
import logging
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import SharedReportModel

logger = logging.getLogger(__name__)

# AURA Brand Palette
NAVY_PRIMARY = colors.HexColor("#0F172A")
SLATE_DARK = colors.HexColor("#1E293B")
SLATE_MUTED = colors.HexColor("#475569")
CYAN_ACCENT = colors.HexColor("#0284C7")
EMERALD_GREEN = colors.HexColor("#059669")
AMBER_WARNING = colors.HexColor("#D97706")
ROSE_CRITICAL = colors.HexColor("#DC2626")
BG_LIGHT = colors.HexColor("#F8FAFC")
BORDER_LIGHT = colors.HexColor("#E2E8F0")


def _get_aura_styles():
    """Builds a curated palette of ReportLab ParagraphStyles."""
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AuraTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=NAVY_PRIMARY,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "AuraSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=SLATE_MUTED,
        spaceAfter=12,
    )

    h2_style = ParagraphStyle(
        "AuraH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=NAVY_PRIMARY,
        spaceBefore=12,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "AuraBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=SLATE_DARK,
        spaceAfter=6,
    )

    body_bold = ParagraphStyle(
        "AuraBodyBold",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    badge_ready = ParagraphStyle(
        "BadgeReady",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=EMERALD_GREEN,
    )

    badge_warn = ParagraphStyle(
        "BadgeWarn",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=AMBER_WARNING,
    )

    badge_crit = ParagraphStyle(
        "BadgeCrit",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=ROSE_CRITICAL,
    )

    table_header = ParagraphStyle(
        "AuraTableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.white,
    )

    table_cell = ParagraphStyle(
        "AuraTableCell",
        parent=body_style,
        fontSize=8,
        leading=11,
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "h2": h2_style,
        "body": body_style,
        "body_bold": body_bold,
        "badge_ready": badge_ready,
        "badge_warn": badge_warn,
        "badge_crit": badge_crit,
        "th": table_header,
        "td": table_cell,
    }


def _page_number_canvas(canvas, doc):
    """Draws consistent footer and page numbering."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SLATE_MUTED)
    page_text = f"Page {doc.page} | AURA Decision Intelligence Platform"
    canvas.drawRightString(doc.pagesize[0] - 0.75 * inch, 0.4 * inch, page_text)
    canvas.drawString(0.75 * inch, 0.4 * inch, "Confidential — Evaluated Deterministically")
    canvas.restoreState()


class AuraPDFGenerator:
    """Generates server-side vector PDFs matching AURA design tokens."""

    def generate_summary_pdf(self, report: SharedReportModel) -> bytes:
        """Generates executive 2-4 page summary PDF."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        styles = _get_aura_styles()
        elements = []

        # 1. Header Banner
        elements.append(Paragraph("AURA EXECUTIVE DECISION SUMMARY", styles["subtitle"]))
        elements.append(Paragraph(report.overview.title, styles["title"]))
        elements.append(
            Paragraph(
                f"Analysis ID: {report.analysis_id} | Readiness: <b>{report.overview.decision_readiness.value.upper()}</b> "
                f"| Integrity: <b>{report.overview.integrity_status.value.upper()}</b>",
                styles["subtitle"],
            )
        )
        elements.append(HRFlowable(width="100%", thickness=1.5, color=CYAN_ACCENT, spaceAfter=10))

        # 2. Recommended Direction Callout Box
        callout_data = [
            [
                Paragraph("<b>RECOMMENDED DIRECTION</b>", styles["body_bold"]),
                Paragraph(f"<b>{report.overview.recommended_direction}</b>", styles["body_bold"]),
            ],
            [
                Paragraph("<b>CORE RATIONALE</b>", styles["body_bold"]),
                Paragraph(report.overview.short_rationale, styles["body"]),
            ],
            [
                Paragraph("<b>FALSIFICATION CONDITION</b>", styles["body_bold"]),
                Paragraph(report.overview.falsification_condition, styles["badge_warn"]),
            ],
        ]
        callout_table = Table(callout_data, colWidths=[1.8 * inch, 5.2 * inch])
        callout_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(callout_table)
        elements.append(Spacer(1, 12))

        # 3. Alternatives Comparison Matrix
        elements.append(Paragraph("Viable Alternatives Comparison", styles["h2"]))
        alt_data = [[
            Paragraph("Option", styles["th"]),
            Paragraph("Strengths", styles["th"]),
            Paragraph("Weaknesses / Downsides", styles["th"]),
            Paragraph("Constraint Compatibility", styles["th"]),
        ]]
        for opt in report.option_comparison.options[:4]:
            alt_data.append([
                Paragraph(f"<b>{opt.title}</b>" + ("<br/><font color='#0284C7'>(Recommended)</font>" if opt.is_recommended else ""), styles["td"]),
                Paragraph("; ".join(opt.strengths[:2]), styles["td"]),
                Paragraph("; ".join(opt.weaknesses[:2]), styles["td"]),
                Paragraph(opt.constraint_compatibility, styles["td"]),
            ])
        alt_table = Table(alt_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.6 * inch])
        alt_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(alt_table)
        elements.append(Spacer(1, 12))

        # Page break before Quantitative & Scenarios
        elements.append(PageBreak())

        # 4. Quantitative Feasibility & Calculations
        elements.append(Paragraph("Deterministic Calculations & Feasibility", styles["h2"]))
        calc_data = [[
            Paragraph("Metric", styles["th"]),
            Paragraph("Formula / Expression", styles["th"]),
            Paragraph("Value / Range", styles["th"]),
            Paragraph("Status", styles["th"]),
        ]]
        for c in report.calculations:
            status_p = (
                Paragraph("<b>FEASIBLE</b>", styles["badge_ready"]) if c.status.value == "feasible"
                else (Paragraph("<b>INFEASIBLE</b>", styles["badge_crit"]) if c.status.value == "infeasible"
                else Paragraph("<b>UNRESOLVED</b>", styles["badge_warn"]))
            )
            val_str = f"{c.value:,.2f} {c.unit or ''}" if c.value is not None else "Inputs missing"
            calc_data.append([
                Paragraph(f"<b>{c.title}</b>", styles["td"]),
                Paragraph(c.formula_expression, styles["td"]),
                Paragraph(val_str, styles["td"]),
                status_p,
            ])
        calc_table = Table(calc_data, colWidths=[1.8 * inch, 2.6 * inch, 1.4 * inch, 1.2 * inch])
        calc_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), SLATE_DARK),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(calc_table)
        elements.append(Spacer(1, 12))

        # 5. Scenario Matrix & Resilience
        elements.append(Paragraph("Scenario Implications & Resilience Scorecard", styles["h2"]))
        scen_data = [[
            Paragraph("Scenario", styles["th"]),
            Paragraph("Weight Note", styles["th"]),
            Paragraph("Implications & Signposts", styles["th"]),
        ]]
        for s in report.scenario_matrix[:3]:
            scen_data.append([
                Paragraph(f"<b>{s.get('name', 'Scenario')}</b>", styles["td"]),
                Paragraph(s.get("probability_label", "Unweighted"), styles["td"]),
                Paragraph("; ".join(s.get("implications", [])[:2]), styles["td"]),
            ])
        scen_table = Table(scen_data, colWidths=[1.8 * inch, 1.4 * inch, 3.8 * inch])
        scen_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), SLATE_DARK),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(scen_table)
        elements.append(Spacer(1, 12))

        # 6. Integrity Findings & Next Steps
        elements.append(Paragraph("Key Integrity Warnings & Action Roadmap", styles["h2"]))
        if report.integrity_findings:
            for f in report.integrity_findings[:3]:
                sev_color = ROSE_CRITICAL if f.severity.value in ("critical", "high") else AMBER_WARNING
                elements.append(Paragraph(f"<b>[{f.severity.value.upper()}] {f.title}</b>", styles["body_bold"]))
                elements.append(Paragraph(f"{f.description} <i>Resolution: {f.suggested_resolution}</i>", styles["body"]))
                elements.append(Spacer(1, 4))
        else:
            elements.append(Paragraph("No critical or high integrity inconsistencies detected.", styles["body"]))

        doc.build(elements, onFirstPage=_page_number_canvas, onLaterPages=_page_number_canvas)
        buffer.seek(0)
        return buffer.getvalue()

    def generate_detailed_pdf(self, report: SharedReportModel) -> bytes:
        """Generates comprehensive multi-page detailed audit PDF."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        styles = _get_aura_styles()
        elements = []

        # Title & Metadata
        elements.append(Paragraph("AURA COMPREHENSIVE DECISION AUDIT REPORT", styles["subtitle"]))
        elements.append(Paragraph(report.overview.title, styles["title"]))
        elements.append(
            Paragraph(
                f"Analysis ID: {report.analysis_id} | Fingerprint: {report.source_fingerprint[:16]}... "
                f"| Evaluated: {report.generated_at}",
                styles["subtitle"],
            )
        )
        elements.append(HRFlowable(width="100%", thickness=2, color=NAVY_PRIMARY, spaceAfter=14))

        # Table of Contents
        elements.append(Paragraph("Table of Contents", styles["h2"]))
        toc_items = [
            "1. Executive Overview & Falsification Conditions",
            "2. Viable Alternative Options Matrix",
            "3. Deterministic Arithmetic & Feasibility Evaluation",
            "4. Scenario Sensitivity & Downside Projections",
            "5. Deterministic Resilience Scorecard",
            "6. AI Boardroom Multi-Perspective Synthesis",
            "7. Evidence Quality Classification & Citation Audit",
            "8. Decision-Impact Ranked Uncertainty & Gaps",
            "9. Cross-Stage Consistency & Integrity Findings",
            "10. Operational Action Roadmap & Decision Gates",
        ]
        for t in toc_items:
            elements.append(Paragraph(f"• <b>{t}</b>", styles["body"]))
        elements.append(Spacer(1, 14))

        # Section 1: Overview
        elements.append(PageBreak())
        elements.append(Paragraph("1. Executive Overview & Falsification Conditions", styles["h2"]))
        elements.append(Paragraph(f"<b>Recommended Direction:</b> {report.overview.recommended_direction}", styles["body_bold"]))
        elements.append(Paragraph(f"<b>Rationale:</b> {report.overview.short_rationale}", styles["body"]))
        elements.append(Paragraph(f"<b>Falsification Condition:</b> {report.overview.falsification_condition}", styles["badge_warn"]))
        elements.append(Spacer(1, 10))

        # Section 2: Option Comparison
        elements.append(Paragraph("2. Viable Alternative Options Matrix", styles["h2"]))
        elements.append(Paragraph(report.option_comparison.summary, styles["body"]))
        if report.option_comparison.unranked_reason:
            elements.append(Paragraph(f"<i>Audit Note: {report.option_comparison.unranked_reason}</i>", styles["subtitle"]))
        for opt in report.option_comparison.options:
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<b>Alternative: {opt.title}</b>", styles["body_bold"]))
            elements.append(Paragraph(f"Summary: {opt.description}", styles["body"]))
            elements.append(Paragraph(f"Strengths: {'; '.join(opt.strengths)}", styles["body"]))
            elements.append(Paragraph(f"Weaknesses: {'; '.join(opt.weaknesses)}", styles["body"]))
            elements.append(Paragraph(f"Constraint Fit: {opt.constraint_compatibility}", styles["body"]))
        elements.append(Spacer(1, 10))

        # Section 3: Calculations
        elements.append(PageBreak())
        elements.append(Paragraph("3. Deterministic Arithmetic & Feasibility Evaluation", styles["h2"]))
        for c in report.calculations:
            elements.append(Paragraph(f"<b>{c.title} [{c.status.value.upper()}]</b>", styles["body_bold"]))
            elements.append(Paragraph(f"Formula: <code>{c.formula_expression}</code>", styles["body"]))
            elements.append(Paragraph(f"Explanation: {c.explanation}", styles["body"]))
            if c.missing_inputs:
                elements.append(Paragraph(f"Missing Inputs: {', '.join(c.missing_inputs)}", styles["badge_warn"]))
            elements.append(Spacer(1, 6))

        # Section 4 & 5: Scenarios & Resilience
        elements.append(Paragraph("4. Scenario Projections & 5. Resilience Scorecard", styles["h2"]))
        elements.append(
            Paragraph(
                f"Resilience Score: <b>{report.resilience_scorecard.get('score', 0):.1f}/100</b> "
                f"({report.resilience_scorecard.get('category', 'Evaluated')})",
                styles["body_bold"],
            )
        )
        elements.append(Paragraph(report.resilience_scorecard.get("explanation", ""), styles["body"]))
        elements.append(Spacer(1, 6))

        # Section 6: Boardroom Perspectives
        elements.append(PageBreak())
        elements.append(Paragraph("6. AI Boardroom Multi-Perspective Synthesis", styles["h2"]))
        for p in report.boardroom_perspectives:
            elements.append(Paragraph(f"<b>Perspective: {p.role}</b>", styles["body_bold"]))
            elements.append(Paragraph(p.perspective, styles["body"]))
            if p.dissent_or_concerns:
                elements.append(Paragraph(f"Dissent/Concerns: {'; '.join(p.dissent_or_concerns)}", styles["badge_warn"]))
            elements.append(Spacer(1, 6))

        # Section 7 & 8: Evidence Quality & Ranked Gaps
        elements.append(Paragraph("7. Evidence Quality & 8. Decision-Impact Ranked Gaps", styles["h2"]))
        elements.append(Paragraph(report.evidence_quality.summary, styles["body"]))
        elements.append(Paragraph(f"<i>{report.uncertainty_calibration.scenario_weights_note}</i>", styles["subtitle"]))
        for gap in report.uncertainty_calibration.ranked_gaps[:5]:
            elements.append(Paragraph(f"<b>Rank #{gap.rank} [{gap.decision_impact.value.upper()}]:</b> {gap.description}", styles["body_bold"]))
            elements.append(Paragraph(f"Action: {gap.concrete_validation_action}", styles["body"]))
            elements.append(Spacer(1, 4))

        # Section 9 & 10: Integrity Findings & Action Roadmap
        elements.append(PageBreak())
        elements.append(Paragraph("9. Cross-Stage Consistency & Integrity Findings", styles["h2"]))
        for f in report.integrity_findings:
            elements.append(Paragraph(f"<b>[{f.severity.value.upper()}] {f.rule_code}: {f.title}</b>", styles["body_bold"]))
            elements.append(Paragraph(f"{f.description}", styles["body"]))
            elements.append(Paragraph(f"Suggested Resolution: {f.suggested_resolution}", styles["body"]))
            elements.append(Spacer(1, 6))

        elements.append(Paragraph("10. Operational Action Roadmap & Decision Gates", styles["h2"]))
        for a in report.action_roadmap:
            elements.append(Paragraph(f"<b>[{a.phase.upper()}] {a.title}</b> (Owner: {a.owner_role}, Timeframe: {a.timeframe})", styles["body_bold"]))
            if a.decision_gate:
                elements.append(Paragraph(f"Gate: {a.decision_gate}", styles["body"]))
            if a.validation_criteria:
                elements.append(Paragraph(f"Validation: {a.validation_criteria}", styles["body"]))
            elements.append(Spacer(1, 4))

        doc.build(elements, onFirstPage=_page_number_canvas, onLaterPages=_page_number_canvas)
        buffer.seek(0)
        return buffer.getvalue()
