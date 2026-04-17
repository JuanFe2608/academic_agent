"""Offline evaluation helpers for the study recommendations RAG."""

from .models import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalMetrics,
    RagEvaluationReport,
)
from .runner import (
    DEFAULT_EVAL_DATASET_PATH,
    CapturingStudyRecommendationRetriever,
    build_local_evaluation_target,
    build_postgres_evaluation_target,
    evaluate_cases,
    evaluate_disabled_fallback,
    load_eval_cases,
)

__all__ = [
    "CapturingStudyRecommendationRetriever",
    "DEFAULT_EVAL_DATASET_PATH",
    "RagEvalCase",
    "RagEvalCaseResult",
    "RagEvalMetrics",
    "RagEvaluationReport",
    "build_local_evaluation_target",
    "build_postgres_evaluation_target",
    "evaluate_cases",
    "evaluate_disabled_fallback",
    "load_eval_cases",
]
