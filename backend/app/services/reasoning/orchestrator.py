"""AURA Bounded Four-Perspective Orchestrator.

Coordinates bounded, deterministic execution of the four canonical boardroom perspectives:
- Growth, Finance, Customer, Risk.
- Constructs shared ReasoningContext once; fans out to four PerspectiveContexts.
- Propagates a shared monotonic deadline across all workers without resetting budgets.
- Supports bounded concurrency via ThreadPoolExecutor with sequential fallback (max_workers=1).
- Enforces strict canonical result ordering regardless of completion order.
- Guarantees fail-closed semantics: all four perspectives must succeed or orchestration fails.
- Validates output uniqueness and canonical integrity before returning.
- Zero downstream logic: does NOT perform disagreement detection, synthesis, or board creation.
"""

import concurrent.futures
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.schemas.reasoning import (
    PerspectiveType,
    ReasoningPerspective,
)
from app.services.llm.client import LLMTimeoutError
from app.services.reasoning.context_builder import (
    PerspectiveContext,
    ReasoningContext,
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.evaluator import PerspectiveReasoner
from app.services.reasoning.perspectives import (
    CANONICAL_PERSPECTIVES,
    PerspectiveDefinition,
)
from app.services.reasoning.validator import (
    ReasoningOrchestrationError,
    ReasoningValidationError,
)

# ------------------------------------------------------------------------------
# 1. Concurrency Constants
# ------------------------------------------------------------------------------

# Consistent with EvidenceMapper bounded concurrency pattern (MAX_EVIDENCE_MAPPING_WORKERS = 3)
MAX_PERSPECTIVE_WORKERS: int = 3


# ------------------------------------------------------------------------------
# 2. Authoritative Output Validation
# ------------------------------------------------------------------------------

def validate_orchestrated_perspectives(
    perspectives: Sequence[ReasoningPerspective],
) -> Tuple[ReasoningPerspective, ...]:
    """Validates that orchestrated output contains exactly four canonical perspectives.

    Checks:
    - Exactly 4 perspectives.
    - Expected types in exact canonical order: growth, finance, customer, risk.
    - Perspective IDs are non-empty and unique.
    - Argument IDs are unique across all perspectives.

    Raises:
        ReasoningValidationError: If any output invariant is violated.
    """
    if len(perspectives) != 4:
        raise ReasoningValidationError(
            f"Expected exactly 4 perspectives, received {len(perspectives)}."
        )

    canonical_types = [
        PerspectiveType.GROWTH,
        PerspectiveType.FINANCE,
        PerspectiveType.CUSTOMER,
        PerspectiveType.RISK,
    ]

    seen_types: Set[PerspectiveType] = set()
    seen_perspective_ids: Set[str] = set()
    seen_argument_ids: Set[str] = set()

    for idx, (expected_type, p) in enumerate(zip(canonical_types, perspectives)):
        if not isinstance(p, ReasoningPerspective):
            raise ReasoningValidationError(
                f"Element at index {idx} is not a ReasoningPerspective: {type(p).__name__}."
            )

        if p.perspective_type != expected_type:
            raise ReasoningValidationError(
                f"Perspective at index {idx} has type '{p.perspective_type.value}', "
                f"expected '{expected_type.value}'."
            )

        if p.perspective_type in seen_types:
            raise ReasoningValidationError(
                f"Duplicate perspective type encountered: '{p.perspective_type.value}'."
            )
        seen_types.add(p.perspective_type)

        if not p.id:
            raise ReasoningValidationError(
                f"Perspective of type '{p.perspective_type.value}' has empty ID."
            )

        if p.id in seen_perspective_ids:
            raise ReasoningValidationError(
                f"Duplicate perspective ID encountered: '{p.id}'."
            )
        seen_perspective_ids.add(p.id)

        for arg in p.arguments:
            if not arg.id:
                raise ReasoningValidationError(
                    f"Perspective '{p.id}' contains argument with empty ID."
                )
            if arg.id in seen_argument_ids:
                raise ReasoningValidationError(
                    f"Duplicate argument ID encountered across board: '{arg.id}'."
                )
            seen_argument_ids.add(arg.id)

    return tuple(perspectives)


# ------------------------------------------------------------------------------
# 3. Perspective Orchestrator
# ------------------------------------------------------------------------------

class PerspectiveOrchestrator:
    """Coordinates bounded, deterministic execution of the four canonical boardroom perspectives."""

    def __init__(
        self,
        reasoner: PerspectiveReasoner,
        max_workers: int = MAX_PERSPECTIVE_WORKERS,
    ) -> None:
        """Initializes orchestrator with an injected reasoner and worker ceiling.

        Args:
            reasoner: Single-perspective evaluation service.
            max_workers: Maximum worker count for thread pool (must be >= 1).
        """
        if max_workers < 1:
            raise ValueError(f"max_workers must be at least 1, got {max_workers}.")
        self.reasoner = reasoner
        self.max_workers = max_workers

    def evaluate_all(
        self,
        decision_model: DecisionModel,
        evidence_package: EvidencePackage,
        deadline_monotonic: Optional[float] = None,
    ) -> Tuple[ReasoningPerspective, ...]:
        """Evaluates all four canonical perspectives concurrently or sequentially under a shared deadline.

        Args:
            decision_model: Authoritative decision problem context.
            evidence_package: Authoritative evidence package context.
            deadline_monotonic: Optional monotonic deadline for bounded execution.

        Returns:
            Tuple[ReasoningPerspective, ...]: Exactly four authoritative perspectives in canonical order:
                (growth, finance, customer, risk).

        Raises:
            ReasoningOrchestrationError: If execution exceeds deadline or any worker fails.
            ReasoningValidationError: If post-execution validation detects invalid/duplicate outputs.
        """
        # 1. Deadline pre-check before starting any work
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Evaluation deadline expired prior to orchestration.")
            raise ReasoningOrchestrationError(
                "Perspective evaluation deadline already expired before orchestration began."
            ) from timeout_err

        # 2. Build shared ReasoningContext once
        reasoning_context: ReasoningContext = build_reasoning_context(
            decision_model, evidence_package
        )

        # 3. Build PerspectiveContexts for all four canonical perspectives
        perspective_contexts: List[PerspectiveContext] = [
            build_perspective_context(persp_def, reasoning_context)
            for persp_def in CANONICAL_PERSPECTIVES
        ]

        # 4. Determine effective worker count
        effective_workers = min(self.max_workers, len(CANONICAL_PERSPECTIVES))

        raw_results: Tuple[ReasoningPerspective, ...]

        if effective_workers <= 1:
            # Sequential execution path (max_workers=1 fallback)
            sequential_results: List[ReasoningPerspective] = []
            for ctx in perspective_contexts:
                ptype = ctx.perspective.perspective_type
                # Check deadline before invoking next perspective
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                    timeout_err = LLMTimeoutError(
                        f"Evaluation deadline expired before executing perspective '{ptype.value}'."
                    )
                    raise ReasoningOrchestrationError(
                        f"Perspective evaluation timed out: {ptype.value}"
                    ) from timeout_err

                try:
                    res = self.reasoner.evaluate(ctx, deadline_monotonic=deadline_monotonic)
                    sequential_results.append(res)
                except Exception as exc:
                    if (
                        isinstance(exc, LLMTimeoutError)
                        or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                    ):
                        raise ReasoningOrchestrationError(
                            f"Perspective evaluation timed out: {ptype.value}"
                        ) from exc
                    raise ReasoningOrchestrationError(
                        f"Perspective evaluation failed: {ptype.value}"
                    ) from exc

            raw_results = tuple(sequential_results)

        else:
            # Bounded concurrent execution path
            results_by_type: Dict[PerspectiveType, ReasoningPerspective] = {}
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers)
            futures: Dict[concurrent.futures.Future, PerspectiveType] = {}

            try:
                for ctx in perspective_contexts:
                    ptype = ctx.perspective.perspective_type
                    fut = executor.submit(self.reasoner.evaluate, ctx, deadline_monotonic)
                    futures[fut] = ptype

                remaining = (
                    max(0.0, deadline_monotonic - time.monotonic())
                    if deadline_monotonic is not None
                    else None
                )
                done, not_done = concurrent.futures.wait(
                    futures.keys(),
                    timeout=remaining,
                    return_when=concurrent.futures.ALL_COMPLETED,
                )
            finally:
                # Cancel queued futures that haven't started; do not block indefinitely on running workers
                executor.shutdown(wait=False, cancel_futures=True)

            # Deterministic inspection in canonical perspective order
            # If not all completed or deadline expired while waiting
            if not_done or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic):
                # Check if any completed worker already failed with an explicit error
                for ctx in perspective_contexts:
                    ptype = ctx.perspective.perspective_type
                    fut = next(f for f, t in futures.items() if t == ptype)
                    if fut in done and fut.exception() is not None:
                        exc = fut.exception()
                        if (
                            isinstance(exc, LLMTimeoutError)
                            or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                        ):
                            raise ReasoningOrchestrationError(
                                f"Perspective evaluation timed out: {ptype.value}"
                            ) from exc
                        raise ReasoningOrchestrationError(
                            f"Perspective evaluation failed: {ptype.value}"
                        ) from exc

                # If none completed with an explicit exception, report timeout
                timed_out_types = [t.value for f, t in futures.items() if f in not_done]
                timed_out_desc = timed_out_types[0] if timed_out_types else "deadline exceeded"
                timeout_err = LLMTimeoutError(
                    f"Operation timed out waiting for perspective '{timed_out_desc}'."
                )
                raise ReasoningOrchestrationError(
                    f"Perspective evaluation timed out: {timed_out_desc}"
                ) from timeout_err

            # All completed: inspect exceptions strictly by canonical perspective order
            for ctx in perspective_contexts:
                ptype = ctx.perspective.perspective_type
                fut = next(f for f, t in futures.items() if t == ptype)
                exc = fut.exception()
                if exc is not None:
                    if (
                        isinstance(exc, LLMTimeoutError)
                        or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                    ):
                        raise ReasoningOrchestrationError(
                            f"Perspective evaluation timed out: {ptype.value}"
                        ) from exc
                    raise ReasoningOrchestrationError(
                        f"Perspective evaluation failed: {ptype.value}"
                    ) from exc

                results_by_type[ptype] = fut.result()

            raw_results = tuple(
                results_by_type[p_def.perspective_type] for p_def in CANONICAL_PERSPECTIVES
            )

        # 5. Deterministic post-execution validation
        return validate_orchestrated_perspectives(raw_results)
