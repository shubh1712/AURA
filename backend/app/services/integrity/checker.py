"""Cross-Stage Consistency Checker (Day 8G-A).

Implements 15 deterministic, scope-aware cross-stage consistency rules:
- Hard vs soft constraint classification conflicts
- Conflicting metric thresholds across stages
- Scenario values breaching decision gates
- Unit and currency mismatches
- Percentage vs percentage-point confusion
- Timeline and dependency ordering conflicts
- Unsupported quantitative claims
- Missing net calculations
- Calculations contradicting recommendations
- Resilience claims contradicting scenario failures
- Action Intelligence gates diverging from Stage 4 gates
- Undefined metrics used as quantitative gates
- Duplicate evidence references
- Contradictory scenario assumptions
- Incompatible objective and recommendation conditions
"""

from decimal import Decimal
import logging
import re
from typing import Any, Dict, List, Optional, Set

from app.schemas.action_intelligence import IntelligentActionPlan
from app.schemas.decision_integrity import (
    CalculationResult,
    CalculationStatus,
    FindingStatus,
    IntegrityFinding,
    IntegritySeverity,
)
from app.schemas.decision_model import Constraint, DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import ReasoningBoard
from app.schemas.recommendation import DecisionRecommendation
from app.schemas.resilience import ResilienceReport
from app.schemas.scenario import ScenarioSet

logger = logging.getLogger(__name__)


class CrossStageConsistencyChecker:
    """Evaluates cross-stage logical and mathematical consistency across pipeline artifacts."""

    def evaluate_all(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        reasoning_board: Optional[ReasoningBoard],
        recommendation: DecisionRecommendation,
        scenario_set: ScenarioSet,
        resilience_report: ResilienceReport,
        calculations: List[CalculationResult],
        action_plan: Optional[IntelligentActionPlan] = None,
    ) -> List[IntegrityFinding]:
        """Runs all 15 deterministic consistency checks across stages."""
        findings: List[IntegrityFinding] = []

        # 1. Hard vs soft constraint classification
        findings.extend(self._check_constraint_classification(decision_model, recommendation, action_plan))

        # 2. Threshold mismatches
        findings.extend(self._check_threshold_mismatches(decision_model, recommendation, scenario_set))

        # 3. Scenario values breaching decision gates
        findings.extend(self._check_scenario_gate_breaches(recommendation, scenario_set))

        # 4. Unit and currency mismatches
        findings.extend(self._check_unit_currency_mismatches(decision_model, recommendation, calculations))

        # 5. Percentage vs percentage-point confusion
        findings.extend(self._check_percentage_confusion(decision_model, recommendation))

        # 6. Timeline and dependency cycle / order
        findings.extend(self._check_timeline_dependencies(recommendation, action_plan))

        # 7. Unsupported quantitative claims
        findings.extend(self._check_unsupported_quantitative_claims(recommendation, evidence_package))

        # 8. Missing net calculation
        findings.extend(self._check_missing_net_calculations(recommendation, calculations))

        # 9. Calculation contradicts recommendation
        findings.extend(self._check_calc_contradicts_recommendation(recommendation, calculations))

        # 10. Resilience claims contradicting scenario failures
        findings.extend(self._check_resilience_scenario_contradictions(resilience_report, scenario_set))

        # 11. Action Intelligence gates diverging from Stage 4 gates
        if action_plan:
            findings.extend(self._check_action_gate_divergence(recommendation, action_plan))

        # 12. Undefined metrics as quantitative gates
        findings.extend(self._check_undefined_quantitative_gates(recommendation, action_plan))

        # 13. Duplicate evidence sources
        findings.extend(self._check_duplicate_evidence(evidence_package))

        # 14. Contradictory scenario assumptions
        findings.extend(self._check_scenario_assumptions(scenario_set))

        # 15. Incompatible objective and recommendation conditions
        findings.extend(self._check_incompatible_objectives(decision_model, recommendation))

        return findings

    def _get_gate_props(self, gate: Any) -> tuple[str, str, str]:
        """Safely returns (name, threshold, description) across different gate schemas."""
        name = (
            getattr(gate, "name", None)
            or getattr(gate, "target_milestone", None)
            or getattr(gate, "gate_name", None)
            or "Decision Gate"
        )
        threshold = (
            getattr(gate, "threshold", None)
            or getattr(gate, "condition", None)
            or ""
        )
        desc = (
            getattr(gate, "description", None)
            or getattr(gate, "verification_method", None)
            or getattr(gate, "fallback_action", None)
            or ""
        )
        return str(name), str(threshold), str(desc)

    def _get_rec_gates(self, recommendation: DecisionRecommendation) -> List[Any]:
        """Safely extracts decision gates from root or nested action plan actions."""
        if hasattr(recommendation, "decision_gates") and recommendation.decision_gates:
            return recommendation.decision_gates
        gates = []
        actions = (
            recommendation.action_plan.actions
            if hasattr(recommendation, "action_plan") and hasattr(recommendation.action_plan, "actions")
            else (getattr(recommendation, "action_plan", []) or [])
        )
        for act in actions:
            if hasattr(act, "decision_gates") and act.decision_gates:
                gates.extend(act.decision_gates)
        return gates

    # --------------------------------------------------------------------------
    # Rule 1: Hard vs Soft Constraint Classification
    # --------------------------------------------------------------------------
    def _check_constraint_classification(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
        action_plan: Optional[IntelligentActionPlan],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        for cnstr in decision_model.constraints:
            stmt = getattr(cnstr, "statement", None) or getattr(cnstr, "description", "")
            is_hard = (
                getattr(cnstr, "is_hard", False)
                or getattr(cnstr, "is_hard_constraint", False)
                or "hard" in stmt.lower()
                or "must" in stmt.lower()
            )
            # Check if recommendation or gates treat this as soft or negotiable
            stmt_lower = stmt.lower()
            for gate in self._get_rec_gates(recommendation):
                g_name, g_thresh, g_desc = self._get_gate_props(gate)
                if any(word in g_name.lower() for word in stmt_lower.split() if len(word) > 4):
                    # Check if gate allows bypassing or soft threshold
                    if "optional" in g_desc.lower() or "soft" in g_desc.lower():
                        findings.append(
                            IntegrityFinding(
                                finding_id=f"find_cnstr_class_{cnstr.id}",
                                rule_code="RULE_CNSTR_CLASS_CONFLICT",
                                severity=IntegritySeverity.HIGH,
                                status=FindingStatus.CONFIRMED,
                                affected_stages=[1, 4],
                                title=f"Hard Constraint Classified as Soft in Decision Gate",
                                description=(
                                    f"Constraint '{stmt}' is specified as a non-negotiable boundary in Stage 1, "
                                    f"but Gate '{g_name}' treats it as optional or soft."
                                ),
                                relevant_values={"constraint": stmt, "gate": g_name},
                                suggested_resolution="Enforce strict go/no-go gating for all Stage 1 hard constraints.",
                                provenance="Stage 1 constraints vs Stage 4 decision gates",
                            )
                        )
        return findings

    # --------------------------------------------------------------------------
    # Rule 2: Metric Threshold Mismatches across Stages
    # --------------------------------------------------------------------------
    def _check_threshold_mismatches(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
        scenario_set: ScenarioSet,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        # Look for numeric thresholds in constraints vs gates
        for cnstr in decision_model.constraints:
            stmt = getattr(cnstr, "statement", None) or getattr(cnstr, "description", "")
            cnstr_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(%|ms|k|m|usd|\$)", stmt, re.I)
            for gate in self._get_rec_gates(recommendation):
                g_name, g_thresh, g_desc = self._get_gate_props(gate)
                gate_nums = re.findall(r"(\d+(?:\.\d+)?)\s*(%|ms|k|m|usd|\$)", g_thresh, re.I)
                # If metric names match but values differ
                for c_val, c_unit in cnstr_nums:
                    for g_val, g_unit in gate_nums:
                        if c_unit.lower() == g_unit.lower() and c_val != g_val:
                            # Verify if context refers to the same subject
                            common_words = (set(stmt.lower().split()) | set((getattr(cnstr, "name", "") or "").lower().split())) & (set(g_name.lower().split()) | set(g_thresh.lower().split()))
                            meaningful = [w for w in common_words if len(w) >= 3 and w not in ("under", "above", "minimum", "maximum", "than", "with", "from", "must", "pilot")]
                            if meaningful:
                                g_id = getattr(gate, "id", getattr(gate, "gate_id", "gate"))
                                findings.append(
                                    IntegrityFinding(
                                        finding_id=f"find_thresh_mismatch_{g_id}",
                                        rule_code="RULE_THRESHOLD_MISMATCH",
                                        severity=IntegritySeverity.HIGH,
                                        status=FindingStatus.REQUIRES_REVIEW,
                                        affected_stages=[1, 4],
                                        title=f"Threshold Mismatch on Metric: {', '.join(meaningful)}",
                                        description=(
                                            f"Stage 1 defines constraint '{stmt}' ({c_val}{c_unit}), "
                                            f"whereas Stage 4 gate '{g_name}' specifies threshold ({g_val}{g_unit})."
                                        ),
                                        relevant_values={"stage1_val": f"{c_val}{c_unit}", "stage4_gate_val": f"{g_val}{g_unit}"},
                                        suggested_resolution="Reconcile constraint target and gate threshold to ensure metric consistency.",
                                        provenance="Stage 1 constraints vs Stage 4 decision gates",
                                    )
                                )
        return findings

    # --------------------------------------------------------------------------
    # Rule 3: Scenario Values Violating Defined Decision Gates
    # --------------------------------------------------------------------------
    def _check_scenario_gate_breaches(
        self,
        recommendation: DecisionRecommendation,
        scenario_set: ScenarioSet,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        for sc in scenario_set.scenarios:
            risks_list = getattr(sc, "risks", []) or getattr(sc, "implications", []) or []
            sc_text = (getattr(sc, "narrative", "") + " " + " ".join(risks_list)).lower()
            for gate in self._get_rec_gates(recommendation):
                g_name, g_thresh, g_desc = self._get_gate_props(gate)
                # Check for explicit violation language in pessimistic scenarios
                if "pessimistic" in sc.name.lower() or "downside" in sc.name.lower():
                    if "fails" in sc_text or "breach" in sc_text or "unacceptable" in sc_text:
                        findings.append(
                            IntegrityFinding(
                                finding_id=f"find_scen_gate_breach_{sc.id}",
                                rule_code="RULE_SCENARIO_GATE_BREACH",
                                severity=IntegritySeverity.CRITICAL,
                                status=FindingStatus.CONFIRMED,
                                affected_stages=[4, 5],
                                title=f"Downside Scenario Breaches Decision Gate '{g_name}'",
                                description=(
                                    f"Scenario '{sc.name}' projects outcome conditions that violate decision gate "
                                    f"'{g_name}' (threshold: {g_thresh})."
                                ),
                                relevant_values={"scenario": sc.name, "gate": g_name, "threshold": g_thresh},
                                suggested_resolution="Establish explicit fallback or circuit-breaker trigger in action roadmap.",
                                provenance="Stage 4 decision gates vs Stage 5 scenario set",
                            )
                        )
        return findings

    # --------------------------------------------------------------------------
    # Rule 4: Unit and Currency Mismatches
    # --------------------------------------------------------------------------
    def _check_unit_currency_mismatches(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
        calculations: List[CalculationResult],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        # Check if monthly costs are directly compared with annual limits without x12
        for calc in calculations:
            if calc.category == "annualized_cost" and calc.status == CalculationStatus.FEASIBLE:
                # Good: explicitly annualized
                continue
            if calc.category == "net_savings" and calc.status == CalculationStatus.UNRESOLVED:
                if any("monthly" in mi for mi in calc.missing_inputs):
                    findings.append(
                        IntegrityFinding(
                            finding_id="find_unit_annual_vs_monthly",
                            rule_code="RULE_UNIT_CURRENCY_MISMATCH",
                            severity=IntegritySeverity.MEDIUM,
                            status=FindingStatus.REQUIRES_REVIEW,
                            affected_stages=[1, 4],
                            title="Unverified Monthly vs Annual Recurring Cost Conversion",
                            description="Monthly recurring operational expenses must be explicitly annualized (x12) when evaluated against annual budgets.",
                            relevant_values={"missing_inputs": calc.missing_inputs},
                            suggested_resolution="Specify distinct billing intervals for all recurring SaaS and infrastructure costs.",
                            provenance="Deterministic Calculation Engine",
                        )
                    )
        return findings

    # --------------------------------------------------------------------------
    # Rule 5: Percentage vs Percentage-Point Confusion
    # --------------------------------------------------------------------------
    def _check_percentage_confusion(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        rec_rat = getattr(recommendation, "executive_rationale", getattr(recommendation, "rationale", ""))
        rec_sum = getattr(recommendation, "executive_summary", getattr(recommendation, "recommended_action", ""))
        rec_text = (rec_rat + " " + rec_sum).lower()
        matches = re.findall(r"(\d+)%\s+(?:increase|decrease|gain|drop|improvement)", rec_text)
        for m in matches:
            if int(m) > 50:
                findings.append(
                    IntegrityFinding(
                        finding_id="find_pct_pt_ambiguity",
                        rule_code="RULE_PCT_CONFUSION",
                        severity=IntegritySeverity.LOW,
                        status=FindingStatus.REQUIRES_REVIEW,
                        affected_stages=[4],
                        title="Potential Percentage vs Percentage-Point Ambiguity",
                        description=f"A metric shift of {m}% is cited in the recommendation rationale without clarifying relative change vs percentage-point delta.",
                        relevant_values={"shift_value": f"{m}%"},
                        suggested_resolution="Disambiguate whether metric movement is a relative change (%) or absolute points (pp).",
                        provenance="Stage 4 recommendation narrative",
                    )
                )
                break
        return findings

    # --------------------------------------------------------------------------
    # Rule 6: Timeline and Dependency Conflicts
    # --------------------------------------------------------------------------
    def _check_timeline_dependencies(
        self,
        recommendation: DecisionRecommendation,
        action_plan: Optional[IntelligentActionPlan],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        if not action_plan or not action_plan.actions:
            return findings

        # Check for dependency cycle or missing parent
        id_set = {getattr(a, "action_id", getattr(a, "id", f"act_{idx}")) for idx, a in enumerate(action_plan.actions)}
        order_map = {getattr(a, "action_id", getattr(a, "id", f"act_{idx}")): idx for idx, a in enumerate(action_plan.actions)}

        for idx, action in enumerate(action_plan.actions):
            act_id = getattr(action, "action_id", getattr(action, "id", f"act_{idx}"))
            for dep_id in getattr(action, "dependencies", []):
                if dep_id not in id_set:
                    findings.append(
                        IntegrityFinding(
                            finding_id=f"find_dep_missing_{act_id}",
                            rule_code="RULE_TIMELINE_DEPENDENCY_CYCLE",
                            severity=IntegritySeverity.HIGH,
                            status=FindingStatus.CONFIRMED,
                            affected_stages=[4],
                            title=f"Unresolved Action Dependency: '{dep_id}'",
                            description=f"Action '{action.title}' lists dependency '{dep_id}' which does not exist in the action plan.",
                            relevant_values={"action_id": act_id, "dependency_id": dep_id},
                            suggested_resolution="Ensure all dependent tasks reference valid existing roadmap actions.",
                            provenance="Action Intelligence dependency graph",
                        )
                    )
                elif order_map[dep_id] > order_map[act_id]:
                    findings.append(
                        IntegrityFinding(
                            finding_id=f"find_dep_order_{act_id}",
                            rule_code="RULE_TIMELINE_DEPENDENCY_CYCLE",
                            severity=IntegritySeverity.HIGH,
                            status=FindingStatus.CONFIRMED,
                            affected_stages=[4],
                            title=f"Roadmap Order Inversion for Action '{action.title}'",
                            description=f"Action '{action.title}' is scheduled before its required prerequisite '{dep_id}'.",
                            relevant_values={"action": action.title, "prerequisite_id": dep_id},
                            suggested_resolution="Reorder roadmap sequence so prerequisite tasks precede dependent executions.",
                            provenance="Action Intelligence dependency sequence",
                        )
                    )
        return findings

    # --------------------------------------------------------------------------
    # Rule 7: Unsupported Quantitative Claims
    # --------------------------------------------------------------------------
    def _check_unsupported_quantitative_claims(
        self,
        recommendation: DecisionRecommendation,
        evidence_package: EvidencePackage,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        rec_summary = getattr(recommendation, "executive_summary", getattr(recommendation, "executive_rationale", ""))
        # Find exact numeric percentages or dollar figures claimed in recommendation
        claimed_metrics = re.findall(r"(\$\d+(?:,\d+)*(?:\.\d+)?|\d+%)", rec_summary)
        has_citations = len(evidence_package.sources) > 0 or len(evidence_package.items) > 0

        if claimed_metrics and not has_citations:
            findings.append(
                IntegrityFinding(
                    finding_id="find_unsupported_quant_claim",
                    rule_code="RULE_UNSUPPORTED_QUANTITATIVE_CLAIM",
                    severity=IntegritySeverity.HIGH,
                    status=FindingStatus.CONFIRMED,
                    affected_stages=[2, 4],
                    title="Unsupported Quantitative Claims in Recommendation",
                    description=f"Recommendation asserts exact figures ({', '.join(claimed_metrics[:3])}) but Stage 2 Evidence Package contains 0 citations.",
                    relevant_values={"metrics_claimed": claimed_metrics[:3]},
                    suggested_resolution="Attach empirical evidence links or mark asserted metrics explicitly as hypothetical model assumptions.",
                    provenance="Stage 2 evidence sources vs Stage 4 recommendation",
                )
            )
        return findings

    # --------------------------------------------------------------------------
    # Rule 8: Missing Net Calculation
    # --------------------------------------------------------------------------
    def _check_missing_net_calculations(
        self,
        recommendation: DecisionRecommendation,
        calculations: List[CalculationResult],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        net_calc = next((c for c in calculations if c.category == "net_savings"), None)
        if net_calc and net_calc.status == CalculationStatus.UNRESOLVED:
            findings.append(
                IntegrityFinding(
                    finding_id="find_missing_net_calc",
                    rule_code="RULE_MISSING_NET_CALCULATION",
                    severity=IntegritySeverity.HIGH,
                    status=FindingStatus.CONFIRMED,
                    affected_stages=[4],
                    title="Net Financial Savings Calculation Unresolved",
                    description="Financial recommendations must not conflate gross deflection with net cost savings without subtracting recurring cloud/operational expenses.",
                    relevant_values={"missing_inputs": net_calc.missing_inputs},
                    suggested_resolution="Supply required cost variables to resolve net savings formula.",
                    provenance="Deterministic Calculation Engine",
                )
            )
        return findings

    # --------------------------------------------------------------------------
    # Rule 9: Calculated Results Contradict Recommendation
    # --------------------------------------------------------------------------
    def _check_calc_contradicts_recommendation(
        self,
        recommendation: DecisionRecommendation,
        calculations: List[CalculationResult],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        for calc in calculations:
            if calc.status == CalculationStatus.INFEASIBLE:
                findings.append(
                    IntegrityFinding(
                        finding_id=f"find_calc_contradiction_{calc.calculation_id}",
                        rule_code="RULE_CALC_CONTRADICTS_RECOMMENDATION",
                        severity=IntegritySeverity.CRITICAL,
                        status=FindingStatus.CONFIRMED,
                        affected_stages=[4],
                        title=f"Calculation Infeasibility Contradicts Recommendation",
                        description=f"Deterministic calculation '{calc.title}' is INFEASIBLE: {calc.explanation}",
                        relevant_values={"value": calc.value, "unit": calc.unit},
                        suggested_resolution="Re-evaluate recommendation conditions; the plan is mathematically infeasible under stated parameters.",
                        provenance=calc.calculation_id,
                    )
                )
        return findings

    # --------------------------------------------------------------------------
    # Rule 10: Resilience Claims Contradicting Scenario Failures
    # --------------------------------------------------------------------------
    def _check_resilience_scenario_contradictions(
        self,
        resilience_report: ResilienceReport,
        scenario_set: ScenarioSet,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        pessimistic_scenarios = [s for s in scenario_set.scenarios if "pessimistic" in s.name.lower() or "downside" in s.name.lower()]
        res_score = getattr(resilience_report, "overall_score", getattr(resilience_report, "composite_score", 0.0))
        if res_score >= 80.0 and pessimistic_scenarios:
            for sc in pessimistic_scenarios:
                risks_list = getattr(sc, "risks", []) or getattr(sc, "implications", []) or []
                if any("catastrophic" in imp.lower() or "irreversible" in imp.lower() for imp in risks_list):
                    findings.append(
                        IntegrityFinding(
                            finding_id="find_resilience_contradiction",
                            rule_code="RULE_RESILIENCE_SCENARIO_CONTRADICTION",
                            severity=IntegritySeverity.CRITICAL,
                            status=FindingStatus.CONFIRMED,
                            affected_stages=[5, 6],
                            title="Resilience Scorecard Contradicts Pessimistic Scenario",
                            description=(
                                f"Resilience composite score is rated high ({res_score:.1f}/100), "
                                f"yet Scenario '{sc.name}' projects severe or irreversible downside implications."
                            ),
                            relevant_values={"composite_score": res_score, "scenario": sc.name},
                            suggested_resolution="Calibrate resilience downward to reflect unmitigated catastrophic scenario exposure.",
                            provenance="Stage 5 scenario implications vs Stage 6 resilience score",
                        )
                    )
        return findings

    # --------------------------------------------------------------------------
    # Rule 11: Action Intelligence Gates Diverging from Stage 4 Gates
    # --------------------------------------------------------------------------
    def _check_action_gate_divergence(
        self,
        recommendation: DecisionRecommendation,
        action_plan: IntelligentActionPlan,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        st4_gates = self._get_rec_gates(recommendation)
        st4_gate_names = {self._get_gate_props(g)[0].lower().strip() for g in st4_gates}
        action_gates = action_plan.decision_gates or []

        for ag in action_gates:
            ag_title = getattr(ag, "title", None) or getattr(ag, "gate_name", None) or getattr(ag, "name", "Gate")
            ag_name = str(ag_title).lower().strip()
            ag_id = getattr(ag, "gate_id", getattr(ag, "id", "gate"))
            # If action gate is completely missing from stage 4 gates
            if not any(g in ag_name or ag_name in g for g in st4_gate_names):
                findings.append(
                    IntegrityFinding(
                        finding_id=f"find_action_gate_divergence_{ag_id}",
                        rule_code="RULE_ACTION_GATE_DIVERGENCE",
                        severity=IntegritySeverity.MEDIUM,
                        status=FindingStatus.REQUIRES_REVIEW,
                        affected_stages=[4],
                        title=f"Action Plan Gate Diverges from Stage 4 Gates",
                        description=f"Action Intelligence introduces Gate '{ag_title}' which has no reconciled counterpart in Stage 4 decision gates.",
                        relevant_values={"action_gate": str(ag_title)},
                        suggested_resolution="Synchronize Stage 4 formal decision gates with Action Intelligence milestones.",
                        provenance="Stage 4 recommendation gates vs Action Intelligence gates",
                    )
                )
        return findings

    # --------------------------------------------------------------------------
    # Rule 12: Undefined Metrics as Quantitative Gates
    # --------------------------------------------------------------------------
    def _check_undefined_quantitative_gates(
        self,
        recommendation: DecisionRecommendation,
        action_plan: Optional[IntelligentActionPlan],
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        rec_gates = self._get_rec_gates(recommendation)
        for gate in rec_gates:
            g_name, g_thresh, g_desc = self._get_gate_props(gate)
            if not g_thresh or g_thresh.strip() in ("", "TBD", "N/A", "undefined"):
                gate_id = getattr(gate, "id", getattr(gate, "gate_id", "gate_undefined"))
                findings.append(
                    IntegrityFinding(
                        finding_id=f"find_undefined_gate_{gate_id}",
                        rule_code="RULE_UNDEFINED_QUANTITATIVE_GATE",
                        severity=IntegritySeverity.HIGH,
                        status=FindingStatus.CONFIRMED,
                        affected_stages=[4],
                        title=f"Decision Gate '{g_name}' Lacks Quantitative Threshold",
                        description=f"Decision gate '{g_name}' is declared as a go/no-go criterion but threshold is undefined or placeholder.",
                        relevant_values={"gate": g_name, "threshold": g_thresh},
                        suggested_resolution="Specify measurable numeric threshold, unit, and verification method for this gate.",
                        provenance="Stage 4 decision gates",
                    )
                )
        return findings

    # --------------------------------------------------------------------------
    # Rule 13: Duplicate Evidence Sources
    # --------------------------------------------------------------------------
    def _check_duplicate_evidence(
        self,
        evidence_package: EvidencePackage,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        seen_urls: Dict[str, str] = {}
        for src in evidence_package.sources:
            url_norm = (src.url or "").strip().lower()
            if url_norm and len(url_norm) > 10:
                if url_norm in seen_urls:
                    findings.append(
                        IntegrityFinding(
                            finding_id=f"find_dup_evidence_{src.id}",
                            rule_code="RULE_DUPLICATE_EVIDENCE",
                            severity=IntegritySeverity.LOW,
                            status=FindingStatus.CONFIRMED,
                            affected_stages=[2],
                            title="Duplicate Evidence Source URL Detected",
                            description=f"Source '{src.title}' duplicates previously referenced URL: {src.url}",
                            relevant_values={"url": src.url, "duplicate_id": src.id, "original_id": seen_urls[url_norm]},
                            suggested_resolution="Deduplicate evidence sources to ensure independent citation diversity.",
                            provenance="Stage 2 evidence sources",
                        )
                    )
                else:
                    seen_urls[url_norm] = src.id
        return findings

    # --------------------------------------------------------------------------
    # Rule 14: Contradictory Scenario Assumptions
    # --------------------------------------------------------------------------
    def _check_scenario_assumptions(
        self,
        scenario_set: ScenarioSet,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        # Check if probability distribution sums to 1.0 (if present)
        prob_sum = sum(s.probability for s in scenario_set.scenarios if s.probability is not None)
        if prob_sum > 0 and abs(prob_sum - 1.0) > 0.05:
            findings.append(
                IntegrityFinding(
                    finding_id="find_scenario_prob_sum",
                    rule_code="RULE_CONTRADICTORY_SCENARIO_ASSUMPTIONS",
                    severity=IntegritySeverity.MEDIUM,
                    status=FindingStatus.REQUIRES_REVIEW,
                    affected_stages=[5],
                    title="Scenario Probability Sum Variance",
                    description=f"Assigned scenario probabilities sum to {prob_sum:.2f} instead of 1.00 (100%). Model weights must not be treated as calibrated probabilities.",
                    relevant_values={"probability_sum": round(prob_sum, 3)},
                    suggested_resolution="Normalize scenario weights or clearly designate them as qualitative weightings.",
                    provenance="Stage 5 scenario probabilities",
                )
            )
        return findings

    # --------------------------------------------------------------------------
    # Rule 15: Incompatible Objective and Recommendation Conditions
    # --------------------------------------------------------------------------
    def _check_incompatible_objectives(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
    ) -> List[IntegrityFinding]:
        findings: List[IntegrityFinding] = []
        for obj in decision_model.objectives:
            # If objective mentions "minimize cost" or "budget", check if recommendation specifies high capital requirement without mitigation
            obj_text = obj.description.lower()
            if "minimize cost" in obj_text or "zero downtime" in obj_text:
                rec_mitigations = getattr(recommendation, "risk_mitigations", [])
                rec_risks = " ".join(getattr(r, "description", str(r)).lower() for r in rec_mitigations)
                if "zero downtime" in obj_text and ("downtime" in rec_risks or "outage" in rec_risks):
                    findings.append(
                        IntegrityFinding(
                            finding_id=f"find_incompat_obj_{obj.id}",
                            rule_code="RULE_INCOMPATIBLE_OBJECTIVE_CONDITION",
                            severity=IntegritySeverity.HIGH,
                            status=FindingStatus.REQUIRES_REVIEW,
                            affected_stages=[1, 4],
                            title=f"Potential Conflict with Objective '{obj.description}'",
                            description=f"Objective mandates '{obj.description}', while recommendation risk analysis identifies operational downtime exposure.",
                            relevant_values={"objective": obj.description},
                            suggested_resolution="Confirm automated fallback or blue/green routing to satisfy zero-downtime objective.",
                            provenance="Stage 1 objectives vs Stage 4 recommendation risks",
                        )
                    )
        return findings
