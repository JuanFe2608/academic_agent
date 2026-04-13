#!/usr/bin/env python3

"""Sincroniza el horario fijo recurrente hacia Outlook Calendar."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.support.tools.db import (
    get_outlook_fixed_schedule_sync_service,
    get_schedule_service,
)


def main() -> int:
    args = _build_parser().parse_args()
    schedule_profile_id = args.schedule_profile_id or _resolve_current_schedule_profile_id(
        student_id=args.student_id
    )
    if schedule_profile_id is None:
        print(
            "sync_outlook_fixed_schedule failed",
            "error=current_schedule_profile_not_found",
            "detail=No encontré un horario fijo actual para ese estudiante.",
        )
        return 1

    service = get_outlook_fixed_schedule_sync_service()
    result = service.sync_schedule_profile(
        student_id=args.student_id,
        schedule_profile_id=schedule_profile_id,
        calendar_id=args.calendar_id,
    )

    if not result.synced:
        print(
            "sync_outlook_fixed_schedule failed",
            f"schedule_profile_id={schedule_profile_id}",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "sync_outlook_fixed_schedule ok",
        f"schedule_profile_id={schedule_profile_id}",
        f"upserted={result.upserted_count}",
        f"deleted={result.deleted_count}",
        f"active_links={len(result.synced_event_map)}",
    )
    return 0


def _resolve_current_schedule_profile_id(*, student_id: int) -> int | None:
    schedule_service = get_schedule_service()
    repository = getattr(schedule_service, "repository", None)
    if repository is None or not hasattr(repository, "list_student_schedule_blocks"):
        return None

    blocks = repository.list_student_schedule_blocks(
        student_id=student_id,
        only_current_profile=True,
    )
    if not blocks:
        return None
    return int(blocks[0].schedule_profile_id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza el horario fijo confirmado hacia Outlook Calendar.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--schedule-profile-id", type=int, default=None)
    parser.add_argument("--calendar-id", default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
