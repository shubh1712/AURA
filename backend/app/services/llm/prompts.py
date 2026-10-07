"""AURA LLM Prompt Templates & Builders.

Contains modular system instructions and prompt formatting functions for
decision understanding and decomposition. Prompts remain focused and minimal,
leaving structural schema enforcement to Pydantic contracts.
"""

from typing import Any, Dict, List, Optional


DECOMPOSITION_SYSTEM_PROMPT = """You are AURA, an autonomous decision-intelligence analyst.
Deconstruct inquiries into structured decision models without recommendation or advice.

Analytical Principles:
1. Grounding: Preserve user numerical values. Distinguish user_provided facts from inferred deductions. Never invent unsupported facts or metrics.
2. Variables: The 'unit' field must be strictly the unit symbol itself (e.g. '%' or 'USD'), at most 10 characters, never combined with metadata or commentary.
3. Constraints: User-stated boundaries are hard (is_hard_constraint=true); inferred operational limits are soft (is_hard_constraint=false).
4. Rigor & Tradeoffs: Frame core tensions between upsides and downsides without inventing unverified metrics. Isolate unverified premises as assumptions and empirical gaps as unknowns.
5. Ambiguity: For vague inquiries, capture missing dimensions in key_questions and unknowns rather than guessing.
6. Bounded Granularity: Generate 1-2 high-priority items per collection (objectives, variables, constraints, stakeholders, tradeoffs, assumptions, unknowns, key questions). Output direct values only without internal deliberation.
"""


def build_decomposition_prompt(
    question: str,
    context: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None,
) -> str:
    """Constructs the prompt for decision decomposition.

    Args:
        question: The core decision question submitted by the user.
        context: Optional dictionary of operational background or metrics.
        constraints: Optional list of boundaries or non-negotiable criteria.

    Returns:
        Formatted prompt string.
    """
    sections: List[str] = [f"Decision Question:\n{question.strip()}"]

    if context:
        context_lines = [f"- {k}: {v}" for k, v in context.items()]
        sections.append("Operational Context:\n" + "\n".join(context_lines))

    if constraints:
        constraints_lines = [f"- {c}" for c in constraints if c.strip()]
        if constraints_lines:
            sections.append("Stated Constraints:\n" + "\n".join(constraints_lines))

    sections.append(
        "Deconstruct this decision problem into its structured components according to the requested schema."
    )

    return "\n\n".join(sections)
