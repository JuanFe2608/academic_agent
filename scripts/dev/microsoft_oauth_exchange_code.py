#!/usr/bin/env python3

"""Canjea un authorization code de Microsoft y persiste la conexión."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    build_microsoft_oauth_client_from_env,
)
from bootstrap.settings import database_url_from_env
from repositories.microsoft_graph.state_repository import (
    build_microsoft_graph_state_repository,
)


def main() -> int:
    args = _build_parser().parse_args()
    code = args.code or _extract_code_from_callback_url(args.callback_url)
    if not code:
        print(
            "microsoft_oauth_exchange_code failed",
            "error=missing_authorization_code",
            "detail=Debes enviar --code o --callback-url con un code válido.",
        )
        return 1

    state_repository = build_microsoft_graph_state_repository(database_url_from_env())
    oauth_client = build_microsoft_oauth_client_from_env(
        token_store=MicrosoftGraphStateTokenStore(state_repository)
    )

    result = oauth_client.exchange_authorization_code(
        student_id=args.student_id,
        authorization_code=code,
    )
    if not result.ok or result.token is None:
        print(
            "microsoft_oauth_exchange_code failed",
            f"error={result.error_code}",
            f"detail={result.detail}",
        )
        return 1

    connection = state_repository.get_connection(student_id=args.student_id)
    if connection is None:
        print(
            "microsoft_oauth_exchange_code failed",
            "error=microsoft_connection_not_found",
            "detail=El exchange termino sin persistir microsoft_graph_connections.",
        )
        return 1

    if args.calendar_id or args.todo_task_list_id:
        connection = state_repository.upsert_connection(
            record=replace(
                connection,
                calendar_id=args.calendar_id or connection.calendar_id,
                todo_task_list_id=args.todo_task_list_id or connection.todo_task_list_id,
            )
        )

    print(
        "microsoft_oauth_exchange_code ok",
        f"student_id={connection.student_id}",
        f"email={connection.email or 'n/a'}",
        f"calendar_id={connection.calendar_id or '__default__'}",
        f"todo_task_list_id={connection.todo_task_list_id or 'n/a'}",
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Intercambia el code OAuth de Microsoft y persiste la conexión durable.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code")
    group.add_argument("--callback-url")
    parser.add_argument("--calendar-id", default=None)
    parser.add_argument("--todo-task-list-id", default=None)
    return parser


def _extract_code_from_callback_url(callback_url: str | None) -> str | None:
    normalized = str(callback_url or "").strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    params = parse_qs(parsed.query, keep_blank_values=False)
    values = params.get("code") or []
    if not values:
        return None
    code = str(values[0]).strip()
    return code or None


if __name__ == "__main__":
    raise SystemExit(main())
