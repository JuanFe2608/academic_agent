"""Sincroniza instancias materializadas hacia Outlook Calendar."""

from __future__ import annotations

import argparse

from agents.support.tools.db import get_outlook_calendar_sync_service


def main() -> int:
    args = _build_parser().parse_args()
    service = get_outlook_calendar_sync_service()
    result = service.sync_student_calendar(
        student_id=args.student_id,
        calendar_id=args.calendar_id,
        study_plan_profile_id=args.study_plan_profile_id,
    )

    if not result.synced:
        print(
            "sync_outlook_calendar failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "sync_outlook_calendar ok",
        f"upserted={result.upserted_count}",
        f"deleted={result.deleted_count}",
        f"active_links={len(result.synced_event_map)}",
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza study_plan_event_instances hacia Outlook Calendar.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--calendar-id", default=None)
    parser.add_argument("--study-plan-profile-id", type=int, default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
