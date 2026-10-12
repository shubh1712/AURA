"""Alternative Option Comparison Service (Day 8G-B).

Provides transparent, qualitative, and empirical comparison across all viable alternatives.
Evaluates explicit criteria supported by available data without manufacturing weighted scores.
Clearly states when data is insufficient to responsibly rank options.
"""

import logging
from typing import List, Optional

from app.schemas.decision_integrity import (
    OptionComparisonItem,
    OptionComparisonReport,
)
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.recommendation import AlternativeOption, DecisionRecommendation

logger = logging.getLogger(__name__)


class OptionComparisonService:
    """Builds an objective comparison matrix comparing all viable alternatives."""

    def compare_options(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        recommendation: DecisionRecommendation,
    ) -> OptionComparisonReport:
        """Constructs an OptionComparisonReport across all alternatives."""
        options: List[OptionComparisonItem] = []

        # 1. Primary Recommended Option
        rec_title = (
            getattr(recommendation, "recommended_action", "")
            or getattr(recommendation, "executive_summary", "")
        ).split(".")[0].strip() or "Primary Recommended Direction"
        if len(rec_title) > 80:
            rec_title = rec_title[:77] + "..."

        rec_rationale = getattr(recommendation, "executive_rationale", "") or getattr(recommendation, "rationale", "")

        actions = (
            recommendation.action_plan.actions
            if hasattr(recommendation, "action_plan") and hasattr(recommendation.action_plan, "actions")
            else (getattr(recommendation, "action_plan", []) or [])
        )
        rec_strengths = [
            getattr(a, "description", getattr(a, "title", "")) for a in actions[:3]
        ] if actions else ["Formally recommended direction by AI consensus."]

        rec_weaknesses = [
            getattr(r, "description", str(r)) for r in getattr(recommendation, "risk_mitigations", [])[:3]
        ] if getattr(recommendation, "risk_mitigations", None) else ["Requires active monitoring and staged rollback gates."]

        options.append(
            OptionComparisonItem(
                option_id="opt_recommended",
                title=f"[Recommended] {rec_title}",
                description=rec_rationale[:250] + ("..." if len(rec_rationale) > 250 else ""),
                is_recommended=True,
                strengths=rec_strengths,
                weaknesses=rec_weaknesses,
                constraint_compatibility="Satisfies evaluated baseline constraints",
                supporting_evidence_count=len(evidence_package.sources),
                missing_evidence=[g.description for g in evidence_package.gaps[:2]] if evidence_package.gaps else [],
                key_tradeoffs=[
                    getattr(t, "description", None) or f"{getattr(t, 'upside', '')} vs {getattr(t, 'downside', '')}"
                    for t in decision_model.tradeoffs[:2]
                ] if decision_model.tradeoffs else ["Implementation investment vs operational gain"],
                feasibility_status="feasible",
            )
        )

        # 2. Alternative Options from Stage 4
        for idx, alt in enumerate(recommendation.alternative_options):
            alt_id = f"opt_alt_{idx+1}"
            alt_name = getattr(alt, "name", f"Alternative {idx+1}")
            alt_desc = getattr(alt, "description", "") or "Alternative approach identified during decision framing."
            alt_pros = getattr(alt, "pros", "") or "; ".join(getattr(alt, "tradeoffs", []))
            alt_cons = getattr(alt, "cons", "") or getattr(alt, "why_not_recommended", "")
            alt_tradeoff = getattr(alt, "tradeoff_vs_recommended", "") or "; ".join(getattr(alt, "tradeoffs", [])) or "Partial"

            tradeoffs = [f"Pros: {alt_pros}", f"Cons: {alt_cons}"] if alt_pros and alt_cons else []

            options.append(
                OptionComparisonItem(
                    option_id=alt_id,
                    title=alt_name,
                    description=alt_desc,
                    is_recommended=False,
                    strengths=[alt_pros] if alt_pros else ["Preserves flexibility or requires lower immediate commitment."],
                    weaknesses=[alt_cons] if alt_cons else ["May not fully address primary objective targets."],
                    constraint_compatibility=f"Feasibility relative to baseline: {alt_tradeoff}",
                    supporting_evidence_count=0,  # Alternatives rarely receive independent evidence searches
                    missing_evidence=[
                        "Detailed empirical cost/benefit benchmarks for this specific alternative are unmeasured."
                    ],
                    key_tradeoffs=tradeoffs or ["Lower implementation risk vs reduced capability ceiling"],
                    feasibility_status="partially_evaluated",
                )
            )

        # Determine if ranking is justified
        has_multiple_options = len(options) > 1
        has_deep_alt_data = any(opt.supporting_evidence_count > 0 for opt in options[1:])
        ranking_justified = has_multiple_options and has_deep_alt_data

        unranked_reason = None
        if not ranking_justified and has_multiple_options:
            unranked_reason = (
                "Only the primary recommended option received detailed multi-stage resilience and evidence analysis. "
                "Alternative options lack equivalent empirical benchmarks, preventing responsible mathematical ranking."
            )

        summary = (
            f"Evaluated {len(options)} viable alternatives against stated objectives. "
            f"Primary option '{options[0].title}' was evaluated in depth; "
            + (
                "alternative options require scoped pilot validation before definitive ordinal ranking."
                if not ranking_justified
                else "options are ranked based on available constraint satisfaction and evidence."
            )
        )

        criteria = [
            "Financial Cost",
            "Downside Risk",
            "Constraint Satisfaction",
            "Implementation Complexity",
            "Reversibility",
            "Evidence Strength",
        ]

        return OptionComparisonReport(
            options=options,
            evaluation_criteria=criteria,
            ranking_justified=ranking_justified,
            unranked_reason=unranked_reason,
            summary=summary,
        )
