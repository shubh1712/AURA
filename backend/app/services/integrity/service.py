"""Decision Integrity Service (Day 8G-A & Day 8G-B).

Orchestrates deterministic calculations, cross-stage consistency checks, alternative
option comparisons, evidence quality classifications, and decision readiness evaluations.
Never invokes Gemini. Authoritative, reproducible, and cached by artifact fingerprint.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.schemas.action_intelligence import IntelligentActionPlan
from app.schemas.analysis import AnalysisResponse
from app.schemas.decision_integrity import (
    DecisionIntegrityReport,
    DecisionReadinessStatus,
    FindingStatus,
    IntegritySeverity,
    IntegrityStatus,
    INTEGRITY_RULE_VERSION,
)
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.integrity.calculator import DeterministicCalculator
from app.services.integrity.checker import CrossStageConsistencyChecker
from app.services.integrity.evidence_quality import EvidenceQualityService
from app.services.integrity.options import OptionComparisonService
from app.services.integrity.uncertainty import UncertaintyCalibrationService
from app.services.jobs.manager import AnalysisJobManager

logger = logging.getLogger(__name__)


def _compute_analysis_fingerprint(analysis: AnalysisResponse) -> str:
    """Computes a deterministic SHA-256 fingerprint from the 6 analysis stages."""
    decision_model = getattr(analysis, "decision_model", None)
    recommendation = getattr(analysis, "recommendation", None)
    scenarios = getattr(analysis, "scenarios", None) or getattr(analysis, "scenario_set", None)
    resilience = getattr(analysis, "resilience", None) or getattr(analysis, "resilience_report", None)

    constraint_texts = []
    if decision_model and getattr(decision_model, "constraints", None):
        for c in decision_model.constraints:
            text = getattr(c, "statement", None) or getattr(c, "description", None) or getattr(c, "name", None) or str(c)
            constraint_texts.append(str(text))

    rec_summary = ""
    gate_names = []
    if recommendation:
        rec_summary = (
            getattr(recommendation, "executive_rationale", None)
            or getattr(recommendation, "recommended_action", None)
            or getattr(recommendation, "executive_summary", "")
        )
        action_plan = getattr(recommendation, "action_plan", None)
        if action_plan:
            actions = getattr(action_plan, "actions", []) if not isinstance(action_plan, list) else action_plan
            for act in actions:
                for g in getattr(act, "decision_gates", []) or []:
                    gate_names.append(
                        getattr(g, "target_milestone", None)
                        or getattr(g, "name", None)
                        or getattr(g, "condition", str(g))
                    )
        for g in getattr(recommendation, "decision_gates", []) or []:
            gate_names.append(getattr(g, "name", None) or getattr(g, "condition", str(g)))

    scenario_names = []
    if scenarios and getattr(scenarios, "scenarios", None):
        for s in scenarios.scenarios:
            scenario_names.append(getattr(s, "name", str(s)))

    res_score = None
    if resilience:
        res_score = getattr(resilience, "overall_score", None) or getattr(resilience, "composite_score", None)

    dec_summary = ""
    if decision_model and getattr(decision_model, "decision", None):
        dec_summary = getattr(decision_model.decision, "summary", "") or ""

    objectives = []
    if decision_model and getattr(decision_model, "objectives", None):
        objectives = [getattr(o, "description", "") for o in decision_model.objectives]

    payload = {
        "analysis_id": getattr(analysis, "analysis_id", ""),
        "decision_summary": dec_summary,
        "objectives": objectives,
        "constraints": constraint_texts,
        "recommendation_summary": rec_summary,
        "recommendation_gates": gate_names,
        "scenarios": scenario_names,
        "resilience_score": res_score,
    }
    dumped = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


class DecisionIntegrityService:
    """Evaluates decision integrity deterministically against completed analysis artifacts."""

    def __init__(
        self,
        manager: AnalysisJobManager,
        action_service: Optional[ActionIntelligenceService] = None,
    ) -> None:
        self.manager = manager
        self.action_service = action_service or ActionIntelligenceService(manager=manager)
        self.calculator = DeterministicCalculator()
        self.checker = CrossStageConsistencyChecker()
        self.option_service = OptionComparisonService()
        self.evidence_service = EvidenceQualityService()
        self.uncertainty_service = UncertaintyCalibrationService()
        self._cache: Dict[str, DecisionIntegrityReport] = {}

    def get_integrity_report(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> DecisionIntegrityReport:
        """Retrieves or deterministically calculates the Decision Integrity Report.

        Zero LLM calls executed.
        """
        # Fetch validated upstream analysis response
        analysis: AnalysisResponse = self.manager.get_job_result(analysis_id, owner_id)

        # Check for saved action intelligence plan
        action_plan: Optional[IntelligentActionPlan] = self.action_service.get_action_plan(
            analysis_id=analysis_id,
            owner_id=owner_id,
        )

        fingerprint = _compute_analysis_fingerprint(analysis)
        cache_key = f"{analysis_id}:{fingerprint}:{INTEGRITY_RULE_VERSION}:{bool(action_plan)}"

        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        # Extract any context dictionary from the request/decision model
        context = getattr(analysis.decision_model, "context", {}) or {}

        # 1. Deterministic Calculations
        calculations = self.calculator.evaluate_all(
            decision_model=analysis.decision_model,
            recommendation=analysis.recommendation,
            context=context,
        )

        scenarios = getattr(analysis, "scenarios", None) or getattr(analysis, "scenario_set", None)
        resilience = getattr(analysis, "resilience", None) or getattr(analysis, "resilience_report", None)

        # 2. Cross-Stage Consistency Checks
        findings = self.checker.evaluate_all(
            decision_model=analysis.decision_model,
            evidence_package=analysis.evidence_package,
            reasoning_board=analysis.reasoning_board,
            recommendation=analysis.recommendation,
            scenario_set=scenarios,
            resilience_report=resilience,
            calculations=calculations,
            action_plan=action_plan,
        )

        # 3. Alternative Options Comparison
        option_comp = self.option_service.compare_options(
            decision_model=analysis.decision_model,
            evidence_package=analysis.evidence_package,
            recommendation=analysis.recommendation,
        )

        # 4. Evidence Quality & Deduplication
        evidence_quality = self.evidence_service.evaluate_evidence(analysis.evidence_package)

        # 5. Uncertainty Calibration & Ranked Gaps
        uncertainty = self.uncertainty_service.evaluate_uncertainty(
            decision_model=analysis.decision_model,
            evidence_package=analysis.evidence_package,
            recommendation=analysis.recommendation,
            scenario_set=scenarios,
            calculations=calculations,
        )

        # Tally severities and statuses
        severity_counts: Dict[str, int] = {
            IntegritySeverity.CRITICAL.value: 0,
            IntegritySeverity.HIGH.value: 0,
            IntegritySeverity.MEDIUM.value: 0,
            IntegritySeverity.LOW.value: 0,
        }
        status_counts: Dict[str, int] = {
            FindingStatus.CONFIRMED.value: 0,
            FindingStatus.REQUIRES_REVIEW.value: 0,
            FindingStatus.UNRESOLVED.value: 0,
        }
        for f in findings:
            sev_key = f.severity.value
            severity_counts[sev_key] = severity_counts.get(sev_key, 0) + 1
            st_key = f.status.value
            status_counts[st_key] = status_counts.get(st_key, 0) + 1

        # Determine overall integrity health
        crit_count = severity_counts.get(IntegritySeverity.CRITICAL.value, 0)
        high_count = severity_counts.get(IntegritySeverity.HIGH.value, 0)

        if crit_count > 0:
            overall_integrity = IntegrityStatus.CRITICAL_CONCERNS
        elif high_count > 0:
            overall_integrity = IntegrityStatus.WARNING
        elif any(c.status.value == "unresolved" for c in calculations):
            overall_integrity = IntegrityStatus.INSUFFICIENT_DATA
        else:
            overall_integrity = IntegrityStatus.PASSED

        # Determine decision readiness (distinct from technical completion)
        infeasible_calcs = any(c.status.value == "infeasible" for c in calculations)
        if crit_count > 0 or infeasible_calcs:
            readiness = DecisionReadinessStatus.BLOCKED
        elif high_count > 0 or overall_integrity == IntegrityStatus.INSUFFICIENT_DATA:
            readiness = DecisionReadinessStatus.NEEDS_VALIDATION
        elif severity_counts.get(IntegritySeverity.MEDIUM.value, 0) > 0:
            readiness = DecisionReadinessStatus.CONDITIONAL
        else:
            readiness = DecisionReadinessStatus.READY

        report = DecisionIntegrityReport(
            analysis_id=analysis_id,
            overall_integrity_status=overall_integrity,
            decision_readiness=readiness,
            calculations=calculations,
            findings=findings,
            severity_counts=severity_counts,
            status_counts=status_counts,
            option_comparison=option_comp,
            evidence_quality=evidence_quality,
            uncertainty_calibration=uncertainty,
            rule_version=INTEGRITY_RULE_VERSION,
            source_artifact_fingerprint=fingerprint,
        )

        self._cache[cache_key] = report
        return report
