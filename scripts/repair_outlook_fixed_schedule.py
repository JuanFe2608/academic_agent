#!/usr/bin/env python3

"""Repara en Outlook el horario fijo actual usando la BD como fuente de verdad."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.support.tools.db import get_schedule_service
from services.sync import build_outlook_fixed_schedule_repair_service


def main() -> int:
    args = _build_parser().parse_args()
    schedule_profile_id = args.schedule_profile_id or _resolve_current_schedule_profile_id(
        student_id=args.student_id
    )
    if schedule_profile_id is None:
        print(
            "repair_outlook_fixed_schedule failed",
            "error=current_schedule_profile_not_found",
            "detail=No encontré un horario fijo actual para ese estudiante.",
        )
        return 1

    service = build_outlook_fixed_schedule_repair_service()
    result = service.repair_schedule_profile(
        student_id=args.student_id,
        schedule_profile_id=schedule_profile_id,
        calendar_id=args.calendar_id,
        reconcile_first=not args.skip_reconcile,
    )

    if not result.repaired:
        print(
            "repair_outlook_fixed_schedule failed",
            f"schedule_profile_id={schedule_profile_id}",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "repair_outlook_fixed_schedule ok",
        f"schedule_profile_id={schedule_profile_id}",
        f"repairable={result.repairable_count}",
        f"restored={result.restored_count}",
        f"recreated={result.recreated_count}",
        f"skipped={result.skipped_count}",
        f"events={len(result.synced_event_map)}",
    )
    return 0


def _resolve_current_schedule_profile_id(*, student_id: int) -> int | None:
    lookup = get_schedule_service().get_current_schedule_profile(student_id=student_id)
    if not lookup.found or lookup.profile is None:
        return None
    return int(lookup.profile.id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Restaura Outlook desde el horario fijo interno cuando la reconciliación "
            "detectó drifted o missing."
        ),
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--schedule-profile-id", type=int, default=None)
    parser.add_argument("--calendar-id", default=None)
    parser.add_argument(
        "--skip-reconcile",
        action="store_true",
        help=(
            "No consulta Outlook antes de reparar; usa los estados drifted/missing "
            "que ya estén persistidos en la BD."
        ),
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
