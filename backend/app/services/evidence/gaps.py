"""AURA Evidence Gap Detector.

Identifies unresolved empirical gaps, contradictions, and deficiencies across
the decision structure and deterministically derives RequirementStatus values.

Guarantees:
- Pure deterministic Python (Zero LLM, Zero SearchProvider, Zero network).
- Evaluates evidence per requirement to preserve strict requirement-level provenance.
- Distinguishes UNSUPPORTED_CLAIM, UNRESOLVED_UNKNOWN, CONFLICTING_EVIDENCE, and INSUFFICIENT_EVIDENCE.
- Derives RequirementStatus (FULFILLED, CONTESTED, INCONCLUSIVE, UNSUPPORTED, PENDING).
- Does not mutate input requirement objects in place.
- Derives gap impact strictly from requirement priority (CriticalityLevel).
- Validates input referential integrity against DecisionModel.
"""

from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decision_model import CriticalityLevel, DecisionModel
from app.schemas.evidence import (
    ClaimEvidenceLink,
    DecisionEntityType,
    EvidenceGap,
    EvidenceGapType,
    EvidenceItem,
    EvidenceKind,
    EvidenceRequirement,
    EvidenceStance,
    RequirementStatus,
)
from app.services.evidence.mapper import EvidenceMappingResult
from app.services.evidence.requirements import validate_target_reference


# ------------------------------------------------------------------------------
# 1. Result Model
# ------------------------------------------------------------------------------

class EvidenceGapDetectionResult(BaseModel):
    """Result of empirical evidence gap detection and status resolution."""
    model_config = ConfigDict(str_strip_whitespace=True)

    requirements: List[EvidenceRequirement] = Field(
        default_factory=list,
        description="Requirements with deterministically updated RequirementStatus.",
    )
    gaps: List[EvidenceGap] = Field(
        default_factory=list,
        description="Identified empirical evidence gaps and contradictions.",
    )


# ------------------------------------------------------------------------------
# 2. EvidenceGapDetector Implementation
# ------------------------------------------------------------------------------

class EvidenceGapDetector:
    """Analyzes the evidence graph to identify empirical deficiencies and derive requirement status."""

    def __init__(self) -> None:
        """Initializes EvidenceGapDetector. Fully deterministic with zero external dependencies."""
        pass

    def _validate_inputs(
        self,
        decision_model: DecisionModel,
        requirements: List[EvidenceRequirement],
        mapping_result: EvidenceMappingResult,
    ) -> None:
        """Validates referential integrity of inputs before gap analysis.

        Raises:
            ValueError: If duplicate IDs, missing references, or invalid target entities are detected.
        """
        # 1. Unique requirement IDs
        seen_req_ids: Set[str] = set()
        for r in requirements:
            if r.id in seen_req_ids:
                raise ValueError(f"Duplicate requirement ID '{r.id}' detected in input requirements.")
            seen_req_ids.add(r.id)

        # 2. Unique EvidenceItem IDs
        seen_item_ids: Set[str] = set()
        for item in mapping_result.items:
            if item.id in seen_item_ids:
                raise ValueError(f"Duplicate EvidenceItem ID '{item.id}' detected in mapping result.")
            seen_item_ids.add(item.id)

        # 3. Unique ClaimEvidenceLink IDs
        seen_link_ids: Set[str] = set()
        for link in mapping_result.claim_links:
            if link.id in seen_link_ids:
                raise ValueError(f"Duplicate ClaimEvidenceLink ID '{link.id}' detected in mapping result.")
            seen_link_ids.add(link.id)

            # Every ClaimEvidenceLink.evidence_item_id must reference an existing EvidenceItem
            if link.evidence_item_id not in seen_item_ids:
                raise ValueError(
                    f"ClaimEvidenceLink '{link.id}' references non-existent evidence_item_id '{link.evidence_item_id}'."
                )

            # Every ClaimEvidenceLink.requirement_id (if present) must reference an existing EvidenceRequirement
            if link.requirement_id is not None and link.requirement_id not in seen_req_ids:
                raise ValueError(
                    f"ClaimEvidenceLink '{link.id}' references non-existent requirement_id '{link.requirement_id}'."
                )

        # 4. Target reference validation against DecisionModel
        for r in requirements:
            validate_target_reference(
                decision_model=decision_model,
                target_id=r.target_entity_id,
                target_type=r.target_entity_type,
            )
        for link in mapping_result.claim_links:
            validate_target_reference(
                decision_model=decision_model,
                target_id=link.target_entity_id,
                target_type=link.target_entity_type,
            )

    def detect_gaps(
        self,
        decision_model: DecisionModel,
        requirements: List[EvidenceRequirement],
        mapping_result: EvidenceMappingResult,
    ) -> EvidenceGapDetectionResult:
        """Analyzes evidence coverage, resolves requirement statuses, and detects gaps.

        Args:
            decision_model: Canonical DecisionModel containing target entities.
            requirements: Candidate EvidenceRequirement objects to evaluate.
            mapping_result: Evidence mapping result containing items and claim links.

        Returns:
            EvidenceGapDetectionResult with updated requirements and generated gaps.

        Raises:
            ValueError: On input validation failure.
        """
        # Handle empty case
        if not requirements and not mapping_result.items and not mapping_result.claim_links:
            return EvidenceGapDetectionResult(requirements=[], gaps=[])

        # Validate referential integrity
        self._validate_inputs(decision_model, requirements, mapping_result)

        updated_requirements: List[EvidenceRequirement] = []
        gaps: List[EvidenceGap] = []
        gap_counter = 1

        # Index links by requirement_id (primary) and target entity (fallback if requirement_id is None)
        links_by_req: Dict[str, List[ClaimEvidenceLink]] = {r.id: [] for r in requirements}
        reqs_by_target: Dict[Tuple[str, DecisionEntityType], List[str]] = {}
        for r in requirements:
            key = (r.target_entity_id, r.target_entity_type)
            reqs_by_target.setdefault(key, []).append(r.id)

        for link in mapping_result.claim_links:
            if link.requirement_id and link.requirement_id in links_by_req:
                links_by_req[link.requirement_id].append(link)
            else:
                # Fallback only if exactly one requirement targets this entity
                target_key = (link.target_entity_id, link.target_entity_type)
                candidate_req_ids = reqs_by_target.get(target_key, [])
                if len(candidate_req_ids) == 1:
                    links_by_req[candidate_req_ids[0]].append(link)

        # Process each requirement independently to preserve provenance
        for req in requirements:
            req_links = links_by_req[req.id]

            if req.kind == EvidenceKind.EXTERNAL_RESEARCH:
                supports = [l for l in req_links if l.stance == EvidenceStance.SUPPORTS]
                challenges = [l for l in req_links if l.stance == EvidenceStance.CHALLENGES]
                context = [l for l in req_links if l.stance == EvidenceStance.CONTEXT]
                inconclusive = [l for l in req_links if l.stance == EvidenceStance.INCONCLUSIVE]

                # Case A: Zero mapped evidence -> UNSUPPORTED & UNSUPPORTED_CLAIM
                if not req_links:
                    new_status = RequirementStatus.UNSUPPORTED
                    gap_id = f"gap_{gap_counter}"
                    gap_counter += 1

                    gaps.append(
                        EvidenceGap(
                            id=gap_id,
                            gap_type=EvidenceGapType.UNSUPPORTED_CLAIM,
                            target_entity_id=req.target_entity_id,
                            target_entity_type=req.target_entity_type,
                            requirement_id=req.id,
                            description=f"Empirical claim for {req.target_entity_type.value} '{req.target_entity_id}' has no supporting evidence: {req.description}",
                            impact=req.priority,
                            conflicting_evidence_ids=[],
                            resolution_guidance=f"Conduct targeted external research to validate {req.target_entity_type.value} '{req.target_entity_id}'.",
                        )
                    )

                # Case B: Conflicting evidence (SUPPORTS + CHALLENGES) -> CONTESTED & CONFLICTING_EVIDENCE
                elif len(supports) > 0 and len(challenges) > 0:
                    new_status = RequirementStatus.CONTESTED
                    # Deduplicate evidence IDs while preserving order
                    seen_eids: Set[str] = set()
                    conflict_ids: List[str] = []
                    for l in supports + challenges:
                        if l.evidence_item_id not in seen_eids:
                            seen_eids.add(l.evidence_item_id)
                            conflict_ids.append(l.evidence_item_id)

                    if len(conflict_ids) >= 2:
                        gap_id = f"gap_{gap_counter}"
                        gap_counter += 1
                        gaps.append(
                            EvidenceGap(
                                id=gap_id,
                                gap_type=EvidenceGapType.CONFLICTING_EVIDENCE,
                                target_entity_id=req.target_entity_id,
                                target_entity_type=req.target_entity_type,
                                requirement_id=req.id,
                                description=f"Contradictory evidence found for {req.target_entity_type.value} '{req.target_entity_id}': both supporting and challenging findings exist.",
                                impact=req.priority,
                                conflicting_evidence_ids=conflict_ids,
                                resolution_guidance=f"Reconcile contradictory findings across {len(conflict_ids)} sources or obtain higher-fidelity cohort data.",
                            )
                        )

                # Case C: Fulfilled (SUPPORTS only OR CHALLENGES only) -> FULFILLED (no gap)
                elif (len(supports) > 0 and len(challenges) == 0) or (len(challenges) > 0 and len(supports) == 0):
                    new_status = RequirementStatus.FULFILLED

                # Case D: Insufficient evidence (only CONTEXT and/or INCONCLUSIVE) -> INCONCLUSIVE & INSUFFICIENT_EVIDENCE
                else:
                    new_status = RequirementStatus.INCONCLUSIVE
                    gap_id = f"gap_{gap_counter}"
                    gap_counter += 1

                    gaps.append(
                        EvidenceGap(
                            id=gap_id,
                            gap_type=EvidenceGapType.INSUFFICIENT_EVIDENCE,
                            target_entity_id=req.target_entity_id,
                            target_entity_type=req.target_entity_type,
                            requirement_id=req.id,
                            description=f"Retrieved evidence for {req.target_entity_type.value} '{req.target_entity_id}' is context-only or inconclusive, leaving the claim unresolved.",
                            impact=req.priority,
                            conflicting_evidence_ids=[],
                            resolution_guidance=f"Target specific empirical benchmarks establishing directional support or refutation rather than general context.",
                        )
                    )

            elif req.kind == EvidenceKind.INTERNAL_DATA:
                # Internal data unresolved in current pipeline -> PENDING & UNRESOLVED_UNKNOWN
                new_status = RequirementStatus.PENDING
                gap_id = f"gap_{gap_counter}"
                gap_counter += 1

                gaps.append(
                    EvidenceGap(
                        id=gap_id,
                        gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
                        target_entity_id=req.target_entity_id,
                        target_entity_type=req.target_entity_type,
                        requirement_id=req.id,
                        description=f"Internal organizational data required for {req.target_entity_type.value} '{req.target_entity_id}' has not been provided: {req.description}",
                        impact=req.priority,
                        conflicting_evidence_ids=[],
                        resolution_guidance=f"Extract internal proprietary records, analytics, or subscription telemetry for '{req.description}'.",
                    )
                )

            elif req.kind == EvidenceKind.USER_CLARIFICATION:
                # User clarification unresolved in current pipeline -> PENDING & UNRESOLVED_UNKNOWN
                new_status = RequirementStatus.PENDING
                gap_id = f"gap_{gap_counter}"
                gap_counter += 1

                gaps.append(
                    EvidenceGap(
                        id=gap_id,
                        gap_type=EvidenceGapType.UNRESOLVED_UNKNOWN,
                        target_entity_id=req.target_entity_id,
                        target_entity_type=req.target_entity_type,
                        requirement_id=req.id,
                        description=f"User clarification required for {req.target_entity_type.value} '{req.target_entity_id}' is unresolved: {req.description}",
                        impact=req.priority,
                        conflicting_evidence_ids=[],
                        resolution_guidance=f"Clarify decision-maker preference, boundary, or strategic tolerance for '{req.description}'.",
                    )
                )

            elif req.kind == EvidenceKind.DETERMINISTIC_CALCULATION:
                # Calculations are not executed by EvidenceGapDetector (deferred to math engine)
                # Left PENDING without fabricating empirical gaps.
                new_status = RequirementStatus.PENDING

            else:
                new_status = req.status

            # Produce an updated copy of the requirement without mutating caller object
            updated_requirements.append(req.model_copy(update={"status": new_status}))

        return EvidenceGapDetectionResult(
            requirements=updated_requirements,
            gaps=gaps,
        )
