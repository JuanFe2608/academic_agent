"""Servicios del dominio de personalización."""

from .config import (
    PersonalizationConfig,
    is_personalization_enabled,
    load_personalization_config,
)
from .models import (
    PersonalizationAnswer,
    PersonalizationResult,
    TechniqueDefinition,
    TechniqueScore,
    TiebreakerAnswer,
)
from .parser import likert_label, parse_choice_answer, parse_likert_answer
from .questionnaire import (
    QUESTIONNAIRE_VERSION,
    SCORING_VERSION,
    get_question_by_index,
    get_question_count,
    get_questions,
    get_questions_for_technique,
    get_technique,
    get_techniques,
    get_tiebreaker_question_by_id,
    get_tiebreaker_question_by_index,
    get_tiebreaker_question_count,
    get_tiebreaker_questions,
)
from .scoring import (
    assess_tiebreaker_need,
    evaluate_questionnaire,
    rank_techniques,
    refine_questionnaire_with_tiebreaker,
)
from .service import (
    PersistStudyProfileResult,
    PersonalizationService,
    build_personalization_service,
)

__all__ = [
    "PersonalizationAnswer",
    "PersonalizationConfig",
    "PersonalizationResult",
    "PersonalizationService",
    "PersistStudyProfileResult",
    "QUESTIONNAIRE_VERSION",
    "SCORING_VERSION",
    "TechniqueDefinition",
    "TechniqueScore",
    "TiebreakerAnswer",
    "assess_tiebreaker_need",
    "build_personalization_service",
    "evaluate_questionnaire",
    "get_question_by_index",
    "get_question_count",
    "get_questions",
    "get_questions_for_technique",
    "get_technique",
    "get_techniques",
    "get_tiebreaker_question_by_id",
    "get_tiebreaker_question_by_index",
    "get_tiebreaker_question_count",
    "get_tiebreaker_questions",
    "is_personalization_enabled",
    "likert_label",
    "load_personalization_config",
    "parse_choice_answer",
    "parse_likert_answer",
    "rank_techniques",
    "refine_questionnaire_with_tiebreaker",
]
