"""AURA Future Scenario Engine Services (Phase 5A)."""

from app.services.scenario.generator import ScenarioGenerator
from app.services.scenario.prompt_builder import (
    MAX_SCENARIO_PROMPT_CHARS,
    build_scenario_prompt,
    build_scenario_system_instruction,
)
from app.services.scenario.service import ScenarioService
from app.services.scenario.validator import (
    ScenarioError,
    ScenarioEvaluationError,
    ScenarioPromptError,
    ScenarioServiceError,
    ScenarioValidationError,
    validate_candidate_scenario_set,
    validate_scenario_inputs,
)

__all__ = [
    "ScenarioGenerator",
    "ScenarioService",
    "build_scenario_prompt",
    "build_scenario_system_instruction",
    "MAX_SCENARIO_PROMPT_CHARS",
    "validate_scenario_inputs",
    "validate_candidate_scenario_set",
    "ScenarioError",
    "ScenarioPromptError",
    "ScenarioValidationError",
    "ScenarioEvaluationError",
    "ScenarioServiceError",
]
