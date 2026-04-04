"""Canjea un authorization code de Microsoft y persiste la conexión."""

from __future__ import annotations

import argparse
from dataclasses import replace

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    build_microsoft_oauth_client_from_env,
)
from agents.support.tools.db_config import database_url_from_env
from agents.support.tools.microsoft_graph_state_repository import (
    build_microsoft_graph_state_repository,
)


def main() -> int:
    args = _build_parser().parse_args()
    state_repository = build_microsoft_graph_state_repository(database_url_from_env())
    oauth_client = build_microsoft_oauth_client_from_env(
        token_store=MicrosoftGraphStateTokenStore(state_repository)
    )

    result = oauth_client.exchange_authorization_code(
        student_id=args.student_id,
        authorization_code=args.code,
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
    parser.add_argument("--code", required=True)
    parser.add_argument("--calendar-id", default=None)
    parser.add_argument("--todo-task-list-id", default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
