"""AURA Evidence & Source Provenance Schemas.

Defines the canonical, strongly-typed data structures for external research,
source provenance, factual evidence items, claim-to-evidence relationships,
and empirical gap detection.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.decision_model import ConfidenceLevel, CriticalityLevel


# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------

class SourceType(str, Enum):
    """Categorical classification of publishing authority.

    Search is an external retrieval channel, not an authority type.
    """
    ACADEMIC = "academic"                      # Peer-reviewed journal, university research paper
    INDUSTRY_REPORT = "industry_report"        # Analyst reports (Gartner, Forrester, McKinsey benchmarks)
    GOVERNMENT = "government"                  # Government bureaus, census, public statistical agencies
    REGULATORY_FILING = "regulatory_filing"    # Statutory filings (SEC 10-K, regulatory compliance audits)
    COMPANY_PRIMARY = "company_primary"        # First-party company disclosures, official documentation, whitepapers
    FINANCIAL_MARKET = "financial_market"      # Audited financial metrics, earnings calls, exchange feeds
    NEWS_MEDIA = "news_media"                  # Fact-checked journalism and reputable trade press
    INTERNAL_DATA = "internal_data"            # Proprietary corporate telemetry, internal data warehouses
    OTHER = "other"                            # Explicit fallback for uncategorized verified sources


class EvidenceKind(str, Enum):
    """The nature of inquiry required to satisfy an evidence requirement."""
    EXTERNAL_RESEARCH = "external_research"                # Secondary research via external literature/benchmarks
    INTERNAL_DATA = "internal_data"                        # First-party query into customer records, logs, or metrics
    USER_CLARIFICATION = "user_clarification"              # Direct question for the user or human decision-maker
    DETERMINISTIC_CALCULATION = "deterministic_calculation" # Downstream math engine task (e.g. break-even analysis)


class DecisionEntityType(str, Enum):
    """Strict taxonomy of DecisionModel entities targeted by requirements, links, and gaps."""
    OBJECTIVE = "objective"
    VARIABLE = "variable"
    CONSTRAINT = "constraint"
    STAKEHOLDER = "stakeholder"
    TRADEOFF = "tradeoff"
    ASSUMPTION = "assumption"
    UNKNOWN = "unknown"
    KEY_QUESTION = "key_question"
    DECISION = "decision"


class EvidenceStance(str, Enum):
    """Epistemic relationship between an evidence excerpt and a target claim."""
    SUPPORTS = "supports"          # Directly bolsters or validates the target claim
    CHALLENGES = "challenges"      # Contradicts, refutes, or weakens the target claim
    CONTEXT = "context"            # Provides baseline framing or market color without asserting polarity
    INCONCLUSIVE = "inconclusive"  # Findings are ambiguous, statistically underpowered, or mixed


class EvidenceGapType(str, Enum):
    """Taxonomy of empirical deficiencies identified in the decision structure."""
    UNSUPPORTED_CLAIM = "unsupported_claim"        # Assumption or inferred variable with 0 supporting evidence
    UNRESOLVED_UNKNOWN = "unresolved_unknown"      # Crucial information gap with no discovered empirical resolution
    CONFLICTING_EVIDENCE = "conflicting_evidence"  # Multiple sources assert contradictory stances (e.g. supports vs challenges)
    INSUFFICIENT_EVIDENCE = "insufficient_evidence" # Found evidence is low-confidence or lacks direct domain transferability


class RequirementStatus(str, Enum):
    """Lifecycle fulfillment state of an EvidenceRequirement."""
    PENDING = "pending"
    FULFILLED = "fulfilled"
    UNSUPPORTED = "unsupported"
    CONTESTED = "contested"
    INCONCLUSIVE = "inconclusive"


# ------------------------------------------------------------------------------
# Core Evidence Models
# ------------------------------------------------------------------------------

class NumericEvidence(BaseModel):
    """Authoritative representation of a single extracted quantitative finding."""
    model_config = ConfigDict(str_strip_whitespace=True)

    metric_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Metric label (e.g. 'median_volume_expansion').",
    )
    value: Optional[float] = Field(
        default=None,
        description="Point estimate or central tendency value.",
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Unit of measurement (e.g. '%', 'USD', 'months').",
    )
    range_min: Optional[float] = Field(
        default=None,
        description="Lower bound of confidence interval or observed range.",
    )
    range_max: Optional[float] = Field(
        default=None,
        description="Upper bound of confidence interval or observed range.",
    )
    confidence_interval: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Statistical interval statement (e.g. '95% CI [12.0, 16.0]').",
    )
    sample_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of observations (n) if reported (must be >= 1).",
    )
    context: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Clarification of scope or sample (e.g. 'B2B SaaS with $1M-$10M ARR').",
    )

    @model_validator(mode="after")
    def validate_numeric_values(self) -> "NumericEvidence":
        """Ensures numeric evidence contains a point value or valid range, and bounds are ordered."""
        has_point = self.value is not None
        has_min = self.range_min is not None
        has_max = self.range_max is not None

        if not has_point and not has_min and not has_max:
            raise ValueError(
                "NumericEvidence must contain a point value or a meaningful range (range_min / range_max)."
            )

        if has_min and has_max and self.range_min > self.range_max:
            raise ValueError(
                f"range_min ({self.range_min}) cannot be greater than range_max ({self.range_max})."
            )

        return self


class Source(BaseModel):
    """Canonical representation of an external document, study, or dataset."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique source identifier (e.g. 'src_openview_2024').",
    )
    url: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="Canonical web URL if available.",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=250,
        description="Official title of document, report, or release.",
    )
    publisher: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Publishing organization or domain (e.g. 'OpenView Labs').",
    )
    source_type: SourceType = Field(
        ...,
        description="Classification of publishing authority.",
    )
    publication_date: Optional[date] = Field(
        default=None,
        description="Typed publication date if recorded.",
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp when content was retrieved.",
    )
    reliability_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Unset for Day 3; reserved for future deterministic SourceQualityEngine.",
    )

    @field_validator("retrieval_timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Guarantees retrieval timestamp is timezone-aware UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class EvidenceItem(BaseModel):
    """Discrete empirical finding extracted from a Source.

    Semantics:
    - content: Evidence derived directly from retrieved source material (verbatim excerpt or finding).
               Never represent generated or paraphrased content as a verbatim quotation.
    - summary: AURA-generated concise interpretation of that evidence.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique evidence item identifier (e.g. 'evi_saas_elasticity_01').",
    )
    source_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Reference to parent Source.id guaranteeing provenance.",
    )
    content: str = Field(
        ...,
        min_length=3,
        description="Evidence derived directly from retrieved source material.",
    )
    summary: Optional[str] = Field(
        default=None,
        max_length=500,
        description="AURA-generated concise interpretation of that evidence.",
    )
    numeric_data: List[NumericEvidence] = Field(
        default_factory=list,
        description="Strict structured numerical data.",
    )
    extraction_confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.HIGH,
        description="Confidence that excerpt faithfully captures source material without distortion.",
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of retrieval.",
    )

    @field_validator("retrieval_timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Guarantees retrieval timestamp is timezone-aware UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class ClaimEvidenceLink(BaseModel):
    """Relational binding connecting an EvidenceItem to a specific DecisionModel entity."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique link identifier (e.g. 'lnk_asm_elasticity_evi_01').",
    )
    evidence_item_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Reference to EvidenceItem.id.",
    )
    target_entity_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of entity in DecisionModel (e.g. 'asm_elasticity').",
    )
    target_entity_type: DecisionEntityType = Field(
        ...,
        description="Entity classification enum.",
    )
    stance: EvidenceStance = Field(
        ...,
        description="Stance: supports, challenges, context, inconclusive.",
    )
    reasoning: str = Field(
        ...,
        min_length=3,
        description="Transparent justification for why this evidence supports or challenges the claim.",
    )
    relationship_confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Confidence in the strength of this specific relationship/stance.",
    )
    requirement_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Reference to parent EvidenceRequirement.id preserving retrieval lineage.",
    )



class EvidenceRequirement(BaseModel):
    """Specification of empirical evidence required to validate an assumption or resolve an unknown."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique requirement identifier (e.g. 'req_elasticity_proof').",
    )
    target_entity_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of target entity in DecisionModel.",
    )
    target_entity_type: DecisionEntityType = Field(
        ...,
        description="Classification of target entity.",
    )
    kind: EvidenceKind = Field(
        ...,
        description="Inquiry kind: external_research, internal_data, user_clarification, deterministic_calculation.",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Factual question or hypothesis needing validation.",
    )
    priority: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM,
        description="Priority of resolving this requirement.",
    )
    status: RequirementStatus = Field(
        default=RequirementStatus.PENDING,
        description="Current resolution status.",
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="Targeted query strings for retrieval providers.",
    )


class EvidenceGap(BaseModel):
    """Identified empirical gap, contradiction, or insufficiency."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique gap identifier (e.g. 'gap_elasticity_conflict').",
    )
    gap_type: EvidenceGapType = Field(
        ...,
        description="Taxonomy: unsupported_claim, unresolved_unknown, conflicting_evidence, insufficient_evidence.",
    )
    target_entity_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the affected DecisionModel entity.",
    )
    target_entity_type: DecisionEntityType = Field(
        ...,
        description="Entity classification.",
    )
    requirement_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Associated EvidenceRequirement.id if applicable.",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Explanation of missing information or contradictory findings.",
    )
    impact: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM,
        description="Impact of leaving this gap unaddressed.",
    )
    conflicting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of contradictory EvidenceItems when gap_type is conflicting_evidence.",
    )
    resolution_guidance: Optional[str] = Field(
        default=None,
        description="Actionable guidance on how to close the gap.",
    )


class EvidencePackage(BaseModel):
    """Canonical domain representation of all empirical evidence, sources, links, and gaps."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Globally unique package identifier.",
    )
    decision_model_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Foreign key to DecisionModel.id.",
    )
    requirements: List[EvidenceRequirement] = Field(
        default_factory=list,
        description="Derived investigative requirements.",
    )
    sources: List[Source] = Field(
        default_factory=list,
        description="Consulted sources with publication metadata.",
    )
    items: List[EvidenceItem] = Field(
        default_factory=list,
        description="Discrete factual findings.",
    )
    claim_links: List[ClaimEvidenceLink] = Field(
        default_factory=list,
        description="Bindings between evidence items and claims.",
    )
    gaps: List[EvidenceGap] = Field(
        default_factory=list,
        description="Detected empirical gaps and contradictions.",
    )
    summary: str = Field(
        ...,
        min_length=3,
        description="High-level synthesis of empirical coverage.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of creation.",
    )

    @field_validator("created_at")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Guarantees created_at is timezone-aware UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_internal_references(self) -> "EvidencePackage":
        """Enforces referential integrity inside the EvidencePackage.

        Validates:
        1. IDs are unique within each collection.
        2. Every EvidenceItem.source_id references an existing Source.id.
        3. Every ClaimEvidenceLink.evidence_item_id references an existing EvidenceItem.id.
        4. Every non-null EvidenceGap.requirement_id references an existing EvidenceRequirement.id.
        5. For CONFLICTING_EVIDENCE gaps:
           - At least two conflicting_evidence_ids.
           - Every conflicting ID references an existing EvidenceItem.
        """
        # 1. Unique IDs within each collection
        collections = {
            "requirements": [r.id for r in self.requirements],
            "sources": [s.id for s in self.sources],
            "items": [i.id for i in self.items],
            "claim_links": [l.id for l in self.claim_links],
            "gaps": [g.id for g in self.gaps],
        }
        for name, ids in collections.items():
            seen: Set[str] = set()
            for entity_id in ids:
                if entity_id in seen:
                    raise ValueError(f"Duplicate ID '{entity_id}' found in '{name}' collection.")
                seen.add(entity_id)

        # 2. EvidenceItem.source_id references an existing Source.id
        source_ids = {s.id for s in self.sources}
        for item in self.items:
            if item.source_id not in source_ids:
                raise ValueError(
                    f"EvidenceItem '{item.id}' references non-existent source_id '{item.source_id}'."
                )

        # 3. ClaimEvidenceLink.evidence_item_id references an existing EvidenceItem.id
        item_ids = {i.id for i in self.items}
        req_ids = {r.id for r in self.requirements}
        for link in self.claim_links:
            if link.evidence_item_id not in item_ids:
                raise ValueError(
                    f"ClaimEvidenceLink '{link.id}' references non-existent evidence_item_id '{link.evidence_item_id}'."
                )
            if link.requirement_id is not None and link.requirement_id not in req_ids:
                raise ValueError(
                    f"ClaimEvidenceLink '{link.id}' references non-existent requirement_id '{link.requirement_id}'."
                )

        # 4. EvidenceGap.requirement_id references an existing EvidenceRequirement.id (when non-null)
        for gap in self.gaps:
            if gap.requirement_id is not None and gap.requirement_id not in req_ids:
                raise ValueError(
                    f"EvidenceGap '{gap.id}' references non-existent requirement_id '{gap.requirement_id}'."
                )

            # 5. For CONFLICTING_EVIDENCE:
            # - at least two conflicting_evidence_ids
            # - every ID references an existing EvidenceItem
            if gap.gap_type == EvidenceGapType.CONFLICTING_EVIDENCE:
                if len(gap.conflicting_evidence_ids) < 2:
                    raise ValueError(
                        f"EvidenceGap '{gap.id}' of type conflicting_evidence must contain at least two conflicting_evidence_ids."
                    )
                for eid in gap.conflicting_evidence_ids:
                    if eid not in item_ids:
                        raise ValueError(
                            f"EvidenceGap '{gap.id}' references non-existent conflicting evidence ID '{eid}'."
                        )

        return self
