"""AURA Recommendation & Action Planning Package.

Provides structured decision recommendation, explainable uncertainty assessment,
and grounded action planning grounded in empirical evidence and boardroom deliberations.
"""

from app.services.recommendation.generator import RecommendationGenerator
from app.services.recommendation.prompt_builder import (
    build_recommendation_prompt,
    build_recommendation_system_instruction,
)
from app.services.recommendation.service import RecommendationService
from app.services.recommendation.validator import (
    RecommendationError,
    RecommendationEvaluationError,
    RecommendationPromptError,
    RecommendationServiceError,
    RecommendationValidationError,
    clean_id_list,
    validate_action_dependencies,
    validate_candidate_recommendation,
    validate_decision_consistency,
    validate_recommendation_inputs,
    validate_recommendation_references,
)

__all__ = [
    "RecommendationGenerator",
    "RecommendationService",
    "RecommendationError",
    "RecommendationEvaluationError",
    "RecommendationPromptError",
    "RecommendationServiceError",
    "RecommendationValidationError",
    "build_recommendation_prompt",
    "build_recommendation_system_instruction",
    "clean_id_list",
    "validate_action_dependencies",
    "validate_candidate_recommendation",
    "validate_decision_consistency",
    "validate_recommendation_inputs",
    "validate_recommendation_references",
]
