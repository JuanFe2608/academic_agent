"""Sincroniza sesiones accionables hacia Microsoft To Do."""

from __future__ import annotations

import argparse

from agents.support.tools.db import get_microsoft_todo_sync_service


def main() -> int:
    args = _build_parser().parse_args()
    service = get_microsoft_todo_sync_service()
    result = service.sync_actionable_sessions(
        student_id=args.student_id,
        task_list_id=args.task_list_id,
        study_plan_profile_id=args.study_plan_profile_id,
    )

    if not result.synced:
        print(
            "sync_microsoft_todo failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "sync_microsoft_todo ok",
        f"upserted={result.upserted_count}",
        f"deleted={result.deleted_count}",
        f"active_links={len(result.synced_task_map)}",
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza sesiones missed/skipped hacia Microsoft To Do.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--task-list-id", default=None)
    parser.add_argument("--study-plan-profile-id", type=int, default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
