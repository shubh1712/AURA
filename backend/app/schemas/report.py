"""Shared Report Data Model (Day 8G-C).

Defines the single authoritative, normalized presentation data model used across:
- Main Dashboard
- Summary Online Page (/analysis/[id]/summary)
- Detailed Online Page (/analysis/[id]/detailed)
- Summary PDF Export (2-4 pages executive brief)
- Detailed PDF Export (comprehensive multi-page audit report)
Guarantees parity and zero divergent interpretations across views.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.decision_integrity import (
    CalculationResult,
    DecisionIntegrityReport,
    DecisionReadinessStatus,
    EvidenceQualityReport,
    IntegrityFinding,
    IntegrityStatus,
    OptionComparisonReport,
    UncertaintyCalibrationReport,
)


class DecisionOverviewModel(BaseModel):
    """Persistent executive overview visible at top of dashboard and leading all reports."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., description="Decision summary or core question.")
    decision_title: str = Field(default="", description="Frontend alias for title.")
    recommended_direction: str = Field(..., description="Primary recommendation directive.")
    short_rationale: str = Field(..., description="1-2 sentence core justification.")
    decision_readiness: DecisionReadinessStatus = Field(..., description="Executive readiness state.")
    integrity_status: IntegrityStatus = Field(..., description="Deterministic integrity health rating.")
    critical_warning_count: int = Field(default=0, description="Count of critical and high integrity warnings.")
    key_metrics: Dict[str, Any] = Field(default_factory=dict, description="Key supported empirical/calculated metrics.")
    falsification_condition: str = Field(
        default="If pilot metrics drop below threshold or recurring infrastructure costs exceed ceiling.",
        description="The primary condition that would invalidate the recommendation.",
    )
    top_falsification_condition: str = Field(
        default="",
        description="Frontend alias for falsification_condition.",
    )
    analysis_id: str = Field(..., description="Unique analysis job identifier.")
    created_at: str = Field(default="", description="Analysis creation timestamp.")

    @model_validator(mode="after")
    def sync_aliases(self) -> "DecisionOverviewModel":
        if not self.decision_title:
            object.__setattr__(self, "decision_title", self.title)
        if not self.title and self.decision_title:
            object.__setattr__(self, "title", self.decision_title)
        if not self.top_falsification_condition:
            object.__setattr__(self, "top_falsification_condition", self.falsification_condition)
        if not self.falsification_condition and self.top_falsification_condition:
            object.__setattr__(self, "falsification_condition", self.top_falsification_condition)
        return self


class PerspectiveSummary(BaseModel):
    """Boardroom perspective breakdown."""
    model_config = ConfigDict(str_strip_whitespace=True)

    role: str = Field(default="")
    perspective_type: str = Field(default="")
    title: str = Field(default="")
    stance: str = Field(default="neutral")
    perspective: str = Field(default="")
    key_argument: str = Field(default="")
    key_arguments: List[str] = Field(default_factory=list)
    dissent_or_concerns: List[str] = Field(default_factory=list)
    critical_concerns: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_aliases(self) -> "PerspectiveSummary":
        if not self.title and self.role:
            object.__setattr__(self, "title", self.role)
        if not self.role and self.title:
            object.__setattr__(self, "role", self.title)
        if not self.perspective_type and self.title:
            object.__setattr__(self, "perspective_type", self.title.lower().replace(" perspective", ""))
        if not self.key_argument and self.key_arguments:
            object.__setattr__(self, "key_argument", self.key_arguments[0])
        elif not self.key_arguments and self.key_argument:
            object.__setattr__(self, "key_arguments", [self.key_argument])
        if not self.critical_concerns and self.dissent_or_concerns:
            object.__setattr__(self, "critical_concerns", list(self.dissent_or_concerns))
        elif not self.dissent_or_concerns and self.critical_concerns:
            object.__setattr__(self, "dissent_or_concerns", list(self.critical_concerns))
        return self


class ActionRoadmapItem(BaseModel):
    """Normalized action roadmap item."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default="")
    step: int = Field(default=1)
    title: str = Field(default="")
    phase: str = Field(default="")
    timeframe: str = Field(default="")
    time_horizon: str = Field(default="")
    owner_role: str = Field(default="")
    responsible_role: str = Field(default="")
    decision_gate: Optional[str] = None
    validation_criteria: Optional[str] = None
    fallback: Optional[str] = None
    fallback_plan: Optional[str] = None

    @model_validator(mode="after")
    def sync_aliases(self) -> "ActionRoadmapItem":
        if not self.responsible_role and self.owner_role:
            object.__setattr__(self, "responsible_role", self.owner_role)
        if not self.owner_role and self.responsible_role:
            object.__setattr__(self, "owner_role", self.responsible_role)
        if not self.time_horizon and self.timeframe:
            object.__setattr__(self, "time_horizon", self.timeframe)
        if not self.timeframe and self.time_horizon:
            object.__setattr__(self, "timeframe", self.time_horizon)
        if not self.fallback_plan and self.fallback:
            object.__setattr__(self, "fallback_plan", self.fallback)
        if not self.fallback and self.fallback_plan:
            object.__setattr__(self, "fallback", self.fallback_plan)
        return self


class SharedReportModel(BaseModel):
    """Authoritative normalized report model used for web rendering and PDF exports."""
    model_config = ConfigDict(str_strip_whitespace=True)

    analysis_id: str
    overview: DecisionOverviewModel
    option_comparison: OptionComparisonReport
    calculations: List[CalculationResult] = Field(default_factory=list)
    scenario_matrix: List[Dict[str, Any]] = Field(default_factory=list)
    scenarios_summary: List[Dict[str, Any]] = Field(default_factory=list)
    resilience_scorecard: Dict[str, Any] = Field(default_factory=dict)
    evidence_quality: EvidenceQualityReport
    uncertainty_calibration: UncertaintyCalibrationReport
    integrity_findings: List[IntegrityFinding] = Field(default_factory=list)
    integrity_report: Optional[DecisionIntegrityReport] = Field(default=None)
    boardroom_perspectives: List[PerspectiveSummary] = Field(default_factory=list)
    perspectives: List[PerspectiveSummary] = Field(default_factory=list)
    action_roadmap: List[ActionRoadmapItem] = Field(default_factory=list)
    roadmap: List[ActionRoadmapItem] = Field(default_factory=list)
    decision_gates: List[Dict[str, Any]] = Field(default_factory=list)
    full_decision_model: Optional[Dict[str, Any]] = Field(default=None)
    full_framing: Optional[Dict[str, Any]] = Field(default=None)
    full_evidence_package: Optional[Dict[str, Any]] = Field(default=None)
    full_recommendation: Optional[Dict[str, Any]] = Field(default=None)
    full_resilience_report: Optional[Dict[str, Any]] = Field(default=None)
    full_scenarios: Optional[Dict[str, Any]] = Field(default=None)
    source_fingerprint: str = Field(default="")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default="")
    report_mode: str = Field(default="shared", description="'summary', 'detailed', or 'shared'")

    @model_validator(mode="after")
    def sync_aliases(self) -> "SharedReportModel":
        if not self.perspectives and self.boardroom_perspectives:
            object.__setattr__(self, "perspectives", list(self.boardroom_perspectives))
        elif not self.boardroom_perspectives and self.perspectives:
            object.__setattr__(self, "boardroom_perspectives", list(self.perspectives))

        if not self.roadmap and self.action_roadmap:
            object.__setattr__(self, "roadmap", list(self.action_roadmap))
        elif not self.action_roadmap and self.roadmap:
            object.__setattr__(self, "action_roadmap", list(self.roadmap))

        if not self.full_framing and self.full_decision_model:
            object.__setattr__(self, "full_framing", self.full_decision_model)
        elif not self.full_decision_model and self.full_framing:
            object.__setattr__(self, "full_decision_model", self.full_framing)

        if not self.created_at and self.overview.created_at:
            object.__setattr__(self, "created_at", self.overview.created_at)
        return self
