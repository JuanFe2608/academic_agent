"""Tests del repositorio de estado Microsoft Graph."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from repositories.microsoft_graph.state_repository import PostgresMicrosoftGraphStateRepository


class _FakeResult:
    def fetchone(self) -> None:
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...]) -> _FakeResult:
        self.calls.append((sql, params))
        return _FakeResult()


def test_find_connection_by_microsoft_identity_casts_nullable_user_id_as_text() -> None:
    repository = PostgresMicrosoftGraphStateRepository("postgresql://example")
    connection = _FakeConnection()

    @contextmanager
    def fake_connect() -> Iterator[_FakeConnection]:
        yield connection

    repository._connect = fake_connect  # type: ignore[method-assign]

    result = repository.find_connection_by_microsoft_identity(
        microsoft_user_id=None,
        account_identifiers=("Student@Example.edu",),
        exclude_student_id=7,
    )

    assert result is None
    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert "%s::text IS NOT NULL" in sql
    assert "lower(microsoft_user_id) = %s::text" in sql
    assert params == (7, None, None, ["student@example.edu"], ["student@example.edu"])
