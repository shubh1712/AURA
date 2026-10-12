"""Uncertainty Calibration and Decision-Impact Gap Ranking Service (Day 8G-B).

Calibrates uncertainty representations across pipeline stages:
- Distinguishes model heuristic scenario weights from frequentist/calibrated probabilities.
- Audits confidence claims for overconfidence.
- Ranks evidence gaps and unknowns strictly by decision impact without fabricated numeric scores.
- Turns generic knowledge gaps into concrete, testable validation actions.
"""

import logging
from typing import List

from app.schemas.decision_integrity import (
    CalculationResult,
    CalculationStatus,
    GapDecisionImpact,
    RankedEvidenceGap,
    UncertaintyCalibrationReport,
)
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.scenario import ScenarioSet

logger = logging.getLogger(__name__)


class UncertaintyCalibrationService:
    """Audits uncertainty calibration and ranks evidence gaps by decision impact."""

    def evaluate_uncertainty(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        recommendation: DecisionRecommendation,
        scenario_set: ScenarioSet,
        calculations: List[CalculationResult],
    ) -> UncertaintyCalibrationReport:
        """Constructs an UncertaintyCalibrationReport with ranked evidence gaps."""
        warnings: List[str] = []

        # 1. Audit Scenario Probabilities
        has_probabilities = any(s.probability is not None for s in scenario_set.scenarios)
        if has_probabilities:
            warnings.append(
                "Scenario probabilities are qualitative model heuristics, not frequentist statistical likelihoods. "
                "Do not treat 20% / 55% / 25% weights as empirical actuarial forecasts."
            )

        # 2. Check for Overstated Confidence
        confidence_str = str(getattr(recommendation, "confidence_score", "")).lower()
        if "high" in confidence_str or (isinstance(getattr(recommendation, "confidence_score", None), (int, float)) and getattr(recommendation, "confidence_score", 0) > 0.8):
            if len(evidence_package.sources) < 2 or len(evidence_package.gaps) > 2:
                warnings.append(
                    "Recommendation displays high confidence despite sparse empirical citations "
                    f"({len(evidence_package.sources)} source(s)) and {len(evidence_package.gaps)} unresolved gap(s)."
                )

        # 3. Decision-Impact Ranked Evidence Gaps
        ranked_gaps: List[RankedEvidenceGap] = []
        rank_counter = 1

        # Priority 1: Gaps that block mathematical calculations
        for calc in calculations:
            if calc.status == CalculationStatus.UNRESOLVED:
                for mi in calc.missing_inputs:
                    ranked_gaps.append(
                        RankedEvidenceGap(
                            gap_id=f"gap_calc_{rank_counter}",
                            description=f"Missing input '{mi}' required to resolve {calc.title}.",
                            decision_impact=GapDecisionImpact.BLOCKS_CALCULATION,
                            rank=rank_counter,
                            concrete_validation_action=(
                                f"Audit historical finance/billing data to establish an empirical value for '{mi}'."
                            ),
                        )
                    )
                    rank_counter += 1

        # Priority 2: Gaps that determine hard constraint satisfaction
        for cnstr in decision_model.constraints:
            stmt = getattr(cnstr, "statement", None) or getattr(cnstr, "description", "")
            is_hard = (
                getattr(cnstr, "is_hard", False)
                or getattr(cnstr, "is_hard_constraint", False)
                or "hard" in stmt.lower()
                or "must" in stmt.lower()
            )
            if is_hard:
                ranked_gaps.append(
                    RankedEvidenceGap(
                        gap_id=f"gap_cnstr_{rank_counter}",
                        description=f"Unverified compliance with non-negotiable constraint: '{stmt}'.",
                        decision_impact=GapDecisionImpact.DETERMINES_HARD_CONSTRAINT,
                        rank=rank_counter,
                        concrete_validation_action=(
                            f"Run technical proof-of-concept benchmark measuring strict adherence to '{stmt}'."
                        ),
                    )
                )
                rank_counter += 1

        # Priority 3: Gaps from Stage 2 Evidence Package
        for gap in evidence_package.gaps:
            desc = gap.description
            impact = GapDecisionImpact.EXPANSION_GATE_DEPENDENCY
            action = f"Execute targeted research or vendor trial addressing '{desc}'."

            if any(term in desc.lower() for term in ["alternative", "switch", "fallback"]):
                impact = GapDecisionImpact.CHANGES_PREFERRED_OPTION
                action = f"Benchmark alternative solution against current baseline for '{desc}'."

            ranked_gaps.append(
                RankedEvidenceGap(
                    gap_id=gap.id or f"gap_ev_{rank_counter}",
                    description=desc,
                    decision_impact=impact,
                    rank=rank_counter,
                    concrete_validation_action=action,
                )
            )
            rank_counter += 1

        # Priority 4: Decision Model Unknowns
        for unk in decision_model.unknowns[:3]:
            unk_text = getattr(unk, "question", None) or getattr(unk, "description", str(unk))
            ranked_gaps.append(
                RankedEvidenceGap(
                    gap_id=unk.id or f"gap_unk_{rank_counter}",
                    description=unk_text,
                    decision_impact=GapDecisionImpact.INFORMATIONAL,
                    rank=rank_counter,
                    concrete_validation_action=f"Consult domain stakeholders: {unk_text}",
                )
            )
            rank_counter += 1

        return UncertaintyCalibrationReport(
            is_calibrated=False,
            scenario_weights_note=(
                "Scenario distribution weights reflect qualitative generative heuristics and must not be interpreted "
                "as calibrated actuarial likelihoods. Real-world tail risk requires explicit hedging."
            ),
            ranked_gaps=ranked_gaps,
            calibration_warnings=warnings,
        )
