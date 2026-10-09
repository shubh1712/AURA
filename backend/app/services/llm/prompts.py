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
2. Variables: For 'unit', output a short measurement symbol or abbreviation, no longer than 10 characters, such as '%', 'USD', 'USD/mo', 'users', or 'months'. Use JSON null when no accurate short unit is available. Do not return prose descriptions or explanations in this field.
3. Constraints: All materially distinct user-stated boundaries must be preserved as hard constraints (is_hard_constraint=true). Inferred operational limits are soft (is_hard_constraint=false).
4. Rigor & Tradeoffs: Frame core tensions between upsides and downsides without inventing unverified metrics. Isolate unverified premises as assumptions and empirical gaps as unknowns.
5. Ambiguity & Unknowns: For missing or unverified dimensions, capture factual gaps in unknowns and key_questions rather than guessing.
6. Bounded Granularity & Conciseness: Write concise, direct descriptions without conversational filler. Prioritize high-impact, nonredundant entities (typically 1–3 per collection for focused inquiries), while including all entities necessary for completeness. Avoid duplicate or speculative items. Output direct JSON values only without internal deliberation.
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
