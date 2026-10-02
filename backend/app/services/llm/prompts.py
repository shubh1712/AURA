"""AURA LLM Prompt Templates & Builders.

Contains modular system instructions and prompt formatting functions for
decision understanding and decomposition. Prompts remain focused and minimal,
leaving structural schema enforcement to Pydantic contracts.
"""

from typing import Any, Dict, List, Optional


DECOMPOSITION_SYSTEM_PROMPT = """You are AURA, an autonomous decision-intelligence analyst.
Your objective is to deconstruct unstructured human decision inquiries into a rigorous,
structured decision model.

Follow these analytical principles:
1. Identify the core decision question, primary objective, and operational time horizon.
2. Unpack key controllable levers as variables. Do NOT invent missing numerical baseline or proposed values if they were not provided.
3. Distinguish explicit user constraints from inferred operational realities.
4. Highlight competing trade-offs between upside potential and downside risks.
5. Explicitly isolate unverified premises as assumptions and identify critical empirical unknowns.
6. Do NOT provide recommendations or tell the user what decision to make.
7. Do NOT fabricate evidence, metrics, or claim unverified assertions are facts.
8. When inquiries are vague or multi-faceted, capture alternative interpretations in key_questions and unknowns rather than guessing a single scenario.
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
