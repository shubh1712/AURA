"""Mock DecisionModel Factory.

Provides a canonical, fully-typed DecisionModel instance for use in unit tests
and offline development without active external LLM connections.
"""

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


def get_default_decision_model(question: str = "Should our startup reduce pricing by 20% to acquire more customers?") -> DecisionModel:
    """Generates a valid canonical DecisionModel matching the supplied question."""
    return DecisionModel(
        id="dec_mock_default_01",
        decision=Decision(
            raw_prompt=question,
            summary="Evaluate pricing adjustment to optimize customer acquisition and unit economics.",
            decision_type=DecisionType.STRATEGIC_DIRECTION,
            time_horizon=TimeHorizon.MEDIUM_TERM,
        ),
        complexity=Complexity(
            level=ComplexityLevel.MEDIUM,
            reasoning="Multi-variable optimization involving pricing, churn, CAC, and margins.",
            reversibility=ReversibilityLevel.PARTIALLY_REVERSIBLE,
            score=45.0,
        ),
        objectives=[
            Objective(
                id="obj_primary_growth",
                description="Accelerate net customer acquisition volume.",
                is_primary=True,
                target_metric="+25% MoM account growth",
                provenance=ProvenanceType.USER_PROVIDED,
            ),
            Objective(
                id="obj_protect_margins",
                description="Maintain gross profit margin above baseline threshold.",
                is_primary=False,
                target_metric=">= 70% gross margin",
                provenance=ProvenanceType.INFERRED,
            ),
        ],
        variables=[
            Variable(
                id="var_discount_percentage",
                name="Pricing Discount",
                description="Percentage discount on standard tier subscription.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=None,
                proposed_value=20.0,
                unit="%",
                is_controllable=True,
                provenance=ProvenanceType.USER_PROVIDED,
                baseline_provenance=ProvenanceType.UNKNOWN,
                proposed_provenance=ProvenanceType.USER_PROVIDED,
            ),
            Variable(
                id="var_monthly_churn",
                name="Monthly Churn Rate",
                description="Customer attrition rate.",
                variable_type=VariableType.PERCENTAGE,
                baseline_value=None,
                proposed_value=None,
                unit="%",
                is_controllable=False,
                provenance=ProvenanceType.INFERRED,
                baseline_provenance=ProvenanceType.UNKNOWN,
                proposed_provenance=ProvenanceType.UNKNOWN,
            ),
        ],
        constraints=[
            Constraint(
                id="cnstr_min_margin",
                name="Gross Margin Floor",
                description="Gross margin must not fall below 70%.",
                is_hard_constraint=True,
                source="user_specified",
                provenance=ProvenanceType.USER_PROVIDED,
            )
        ],
        stakeholders=[
            Stakeholder(
                id="stk_prospects",
                group="Target Market Prospects",
                impact_nature="Lower pricing reduces evaluation friction.",
                influence_level=CriticalityLevel.HIGH,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        tradeoffs=[
            Tradeoff(
                id="trd_volume_vs_arpu",
                upside="Accelerated top-of-funnel customer adoption.",
                downside="Reduced average revenue per user.",
                affected_variable_ids=["var_discount_percentage"],
                provenance=ProvenanceType.INFERRED,
            )
        ],
        assumptions=[
            Assumption(
                id="asm_elasticity",
                statement="Demand elasticity is sufficient for signup volume to offset price discount.",
                confidence=ConfidenceLevel.UNTESTED,
                provenance=ProvenanceType.INFERRED,
            )
        ],
        unknowns=[
            Unknown(
                id="unk_competitor_pricing",
                question="How aggressively will key competitors match or undercut this price discount?",
                criticality=CriticalityLevel.HIGH,
                potential_sources=["Market intelligence", "Customer feedback"],
                provenance=ProvenanceType.UNKNOWN,
            )
        ],
        key_questions=[
            "What is the estimated CAC payback period under the discounted rate?",
            "Will existing cohort customers request retroactive price adjustments?",
        ],
    )


def get_default_candidate_recommendation():
    """Generates a valid canonical CandidateDecisionRecommendation for mock/fake LLM runs."""
    from app.schemas.recommendation import (
        ActionPriority,
        ActionTimeHorizon,
        CandidateActionItem,
        CandidateActionPlan,
        CandidateAlternativeOption,
        CandidateDecisionRecommendation,
        CandidateUncertaintyAssessment,
        DecisionReadiness,
        DecisionStatus,
        EvidenceStrength,
        RecommendationStability,
    )

    return CandidateDecisionRecommendation(
        decision_status=DecisionStatus.PROCEED,
        recommended_action="Proceed with phased execution and structured milestone validation.",
        executive_rationale="Analysis indicates favorable conditions for proceeding with phased implementation under monitored risk controls.",
        supporting_evidence_item_ids=[],
        relevant_assumption_ids=[],
        relevant_evidence_gap_ids=[],
        unresolved_disagreement_ids=[],
        alternative_options=[
            CandidateAlternativeOption(
                name="Status Quo Baseline",
                description="Maintain current operating baseline without changes.",
                tradeoffs=["Preserves resources", "Forgoes strategic opportunities"],
                why_not_recommended="Does not address primary strategic objectives.",
            )
        ],
        uncertainty_assessment=CandidateUncertaintyAssessment(
            evidence_strength=EvidenceStrength.MODERATE,
            decision_readiness=DecisionReadiness.READY,
            recommendation_stability=RecommendationStability.HIGH,
            critical_missing_information=[],
            conditions_changing_recommendation=[],
            assumptions_relied_upon=[],
            evidence_gaps_relied_upon=[],
        ),
        action_plan=CandidateActionPlan(
            summary="Phased rollout prioritizing pilot validation followed by scaled execution.",
            actions=[
                CandidateActionItem(
                    title="Pilot Execution",
                    objective="Validate initial operational assumptions",
                    description="Execute targeted pilot across primary stakeholder segments.",
                    priority=ActionPriority.HIGH,
                    responsible_role="Project Lead",
                    time_horizon=ActionTimeHorizon.IMMEDIATE,
                    dependencies=[],
                    success_metrics=["Pilot milestones completed"],
                    risk_mitigations=["Regular review checkpoints"],
                    decision_gates=[],
                    fallback_action="Re-evaluate scope and assumptions",
                )
            ],
            key_milestones=["Pilot review", "Scaled rollout"],
        ),
    )
