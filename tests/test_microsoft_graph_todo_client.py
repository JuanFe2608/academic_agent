"""Pruebas del cliente Microsoft To Do sobre Microsoft Graph."""

from __future__ import annotations

from integrations.microsoft_graph._clients_impl import GraphMicrosoftTodoClient


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert access_token == "token-123"
        self.calls.append((method, url, json_payload))
        return {
            "value": [
                {
                    "id": "todo-1",
                    "title": "[tarea] Fisica: Tarea 1",
                    "dueDateTime": {
                        "dateTime": "2026-05-02T23:59:00.0000000",
                        "timeZone": "UTC",
                    },
                    "status": "completed",
                    "importance": "high",
                    "lastModifiedDateTime": {
                        "dateTime": "2026-05-01T15:30:00Z",
                        "timeZone": "UTC",
                    },
                    "webLink": "https://to-do.office.com/tasks/todo-1",
                }
            ]
        }

    def request_no_content(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_payload: dict[str, object] | None = None,
    ) -> None:
        raise AssertionError("delete no esperado en esta prueba")


def test_graph_microsoft_todo_client_reads_existing_task_snapshots() -> None:
    transport = _FakeTransport()
    client = GraphMicrosoftTodoClient(transport=transport)

    snapshots = client.list_tasks(
        access_token="token-123",
        task_list_id="todo-list-1",
    )

    assert len(snapshots) == 1
    assert snapshots[0].external_task_id == "todo-1"
    assert snapshots[0].title == "[tarea] Fisica: Tarea 1"
    assert snapshots[0].is_completed is True
    assert snapshots[0].importance == "high"
    assert snapshots[0].due_at is not None
    assert snapshots[0].due_at.date().isoformat() == "2026-05-02"
    assert snapshots[0].web_link == "https://to-do.office.com/tasks/todo-1"
    assert transport.calls[0][0] == "GET"
    assert "/me/todo/lists/todo-list-1/tasks" in transport.calls[0][1]
