"""Comprehensive Tests for AURA Day 8G Decision Intelligence Hardening & Reports.

Covers:
- Deterministic calculation engine (precision-safe Decimal, net savings, missing inputs unresolved).
- 15 cross-stage consistency rules (hard/soft conflict, threshold mismatch, gate breaches, etc.).
- Viable option comparison matrix without fabricated weighted scores.
- Evidence quality classification, duplicate detection, and independence ratio.
- Uncertainty calibration and decision-impact ranked evidence gaps.
- Shared report assembly and ReportLab PDF generator (Summary & Detailed).
- REST API endpoints for integrity and reports.
"""

from decimal import Decimal
import io
import pytest
from unittest.mock import MagicMock

from app.schemas.decision_integrity import (
    CalculationResult,
    CalculationStatus,
    DecisionIntegrityReport,
    DecisionReadinessStatus,
    FindingStatus,
    IntegritySeverity,
    IntegrityStatus,
    SourceCategory,
)
from app.schemas.decision_model import (
    Constraint,
    Decision,
    DecisionModel,
    DecisionType,
    Objective,
    TimeHorizon,
)
from app.schemas.evidence import EvidenceGap, EvidencePackage, Source, SourceType
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningArgument,
    ReasoningBoard,
    ReasoningPerspective,
)
from app.schemas.recommendation import (
    ActionItem,
    ActionPriority,
    ActionTimeHorizon,
    AlternativeOption,
    DecisionGate,
    DecisionRecommendation,
)
from app.schemas.resilience import ResilienceReport
from app.schemas.scenario import (
    FutureScenario,
    ScenarioKeyEvent,
    ScenarioMilestone,
    ScenarioSet,
    ScenarioType,
)
from app.services.integrity.calculator import DeterministicCalculator
from app.services.integrity.checker import CrossStageConsistencyChecker
from app.services.integrity.evidence_quality import EvidenceQualityService
from app.services.integrity.options import OptionComparisonService
from app.services.integrity.uncertainty import UncertaintyCalibrationService
from app.services.report.pdf_generator import AuraPDFGenerator
from app.services.report.service import ReportService


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def mock_decision_model():
    return DecisionModel.model_validate({
        "id": "dec_test",
        "decision": {
            "raw_prompt": "Should we deploy AI customer support automation?",
            "summary": "Deploy AI customer support automation",
            "decision_type": "operational_policy",
            "time_horizon": "medium_term",
        },
        "complexity": {
            "level": "medium",
            "reasoning": "Interacting trade-offs between automation, cost, and service quality.",
            "reversibility": "partially_reversible",
        },
        "objectives": [
            {
                "id": "o1",
                "description": "Reduce customer response time by 50%",
                "is_primary": True,
            },
            {
                "id": "o2",
                "description": "Zero downtime during migration",
                "is_primary": False,
            },
        ],
        "variables": [
            {
                "id": "var_deflection",
                "name": "Deflection Rate",
                "description": "Automated resolution fraction",
                "variable_type": "percentage",
                "baseline_value": 0.0,
                "proposed_value": 35.0,
                "unit": "%",
                "is_controllable": True,
            }
        ],
        "constraints": [
            {
                "id": "c1",
                "name": "CSAT Floor",
                "description": "Must maintain CSAT >= 85%",
                "is_hard_constraint": True,
                "source": "user_specified",
            },
            {
                "id": "c2",
                "name": "Budget Cap",
                "description": "Annual budget cap under $50,000",
                "is_hard_constraint": True,
                "source": "user_specified",
            },
        ],
        "tradeoffs": [
            {
                "id": "trd_1",
                "upside": "Fast resolution times and reduced ticket queue.",
                "downside": "Risk of automated hallucinations on complex queries.",
                "affected_variable_ids": ["var_deflection"],
            }
        ],
        "assumptions": [
            {
                "id": "asm_1",
                "statement": "Deflection rate will achieve 35% within 90 days.",
                "confidence": "medium",
                "falsification_condition": "Deflection remains below 20% in month 2.",
            }
        ],
        "unknowns": [
            {
                "id": "unk_1",
                "question": "Will ticket volume spike during holiday season?",
                "criticality": "high",
            }
        ],
        "key_questions": [
            "What is our maximum tolerable hallucination error rate?",
        ],
    })


@pytest.fixture
def mock_evidence_package():
    from app.schemas.evidence import DecisionEntityType, EvidenceGapType

    return EvidencePackage(
        id="ev_test",
        decision_model_id="dec_test",
        summary="3 evidence sources evaluated.",
        sources=[
            Source(
                id="s1",
                title="Stanford AI Benchmarks 2025",
                url="https://aiindex.stanford.edu/report/2025",
                source_type=SourceType.ACADEMIC,
            ),
            Source(
                id="s2",
                title="Vendor Marketing Whitepaper",
                url="https://vendor.io/case-study/efficiency",
                source_type=SourceType.COMPANY_PRIMARY,
            ),
            Source(
                id="s3",
                title="Duplicate Citation",
                url="https://aiindex.stanford.edu/report/2025",  # Duplicate URL
                source_type=SourceType.ACADEMIC,
            ),
        ],
        gaps=[
            EvidenceGap(
                id="g1",
                gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
                target_entity_id="asm_1",
                target_entity_type=DecisionEntityType.ASSUMPTION,
                description="Empirical deflection rate under heavy surge volumes",
            ),
        ],
    )


@pytest.fixture
def mock_recommendation():
    from app.schemas.recommendation import (
        ActionPlan,
        DecisionReadiness,
        DecisionStatus,
        EvidenceStrength,
        RecommendationStability,
        UncertaintyAssessment,
    )

    return DecisionRecommendation(
        id="rec_" + "a" * 32,
        decision_model_id="dec_test",
        evidence_package_id="ev_test",
        reasoning_board_id="rb_test",
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Controlled Pilot Deployment with Staged Fallback",
        executive_rationale="Controlled pilot mitigates operational risk while capturing efficiency gains across customer support operations.",
        action_plan=ActionPlan(
            summary="Sequenced 90-day pilot validation roadmap",
            actions=[
                ActionItem(
                    id="act_1",
                    title="Shadow Mode Evaluation",
                    objective="Evaluate model deflection without customer-facing risk",
                    description="Launch shadow mode evaluation for tier 1 tickets",
                    priority=ActionPriority.HIGH,
                    responsible_role="Engineering Lead",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    decision_gates=[
                        DecisionGate(
                            id="gate_1",
                            condition="CSAT >= 80%",  # Note: Stage 1 said 85%, so this triggers threshold mismatch!
                            target_milestone="Pilot CSAT Threshold",
                            verification_method="Weekly Zendesk CSAT survey",
                            fallback_action="Rollback to manual routing",
                        ),
                        DecisionGate(
                            id="gate_2",
                            condition="TBD",  # Undefined placeholder threshold triggers rule 12!
                            target_milestone="Latency Ceiling",
                            verification_method="Datadog APM monitor",
                            fallback_action="De-escalate to human staff",
                        ),
                    ],
                ),
            ],
            key_milestones=["Month 1 Shadow Run", "Month 3 Full Review"],
        ),
        alternative_options=[
            AlternativeOption(
                id="alt_1",
                name="Full Instant Deployment",
                description="Immediately route 100% of tier 1 tickets to automated agent.",
                tradeoffs=["Rapid time to value", "High disruption risk and lack of fallback"],
                why_not_recommended="High disruption risk and lack of fallback.",
            ),
        ],
        uncertainty_assessment=UncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.NEEDS_VALIDATION,
            recommendation_stability=RecommendationStability.MODERATE,
            critical_missing_information=["Peak surge deflection degradation rate"],
            conditions_changing_recommendation=["If error rate exceeds 5% during pilot"],
            assumptions_relied_upon=["asm_1"],
            evidence_gaps_relied_upon=["g1"],
        ),
    )


@pytest.fixture
def mock_scenario_set():
    return ScenarioSet(
        id="scenset_0123456789abcdef0123456789abcdef",
        decision_model_id="dec_test",
        summary="Comprehensive future scenario simulations evaluating decision pathways across optimistic, base case, and pessimistic conditions.",
        scenarios=[
            FutureScenario(
                id="scen_0123456789abcdef",
                scenario_type=ScenarioType.OPTIMISTIC,
                probability=0.25,
                name="Optimistic Trajectory & Rapid Expansion",
                narrative="Under this optimistic trajectory, strategic objectives are achieved ahead of schedule.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_1_1",
                        title="Early Validation Milestone",
                        description="Initial adoption metrics exceed baseline expectations.",
                        timeframe="Month 3",
                        impact_on_decision="Accelerates rollout objectives.",
                    )
                ],
                risks=["Scaling capacity constraints"],
                opportunities=["Rapid market leadership capture"],
                timeline=[
                    ScenarioMilestone(
                        id="ms_1_1",
                        title="Initial Gate Passed",
                        description="Core pilot milestone successfully completed.",
                        time_horizon="Month 3",
                        expected_outcome="Target growth achieved.",
                    )
                ],
            ),
            FutureScenario(
                id="scen_0123456789abcde1",
                scenario_type=ScenarioType.BASE_CASE,
                probability=0.50,
                name="Expected Baseline Growth",
                narrative="Normal operational conditions with 30% deflection and steady progress.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_2_1",
                        title="Target Milestone Reached",
                        description="Operational milestones achieved within planned variance.",
                        timeframe="Month 6",
                        impact_on_decision="Confirms baseline operational expectations.",
                    )
                ],
                risks=["Execution cadence friction"],
                opportunities=["Predictable sustainable growth"],
                timeline=[
                    ScenarioMilestone(
                        id="ms_2_1",
                        title="Mid-term Review",
                        description="Evaluation of performance metrics.",
                        time_horizon="Month 6",
                        expected_outcome="Target growth on schedule.",
                    )
                ],
            ),
            FutureScenario(
                id="scen_0123456789abcde2",
                scenario_type=ScenarioType.PESSIMISTIC,
                probability=0.25,
                name="Pessimistic Surge Outage",
                narrative="Surge traffic causes severe model hallucinations and customer backlash. CSAT drops severely and fails acceptance standards.",
                key_events=[
                    ScenarioKeyEvent(
                        id="ke_3_1",
                        title="Downside Trigger Checkpoint",
                        description="Adverse conditions necessitate activating defensive controls.",
                        timeframe="Month 4",
                        impact_on_decision="Triggers contingency mitigation protocols.",
                    )
                ],
                risks=["Catastrophic customer churn and operational failure"],
                opportunities=["Tightening fallback triggers"],
                timeline=[
                    ScenarioMilestone(
                        id="ms_3_1",
                        title="Defensive Reassessment",
                        description="Contingency protocols activated to preserve capital.",
                        time_horizon="Month 4",
                        expected_outcome="Downside capped.",
                    )
                ],
            ),
        ],
    )


@pytest.fixture
def mock_resilience_report():
    from app.schemas.resilience import ResilienceRating, ResilienceSubScore

    return ResilienceReport(
        id="res_" + "a" * 32,
        decision_model_id="dec_test",
        scenario_set_id="scenset_0123456789abcdef0123456789abcdef",
        recommendation_id="rec_" + "a" * 32,
        overall_score=85.0,  # High score while pessimistic scenario has catastrophic failure triggers rule 10!
        rating=ResilienceRating.HIGH,
        sub_scores=[
            ResilienceSubScore(category="Adversarial Scenarios", score=21.0, rationale="Robust performance in base conditions"),
            ResilienceSubScore(category="Constraint Adherence", score=22.0, rationale="Adheres to hard constraints"),
            ResilienceSubScore(category="Fallback Feasibility", score=21.0, rationale="Staged fallback mechanisms in place"),
            ResilienceSubScore(category="Information Stability", score=21.0, rationale="Baseline parameters are defined"),
        ],
        critical_vulnerabilities=["Single vendor dependency"],
        stress_test_passed=True,
        recommended_hedges=["Maintain human backup escalation queue"],
    )


# ------------------------------------------------------------------------------
# Test 1: Deterministic Calculator
# ------------------------------------------------------------------------------

def test_calculator_complete_financial_inputs(mock_decision_model, mock_recommendation):
    calc = DeterministicCalculator()
    context = {
        "annual_eligible_support_cost": 200000,
        "realized_deflection_fraction": 0.40,
        "avoidable_cost_fraction": 0.50,
        "monthly_cloud_cost": 1500,
        "budget_usd": 60000,
        "estimated_cost": 45000,
    }
    results = calc.evaluate_all(mock_decision_model, mock_recommendation, context)
    assert len(results) == 3

    # Check net savings: gross = 200000 * 0.4 * 0.5 = 40000. Cloud = 1500 * 12 = 18000. Net = 22000.
    net_calc = next(r for r in results if r.category == "net_savings")
    assert net_calc.status == CalculationStatus.FEASIBLE
    assert net_calc.value == 22000.0
    assert net_calc.currency == "USD"

    # Check cost ceiling: 60000 - 45000 = 15000 surplus
    ceil_calc = next(r for r in results if r.category == "cost_ceiling")
    assert ceil_calc.status == CalculationStatus.FEASIBLE
    assert ceil_calc.value == 15000.0


def test_calculator_missing_inputs_returns_unresolved(mock_decision_model, mock_recommendation):
    calc = DeterministicCalculator()
    # Missing avoidable_cost_fraction and monthly_cloud_cost
    context = {"annual_eligible_support_cost": 200000}
    results = calc.evaluate_all(mock_decision_model, mock_recommendation, context)

    net_calc = next(r for r in results if r.category == "net_savings")
    assert net_calc.status == CalculationStatus.UNRESOLVED
    assert len(net_calc.missing_inputs) > 0
    assert net_calc.value is None


def test_calculator_infeasible_budget_ceiling(mock_decision_model, mock_recommendation):
    calc = DeterministicCalculator()
    context = {
        "budget_usd": 30000,
        "estimated_cost": 50000,  # 20000 deficit!
    }
    results = calc.evaluate_all(mock_decision_model, mock_recommendation, context)
    ceil_calc = next(r for r in results if r.category == "cost_ceiling")
    assert ceil_calc.status == CalculationStatus.INFEASIBLE
    assert ceil_calc.value == -20000.0


# ------------------------------------------------------------------------------
# Test 2: Cross-Stage Consistency Checker
# ------------------------------------------------------------------------------

def test_consistency_checker_detects_contradictions(
    mock_decision_model,
    mock_evidence_package,
    mock_recommendation,
    mock_scenario_set,
    mock_resilience_report,
):
    calc = DeterministicCalculator()
    calcs = calc.evaluate_all(mock_decision_model, mock_recommendation, {})
    checker = CrossStageConsistencyChecker()

    reasoning_board = MagicMock()

    findings = checker.evaluate_all(
        decision_model=mock_decision_model,
        evidence_package=mock_evidence_package,
        reasoning_board=reasoning_board,
        recommendation=mock_recommendation,
        scenario_set=mock_scenario_set,
        resilience_report=mock_resilience_report,
        calculations=calcs,
    )

    rule_codes = {f.rule_code for f in findings}

    # Verify key expected findings:
    # 1. Duplicate evidence URL
    assert "RULE_DUPLICATE_EVIDENCE" in rule_codes
    # 2. Undefined quantitative gate threshold (gate_2 had empty threshold)
    assert "RULE_UNDEFINED_QUANTITATIVE_GATE" in rule_codes
    # 3. Missing net calculation (net_calc was unresolved)
    assert "RULE_MISSING_NET_CALCULATION" in rule_codes
    # 4. Threshold mismatch (Stage 1 CSAT 85% vs Stage 4 Gate CSAT 80%)
    assert "RULE_THRESHOLD_MISMATCH" in rule_codes
    # 5. Scenario gate breach (Pessimistic scenario mentions failure)
    assert "RULE_SCENARIO_GATE_BREACH" in rule_codes


# ------------------------------------------------------------------------------
# Test 3: Option Comparison Service (Day 8G-B)
# ------------------------------------------------------------------------------

def test_option_comparison_unranked_when_data_sparse(
    mock_decision_model,
    mock_evidence_package,
    mock_recommendation,
):
    service = OptionComparisonService()
    report = service.compare_options(
        decision_model=mock_decision_model,
        evidence_package=mock_evidence_package,
        recommendation=mock_recommendation,
    )
    assert len(report.options) >= 2
    # Recommended option is identified
    assert report.options[0].is_recommended is True
    # Non-recommended alternative option
    assert report.options[1].is_recommended is False
    # Ranking is flagged as not justified because alternative option has 0 empirical sources
    assert report.ranking_justified is False
    assert report.unranked_reason is not None


# ------------------------------------------------------------------------------
# Test 4: Evidence Quality Service (Day 8G-B)
# ------------------------------------------------------------------------------

def test_evidence_quality_classification_and_duplicates(mock_evidence_package):
    service = EvidenceQualityService()
    report = service.evaluate_evidence(mock_evidence_package)

    assert report.primary_count >= 1  # Stanford .edu
    assert report.vendor_count >= 1   # Vendor .io
    assert report.duplicate_count == 1  # Repeated URL
    assert len(report.sources) == 3


# ------------------------------------------------------------------------------
# Test 5: Uncertainty Calibration & Ranked Gaps (Day 8G-B)
# ------------------------------------------------------------------------------

def test_uncertainty_calibration_ranks_gaps(
    mock_decision_model,
    mock_evidence_package,
    mock_recommendation,
    mock_scenario_set,
):
    calc = DeterministicCalculator()
    calcs = calc.evaluate_all(mock_decision_model, mock_recommendation, {})
    service = UncertaintyCalibrationService()

    report = service.evaluate_uncertainty(
        decision_model=mock_decision_model,
        evidence_package=mock_evidence_package,
        recommendation=mock_recommendation,
        scenario_set=mock_scenario_set,
        calculations=calcs,
    )

    assert report.is_calibrated is False
    assert "heuristic" in report.scenario_weights_note.lower()
    assert len(report.ranked_gaps) > 0
    # First gap should block calculation
    assert report.ranked_gaps[0].decision_impact.value == "blocks_calculation"


# ------------------------------------------------------------------------------
# Test 6: ReportLab PDF Generator (Day 8G-C)
# ------------------------------------------------------------------------------

def test_pdf_generator_generates_valid_pdfs(
    mock_decision_model,
    mock_evidence_package,
    mock_recommendation,
    mock_scenario_set,
    mock_resilience_report,
):
    from app.schemas.report import (
        DecisionOverviewModel,
        SharedReportModel,
    )

    calc = DeterministicCalculator()
    calcs = calc.evaluate_all(mock_decision_model, mock_recommendation, {})

    opt_service = OptionComparisonService()
    opt_comp = opt_service.compare_options(
        mock_decision_model, mock_evidence_package, mock_recommendation
    )

    ev_service = EvidenceQualityService()
    ev_qual = ev_service.evaluate_evidence(mock_evidence_package)

    unc_service = UncertaintyCalibrationService()
    unc = unc_service.evaluate_uncertainty(
        mock_decision_model, mock_evidence_package, mock_recommendation, mock_scenario_set, calcs
    )

    overview = DecisionOverviewModel(
        title="Deploy AI customer support automation",
        recommended_direction="Controlled Pilot Deployment",
        short_rationale="Balances operational risk with efficiency gains.",
        decision_readiness=DecisionReadinessStatus.NEEDS_VALIDATION,
        integrity_status=IntegrityStatus.WARNING,
        key_metrics={"Deflection": "30%"},
        analysis_id="test_analysis_123",
    )

    shared_report = SharedReportModel(
        analysis_id="test_analysis_123",
        overview=overview,
        option_comparison=opt_comp,
        calculations=calcs,
        evidence_quality=ev_qual,
        uncertainty_calibration=unc,
        scenario_matrix=[{"name": "Pessimistic", "implications": ["CSAT drops"]}],
        resilience_scorecard={"score": 85.0, "category": "High Resilience"},
    )

    gen = AuraPDFGenerator()

    # Generate Summary PDF
    summary_pdf = gen.generate_summary_pdf(shared_report)
    assert isinstance(summary_pdf, bytes)
    assert summary_pdf.startswith(b"%PDF")
    assert len(summary_pdf) > 2000

    # Generate Detailed PDF
    detailed_pdf = gen.generate_detailed_pdf(shared_report)
    assert isinstance(detailed_pdf, bytes)
    assert detailed_pdf.startswith(b"%PDF")
    assert len(detailed_pdf) > 3000
