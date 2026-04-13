#!/usr/bin/env python3

"""Reconciliación del horario fijo actual contra Outlook Calendar."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.support.tools.db import get_schedule_service
from services.sync import build_outlook_fixed_schedule_reconciliation_service


def main() -> int:
    args = _build_parser().parse_args()
    schedule_profile_id = args.schedule_profile_id or _resolve_current_schedule_profile_id(
        student_id=args.student_id
    )
    if schedule_profile_id is None:
        print(
            "reconcile_outlook_fixed_schedule failed",
            "error=current_schedule_profile_not_found",
            "detail=No encontré un horario fijo actual para ese estudiante.",
        )
        return 1

    service = build_outlook_fixed_schedule_reconciliation_service()
    result = service.reconcile_schedule_profile(
        student_id=args.student_id,
        schedule_profile_id=schedule_profile_id,
        calendar_id=args.calendar_id,
    )

    if not result.reconciled:
        print(
            "reconcile_outlook_fixed_schedule failed",
            f"schedule_profile_id={schedule_profile_id}",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    print(
        "reconcile_outlook_fixed_schedule ok",
        f"schedule_profile_id={schedule_profile_id}",
        f"inspected={result.inspected_count}",
        f"aligned={result.aligned_count}",
        f"drifted={result.drifted_count}",
        f"missing={result.missing_count}",
        f"unsynced={result.unsynced_count}",
        f"errors={result.error_count}",
    )
    for finding in result.findings:
        print(
            "finding",
            f"block_id={finding.block_id}",
            f"status={finding.status}",
            f"event_id={finding.external_event_id or 'n/a'}",
            f"drift_fields={','.join(finding.drift_fields) or 'n/a'}",
            f"detail={finding.detail or 'n/a'}",
        )
    return 0


def _resolve_current_schedule_profile_id(*, student_id: int) -> int | None:
    lookup = get_schedule_service().get_current_schedule_profile(student_id=student_id)
    if not lookup.found or lookup.profile is None:
        return None
    return int(lookup.profile.id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detecta drift manual entre el horario fijo interno y Outlook Calendar.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--schedule-profile-id", type=int, default=None)
    parser.add_argument("--calendar-id", default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
