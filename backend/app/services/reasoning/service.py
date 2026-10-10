"""AURA Reasoning Service & Authoritative Board Deliberation.

Coordinates the full AI Boardroom deliberation pipeline:
1. Validates upstream DecisionModel and EvidencePackage bindings and target references.
2. Bounded execution of the four canonical perspectives (Growth, Finance, Customer, Risk) via PerspectiveOrchestrator.
3. Deterministic cross-perspective disagreement detection via detect_disagreements.
4. Grounded board synthesis via BoardSynthesizer.
5. Deterministic ReasoningBoard assembly with content-derived SHA-256 ID.
6. Defense-in-depth referential validation via validate_reasoning_references.
7. Pure orchestration: zero downstream deliberation bias, voting, or consensus scoring.
"""

from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Callable, List, Optional, Sequence, Tuple

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import (
    BoardSynthesis,
    PerspectiveType,
    ReasoningBoard,
    ReasoningDisagreement,
    ReasoningPerspective,
    validate_reasoning_references,
)
from app.services.evidence.requirements import validate_target_reference
from app.services.llm.client import LLMClient, LLMConfig, LLMTimeoutError
from app.services.reasoning.context_builder import build_reasoning_context
from app.services.reasoning.disagreements import detect_disagreements
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.orchestrator import (
    MAX_PERSPECTIVE_WORKERS,
    PerspectiveOrchestrator,
)
from app.services.reasoning.synthesizer import BoardSynthesizer
from app.services.reasoning.validator import (
    ReasoningServiceError,
    ReasoningValidationError,
)


# ------------------------------------------------------------------------------
# 1. Deterministic Board Identity
# ------------------------------------------------------------------------------

def generate_deterministic_board_id(
    decision_model_id: str,
    evidence_package_id: str,
    perspectives: Sequence[ReasoningPerspective],
    disagreements: Sequence[ReasoningDisagreement],
    synthesis: BoardSynthesis,
) -> str:
    """Computes a deterministic, content-derived board ID using SHA-256.

    Canonicalizes all authoritative components to ensure exact stability
    regardless of timestamps, worker completion order, memory addresses,
    or execution platform.

    Returns:
        str: Stable ID with 'rbd_' prefix and 32 hex chars (length 36 <= 64).
    """
    canonical_type_order = {
        PerspectiveType.GROWTH: 0,
        PerspectiveType.FINANCE: 1,
        PerspectiveType.CUSTOMER: 2,
        PerspectiveType.RISK: 3,
    }
    sorted_persps = sorted(
        perspectives,
        key=lambda p: (canonical_type_order.get(p.perspective_type, 99), p.id),
    )

    persp_payload = []
    for p in sorted_persps:
        arg_payload = []
        for a in sorted(p.arguments, key=lambda x: x.id):
            arg_payload.append({
                "id": a.id,
                "claim": a.claim,
                "direction": a.direction.value,
                "basis": a.basis.value,
                "reasoning": a.reasoning,
                "evidence_item_ids": sorted(a.evidence_item_ids),
                "requirement_ids": sorted(a.requirement_ids),
                "assumption_ids": sorted(a.assumption_ids),
                "unknown_ids": sorted(a.unknown_ids),
                "evidence_gap_ids": sorted(a.evidence_gap_ids),
                "related_entity_ids": sorted(a.related_entity_ids),
            })
        persp_payload.append({
            "id": p.id,
            "type": p.perspective_type.value,
            "summary": p.summary,
            "arguments": arg_payload,
            "critical_assumption_ids": sorted(p.critical_assumption_ids),
            "evidence_gap_ids": sorted(p.evidence_gap_ids),
            "opportunities": sorted(p.opportunities),
            "concerns": sorted(p.concerns),
            "unresolved_questions": sorted(p.unresolved_questions),
            "limitations": sorted(p.limitations),
        })

    dis_payload = []
    for d in sorted(disagreements, key=lambda x: x.id):
        dis_payload.append({
            "id": d.id,
            "topic": d.topic,
            "nature": d.nature.value,
            "perspectives": sorted(d.perspective_ids),
            "arguments": sorted(d.argument_ids),
            "positions": sorted(d.positions.items()),
            "evidence_item_ids": sorted(d.evidence_item_ids),
            "assumption_ids": sorted(d.assumption_ids),
            "evidence_gap_ids": sorted(d.evidence_gap_ids),
        })

    synth_payload = {
        "summary": synthesis.summary,
        "areas_of_agreement": list(synthesis.areas_of_agreement),
        "disagreement_ids": sorted(synthesis.disagreement_ids),
        "critical_assumption_ids": sorted(synthesis.critical_assumption_ids),
        "critical_evidence_gap_ids": sorted(synthesis.critical_evidence_gap_ids),
        "evidence_sensitive_points": list(synthesis.evidence_sensitive_points),
        "unresolved_questions": list(synthesis.unresolved_questions),
    }

    full_payload = {
        "decision_model_id": decision_model_id,
        "evidence_package_id": evidence_package_id,
        "perspectives": persp_payload,
        "disagreements": dis_payload,
        "synthesis": synth_payload,
    }

    serialized = json.dumps(full_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"rbd_{digest[:32]}"


# ------------------------------------------------------------------------------
# 2. Upstream Artifact Validation
# ------------------------------------------------------------------------------

def validate_upstream_artifacts(
    decision_model: DecisionModel,
    evidence_package: EvidencePackage,
) -> None:
    """Validates upstream artifact bindings and target references before reasoning."""
    if evidence_package.decision_model_id != decision_model.id:
        raise ReasoningValidationError(
            f"EvidencePackage decision_model_id '{evidence_package.decision_model_id}' "
            f"does not match DecisionModel id '{decision_model.id}'.",
            details={
                "location": "service.validate_upstream_artifacts",
                "field": "evidence_package.decision_model_id",
                "rule": "decision_model_id_mismatch",
                "expected": decision_model.id,
                "got": evidence_package.decision_model_id,
            },
        )

    try:
        for r in evidence_package.requirements:
            validate_target_reference(
                decision_model=decision_model,
                target_id=r.target_entity_id,
                target_type=r.target_entity_type,
            )
        for link in evidence_package.claim_links:
            validate_target_reference(
                decision_model=decision_model,
                target_id=link.target_entity_id,
                target_type=link.target_entity_type,
            )
        for gap in evidence_package.gaps:
            validate_target_reference(
                decision_model=decision_model,
                target_id=gap.target_entity_id,
                target_type=gap.target_entity_type,
            )
    except Exception as err:
        raise ReasoningValidationError(
            f"Upstream cross-model target validation failed: {err}",
            details={
                "location": "service.validate_upstream_artifacts",
                "field": "upstream_artifacts",
                "rule": "target_reference_validation_failed",
            },
        ) from err


# ------------------------------------------------------------------------------
# 3. Reasoning Service
# ------------------------------------------------------------------------------

class ReasoningService:
    """Orchestrates AI Boardroom multi-perspective deliberation and synthesizes ReasoningBoard."""

    def __init__(
        self,
        orchestrator: PerspectiveOrchestrator,
        synthesizer: BoardSynthesizer,
        clock: Optional[Callable[[], datetime]] = None,
        perspective_config: Optional[LLMConfig] = None,
    ) -> None:
        """Initializes ReasoningService with injected orchestrator, synthesizer, clock, and optional perspective_config."""
        self.orchestrator = orchestrator
        self.synthesizer = synthesizer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.perspective_config = perspective_config

    @classmethod
    def create_default(
        cls,
        llm_client: LLMClient,
        max_workers: int = MAX_PERSPECTIVE_WORKERS,
        clock: Optional[Callable[[], datetime]] = None,
        perspective_config: Optional[LLMConfig] = None,
        boardroom_operation_timeout_seconds: Optional[float] = None,
    ) -> "ReasoningService":
        """Factory creating ReasoningService with shared injected LLMClient across all sub-services."""
        cfg = perspective_config
        if cfg is None and boardroom_operation_timeout_seconds is not None:
            cfg = LLMConfig(
                operation_timeout_seconds=boardroom_operation_timeout_seconds,
                timeout_seconds=min(45.0, boardroom_operation_timeout_seconds),
            )
        reasoner = PerspectiveReasoner(llm_client=llm_client, config=cfg)
        orchestrator = PerspectiveOrchestrator(reasoner=reasoner, max_workers=max_workers)
        synthesizer = BoardSynthesizer(llm_client=llm_client)
        return cls(orchestrator=orchestrator, synthesizer=synthesizer, clock=clock, perspective_config=cfg)

    def build_reasoning_board(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        deadline_monotonic: Optional[float] = None,
        perspective_config: Optional[LLMConfig] = None,
        boardroom_operation_timeout_seconds: Optional[float] = None,
    ) -> ReasoningBoard:
        """Executes full boardroom deliberation and produces an authoritative ReasoningBoard.

        Pipeline Stages:
        1. Pre-flight monotonic deadline pre-check & upstream artifact validation
        2. Bounded execution of four canonical perspectives (growth, finance, customer, risk)
        3. Deterministic cross-perspective disagreement detection
        4. Grounded cross-perspective board synthesis
        5. Deterministic ReasoningBoard assembly
        6. Authoritative cross-artifact referential validation

        Args:
            decision_model: Authoritative decision problem context.
            evidence_package: Authoritative empirical evidence portfolio.
            deadline_monotonic: Single authoritative parent monotonic deadline.

        Returns:
            ReasoningBoard: Authoritative, fully grounded boardroom artifact.

        Raises:
            ReasoningServiceError: If any stage fails or times out.
            ReasoningValidationError: If upstream input or downstream output validation fails.
        """
        # Stage 1: Deadline pre-check & upstream validation
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Reasoning evaluation deadline expired prior to execution.")
            raise ReasoningServiceError(
                "Reasoning service timed out: deadline expired before perspective stage.",
                stage="perspectives",
            ) from timeout_err

        try:
            validate_upstream_artifacts(decision_model, evidence_package)
        except Exception as exc:
            raise ReasoningServiceError(
                "Reasoning upstream artifact validation failed.",
                stage="validation",
            ) from exc

        # Stage 2: Bounded perspective evaluation
        effective_persp_config = perspective_config or self.perspective_config
        if effective_persp_config is None and boardroom_operation_timeout_seconds is not None:
            effective_persp_config = LLMConfig(
                operation_timeout_seconds=boardroom_operation_timeout_seconds,
                timeout_seconds=min(45.0, boardroom_operation_timeout_seconds),
            )

        try:
            try:
                perspectives = self.orchestrator.evaluate_all(
                    decision_model=decision_model,
                    evidence_package=evidence_package,
                    deadline_monotonic=deadline_monotonic,
                    config=effective_persp_config,
                )
            except TypeError as te:
                if "unexpected keyword argument 'config'" in str(te):
                    perspectives = self.orchestrator.evaluate_all(
                        decision_model=decision_model,
                        evidence_package=evidence_package,
                        deadline_monotonic=deadline_monotonic,
                    )
                else:
                    raise
        except Exception as exc:
            raise ReasoningServiceError(
                "Reasoning perspective stage failed.",
                stage="perspectives",
            ) from exc

        # Stage 3: Monotonic deadline check before disagreement detection
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError(
                "Reasoning evaluation deadline expired prior to disagreement detection."
            )
            raise ReasoningServiceError(
                "Reasoning service timed out: deadline expired before disagreement stage.",
                stage="disagreements",
            ) from timeout_err

        # Deterministic disagreement detection (pure Python)
        try:
            disagreements = detect_disagreements(perspectives)
        except Exception as exc:
            raise ReasoningServiceError(
                "Reasoning disagreement stage failed.",
                stage="disagreements",
            ) from exc

        # Stage 4: Monotonic deadline check before synthesis
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError(
                "Reasoning evaluation deadline expired prior to synthesis."
            )
            raise ReasoningServiceError(
                "Reasoning service timed out: deadline expired before synthesis stage.",
                stage="synthesis",
            ) from timeout_err

        # Build reasoning context for synthesis
        # Note: PerspectiveOrchestrator builds its context internally; building here is pure Python and non-networked.
        reasoning_context = build_reasoning_context(decision_model, evidence_package)

        try:
            synthesis = self.synthesizer.synthesize(
                decision_model=decision_model,
                evidence_package=evidence_package,
                reasoning_context=reasoning_context,
                perspectives=perspectives,
                disagreements=disagreements,
                deadline_monotonic=deadline_monotonic,
            )
        except Exception as exc:
            raise ReasoningServiceError(
                "Reasoning synthesis stage failed.",
                stage="synthesis",
            ) from exc

        # Stage 5: Deterministic ReasoningBoard assembly
        board_id = generate_deterministic_board_id(
            decision_model_id=decision_model.id,
            evidence_package_id=evidence_package.id,
            perspectives=perspectives,
            disagreements=disagreements,
            synthesis=synthesis,
        )

        created_at = self.clock()
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        # Sort disagreements deterministically by ID for board storage
        sorted_disagreements = sorted(disagreements, key=lambda d: d.id)

        # Stage 5 & 6: Deterministic ReasoningBoard assembly & validation
        try:
            board = ReasoningBoard(
                id=board_id,
                decision_model_id=decision_model.id,
                evidence_package_id=evidence_package.id,
                perspectives=list(perspectives),
                disagreements=sorted_disagreements,
                synthesis=synthesis,
                created_at=created_at,
            )
            validate_reasoning_references(board, decision_model, evidence_package)
        except Exception as exc:
            raise ReasoningServiceError(
                "Reasoning board validation failed.",
                stage="board_validation",
            ) from exc

        return board
