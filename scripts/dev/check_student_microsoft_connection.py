#!/usr/bin/env python3

"""Diagnostica la conexión Microsoft Graph de un estudiante."""

from __future__ import annotations

import argparse

from _db_check_helpers import open_connection, print_kv_rows, print_section, require_student_exists


def main() -> int:
    args = _build_parser().parse_args()

    with open_connection() as conn:
        student = require_student_exists(conn, student_id=args.student_id)
        connection = conn.execute(
            """
            SELECT
                mgc.student_id,
                mgc.tenant_id,
                mgc.microsoft_user_id,
                mgc.user_principal_name,
                mgc.email,
                mgc.display_name,
                COALESCE(mgc.calendar_id, '__default__') AS calendar_id,
                mgc.todo_task_list_id,
                mgc.token_type,
                mgc.expires_at,
                (mgc.refresh_token IS NOT NULL) AS has_refresh_token,
                jsonb_array_length(mgc.scopes_json) AS scope_count,
                CASE
                    WHEN mgc.id IS NULL THEN 'missing'
                    WHEN mgc.expires_at IS NOT NULL AND mgc.expires_at <= NOW() THEN 'expired'
                    ELSE 'ok'
                END AS connection_status,
                mgc.created_at,
                mgc.updated_at
            FROM microsoft_graph_connections AS mgc
            WHERE mgc.student_id = %s
            """,
            (args.student_id,),
        ).fetchone()
        scopes = conn.execute(
            """
            SELECT jsonb_array_elements_text(scopes_json) AS scope
            FROM microsoft_graph_connections
            WHERE student_id = %s
            """,
            (args.student_id,),
        ).fetchall()

    print_section("Estudiante")
    print_kv_rows([dict(student)])

    print_section("Conexion Microsoft")
    print_kv_rows([dict(connection)] if connection is not None else [])

    print_section("Scopes")
    print_kv_rows([dict(row) for row in scopes])

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida la conexión Microsoft Graph persistida para un estudiante.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
