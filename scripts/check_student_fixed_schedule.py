#!/usr/bin/env python3

"""Diagnostica la persistencia del horario fijo actual de un estudiante."""

from __future__ import annotations

import argparse

from _db_check_helpers import open_connection, print_kv_rows, print_section, require_student_exists


def main() -> int:
    args = _build_parser().parse_args()

    with open_connection() as conn:
        student = require_student_exists(conn, student_id=args.student_id)
        profiles = conn.execute(
            """
            SELECT
                sp.id AS schedule_profile_id,
                sp.version_number,
                sp.occupation,
                sp.base_timezone,
                sp.summary_text,
                sp.has_conflicts,
                sp.conflicts_accepted,
                sp.confirmed_by_user,
                sp.confirmed_at,
                sp.schedule_end_date,
                sp.is_current,
                sp.is_active,
                (
                    SELECT COUNT(*)
                    FROM recurring_schedule_blocks AS rsb
                    WHERE rsb.schedule_profile_id = sp.id
                ) AS block_count,
                (
                    SELECT COUNT(*)
                    FROM schedule_conflicts AS sc
                    WHERE sc.schedule_profile_id = sp.id
                ) AS conflict_count,
                sp.created_at,
                sp.updated_at
            FROM schedule_profiles AS sp
            WHERE sp.student_id = %s
            ORDER BY sp.version_number DESC
            """,
            (args.student_id,),
        ).fetchall()
        current_blocks = conn.execute(
            """
            SELECT
                rsb.id AS recurring_block_id,
                rsb.schedule_profile_id,
                rsb.source_block_id,
                rsb.block_type,
                rsb.title,
                rsb.day_of_week,
                rsb.start_time,
                rsb.end_time,
                rsb.frequency,
                rsb.timezone,
                sp.schedule_end_date,
                rsb.confirmed_by_user,
                rsb.has_conflict,
                rsb.conflict_accepted,
                rsb.external_provider,
                rsb.external_sync_status,
                rsb.created_at,
                rsb.updated_at
            FROM recurring_schedule_blocks AS rsb
            JOIN schedule_profiles AS sp
                ON sp.id = rsb.schedule_profile_id
            WHERE sp.student_id = %s
              AND sp.is_current = TRUE
            ORDER BY rsb.day_of_week, rsb.start_time, rsb.id
            """,
            (args.student_id,),
        ).fetchall()

    print_section("Estudiante")
    print_kv_rows([dict(student)])

    print_section("Historial De Schedule Profiles")
    print_kv_rows([dict(row) for row in profiles])

    print_section("Bloques Del Horario Actual")
    print_kv_rows([dict(row) for row in current_blocks])

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida el horario fijo persistido de un estudiante.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
