"""API publica del modulo de personalizacion academica."""

from .config import (
    PersonalizationConfig,
    is_personalization_enabled,
    load_personalization_config,
)
from .formatter import build_personalization_summary
from .parser import likert_label, parse_likert_answer
from .questionnaire import (
    QUESTIONNAIRE_VERSION,
    SCORING_VERSION,
    get_question_by_index,
    get_question_count,
    get_questions,
    get_questions_for_technique,
    get_technique,
    get_techniques,
)
from .scoring import evaluate_questionnaire, rank_techniques
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
    "is_personalization_enabled",
    "likert_label",
    "load_personalization_config",
    "parse_likert_answer",
    "rank_techniques",
]

