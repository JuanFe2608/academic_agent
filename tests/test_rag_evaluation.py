"""Tests for offline RAG evaluation helpers."""

from __future__ import annotations

from pathlib import Path

from bootstrap.settings import RagSettings
from rag.evaluation import (
    DEFAULT_EVAL_DATASET_PATH,
    build_local_evaluation_target,
    evaluate_cases,
    evaluate_disabled_fallback,
    load_eval_cases,
)


def test_eval_dataset_loads_minimum_plan_categories() -> None:
    cases = load_eval_cases(DEFAULT_EVAL_DATASET_PATH)

    assert len(cases) >= 70
    categories = {case.category for case in cases}
    assert {
        "definition",
        "recommend_technique",
        "recommend_method",
        "comparison",
        "constraint",
        "negative",
        "combination",
    } <= categories
    assert all(case.eval_id for case in cases)
    assert all(case.query for case in cases)


def test_local_evaluation_runner_produces_grounded_metrics() -> None:
    cases = load_eval_cases(DEFAULT_EVAL_DATASET_PATH)[:3]
    target = build_local_evaluation_target(
        settings=RagSettings(
            enabled=True,
            embedding_provider="local_eval",
            embedding_model="hash-bow",
            embedding_dimensions=64,
            top_k_vector=6,
            top_k_lexical=6,
            top_k_final=5,
            min_score=0.0,
        )
    )

    report = evaluate_cases(cases, target=target, dataset_path=Path("evals.jsonl"))

    assert report.backend == "local"
    assert report.metrics.total_cases == 3
    assert report.metrics.groundedness_rate == 1.0
    assert report.metrics.entity_recall_at_k > 0
    assert all(case.source_chunks for case in report.cases)


def test_disabled_fallback_check_uses_service_boundary() -> None:
    cases = load_eval_cases(DEFAULT_EVAL_DATASET_PATH)[:2]

    result = evaluate_disabled_fallback(cases)

    assert result["total_cases"] == 2
    assert result["passed_cases"] == 2
    assert result["pass_rate"] == 1.0
