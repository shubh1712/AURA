"""AURA Question Understanding & Decision Decomposition Engine.

Transforms unstructured user questions, operational context, and constraints
into a canonical, provenance-verified DecisionModel and calculates deterministic
decision complexity.

Guarantees:
- Inferences are strictly distinguished from user facts.
- Hallucinated numerical values are purged and tracked as unknowns.
- Epistemic provenance is preserved end-to-end.
"""

import time
from typing import Any, Dict, List, Optional
from app.engines.complexity import (
    ComplexityConfig,
    ComplexitySignals,
    UncertaintyLevel,
    calculate_complexity,
)
from app.engines.provenance import audit_decision_provenance
from app.schemas.decision_model import DecisionModel
from app.services.llm.client import LLMClient, LLMTimeoutError
from app.services.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
    build_decomposition_prompt,
)


class QuestionUnderstandingEngine:
    """Orchestrator for understanding, deconstructing, and provenance-auditing decisions."""

    def __init__(
        self,
        llm_client: LLMClient,
        complexity_config: Optional[ComplexityConfig] = None,
    ) -> None:
        """Initializes QuestionUnderstandingEngine.

        Args:
            llm_client: Concrete or mock LLMClient for structured generation.
            complexity_config: Optional override configuration for deterministic complexity.
        """
        self.llm_client = llm_client
        self.complexity_config = complexity_config

    def deconstruct(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        deadline_monotonic: Optional[float] = None,
    ) -> DecisionModel:
        """Deconstructs user inquiry into a provenance-audited DecisionModel.

        Args:
            question: Verbatim decision question from the user.
            context: Optional background facts or metrics.
            constraints: Optional explicit boundaries.
            deadline_monotonic: Optional absolute monotonic deadline for the operation.

        Returns:
            Fully instantiated, provenance-verified DecisionModel.
        """
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise LLMTimeoutError("Operation timed out before DecisionModel deconstruction could begin.")

        # 1. Build prompt
        prompt = build_decomposition_prompt(
            question=question,
            context=context,
            constraints=constraints,
        )

        # 2. Invoke structured LLM generation
        try:
            raw_model = self.llm_client.generate_structured(
                prompt=prompt,
                response_schema=DecisionModel,
                system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
                deadline_monotonic=deadline_monotonic,
            )
        except TypeError as te:
            if "unexpected keyword argument 'deadline_monotonic'" in str(te):
                raw_model = self.llm_client.generate_structured(
                    prompt=prompt,
                    response_schema=DecisionModel,
                    system_instruction=DECOMPOSITION_SYSTEM_PROMPT,
                )
            else:
                raise

        # 3. Preserve and verify provenance
        audited_model = audit_decision_provenance(
            model=raw_model,
            raw_prompt=question,
            context=context,
            constraints=constraints,
        )

        # 4. Calculate deterministic complexity based on extracted signals
        unknown_count = len(audited_model.unknowns)
        if unknown_count >= 3:
            unc_level = UncertaintyLevel.HIGH
        elif unknown_count >= 1:
            unc_level = UncertaintyLevel.MEDIUM
        else:
            unc_level = UncertaintyLevel.LOW

        signals = ComplexitySignals(
            variable_count=len(audited_model.variables),
            constraint_count=len(audited_model.constraints),
            stakeholder_count=len(audited_model.stakeholders),
            tradeoff_count=len(audited_model.tradeoffs),
            unknown_count=unknown_count,
            dependency_count=0,
            uncertainty_level=unc_level,
            irreversibility=audited_model.complexity.reversibility,
        )
        complexity_result = calculate_complexity(signals, config=self.complexity_config)

        # 5. Attach deterministic complexity evaluation
        audited_model.complexity.score = complexity_result.score
        audited_model.complexity.level = complexity_result.level

        return audited_model
