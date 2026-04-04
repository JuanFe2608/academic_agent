"""Pruebas basicas para la persistencia de hilos de LangGraph."""

from __future__ import annotations

import pytest

from integrations.langgraph.checkpointer import (
    PostgresLangGraphCheckpointer,
    _assert_schema_ready,
    checkpoint_database_url_from_env,
    create_checkpointer,
)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):  # noqa: ARG002
        return None

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._rows)


def test_checkpoint_database_url_prefers_langgraph_specific_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "LANGGRAPH_CHECKPOINTER_DATABASE_URL",
        "postgresql://checkpoint:secret@localhost:5432/checkpoints",
    )
    monkeypatch.setenv(
        "ACADEMIC_AGENT_DATABASE_URL",
        "postgresql://app:secret@localhost:5432/appdb",
    )

    assert (
        checkpoint_database_url_from_env()
        == "postgresql://checkpoint:secret@localhost:5432/checkpoints"
    )


def test_checkpoint_database_url_falls_back_to_application_database(monkeypatch) -> None:
    monkeypatch.delenv("LANGGRAPH_CHECKPOINTER_DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URI", raising=False)
    monkeypatch.setenv(
        "ACADEMIC_AGENT_DATABASE_URL",
        "postgresql://app:secret@localhost:5432/academic_agent_db",
    )

    assert (
        checkpoint_database_url_from_env()
        == "postgresql://app:secret@localhost:5432/academic_agent_db"
    )


def test_assert_schema_ready_raises_when_tables_are_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.langgraph.checkpointer.connect",
        lambda *args, **kwargs: _FakeConnection(
            [{"table_name": "langgraph_thread_checkpoints"}]
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        _assert_schema_ready("postgresql://ignored")

    assert "migrations/0003_langgraph_thread_persistence.sql" in str(exc.value)


def test_create_checkpointer_builds_instance_when_schema_is_ready(monkeypatch) -> None:
    monkeypatch.setenv(
        "ACADEMIC_AGENT_DATABASE_URL",
        "postgresql://app:secret@localhost:5432/academic_agent_db",
    )
    monkeypatch.delenv("LANGGRAPH_CHECKPOINTER_DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URI", raising=False)
    monkeypatch.setattr(
        "integrations.langgraph.checkpointer.connect",
        lambda *args, **kwargs: _FakeConnection(
            [
                {"table_name": "langgraph_checkpoint_writes"},
                {"table_name": "langgraph_thread_checkpoints"},
            ]
        ),
    )

    checkpointer = create_checkpointer()

    assert isinstance(checkpointer, PostgresLangGraphCheckpointer)
    assert (
        checkpointer.database_url
        == "postgresql://app:secret@localhost:5432/academic_agent_db"
    )
