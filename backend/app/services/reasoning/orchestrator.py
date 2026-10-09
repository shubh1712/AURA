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
import threading
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

# Bounded ceiling aligned with the four canonical perspectives (Growth, Finance, Customer, Risk)
MAX_PERSPECTIVE_WORKERS: int = 4


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
        self._thread_local = threading.local()
        self._diagnostics_lock = threading.Lock()
        self._latest_perspective_diagnostics: Dict[PerspectiveType, Dict[str, Any]] = {}

    @property
    def last_perspective_diagnostics(self) -> Dict[PerspectiveType, Dict[str, Any]]:
        """Thread-safe access to call-scoped diagnostics for the current calling thread."""
        thread_diag = getattr(self._thread_local, "diagnostics", None)
        if thread_diag is not None:
            return thread_diag
        with self._diagnostics_lock:
            return dict(self._latest_perspective_diagnostics)

    @last_perspective_diagnostics.setter
    def last_perspective_diagnostics(self, val: Dict[PerspectiveType, Dict[str, Any]]) -> None:
        self._thread_local.diagnostics = dict(val)
        with self._diagnostics_lock:
            self._latest_perspective_diagnostics = dict(val)

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
        # Call-scoped diagnostics container isolated to the current calling thread
        call_diagnostics: Dict[PerspectiveType, Dict[str, Any]] = {}
        self.last_perspective_diagnostics = call_diagnostics

        # 1. Deadline pre-check before starting any work
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            timeout_err = LLMTimeoutError("Evaluation deadline expired prior to orchestration.")
            orch_err = ReasoningOrchestrationError(
                "Perspective evaluation deadline already expired before orchestration began."
            )
            orch_err.perspective_diagnostics = dict(call_diagnostics)
            raise orch_err from timeout_err

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

        def _invoke_worker(
            ctx: PerspectiveContext,
        ) -> Tuple[PerspectiveType, Optional[ReasoningPerspective], Optional[Exception], Optional[Dict[str, Any]]]:
            ptype = ctx.perspective.perspective_type
            res: Optional[ReasoningPerspective] = None
            err: Optional[Exception] = None
            diag: Optional[Dict[str, Any]] = None
            try:
                res = self.reasoner.evaluate(ctx, deadline_monotonic=deadline_monotonic)
            except Exception as exc:
                err = exc
            finally:
                # Capture diagnostic inside the worker thread immediately after generate_structured completes or fails
                raw_diag = getattr(self.reasoner, "last_diagnostic", None)
                if not isinstance(raw_diag, dict):
                    client = getattr(self.reasoner, "llm_client", None)
                    raw_diag = getattr(client, "last_diagnostic", None) if client is not None else None
                if isinstance(raw_diag, dict):
                    diag = dict(raw_diag)
            return ptype, res, err, diag

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
                    orch_err = ReasoningOrchestrationError(
                        f"Perspective evaluation timed out: {ptype.value}"
                    )
                    orch_err.perspective_diagnostics = dict(self.last_perspective_diagnostics)
                    raise orch_err from timeout_err

                _, res, exc, diag = _invoke_worker(ctx)
                if diag is not None:
                    call_diagnostics[ptype] = diag
                    self.last_perspective_diagnostics = call_diagnostics

                if exc is not None:
                    if (
                        isinstance(exc, LLMTimeoutError)
                        or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                    ):
                        orch_err = ReasoningOrchestrationError(
                            f"Perspective evaluation timed out: {ptype.value}"
                        )
                    else:
                        orch_err = ReasoningOrchestrationError(
                            f"Perspective evaluation failed: {ptype.value}"
                        )
                    orch_err.perspective_diagnostics = dict(call_diagnostics)
                    raise orch_err from exc

                assert res is not None
                sequential_results.append(res)

            raw_results = tuple(sequential_results)

        else:
            # Bounded concurrent execution path
            results_by_type: Dict[PerspectiveType, ReasoningPerspective] = {}
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers)
            futures: Dict[concurrent.futures.Future, PerspectiveType] = {}

            try:
                for ctx in perspective_contexts:
                    ptype = ctx.perspective.perspective_type
                    fut = executor.submit(_invoke_worker, ctx)
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

            # Collect results and diagnostics from completed futures immediately
            worker_outputs: Dict[PerspectiveType, Tuple[Optional[ReasoningPerspective], Optional[Exception]]] = {}
            for fut in done:
                try:
                    ptype, res, exc, diag = fut.result()
                    if diag is not None:
                        call_diagnostics[ptype] = diag
                    worker_outputs[ptype] = (res, exc)
                except Exception as fatal_e:
                    ptype = futures[fut]
                    worker_outputs[ptype] = (None, fatal_e)
            self.last_perspective_diagnostics = call_diagnostics

            # Deterministic inspection in canonical perspective order
            # If not all completed or deadline expired while waiting
            if not_done or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic):
                # Check if any completed worker already failed with an explicit error
                for ctx in perspective_contexts:
                    ptype = ctx.perspective.perspective_type
                    if ptype in worker_outputs:
                        _, exc = worker_outputs[ptype]
                        if exc is not None:
                            if (
                                isinstance(exc, LLMTimeoutError)
                                or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                            ):
                                orch_err = ReasoningOrchestrationError(
                                    f"Perspective evaluation timed out: {ptype.value}"
                                )
                            else:
                                orch_err = ReasoningOrchestrationError(
                                    f"Perspective evaluation failed: {ptype.value}"
                                )
                            orch_err.perspective_diagnostics = dict(call_diagnostics)
                            raise orch_err from exc

                # If none completed with an explicit exception, report timeout
                timed_out_types = [t.value for f, t in futures.items() if f in not_done]
                timed_out_desc = timed_out_types[0] if timed_out_types else "deadline exceeded"
                timeout_err = LLMTimeoutError(
                    f"Operation timed out waiting for perspective '{timed_out_desc}'."
                )
                orch_err = ReasoningOrchestrationError(
                    f"Perspective evaluation timed out: {timed_out_desc}"
                )
                orch_err.perspective_diagnostics = dict(call_diagnostics)
                raise orch_err from timeout_err

            # All completed: inspect exceptions strictly by canonical perspective order
            for ctx in perspective_contexts:
                ptype = ctx.perspective.perspective_type
                res, exc = worker_outputs[ptype]
                if exc is not None:
                    if (
                        isinstance(exc, LLMTimeoutError)
                        or isinstance(getattr(exc, "__cause__", None), LLMTimeoutError)
                    ):
                        orch_err = ReasoningOrchestrationError(
                            f"Perspective evaluation timed out: {ptype.value}"
                        )
                    else:
                        orch_err = ReasoningOrchestrationError(
                            f"Perspective evaluation failed: {ptype.value}"
                        )
                    orch_err.perspective_diagnostics = dict(call_diagnostics)
                    raise orch_err from exc

                assert res is not None
                results_by_type[ptype] = res

            raw_results = tuple(
                results_by_type[p_def.perspective_type] for p_def in CANONICAL_PERSPECTIVES
            )

        # 5. Deterministic post-execution validation
        return validate_orchestrated_perspectives(raw_results)
