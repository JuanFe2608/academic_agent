#!/usr/bin/env python3

"""Diagnostica el estado del sync del horario fijo actual hacia Outlook."""

from __future__ import annotations

import argparse

from _db_check_helpers import open_connection, print_kv_rows, print_section, require_student_exists


def main() -> int:
    args = _build_parser().parse_args()

    with open_connection() as conn:
        student = require_student_exists(conn, student_id=args.student_id)
        summary = conn.execute(
            """
            WITH current_profile AS (
                SELECT id, version_number, schedule_end_date
                FROM schedule_profiles
                WHERE student_id = %s
                  AND is_current = TRUE
                ORDER BY version_number DESC
                LIMIT 1
            )
            SELECT
                cp.id AS schedule_profile_id,
                cp.version_number,
                cp.schedule_end_date,
                COUNT(rsb.id) AS total_blocks,
                COUNT(*) FILTER (WHERE rsb.external_provider = 'outlook') AS outlook_blocks,
                COUNT(*) FILTER (WHERE rsb.external_sync_status = 'active') AS active_synced_blocks,
                COUNT(*) FILTER (WHERE rsb.external_sync_status = 'deleted') AS deleted_blocks,
                COUNT(*) FILTER (WHERE rsb.external_event_id IS NULL) AS blocks_without_external_event_id,
                COUNT(*) FILTER (
                    WHERE COALESCE(rsb.external_sync_metadata->>'calendar_id', '') <> ''
                ) AS blocks_with_calendar_metadata
            FROM current_profile AS cp
            LEFT JOIN recurring_schedule_blocks AS rsb
                ON rsb.schedule_profile_id = cp.id
            GROUP BY cp.id, cp.version_number, cp.schedule_end_date
            """,
            (args.student_id,),
        ).fetchone()
        current_blocks = conn.execute(
            """
            SELECT
                sp.version_number,
                rsb.id AS recurring_block_id,
                rsb.title,
                rsb.block_type,
                rsb.day_of_week,
                rsb.start_time,
                rsb.end_time,
                sp.schedule_end_date,
                rsb.external_provider,
                rsb.external_series_id,
                rsb.external_event_id,
                rsb.external_sync_status,
                COALESCE(rsb.external_sync_metadata->>'calendar_id', '(null)') AS metadata_calendar_id,
                COALESCE(rsb.external_sync_metadata->>'series_start_date', '(null)') AS series_start_date,
                COALESCE(rsb.external_sync_metadata->>'synced_at', '(null)') AS synced_at,
                COALESCE(rsb.external_sync_metadata->>'deleted_at', '(null)') AS deleted_at
            FROM recurring_schedule_blocks AS rsb
            JOIN schedule_profiles AS sp
                ON sp.id = rsb.schedule_profile_id
            WHERE sp.student_id = %s
              AND sp.is_current = TRUE
            ORDER BY rsb.day_of_week, rsb.start_time, rsb.id
            """,
            (args.student_id,),
        ).fetchall()
        previous_synced_blocks = conn.execute(
            """
            SELECT
                sp.version_number,
                rsb.id AS recurring_block_id,
                rsb.title,
                rsb.day_of_week,
                rsb.start_time,
                rsb.end_time,
                rsb.external_event_id,
                rsb.external_sync_status,
                COALESCE(rsb.external_sync_metadata->>'deleted_at', '(null)') AS deleted_at
            FROM recurring_schedule_blocks AS rsb
            JOIN schedule_profiles AS sp
                ON sp.id = rsb.schedule_profile_id
            WHERE sp.student_id = %s
              AND sp.is_current = FALSE
              AND rsb.external_provider = 'outlook'
            ORDER BY sp.version_number DESC, rsb.day_of_week, rsb.start_time, rsb.id
            LIMIT 50
            """,
            (args.student_id,),
        ).fetchall()

    print_section("Estudiante")
    print_kv_rows([dict(student)])

    print_section("Resumen Del Sync Del Horario Actual")
    print_kv_rows([dict(summary)] if summary is not None else [])

    print_section("Bloques Actuales Y Estado De Sync")
    print_kv_rows([dict(row) for row in current_blocks])

    print_section("Bloques De Versiones Anteriores Con Metadata Outlook")
    print_kv_rows([dict(row) for row in previous_synced_blocks])

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida el estado del sync del horario fijo actual hacia Outlook.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
