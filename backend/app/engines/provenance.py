"""AURA Provenance Auditing & Epistemic Verification Engine.

Enforces strict boundaries between:
1. USER_PROVIDED: Information explicitly stated in the user prompt, context, or constraints.
2. INFERRED: Hypotheses, qualitative reasoning, and trade-offs deduced by AI or heuristics.
3. UNKNOWN: Missing empirical facts, unverified parameters, and knowledge gaps.

Guarantees:
- Inferences are NEVER represented as user-provided facts.
- Missing numerical values are NEVER fabricated or hallucinated; they are recorded as UNKNOWN.
"""

import re
from typing import Any, Dict, List, Optional, Set
from app.schemas.decision_model import (
    ConfidenceLevel,
    CriticalityLevel,
    DecisionModel,
    ProvenanceType,
    Unknown,
)


def _generate_unique_unk_id(base_id: str, existing_ids: Set[str]) -> str:
    """Generates a guaranteed unique ID for a newly created Unknown entity."""
    candidate = base_id
    counter = 1
    while candidate in existing_ids:
        candidate = f"{base_id}_{counter}"
        counter += 1
    existing_ids.add(candidate)
    return candidate


def _cleanse_prescriptive_language(text: str) -> str:
    """Neutralizes prescriptive recommendation language to keep analysis epistemically neutral."""
    cleaned = text
    patterns = [
        (r"(?i)^recommendation:\s*", ""),
        (r"(?i)\bwe recommend\s+(that\s+)?(you\s+)?", "evaluate "),
        (r"(?i)\bi recommend\s+(that\s+)?(you\s+)?", "evaluate "),
        (r"(?i)\byou should definitely\s+", "consider whether to "),
        (r"(?i)\bthe recommended (action|choice|decision) is to\s+", "option to "),
    ]
    for pattern, replacement in patterns:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned.strip()


def _extract_numbers_from_text(text: str) -> Set[str]:
    """Extracts numeric tokens (integers, floats, percentages, currency) from text."""
    # Matches patterns like 20, 20%, $50,000, 3.5, -20, +20
    matches = re.findall(r"[-+]?(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)(?:%)?", text)
    normalized = set()
    for m in matches:
        clean = m.replace(",", "").replace("%", "").lstrip("+").strip()
        if not clean:
            continue
        try:
            val = float(clean)
            normalized.add(str(val))
            normalized.add(str(int(val)) if val.is_integer() else str(val))
            normalized.add(clean)
            # Also add decimal fraction equivalent if percentage-like (e.g., 70 -> 0.7)
            if 0 < val <= 100:
                normalized.add(str(round(val / 100.0, 4)))
        except ValueError:
            normalized.add(clean)
    return normalized


def _has_goal_or_decision_intent(text: str) -> bool:
    """Returns True if text contains explicit decision inquiry or goal-directed phrasing."""
    if "?" in text:
        return True
    intent_patterns = [
        r"\b(?:should|whether|could|decide|decision|evaluate|choose|selecting|pick)\b",
        r"\b(?:in order to|so that|goal is|objective is|aim to|aiming to|want to|trying to)\b",
        r"\b(?:to acquire|to increase|to decrease|to improve|to reduce|to optimize|to eliminate|to achieve|to prevent|to build|to migrate)\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in intent_patterns)


def _has_unrecognized_number(text: str, user_numbers: Set[str]) -> bool:
    """Returns True if text contains any numeric token that is not in user_numbers."""
    matches = re.findall(r"[-+]?(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)(?:%)?", text)
    for m in matches:
        token_forms = _extract_numbers_from_text(m)
        if not token_forms:
            continue
        if not any(form in user_numbers for form in token_forms):
            return True
    return False


def _extract_user_corpus_and_numbers(
    raw_prompt: str,
    context: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None,
) -> tuple[str, Set[str]]:
    """Builds a unified lower-cased user text corpus and extracts all explicitly stated numbers."""
    text_chunks = [raw_prompt]

    if context:
        for k, v in context.items():
            text_chunks.append(f"{k} {v}")

    if constraints:
        for c in constraints:
            text_chunks.append(c)

    full_text = " ".join(text_chunks)
    numbers = _extract_numbers_from_text(full_text)

    # Also directly add context numeric values if passed as raw ints/floats
    if context:
        for v in context.values():
            if isinstance(v, (int, float)):
                numbers.add(str(float(v)))
                numbers.add(str(int(v)) if float(v).is_integer() else str(v))

    return full_text.lower(), numbers


def audit_decision_provenance(
    model: DecisionModel,
    raw_prompt: str,
    context: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None,
) -> DecisionModel:
    """Audits and enforces epistemic provenance on a DecisionModel instance.

    Guarantees that:
    - User-stated facts remain USER_PROVIDED.
    - AI-deduced assumptions, metrics, and constraints are tagged INFERRED.
    - Hallucinated or speculative numerical values are stripped and tracked as UNKNOWN.
    - Missing empirical facts are explicitly represented as UNKNOWN.
    - Prescriptive recommendation language is neutralized.
    - Unverified assumptions are bounded to UNTESTED confidence.

    Args:
        model: DecisionModel to audit.
        raw_prompt: The verbatim user question.
        context: Optional dictionary of background data provided by the user.
        constraints: Optional list of explicit user constraints.

    Returns:
        Audited DecisionModel with strictly verified provenance.
    """
    user_corpus, user_numbers = _extract_user_corpus_and_numbers(raw_prompt, context, constraints)
    user_constraint_texts = [c.strip().lower() for c in (constraints or []) if c.strip()]

    existing_unknown_ids = {u.id for u in model.unknowns}
    existing_unknown_questions = {u.question.lower() for u in model.unknowns}
    created_unknowns: List[Unknown] = []

    # 1. Audit Decision
    model.decision.raw_prompt = raw_prompt
    model.decision.summary = _cleanse_prescriptive_language(model.decision.summary)

    # 2. Audit Objectives
    stop_words = {
        "should", "would", "could", "about", "their", "there", "these", "those",
        "which", "where", "while", "evaluate", "assess", "determine", "identify",
        "increase", "decrease", "optimize", "improve", "ensure", "manage", "through",
        "with", "that", "this", "from", "into"
    }
    for obj in model.objectives:
        obj.description = _cleanse_prescriptive_language(obj.description)
        desc_lower = obj.description.lower()
        words = [w for w in re.findall(r"\w+", desc_lower) if len(w) > 3 and w not in stop_words]
        matched_words = [w for w in words if w in user_corpus]
        match_ratio = len(matched_words) / max(1, len(words))

        # Check target metric for hallucinated numbers
        target_has_hallucinated_num = False
        if obj.target_metric and _has_unrecognized_number(obj.target_metric, user_numbers):
            target_has_hallucinated_num = True
            gap_question = f"What is the empirical target metric for objective '{obj.description}'?"
            if gap_question.lower() not in existing_unknown_questions:
                unk_id = _generate_unique_unk_id(f"unk_target_{obj.id}", existing_unknown_ids)
                created_unknowns.append(
                    Unknown(
                        id=unk_id,
                        question=gap_question,
                        criticality=CriticalityLevel.MEDIUM,
                        potential_sources=["Operational goals", "Stakeholder clarification"],
                        provenance=ProvenanceType.UNKNOWN,
                    )
                )
                existing_unknown_questions.add(gap_question.lower())

        # Only classify as USER_PROVIDED if:
        # 1. User input actually contains a goal or decision inquiry.
        # 2. Substantive terms match user input.
        # 3. Target metric is not hallucinated.
        has_intent = _has_goal_or_decision_intent(user_corpus)
        if has_intent and match_ratio >= 0.5 and len(matched_words) >= 2 and not target_has_hallucinated_num:
            obj.provenance = ProvenanceType.USER_PROVIDED
        else:
            obj.provenance = ProvenanceType.INFERRED

    # 3. Audit Constraints
    for cnstr in model.constraints:
        cnstr.description = _cleanse_prescriptive_language(cnstr.description)
        desc_lower = cnstr.description.lower()
        is_explicit_user = any(u in desc_lower or desc_lower in u for u in user_constraint_texts)

        # Check threshold expression for hallucinated numbers
        if cnstr.threshold_expression and _has_unrecognized_number(cnstr.threshold_expression, user_numbers):
            # Hallucinated threshold number -> strip to avoid false deterministic evaluation
            cnstr.threshold_expression = None
            is_explicit_user = False
            gap_question = f"What is the empirical threshold boundary for constraint '{cnstr.name}'?"
            if gap_question.lower() not in existing_unknown_questions:
                unk_id = _generate_unique_unk_id(f"unk_thresh_{cnstr.id}", existing_unknown_ids)
                created_unknowns.append(
                    Unknown(
                        id=unk_id,
                        question=gap_question,
                        criticality=CriticalityLevel.HIGH,
                        potential_sources=["Operational policy", "Executive decision-makers"],
                        provenance=ProvenanceType.UNKNOWN,
                    )
                )
                existing_unknown_questions.add(gap_question.lower())

        if is_explicit_user:
            cnstr.source = "user_specified"
            cnstr.provenance = ProvenanceType.USER_PROVIDED
        else:
            # Epistemic Rule: Inferred constraints must NEVER be represented as user-provided
            cnstr.source = "inferred_operational"
            cnstr.provenance = ProvenanceType.INFERRED

    # 4. Audit Variables & Numerical Hallucinations
    for var in model.variables:
        var_name_lower = var.name.lower()
        # Variable identification provenance
        if var_name_lower in user_corpus or any(part in user_corpus for part in var_name_lower.split() if len(part) > 3):
            var.provenance = ProvenanceType.USER_PROVIDED
        else:
            var.provenance = ProvenanceType.INFERRED

        # --- Baseline Value Audit ---
        if var.baseline_value is not None:
            # Check if this numerical baseline actually appeared in user inputs
            b_str = str(var.baseline_value).replace(",", "").replace("%", "").strip()
            try:
                b_float = str(float(b_str))
                b_int = str(int(float(b_str))) if float(b_str).is_integer() else b_float
            except ValueError:
                b_float, b_int = b_str, b_str

            is_user_baseline = (
                b_str in user_numbers
                or b_float in user_numbers
                or b_int in user_numbers
                or (isinstance(var.baseline_value, str) and var.baseline_value.lower() in user_corpus)
            )

            if is_user_baseline:
                var.baseline_provenance = ProvenanceType.USER_PROVIDED
            else:
                # HALLUCINATION GUARD: Never invent missing numerical values
                # Strip the fabricated baseline value and represent it as UNKNOWN
                var.baseline_value = None
                var.baseline_provenance = ProvenanceType.UNKNOWN

                # Record an Unknown gap for the missing baseline
                gap_question = f"What is the current empirical baseline value for '{var.name}'?"
                if gap_question.lower() not in existing_unknown_questions:
                    unk_id = _generate_unique_unk_id(f"unk_baseline_{var.id}", existing_unknown_ids)
                    created_unknowns.append(
                        Unknown(
                            id=unk_id,
                            question=gap_question,
                            criticality=CriticalityLevel.HIGH,
                            potential_sources=["Historical telemetry", "Internal financial records"],
                            provenance=ProvenanceType.UNKNOWN,
                        )
                    )
                    existing_unknown_questions.add(gap_question.lower())
        else:
            var.baseline_provenance = ProvenanceType.UNKNOWN

        # --- Proposed Value Audit ---
        if var.proposed_value is not None:
            p_str = str(var.proposed_value).replace(",", "").replace("%", "").strip()
            try:
                p_float = str(float(p_str))
                p_int = str(int(float(p_str))) if float(p_str).is_integer() else p_float
            except ValueError:
                p_float, p_int = p_str, p_str

            is_user_proposed = (
                p_str in user_numbers
                or p_float in user_numbers
                or p_int in user_numbers
                or (isinstance(var.proposed_value, str) and var.proposed_value.lower() in user_corpus)
            )

            if is_user_proposed:
                var.proposed_provenance = ProvenanceType.USER_PROVIDED
            elif isinstance(var.proposed_value, (int, float)):
                # HALLUCINATION GUARD: Never invent missing numerical values
                # If proposed value is numeric and was NOT in user inputs, strip it and mark UNKNOWN
                var.proposed_value = None
                var.proposed_provenance = ProvenanceType.UNKNOWN
                gap_question = f"What is the specific target or proposed numerical value for '{var.name}'?"
                if gap_question.lower() not in existing_unknown_questions:
                    unk_id = _generate_unique_unk_id(f"unk_proposed_{var.id}", existing_unknown_ids)
                    created_unknowns.append(
                        Unknown(
                            id=unk_id,
                            question=gap_question,
                            criticality=CriticalityLevel.HIGH,
                            potential_sources=["User inquiry clarification", "Scenario target modeling"],
                            provenance=ProvenanceType.UNKNOWN,
                        )
                    )
                    existing_unknown_questions.add(gap_question.lower())
            else:
                # Qualitative or categorical proposed state (e.g. architecture type, boolean toggle)
                var.proposed_provenance = ProvenanceType.INFERRED
        else:
            var.proposed_provenance = ProvenanceType.UNKNOWN

    # Append any created unknowns from stripped hallucinated baselines/metrics/thresholds
    if created_unknowns:
        model.unknowns.extend(created_unknowns)

    # 5. Audit Unknowns (Always UNKNOWN)
    for unk in model.unknowns:
        unk.provenance = ProvenanceType.UNKNOWN

    # 6. Audit Assumptions (Always INFERRED, never USER_PROVIDED; confidence UNTESTED)
    for asm in model.assumptions:
        asm.provenance = ProvenanceType.INFERRED
        if asm.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM):
            asm.confidence = ConfidenceLevel.UNTESTED

    # 7. Audit Stakeholders
    for stk in model.stakeholders:
        stk_lower = stk.group.lower()
        if stk_lower in user_corpus:
            stk.provenance = ProvenanceType.USER_PROVIDED
        else:
            stk.provenance = ProvenanceType.INFERRED

    # 8. Audit Tradeoffs (Always INFERRED tensions)
    for trd in model.tradeoffs:
        trd.upside = _cleanse_prescriptive_language(trd.upside)
        trd.downside = _cleanse_prescriptive_language(trd.downside)
        trd.provenance = ProvenanceType.INFERRED

    # 9. Audit Key Questions (Ensure exploratory phrasing)
    model.key_questions = [
        _cleanse_prescriptive_language(q) for q in model.key_questions if q.strip()
    ]

    return model
