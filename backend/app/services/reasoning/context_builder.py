"""AURA Deterministic Reasoning Context Builder.

Constructs strongly typed, immutable context structures for the AI Boardroom:
- Preserves trusted structural metadata vs untrusted external source content.
- Preserves exact epistemic semantics (provenance, kinds, statuses, stances).
- Indexes evidence by requirement lineage (requirement -> claim links -> evidence items).
- Indexes evidence by target decision entity (target entity -> requirements, links, gaps).
- Provides deterministic perspective-specific views without dropping contradictory evidence.
- Zero network calls, zero LLMs, zero embeddings, zero non-deterministic generation.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from app.schemas.decision_model import (
    Assumption,
    ComplexityLevel,
    ConfidenceLevel,
    Constraint,
    CriticalityLevel,
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
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidencePackage,
    EvidenceRequirement,
    EvidenceStance,
    NumericEvidence,
    RequirementStatus,
    Source,
    SourceType,
)
from app.schemas.reasoning import PerspectiveType
from app.services.reasoning.perspectives import (
    CANONICAL_PERSPECTIVES,
    PerspectiveDefinition,
)


# ------------------------------------------------------------------------------
# 1. Untrusted Source Material Isolation
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class UntrustedSourceText:
    """Explicitly isolated untrusted text retrieved from external or third-party sources.

    Maintains a strict boundary between trusted system/structural metadata and
    arbitrary external content to guard against prompt injection vulnerabilities.
    """

    raw_text: str

    def format_safe_xml(self) -> str:
        """Wraps untrusted content in defensive XML delimiter tags for downstream prompt generation."""
        return f"<untrusted_source_material>\n{self.raw_text}\n</untrusted_source_material>"


# ------------------------------------------------------------------------------
# 2. Immutable Structural Contexts for Evidence Artifacts
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceContext:
    """Immutable representation of source publishing metadata."""

    id: str
    url: Optional[str]
    title: Optional[str]
    publisher: Optional[str]
    source_type: SourceType
    publication_date: Optional[date]
    retrieval_timestamp: datetime
    reliability_score: Optional[float]


@dataclass(frozen=True)
class EvidenceItemContext:
    """Immutable representation of a discrete factual finding with isolated source text."""

    id: str
    source_id: str
    content: UntrustedSourceText
    summary: Optional[str]
    numeric_data: Tuple[NumericEvidence, ...]
    extraction_confidence: ConfidenceLevel
    retrieval_timestamp: datetime
    source: Optional[SourceContext]


@dataclass(frozen=True)
class ClaimLinkContext:
    """Immutable binding between an evidence finding and a target decision entity."""

    id: str
    evidence_item_id: str
    target_entity_id: str
    target_entity_type: DecisionEntityType
    stance: EvidenceStance
    reasoning: str
    relationship_confidence: ConfidenceLevel
    requirement_id: Optional[str]
    evidence_item: Optional[EvidenceItemContext]


@dataclass(frozen=True)
class RequirementContext:
    """Immutable representation of an investigative requirement with its bound claim links."""

    id: str
    target_entity_id: str
    target_entity_type: DecisionEntityType
    kind: EvidenceKind
    description: str
    priority: CriticalityLevel
    status: RequirementStatus
    suggested_queries: Tuple[str, ...]
    claim_links: Tuple[ClaimLinkContext, ...]


@dataclass(frozen=True)
class GapContext:
    """Immutable representation of an identified empirical gap or contradiction."""

    id: str
    target_entity_id: str
    target_entity_type: DecisionEntityType
    gap_type: EvidenceGapType
    description: str
    impact: CriticalityLevel
    conflicting_evidence_ids: Tuple[str, ...]
    resolution_guidance: Optional[str]


@dataclass(frozen=True)
class EntityEvidenceIndex:
    """Deterministic index of all requirements, claim links, and gaps targeting a specific entity."""

    target_entity_id: str
    target_entity_type: DecisionEntityType
    requirements: Tuple[RequirementContext, ...]
    claim_links: Tuple[ClaimLinkContext, ...]
    gaps: Tuple[GapContext, ...]


# ------------------------------------------------------------------------------
# 3. Macro Decision & Evidence Contexts
# ------------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionContext:
    """Immutable domain representation of the analyzed decision problem."""

    decision_id: str
    raw_prompt: str
    summary: str
    decision_type: DecisionType
    time_horizon: TimeHorizon
    complexity_level: ComplexityLevel
    complexity_reasoning: str
    reversibility: ReversibilityLevel
    objectives: Tuple[Objective, ...]
    variables: Tuple[Variable, ...]
    constraints: Tuple[Constraint, ...]
    stakeholders: Tuple[Stakeholder, ...]
    tradeoffs: Tuple[Tradeoff, ...]
    assumptions: Tuple[Assumption, ...]
    unknowns: Tuple[Unknown, ...]
    key_questions: Tuple[str, ...]


@dataclass(frozen=True)
class EvidenceContext:
    """Immutable representation of all empirical evidence, lineages, and derived indexes."""

    evidence_package_id: str
    decision_model_id: str
    summary: str
    created_at: datetime
    sources: Tuple[SourceContext, ...]
    items: Tuple[EvidenceItemContext, ...]
    claim_links: Tuple[ClaimLinkContext, ...]
    requirements: Tuple[RequirementContext, ...]
    gaps: Tuple[GapContext, ...]
    entity_indexes: Tuple[EntityEvidenceIndex, ...]


@dataclass(frozen=True)
class ReasoningContext:
    """Top-level unified boardroom context encompassing decision and evidence models."""

    decision_context: DecisionContext
    evidence_context: EvidenceContext


@dataclass(frozen=True)
class PerspectiveContext:
    """Deterministic perspective-specific context prepared for a boardroom lens.

    Retains complete access to the decision and evidence base while providing
    perspective-prioritized sequences for focused deliberation.
    """

    perspective: PerspectiveDefinition
    decision_context: DecisionContext
    evidence_context: EvidenceContext

    # Perspective-prioritized views (never deleting contradictory material)
    prioritized_objectives: Tuple[Objective, ...]
    prioritized_variables: Tuple[Variable, ...]
    prioritized_constraints: Tuple[Constraint, ...]
    prioritized_tradeoffs: Tuple[Tradeoff, ...]
    prioritized_stakeholders: Tuple[Stakeholder, ...]
    prioritized_requirements: Tuple[RequirementContext, ...]
    prioritized_claim_links: Tuple[ClaimLinkContext, ...]
    prioritized_gaps: Tuple[GapContext, ...]
    prioritized_assumptions: Tuple[Assumption, ...]
    prioritized_unknowns: Tuple[Unknown, ...]


# ------------------------------------------------------------------------------
# 4. Context Construction Implementation
# ------------------------------------------------------------------------------

def _build_source_context(source: Source) -> SourceContext:
    return SourceContext(
        id=source.id,
        url=source.url,
        title=source.title,
        publisher=source.publisher,
        source_type=source.source_type,
        publication_date=source.publication_date,
        retrieval_timestamp=source.retrieval_timestamp,
        reliability_score=source.reliability_score,
    )


def _build_evidence_item_context(
    item: EvidenceItem,
    sources_by_id: Dict[str, SourceContext],
) -> EvidenceItemContext:
    return EvidenceItemContext(
        id=item.id,
        source_id=item.source_id,
        content=UntrustedSourceText(raw_text=item.content),
        summary=item.summary,
        numeric_data=tuple(item.numeric_data),
        extraction_confidence=item.extraction_confidence,
        retrieval_timestamp=item.retrieval_timestamp,
        source=sources_by_id.get(item.source_id),
    )


def _build_claim_link_context(
    link: ClaimEvidenceLink,
    items_by_id: Dict[str, EvidenceItemContext],
) -> ClaimLinkContext:
    return ClaimLinkContext(
        id=link.id,
        evidence_item_id=link.evidence_item_id,
        target_entity_id=link.target_entity_id,
        target_entity_type=link.target_entity_type,
        stance=link.stance,
        reasoning=link.reasoning,
        relationship_confidence=link.relationship_confidence,
        requirement_id=link.requirement_id,
        evidence_item=items_by_id.get(link.evidence_item_id),
    )


def _build_requirement_context(
    req: EvidenceRequirement,
    claim_links_by_req: Dict[str, List[ClaimLinkContext]],
) -> RequirementContext:
    bound_links = claim_links_by_req.get(req.id, [])
    return RequirementContext(
        id=req.id,
        target_entity_id=req.target_entity_id,
        target_entity_type=req.target_entity_type,
        kind=req.kind,
        description=req.description,
        priority=req.priority,
        status=req.status,
        suggested_queries=tuple(req.suggested_queries),
        claim_links=tuple(bound_links),
    )


def _build_gap_context(gap: EvidenceGap) -> GapContext:
    return GapContext(
        id=gap.id,
        target_entity_id=gap.target_entity_id,
        target_entity_type=gap.target_entity_type,
        gap_type=gap.gap_type,
        description=gap.description,
        impact=gap.impact,
        conflicting_evidence_ids=tuple(gap.conflicting_evidence_ids),
        resolution_guidance=gap.resolution_guidance,
    )


def build_reasoning_context(
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
) -> ReasoningContext:
    """Builds a pure, deterministic ReasoningContext from upstream domain models.

    Preserves all epistemic classifications, indexes evidence by requirement and
    target entity, and isolates external source text without mutating inputs.
    """
    # 1. DecisionContext construction (strictly preserving provenance and structures)
    decision_ctx = DecisionContext(
        decision_id=decision_model.id,
        raw_prompt=decision_model.decision.raw_prompt,
        summary=decision_model.decision.summary,
        decision_type=decision_model.decision.decision_type,
        time_horizon=decision_model.decision.time_horizon,
        complexity_level=decision_model.complexity.level,
        complexity_reasoning=decision_model.complexity.reasoning,
        reversibility=decision_model.complexity.reversibility,
        objectives=tuple(decision_model.objectives),
        variables=tuple(decision_model.variables),
        constraints=tuple(decision_model.constraints),
        stakeholders=tuple(decision_model.stakeholders),
        tradeoffs=tuple(decision_model.tradeoffs),
        assumptions=tuple(decision_model.assumptions),
        unknowns=tuple(decision_model.unknowns),
        key_questions=tuple(decision_model.key_questions),
    )

    # 2. Source Contexts
    source_contexts = tuple(_build_source_context(s) for s in evidence_package.sources)
    sources_by_id = {s.id: s for s in source_contexts}

    # 3. Evidence Item Contexts
    item_contexts = tuple(
        _build_evidence_item_context(item, sources_by_id)
        for item in evidence_package.items
    )
    items_by_id = {item.id: item for item in item_contexts}

    # 4. Claim Link Contexts
    claim_link_contexts = tuple(
        _build_claim_link_context(link, items_by_id)
        for link in evidence_package.claim_links
    )

    # 5. Requirement Contexts with strict requirement_id lineage indexing
    claim_links_by_req: Dict[str, List[ClaimLinkContext]] = {}
    for cl in claim_link_contexts:
        if cl.requirement_id:
            claim_links_by_req.setdefault(cl.requirement_id, []).append(cl)

    requirement_contexts = tuple(
        _build_requirement_context(req, claim_links_by_req)
        for req in evidence_package.requirements
    )

    # 6. Gap Contexts
    gap_contexts = tuple(_build_gap_context(gap) for gap in evidence_package.gaps)

    # 7. Entity Evidence Indexes (deterministic canonical ordering from DecisionModel)
    requirements_by_entity: Dict[str, List[RequirementContext]] = {}
    for req in requirement_contexts:
        requirements_by_entity.setdefault(req.target_entity_id, []).append(req)

    claim_links_by_entity: Dict[str, List[ClaimLinkContext]] = {}
    for cl in claim_link_contexts:
        claim_links_by_entity.setdefault(cl.target_entity_id, []).append(cl)

    gaps_by_entity: Dict[str, List[GapContext]] = {}
    for gap in gap_contexts:
        gaps_by_entity.setdefault(gap.target_entity_id, []).append(gap)

    # Determine canonical entity ID sequence
    canonical_entities: List[Tuple[str, DecisionEntityType]] = [
        (decision_model.id, DecisionEntityType.DECISION),
    ]
    for obj in decision_model.objectives:
        canonical_entities.append((obj.id, DecisionEntityType.OBJECTIVE))
    for var in decision_model.variables:
        canonical_entities.append((var.id, DecisionEntityType.VARIABLE))
    for c in decision_model.constraints:
        canonical_entities.append((c.id, DecisionEntityType.CONSTRAINT))
    for s in decision_model.stakeholders:
        canonical_entities.append((s.id, DecisionEntityType.STAKEHOLDER))
    for t in decision_model.tradeoffs:
        canonical_entities.append((t.id, DecisionEntityType.TRADEOFF))
    for a in decision_model.assumptions:
        canonical_entities.append((a.id, DecisionEntityType.ASSUMPTION))
    for u in decision_model.unknowns:
        canonical_entities.append((u.id, DecisionEntityType.UNKNOWN))

    # Also capture any external target entity referenced in evidence package
    known_entity_ids = {ent_id for ent_id, _ in canonical_entities}
    extra_entity_ids = sorted(
        set(requirements_by_entity.keys())
        | set(claim_links_by_entity.keys())
        | set(gaps_by_entity.keys())
        - known_entity_ids
    )
    for extra_id in extra_entity_ids:
        # Determine entity type from requirements or claim links
        extra_type = DecisionEntityType.DECISION
        if extra_id in requirements_by_entity and requirements_by_entity[extra_id]:
            extra_type = requirements_by_entity[extra_id][0].target_entity_type
        elif extra_id in claim_links_by_entity and claim_links_by_entity[extra_id]:
            extra_type = claim_links_by_entity[extra_id][0].target_entity_type
        elif extra_id in gaps_by_entity and gaps_by_entity[extra_id]:
            extra_type = gaps_by_entity[extra_id][0].target_entity_type
        canonical_entities.append((extra_id, extra_type))

    entity_indexes: List[EntityEvidenceIndex] = []
    for ent_id, ent_type in canonical_entities:
        reqs = requirements_by_entity.get(ent_id, [])
        cls = claim_links_by_entity.get(ent_id, [])
        gps = gaps_by_entity.get(ent_id, [])
        if reqs or cls or gps:
            entity_indexes.append(
                EntityEvidenceIndex(
                    target_entity_id=ent_id,
                    target_entity_type=ent_type,
                    requirements=tuple(reqs),
                    claim_links=tuple(cls),
                    gaps=tuple(gps),
                )
            )

    evidence_ctx = EvidenceContext(
        evidence_package_id=evidence_package.id,
        decision_model_id=evidence_package.decision_model_id,
        summary=evidence_package.summary,
        created_at=evidence_package.created_at,
        sources=source_contexts,
        items=item_contexts,
        claim_links=claim_link_contexts,
        requirements=requirement_contexts,
        gaps=gap_contexts,
        entity_indexes=tuple(entity_indexes),
    )

    return ReasoningContext(
        decision_context=decision_ctx,
        evidence_context=evidence_ctx,
    )


def build_perspective_context(
    perspective: PerspectiveDefinition,
    reasoning_context: ReasoningContext,
) -> PerspectiveContext:
    """Builds a deterministic, perspective-prioritized PerspectiveContext.

    Prioritizes perspective-relevant artifacts while ensuring zero data loss:
    contradictory and challenging evidence is always preserved across all lenses.
    """
    dec_ctx = reasoning_context.decision_context
    evi_ctx = reasoning_context.evidence_context
    ptype = perspective.perspective_type

    if ptype == PerspectiveType.GROWTH:
        # Growth prioritizes primary objectives, controllable variables, and market opportunity
        prioritized_objectives = tuple(
            sorted(dec_ctx.objectives, key=lambda o: (not o.is_primary, o.id))
        )
        prioritized_variables = tuple(
            sorted(dec_ctx.variables, key=lambda v: (not v.is_controllable, v.id))
        )
        prioritized_constraints = dec_ctx.constraints
        prioritized_tradeoffs = dec_ctx.tradeoffs
        prioritized_stakeholders = dec_ctx.stakeholders

        # Prioritize external research and clarification requirements
        prioritized_requirements = tuple(
            sorted(
                evi_ctx.requirements,
                key=lambda r: (
                    r.kind not in (EvidenceKind.EXTERNAL_RESEARCH, EvidenceKind.USER_CLARIFICATION),
                    r.id,
                ),
            )
        )
        # Prioritize supporting and context evidence, while keeping challenges and inconclusive
        prioritized_claim_links = tuple(
            sorted(
                evi_ctx.claim_links,
                key=lambda cl: (
                    cl.stance not in (EvidenceStance.SUPPORTS, EvidenceStance.CONTEXT),
                    cl.id,
                ),
            )
        )
        prioritized_gaps = evi_ctx.gaps
        prioritized_assumptions = dec_ctx.assumptions
        prioritized_unknowns = dec_ctx.unknowns

    elif ptype == PerspectiveType.FINANCE:
        # Finance prioritizes quantitative/financial variables, fiscal constraints, and deterministic requirements
        prioritized_objectives = dec_ctx.objectives
        financial_var_types = {VariableType.CURRENCY, VariableType.PERCENTAGE, VariableType.NUMERIC}
        prioritized_variables = tuple(
            sorted(
                dec_ctx.variables,
                key=lambda v: (v.variable_type not in financial_var_types, v.id),
            )
        )
        prioritized_constraints = tuple(
            sorted(dec_ctx.constraints, key=lambda c: (not c.is_hard_constraint, c.id))
        )
        prioritized_tradeoffs = dec_ctx.tradeoffs
        prioritized_stakeholders = dec_ctx.stakeholders

        # Prioritize internal-data and deterministic-calculation requirements
        financial_kinds = {EvidenceKind.INTERNAL_DATA, EvidenceKind.DETERMINISTIC_CALCULATION}
        prioritized_requirements = tuple(
            sorted(
                evi_ctx.requirements,
                key=lambda r: (r.kind not in financial_kinds, r.id),
            )
        )
        prioritized_claim_links = evi_ctx.claim_links
        prioritized_gaps = evi_ctx.gaps
        prioritized_assumptions = dec_ctx.assumptions
        prioritized_unknowns = dec_ctx.unknowns

    elif ptype == PerspectiveType.CUSTOMER:
        # Customer prioritizes stakeholders, adoption/experience variables, and customer evidence
        prioritized_objectives = dec_ctx.objectives
        prioritized_variables = dec_ctx.variables
        prioritized_constraints = dec_ctx.constraints
        prioritized_tradeoffs = dec_ctx.tradeoffs
        prioritized_stakeholders = dec_ctx.stakeholders

        # Prioritize requirements and claim links targeting stakeholders
        prioritized_requirements = tuple(
            sorted(
                evi_ctx.requirements,
                key=lambda r: (r.target_entity_type != DecisionEntityType.STAKEHOLDER, r.id),
            )
        )
        prioritized_claim_links = tuple(
            sorted(
                evi_ctx.claim_links,
                key=lambda cl: (cl.target_entity_type != DecisionEntityType.STAKEHOLDER, cl.id),
            )
        )
        prioritized_gaps = tuple(
            sorted(
                evi_ctx.gaps,
                key=lambda g: (g.target_entity_type != DecisionEntityType.STAKEHOLDER, g.id),
            )
        )
        prioritized_assumptions = dec_ctx.assumptions
        prioritized_unknowns = dec_ctx.unknowns

    elif ptype == PerspectiveType.RISK:
        # Risk prominently surfaces challenging claim links, contested/unsupported/inconclusive requirements,
        # fragile assumptions, unknowns, and hard constraints — without dropping supporting findings.
        prioritized_objectives = dec_ctx.objectives
        prioritized_variables = tuple(
            sorted(dec_ctx.variables, key=lambda v: (v.is_controllable, v.id))
        )
        prioritized_constraints = tuple(
            sorted(dec_ctx.constraints, key=lambda c: (not c.is_hard_constraint, c.id))
        )
        prioritized_tradeoffs = dec_ctx.tradeoffs
        prioritized_stakeholders = dec_ctx.stakeholders

        # Prominently surface contested, unsupported, and inconclusive requirements first
        risk_statuses = {
            RequirementStatus.CONTESTED,
            RequirementStatus.UNSUPPORTED,
            RequirementStatus.INCONCLUSIVE,
        }
        prioritized_requirements = tuple(
            sorted(
                evi_ctx.requirements,
                key=lambda r: (r.status not in risk_statuses, r.id),
            )
        )

        # Prominently surface CHALLENGES claim links first, then INCONCLUSIVE, then others
        prioritized_claim_links = tuple(
            sorted(
                evi_ctx.claim_links,
                key=lambda cl: (
                    0 if cl.stance == EvidenceStance.CHALLENGES else
                    (1 if cl.stance == EvidenceStance.INCONCLUSIVE else 2),
                    cl.id,
                ),
            )
        )

        # Prominently surface conflicting evidence and unresolved unknown gaps first
        risk_gap_types = {
            EvidenceGapType.CONFLICTING_EVIDENCE,
            EvidenceGapType.UNRESOLVED_UNKNOWN,
            EvidenceGapType.UNSUPPORTED_CLAIM,
        }
        prioritized_gaps = tuple(
            sorted(
                evi_ctx.gaps,
                key=lambda g: (
                    g.gap_type not in risk_gap_types,
                    g.impact != CriticalityLevel.HIGH,
                    g.id,
                ),
            )
        )

        # Prominently surface untested and low-confidence assumptions
        fragile_confidence = {ConfidenceLevel.LOW, ConfidenceLevel.UNTESTED}
        prioritized_assumptions = tuple(
            sorted(
                dec_ctx.assumptions,
                key=lambda a: (a.confidence not in fragile_confidence, a.id),
            )
        )
        prioritized_unknowns = dec_ctx.unknowns

    else:
        # Fallback for completeness
        prioritized_objectives = dec_ctx.objectives
        prioritized_variables = dec_ctx.variables
        prioritized_constraints = dec_ctx.constraints
        prioritized_tradeoffs = dec_ctx.tradeoffs
        prioritized_stakeholders = dec_ctx.stakeholders
        prioritized_requirements = evi_ctx.requirements
        prioritized_claim_links = evi_ctx.claim_links
        prioritized_gaps = evi_ctx.gaps
        prioritized_assumptions = dec_ctx.assumptions
        prioritized_unknowns = dec_ctx.unknowns

    return PerspectiveContext(
        perspective=perspective,
        decision_context=dec_ctx,
        evidence_context=evi_ctx,
        prioritized_objectives=prioritized_objectives,
        prioritized_variables=prioritized_variables,
        prioritized_constraints=prioritized_constraints,
        prioritized_tradeoffs=prioritized_tradeoffs,
        prioritized_stakeholders=prioritized_stakeholders,
        prioritized_requirements=prioritized_requirements,
        prioritized_claim_links=prioritized_claim_links,
        prioritized_gaps=prioritized_gaps,
        prioritized_assumptions=prioritized_assumptions,
        prioritized_unknowns=prioritized_unknowns,
    )


def build_all_perspective_contexts(
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
) -> Tuple[PerspectiveContext, ...]:
    """Constructs PerspectiveContext objects for all four canonical perspectives in authoritative order.

    Canonical order: Growth, Finance, Customer, Risk.
    """
    reasoning_ctx = build_reasoning_context(decision_model, evidence_package)
    return tuple(
        build_perspective_context(persp_def, reasoning_ctx)
        for persp_def in CANONICAL_PERSPECTIVES
    )
