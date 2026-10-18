"""AURA Perspective Reasoner.

Executes structured analytical evaluation for a single canonical boardroom perspective:
- Coordinates prompt serialization, structured LLM generation, and authoritative grounding validation.
- Passes through deadline_monotonic directly to LLMClient.
- Zero direct dependencies on google.genai or raw SDKs.
- Zero secondary retry loops (relies solely on LLMClient's internal transient retries).
- Preserves safe typed exception chains.
- Pure single-perspective execution: does not perform concurrency or multi-perspective orchestration.
"""

import threading
import time
from typing import Any, Dict, Optional

from app.schemas.reasoning import (
    CandidatePerspectiveAnalysis,
    ReasoningPerspective,
)
from app.services.llm.client import (
    DEFAULT_LLM_CONFIG,
    LLMClient,
    LLMError,
    LLMTimeoutError,
    LLMConfig,
)
from app.services.reasoning.context_builder import PerspectiveContext
from app.services.reasoning.prompt_builder import build_perspective_prompt
from app.services.reasoning.validator import (
    ReasoningEvaluationError,
    ReasoningPromptError,
    ReasoningValidationError,
    validate_and_reconcile_candidate_perspective,
)


class PerspectiveReasoner:
    """Evaluates an individual boardroom perspective lens using LLMClient and grounding validation."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: Optional[LLMConfig] = None,
    ) -> None:
        """Initializes reasoner with an injected LLMClient.

        Args:
            llm_client: Abstract LLMClient implementation (MockLLMClient, VertexLLMClient, etc.).
            config: Optional LLM call configuration overrides.
        """
        self.llm_client = llm_client
        self.config = config or DEFAULT_LLM_CONFIG
        self._thread_local = threading.local()
        self._diagnostic_lock = threading.Lock()
        self._latest_diagnostic: Optional[Dict[str, Any]] = None

    @property
    def last_diagnostic(self) -> Optional[Dict[str, Any]]:
        """Thread-safe access to the most recent diagnostic recorded on this reasoner."""
        thread_diag = getattr(self._thread_local, "diagnostic", None)
        if thread_diag is not None:
            return thread_diag
        with self._diagnostic_lock:
            return self._latest_diagnostic

    def evaluate(
        self,
        perspective_context: PerspectiveContext,
        deadline_monotonic: Optional[float] = None,
        config: Optional[LLMConfig] = None,
    ) -> ReasoningPerspective:
        """Evaluates ONE assigned boardroom perspective lens.

        Args:
            perspective_context: Complete immutable context for this perspective.
            deadline_monotonic: Optional monotonic deadline for bounded execution.
            config: Optional LLM call configuration override.

        Returns:
            ReasoningPerspective: Validated, authoritatively grounded perspective analysis.

        Raises:
            ReasoningEvaluationError: If execution exceeds deadline or LLM generation fails.
            ReasoningValidationError: If candidate output violates grounding or lineage rules.
            ReasoningPromptError: If prompt construction exceeds allowable bounds.
        """
        ptype = perspective_context.perspective.perspective_type.value

        # 1. Deadline pre-check
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise ReasoningEvaluationError(
                f"Evaluation deadline exceeded prior to LLM execution for perspective '{ptype}'."
            )

        # 2. Deterministic prompt serialization
        prompt = build_perspective_prompt(perspective_context)

        # 3. Structured candidate generation via LLMClient
        effective_config = config or self.config
        try:
            try:
                candidate: CandidatePerspectiveAnalysis = self.llm_client.generate_structured(
                    prompt=prompt.user_prompt,
                    response_schema=CandidatePerspectiveAnalysis,
                    system_instruction=prompt.system_instruction,
                    config=effective_config,
                    deadline_monotonic=deadline_monotonic,
                )
            except LLMTimeoutError as exc:
                raise ReasoningEvaluationError(
                    f"LLM generation timed out for perspective '{ptype}': {exc.message}"
                ) from exc
            except LLMError as exc:
                raise ReasoningEvaluationError(
                    f"LLM generation failed for perspective '{ptype}': {exc.message}"
                ) from exc
            except Exception as exc:
                raise ReasoningEvaluationError(
                    f"Unexpected failure generating perspective '{ptype}': {str(exc)}"
                ) from exc

            # 4. Deterministic grounding and lineage validation
            return validate_and_reconcile_candidate_perspective(
                candidate=candidate,
                context=perspective_context,
            )
        finally:
            raw_diag = getattr(self.llm_client, "last_diagnostic", None)
            if isinstance(raw_diag, dict):
                diag_copy = dict(raw_diag)
                self._thread_local.diagnostic = diag_copy
                with self._diagnostic_lock:
                    self._latest_diagnostic = diag_copy
