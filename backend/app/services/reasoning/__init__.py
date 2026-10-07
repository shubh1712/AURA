"""AURA Reasoning Service Package.

Provides the canonical boardroom perspectives, deterministic context builder,
prompt builder, grounding validator, and single-perspective reasoner for the AI Boardroom (Day 4).
"""

from app.services.reasoning.perspectives import (
    CANONICAL_PERSPECTIVES,
    COMMON_EPISTEMIC_RULES,
    CUSTOMER,
    FINANCE,
    GROWTH,
    PerspectiveDefinition,
    RISK,
    get_perspective_definition,
)
from app.services.reasoning.context_builder import (
    ClaimLinkContext,
    DecisionContext,
    EntityEvidenceIndex,
    EvidenceContext,
    EvidenceItemContext,
    GapContext,
    PerspectiveContext,
    ReasoningContext,
    RequirementContext,
    SourceContext,
    UntrustedSourceText,
    build_all_perspective_contexts,
    build_perspective_context,
    build_reasoning_context,
)
from app.services.reasoning.prompt_builder import (
    MAX_FIELD_NARRATIVE_CHARS,
    MAX_SOURCE_EXCERPT_CHARS,
    MAX_TOTAL_PROMPT_CHARS,
    TRUNCATION_MARKER,
    PerspectivePrompt,
    build_perspective_prompt,
    build_perspective_system_instruction,
    truncate_narrative,
)
from app.services.reasoning.validator import (
    ReasoningError,
    ReasoningEvaluationError,
    ReasoningOrchestrationError,
    ReasoningPromptError,
    ReasoningServiceError,
    ReasoningValidationError,
    validate_and_reconcile_candidate_perspective,
)
from app.services.reasoning.evaluator import (
    PerspectiveReasoner,
)
from app.services.reasoning.orchestrator import (
    MAX_PERSPECTIVE_WORKERS,
    PerspectiveOrchestrator,
    validate_orchestrated_perspectives,
)
from app.services.reasoning.disagreements import (
    classify_disagreement_nature,
    detect_disagreements,
    generate_deterministic_disagreement_id,
)
from app.services.reasoning.synthesizer import (
    BoardSynthesizer,
    build_synthesis_prompt,
    build_synthesis_system_instruction,
    validate_candidate_synthesis,
    validate_synthesis_inputs,
)
from app.services.reasoning.service import (
    ReasoningService,
    generate_deterministic_board_id,
    validate_upstream_artifacts,
)

__all__ = [
    # Perspectives
    "CANONICAL_PERSPECTIVES",
    "COMMON_EPISTEMIC_RULES",
    "PerspectiveDefinition",
    "GROWTH",
    "FINANCE",
    "CUSTOMER",
    "RISK",
    "get_perspective_definition",
    # Context builder types
    "UntrustedSourceText",
    "SourceContext",
    "EvidenceItemContext",
    "ClaimLinkContext",
    "RequirementContext",
    "GapContext",
    "EntityEvidenceIndex",
    "DecisionContext",
    "EvidenceContext",
    "ReasoningContext",
    "PerspectiveContext",
    # Context builder functions
    "build_reasoning_context",
    "build_perspective_context",
    "build_all_perspective_contexts",
    # Prompt builder
    "MAX_FIELD_NARRATIVE_CHARS",
    "MAX_SOURCE_EXCERPT_CHARS",
    "MAX_TOTAL_PROMPT_CHARS",
    "TRUNCATION_MARKER",
    "PerspectivePrompt",
    "build_perspective_prompt",
    "build_perspective_system_instruction",
    "truncate_narrative",
    # Validator & Errors
    "ReasoningError",
    "ReasoningPromptError",
    "ReasoningValidationError",
    "ReasoningEvaluationError",
    "ReasoningOrchestrationError",
    "ReasoningServiceError",
    "validate_and_reconcile_candidate_perspective",
    # Reasoner
    "PerspectiveReasoner",
    # Orchestrator
    "MAX_PERSPECTIVE_WORKERS",
    "PerspectiveOrchestrator",
    "validate_orchestrated_perspectives",
    # Disagreements
    "detect_disagreements",
    "generate_deterministic_disagreement_id",
    "classify_disagreement_nature",
    # Synthesizer
    "BoardSynthesizer",
    "build_synthesis_prompt",
    "build_synthesis_system_instruction",
    "validate_candidate_synthesis",
    "validate_synthesis_inputs",
    # Service
    "ReasoningService",
    "generate_deterministic_board_id",
    "validate_upstream_artifacts",
]

