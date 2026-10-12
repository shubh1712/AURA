"""Report Service (Day 8G-C).

Builds the normalized SharedReportModel from completed analysis artifacts and
DecisionIntegrityReport. Powers both the web views and PDF exports.
Zero LLM calls.
"""

import logging
from typing import Any, Dict, List, Optional

from app.schemas.action_intelligence import IntelligentActionPlan
from app.schemas.analysis import AnalysisResponse
from app.schemas.decision_integrity import DecisionIntegrityReport
from app.schemas.report import (
    ActionRoadmapItem,
    DecisionOverviewModel,
    PerspectiveSummary,
    SharedReportModel,
)
from app.services.action_intelligence.service import ActionIntelligenceService
from app.services.integrity.service import DecisionIntegrityService
from app.services.jobs.manager import AnalysisJobManager

logger = logging.getLogger(__name__)


class ReportService:
    """Constructs authoritative SharedReportModel instances."""

    def __init__(
        self,
        manager: AnalysisJobManager,
        integrity_service: Optional[DecisionIntegrityService] = None,
        action_service: Optional[ActionIntelligenceService] = None,
    ) -> None:
        self.manager = manager
        self.integrity_service = integrity_service or DecisionIntegrityService(manager=manager)
        self.action_service = action_service or ActionIntelligenceService(manager=manager)

    def get_shared_report(
        self,
        analysis_id: str,
        owner_id: Optional[str] = None,
        mode: str = "shared",
    ) -> SharedReportModel:
        """Constructs or retrieves the complete normalized SharedReportModel."""
        analysis: AnalysisResponse = self.manager.get_job_result(analysis_id, owner_id)
        integrity: DecisionIntegrityReport = self.integrity_service.get_integrity_report(
            analysis_id, owner_id=owner_id
        )
        action_plan: Optional[IntelligentActionPlan] = self.action_service.get_action_plan(
            analysis_id=analysis_id, owner_id=owner_id
        )

        rec = getattr(analysis, "recommendation", None)
        scenarios_obj = getattr(analysis, "scenarios", None) or getattr(analysis, "scenario_set", None)
        resilience_obj = getattr(analysis, "resilience", None) or getattr(analysis, "resilience_report", None)
        decision_model = getattr(analysis, "decision_model", None)

        # 1. Overview
        rec_title = "Recommended Strategy"
        if rec:
            rec_action = getattr(rec, "recommended_action", None) or getattr(rec, "executive_summary", None)
            if rec_action:
                rec_title = rec_action.split(".")[0].strip() or rec_action

        short_rationale = ""
        if rec:
            short_rationale = (
                getattr(rec, "executive_rationale", None)
                or getattr(rec, "rationale", None)
                or getattr(rec, "recommended_action", "")
            )
        if len(short_rationale) > 300:
            short_rationale = short_rationale[:300] + "..."

        falsification = (
            "If downside scenario conditions occur, pilot CSAT drops below acceptable floor, "
            "or annualized infrastructure costs breach budget ceiling."
        )
        if rec:
            unc_assess = getattr(rec, "uncertainty_assessment", None)
            if unc_assess and getattr(unc_assess, "conditions_changing_recommendation", None):
                conds = unc_assess.conditions_changing_recommendation
                if conds and len(conds) > 0:
                    falsification = conds[0]

        key_metrics: Dict[str, Any] = {}
        for c in integrity.calculations:
            if c.value is not None:
                key_metrics[c.title] = f"{c.value:,.2f} {c.unit or ''}".strip()

        dec_summary = "Strategic Decision Analysis"
        if decision_model and getattr(decision_model, "decision", None):
            dec_summary = getattr(decision_model.decision, "summary", "") or dec_summary
        elif getattr(analysis, "question", None):
            dec_summary = analysis.question

        crit_warn_count = integrity.severity_counts.get("critical", 0) + integrity.severity_counts.get("high", 0)

        overview = DecisionOverviewModel(
            title=dec_summary,
            decision_title=dec_summary,
            recommended_direction=rec_title,
            short_rationale=short_rationale,
            decision_readiness=integrity.decision_readiness,
            integrity_status=integrity.overall_integrity_status,
            critical_warning_count=crit_warn_count,
            key_metrics=key_metrics,
            falsification_condition=falsification,
            top_falsification_condition=falsification,
            analysis_id=analysis_id,
        )

        # 2. Scenarios
        scenario_matrix: List[Dict[str, Any]] = []
        scenarios_summary: List[Dict[str, Any]] = []
        if scenarios_obj and getattr(scenarios_obj, "scenarios", None):
            for s in scenarios_obj.scenarios:
                prob = getattr(s, "probability", None)
                prob_label = f"Weight: {int(prob * 100)}%" if prob is not None else "Unweighted"
                s_dict = {
                    "id": getattr(s, "id", ""),
                    "name": getattr(s, "name", ""),
                    "probability_label": prob_label,
                    "probability_weight": prob_label,
                    "probability": prob,
                    "narrative": getattr(s, "narrative", ""),
                    "implications": getattr(s, "risks", []) or getattr(s, "implications", []),
                    "signposts": [e.title for e in getattr(s, "key_events", [])] if getattr(s, "key_events", None) else getattr(s, "signposts", []),
                }
                scenario_matrix.append(s_dict)
                scenarios_summary.append({
                    "name": getattr(s, "name", ""),
                    "probability_weight": prob_label,
                    "implication": getattr(s, "narrative", "")[:120],
                })

        # 3. Resilience Scorecard
        res_score = 0.0
        if resilience_obj:
            res_score = getattr(resilience_obj, "overall_score", None) or getattr(resilience_obj, "composite_score", 0.0)
        res_category = "High Resilience" if res_score >= 75 else (
            "Moderate Resilience" if res_score >= 50 else "Vulnerable"
        )
        res_vulns = getattr(resilience_obj, "critical_vulnerabilities", []) or getattr(resilience_obj, "vulnerabilities", []) if resilience_obj else []
        res_hedges = getattr(resilience_obj, "recommended_hedges", []) or getattr(resilience_obj, "hedges", []) if resilience_obj else []

        resilience_scorecard = {
            "score": res_score,
            "category": res_category,
            "strengths": res_hedges[:3],
            "vulnerabilities": res_vulns[:3],
            "explanation": f"Composite resilience score {res_score:.1f}/100 across 4 deterministic stress-test dimensions.",
        }

        # 4. Boardroom Perspectives
        perspectives: List[PerspectiveSummary] = []
        if getattr(analysis, "reasoning_board", None) and getattr(analysis.reasoning_board, "perspectives", None):
            for p in analysis.reasoning_board.perspectives:
                p_type_val = getattr(p.perspective_type, "value", str(p.perspective_type))
                role_name = p_type_val.capitalize() + " Perspective"
                key_args = [a.claim for a in getattr(p, "arguments", [])[:3]]
                concerns = getattr(p, "concerns", []) or [getattr(a, "caveat", "") for a in getattr(p, "arguments", []) if getattr(a, "caveat", None)]
                perspectives.append(
                    PerspectiveSummary(
                        role=role_name,
                        perspective_type=p_type_val,
                        title=role_name,
                        stance=getattr(p, "stance", "neutral") or "neutral",
                        perspective=getattr(p, "summary", ""),
                        key_argument=key_args[0] if key_args else getattr(p, "summary", "")[:120],
                        key_arguments=key_args,
                        dissent_or_concerns=concerns,
                        critical_concerns=concerns,
                    )
                )

        # 5. Action Roadmap & Decision Gates
        roadmap: List[ActionRoadmapItem] = []
        gates: List[Dict[str, Any]] = []

        if action_plan and getattr(action_plan, "actions", None):
            for idx, a in enumerate(action_plan.actions):
                phase_raw = getattr(a, "phase", None) or getattr(a, "priority", None) or "Execution"
                phase_val = getattr(phase_raw, "value", str(phase_raw))
                timeframe_val = getattr(a, "timing", "") or getattr(a, "timeframe", "") or getattr(a, "time_horizon", "Immediate")
                role_val = getattr(a, "owner_role", "") or getattr(a, "responsible_role", "Executive Lead")

                gate_deps = getattr(a, "dependencies", []) or getattr(a, "gate_dependencies", [])
                gate_str = gate_deps[0] if gate_deps else None

                crit_obj = getattr(a, "success_criteria", None) or getattr(a, "validation_criteria", None)
                if isinstance(crit_obj, list) and crit_obj:
                    crit_str = getattr(crit_obj[0], "description", str(crit_obj[0]))
                elif crit_obj:
                    crit_str = getattr(crit_obj, "success_metric", str(crit_obj))
                else:
                    crit_str = None

                fallback_raw = getattr(a, "contingency_or_rollback", None) or getattr(a, "fallback_action", None)
                fallback_str = getattr(fallback_raw, "trigger", str(fallback_raw)) if fallback_raw else None

                act_id = getattr(a, "action_id", getattr(a, "id", f"act_{idx+1}"))

                roadmap.append(
                    ActionRoadmapItem(
                        step=idx + 1,
                        id=act_id,
                        title=a.title,
                        phase=phase_val,
                        timeframe=timeframe_val,
                        time_horizon=timeframe_val,
                        owner_role=role_val,
                        responsible_role=role_val,
                        decision_gate=gate_str,
                        validation_criteria=crit_str,
                        fallback=fallback_str,
                        fallback_plan=fallback_str,
                    )
                )

            if getattr(action_plan, "decision_gates", None):
                for dg in action_plan.decision_gates:
                    dg_title = getattr(dg, "title", None) or getattr(dg, "gate_name", "Decision Gate")
                    dg_thresh = getattr(dg, "checkpoint", "") or getattr(dg, "threshold", "")
                    dg_desc = getattr(dg, "failure_response", "") or getattr(dg, "description", "")
                    gates.append({
                        "name": dg_title,
                        "threshold": dg_thresh,
                        "description": dg_desc,
                        "fallback_action": getattr(dg, "failure_response", ""),
                    })
        elif rec and getattr(rec, "action_plan", None):
            ap = rec.action_plan
            actions_list = getattr(ap, "actions", []) if not isinstance(ap, list) else ap
            for idx, a in enumerate(actions_list):
                title = getattr(a, "title", None) or getattr(a, "description", f"Action {idx+1}")
                priority = getattr(a, "priority", None)
                phase_val = getattr(priority, "value", str(priority)) if priority else "high"
                th = getattr(a, "time_horizon", None)
                th_val = getattr(th, "value", str(th)) if th else "immediate"
                role_val = getattr(a, "responsible_role", None) or getattr(a, "owner", "Lead")

                first_gate = None
                fb_plan = None
                for g in getattr(a, "decision_gates", []) or []:
                    g_name = getattr(g, "target_milestone", None) or getattr(g, "name", getattr(g, "condition", ""))
                    if not first_gate:
                        first_gate = g_name
                    if getattr(g, "fallback_action", None):
                        fb_plan = g.fallback_action
                    gates.append({
                        "name": g_name,
                        "threshold": getattr(g, "condition", ""),
                        "description": getattr(g, "verification_method", "") or getattr(g, "description", ""),
                        "fallback_action": getattr(g, "fallback_action", ""),
                    })

                roadmap.append(
                    ActionRoadmapItem(
                        step=idx + 1,
                        id=getattr(a, "id", f"act_{idx+1}"),
                        title=title,
                        phase=phase_val,
                        timeframe=th_val,
                        time_horizon=th_val,
                        owner_role=role_val,
                        responsible_role=role_val,
                        decision_gate=first_gate,
                        validation_criteria=None,
                        fallback=fb_plan,
                        fallback_plan=fb_plan,
                    )
                )

        full_dm = decision_model.model_dump() if decision_model else None
        full_ev = analysis.evidence_package.model_dump() if getattr(analysis, "evidence_package", None) else None
        full_rec = rec.model_dump() if rec else None
        full_res = resilience_obj.model_dump() if resilience_obj else None
        full_scen = scenarios_obj.model_dump() if scenarios_obj else None

        return SharedReportModel(
            analysis_id=analysis_id,
            overview=overview,
            option_comparison=integrity.option_comparison,
            calculations=integrity.calculations,
            scenario_matrix=scenario_matrix,
            scenarios_summary=scenarios_summary,
            resilience_scorecard=resilience_scorecard,
            evidence_quality=integrity.evidence_quality,
            uncertainty_calibration=integrity.uncertainty_calibration,
            integrity_findings=integrity.findings,
            integrity_report=integrity,
            boardroom_perspectives=perspectives,
            perspectives=perspectives,
            action_roadmap=roadmap,
            roadmap=roadmap,
            decision_gates=gates,
            full_decision_model=full_dm,
            full_framing=full_dm,
            full_evidence_package=full_ev,
            full_recommendation=full_rec,
            full_resilience_report=full_res,
            full_scenarios=full_scen,
            source_fingerprint=integrity.source_artifact_fingerprint,
            report_mode=mode,
        )
