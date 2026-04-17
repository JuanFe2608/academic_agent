#!/usr/bin/env python
"""Run offline evaluation for the study recommendations RAG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.evaluation import (
    DEFAULT_EVAL_DATASET_PATH,
    build_local_evaluation_target,
    build_postgres_evaluation_target,
    evaluate_cases,
    evaluate_disabled_fallback,
    load_eval_cases,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate study recommendation RAG retrieval and grounded answers."
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_EVAL_DATASET_PATH.as_posix(),
        help="JSONL or JSON eval dataset path.",
    )
    parser.add_argument(
        "--backend",
        choices=("local", "postgres"),
        default="local",
        help="local uses the corpus in memory; postgres uses DB + configured embeddings.",
    )
    parser.add_argument(
        "--corpus-root",
        default="knowledge_base/study_recommendations",
        help="Corpus root used by the local backend.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional limit for quick smoke runs.",
    )
    parser.add_argument(
        "--eval-id",
        action="append",
        default=[],
        help="Run only a specific eval_id. Can be repeated.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Run only a category. Can be repeated.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--check-disabled-fallback",
        action="store_true",
        help="Also verify service fallback behavior with RAG_ENABLED=false.",
    )
    parser.add_argument(
        "--fail-under-entity-recall",
        type=float,
        default=None,
        help="Exit 1 if aggregate entity Recall@k is below this value.",
    )
    parser.add_argument(
        "--fail-under-groundedness",
        type=float,
        default=None,
        help="Exit 1 if groundedness rate is below this value.",
    )
    parser.add_argument(
        "--fail-on-forbidden",
        action="store_true",
        help="Exit 1 if any forbidden entity or answer term is present.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = _filter_cases(
        load_eval_cases(dataset_path),
        eval_ids=set(args.eval_id),
        categories=set(args.category),
        max_cases=args.max_cases,
    )
    if not cases:
        print("RAG evaluation")
        print("- cases: 0")
        print("- status: no cases matched the selected filters")
        return 1

    if args.backend == "postgres":
        target = build_postgres_evaluation_target()
    else:
        target = build_local_evaluation_target(corpus_root=args.corpus_root)

    report = evaluate_cases(cases, target=target, dataset_path=dataset_path)
    if args.check_disabled_fallback:
        report.disabled_fallback = evaluate_disabled_fallback(cases)

    _print_summary(report)
    if args.output:
        _write_report(
            Path(args.output),
            report.model_dump(mode="json"),
            backend=report.backend,
        )

    return _quality_gate_status(
        report,
        fail_under_entity_recall=args.fail_under_entity_recall,
        fail_under_groundedness=args.fail_under_groundedness,
        fail_on_forbidden=args.fail_on_forbidden,
    )


def _filter_cases(
    cases,
    *,
    eval_ids: set[str],
    categories: set[str],
    max_cases: int | None,
):
    selected = [
        case
        for case in cases
        if (not eval_ids or case.eval_id in eval_ids)
        and (not categories or case.category in categories)
    ]
    if max_cases is not None:
        return selected[: max(0, max_cases)]
    return selected


def _print_summary(report) -> None:
    metrics = report.metrics
    print("RAG evaluation")
    print(f"- backend: {report.backend}")
    print(f"- dataset: {report.dataset_path}")
    print(f"- cases: {metrics.total_cases}")
    print(f"- passed: {metrics.passed_cases}")
    print(f"- pass_rate: {metrics.pass_rate:.3f}")
    print(f"- entity_recall_at_k: {metrics.entity_recall_at_k:.3f}")
    print(f"- entity_precision_at_k: {metrics.entity_precision_at_k:.3f}")
    print(f"- mrr: {metrics.mrr:.3f}")
    print(f"- chunk_kind_recall: {metrics.chunk_kind_recall:.3f}")
    print(f"- groundedness_rate: {metrics.groundedness_rate:.3f}")
    print(f"- caution_success_rate: {metrics.caution_success_rate:.3f}")
    print(f"- forbidden_entity_violations: {metrics.forbidden_entity_violations}")
    print(
        "- forbidden_answer_term_violations: "
        f"{metrics.forbidden_answer_term_violations}"
    )
    print(
        "- latency_ms: "
        f"p50={metrics.latency_p50_ms:.1f} "
        f"p95={metrics.latency_p95_ms:.1f} "
        f"max={metrics.latency_max_ms:.1f}"
    )
    if report.disabled_fallback is not None:
        fallback = report.disabled_fallback
        print(
            "- disabled_fallback: "
            f"{fallback['passed_cases']}/{fallback['total_cases']} "
            f"({fallback['pass_rate']:.3f})"
        )
    failed = [case for case in report.cases if not case.passed][:8]
    if failed:
        print("- sample_failures:")
        for case in failed:
            print(
                f"  - {case.eval_id}: {', '.join(case.failure_reasons)} "
                f"hits={case.expected_entity_hits}"
            )


def _write_report(path: Path, payload: object, *, backend: str) -> Path:
    output_path = _resolve_output_path(path, backend=backend)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if output_path != path:
        print(f"- output_path_was_directory: {path.as_posix()}")
    print(f"- report_written: {output_path.as_posix()}")
    return output_path


def _resolve_output_path(path: Path, *, backend: str) -> Path:
    if path.exists() and path.is_dir():
        return path / f"{backend}_report.json"
    return path


def _quality_gate_status(
    report,
    *,
    fail_under_entity_recall: float | None,
    fail_under_groundedness: float | None,
    fail_on_forbidden: bool,
) -> int:
    metrics = report.metrics
    failed = False
    if (
        fail_under_entity_recall is not None
        and metrics.entity_recall_at_k < fail_under_entity_recall
    ):
        print(
            "- quality_gate: failed "
            f"entity_recall_at_k<{fail_under_entity_recall:.3f}"
        )
        failed = True
    if (
        fail_under_groundedness is not None
        and metrics.groundedness_rate < fail_under_groundedness
    ):
        print(
            "- quality_gate: failed "
            f"groundedness_rate<{fail_under_groundedness:.3f}"
        )
        failed = True
    if fail_on_forbidden and (
        metrics.forbidden_entity_violations
        or metrics.forbidden_answer_term_violations
    ):
        print("- quality_gate: failed forbidden violations")
        failed = True
    if (
        report.disabled_fallback is not None
        and report.disabled_fallback["pass_rate"] < 1.0
    ):
        print("- quality_gate: failed disabled fallback")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
