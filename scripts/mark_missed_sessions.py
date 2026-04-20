"""Marca como perdidas las sesiones vencidas sin cierre registrado."""

from __future__ import annotations

import argparse

from services.planning import build_study_session_tracking_service


def main() -> int:
    args = _build_parser().parse_args()
    service = build_study_session_tracking_service()
    result = service.mark_due_sessions_missed(
        student_id=args.student_id,
        as_of=args.as_of,
        grace_minutes=max(0, int(args.grace_minutes)),
        limit=max(1, int(args.limit)),
        actor_type=args.actor_type,
    )

    if not result.processed:
        print(
            "mark_missed_sessions failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "mark_missed_sessions ok",
        f"marked={result.marked_count}",
        f"instance_ids={','.join(str(item) for item in result.instance_ids)}",
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Marca study_plan_event_instances vencidas como missed.",
    )
    parser.add_argument("--student-id", type=int, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--grace-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--actor-type", default="system")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
