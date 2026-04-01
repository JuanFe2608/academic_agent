"""API publica del modulo de personalizacion academica."""

from .config import (
    PersonalizationConfig,
    is_personalization_enabled,
    load_personalization_config,
)
from .formatter import build_personalization_summary
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
    "PersonalizationConfig",
    "PersonalizationService",
    "PersistStudyProfileResult",
    "QUESTIONNAIRE_VERSION",
    "SCORING_VERSION",
    "build_personalization_service",
    "build_personalization_summary",
    "evaluate_questionnaire",
    "get_question_by_index",
    "get_question_count",
    "get_questions",
    "get_questions_for_technique",
    "get_technique",
    "get_techniques",
    "get_tiebreaker_question_by_index",
    "get_tiebreaker_question_count",
    "get_tiebreaker_questions",
    "is_personalization_enabled",
    "assess_tiebreaker_need",
    "likert_label",
    "load_personalization_config",
    "parse_choice_answer",
    "parse_likert_answer",
    "rank_techniques",
    "refine_questionnaire_with_tiebreaker",
]
