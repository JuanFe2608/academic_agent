"""Persistencia durable para conexiones y estado de sync Microsoft Graph."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Iterator, Protocol

from agents.support.onboarding.repository import RepositoryConfigurationError


class MicrosoftGraphStateRepositoryError(Exception):
    """Error base del repositorio de estado Microsoft Graph."""


@dataclass(frozen=True)
class MicrosoftGraphConnectionRecord:
    """Conexión OAuth y defaults operativos de un estudiante."""

    student_id: int
    tenant_id: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: tuple[str, ...]
    token_type: str = "Bearer"
    calendar_id: str | None = None
    todo_task_list_id: str | None = None
    microsoft_user_id: str | None = None
    user_principal_name: str | None = None
    email: str | None = None
    display_name: str | None = None
    auth_metadata: dict[str, object] = field(default_factory=dict)
    id: int | None = None


@dataclass(frozen=True)
class OutlookCalendarEventLinkRecord:
    """Link durable entre instancia interna y evento externo de Outlook."""

    student_id: int
    source_instance_key: str
    calendar_id: str
    external_event_id: str
    study_plan_event_instance_id: int | None = None
    external_change_key: str | None = None
    sync_status: str = "active"
    last_error: str | None = None
    last_synced_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class MicrosoftTodoTaskLinkRecord:
    """Link durable entre instancia interna y tarea externa de To Do."""

    student_id: int
    source_instance_key: str
    task_list_id: str
    external_task_id: str
    study_plan_event_instance_id: int | None = None
    sync_status: str = "active"
    last_error: str | None = None
    last_synced_at: datetime | None = None
    id: int | None = None


class MicrosoftGraphStateRepository(Protocol):
    """Contrato para conexiones, links y datos de contacto."""

    def get_connection(
        self,
        *,
        student_id: int,
    ) -> MicrosoftGraphConnectionRecord | None: ...

    def upsert_connection(
        self,
        *,
        record: MicrosoftGraphConnectionRecord,
    ) -> MicrosoftGraphConnectionRecord: ...

    def delete_connection(self, *, student_id: int) -> None: ...

    def list_calendar_event_links(
        self,
        *,
        student_id: int,
        calendar_id: str | None = None,
    ) -> list[OutlookCalendarEventLinkRecord]: ...

    def upsert_calendar_event_links(
        self,
        *,
        links: list[OutlookCalendarEventLinkRecord],
    ) -> list[OutlookCalendarEventLinkRecord]: ...

    def mark_calendar_event_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int: ...

    def list_todo_task_links(
        self,
        *,
        student_id: int,
        task_list_id: str | None = None,
    ) -> list[MicrosoftTodoTaskLinkRecord]: ...

    def upsert_todo_task_links(
        self,
        *,
        links: list[MicrosoftTodoTaskLinkRecord],
    ) -> list[MicrosoftTodoTaskLinkRecord]: ...

    def mark_todo_task_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int: ...

    def get_student_institutional_email(
        self,
        *,
        student_id: int,
    ) -> str | None: ...


class InMemoryMicrosoftGraphStateRepository:
    """Repositorio en memoria para pruebas de integración Microsoft."""

    def __init__(self) -> None:
        self._connections: dict[int, MicrosoftGraphConnectionRecord] = {}
        self._calendar_links: dict[tuple[int, str], OutlookCalendarEventLinkRecord] = {}
        self._todo_links: dict[tuple[int, str], MicrosoftTodoTaskLinkRecord] = {}
        self._student_emails: dict[int, str] = {}
        self._next_connection_id = 1
        self._next_calendar_link_id = 1
        self._next_todo_link_id = 1

    def get_connection(
        self,
        *,
        student_id: int,
    ) -> MicrosoftGraphConnectionRecord | None:
        return self._connections.get(student_id)

    def upsert_connection(
        self,
        *,
        record: MicrosoftGraphConnectionRecord,
    ) -> MicrosoftGraphConnectionRecord:
        existing = self._connections.get(record.student_id)
        record_id = existing.id if existing and existing.id is not None else self._next_connection_id
        if existing is None or existing.id is None:
            self._next_connection_id += 1
        stored = record if record.id is not None else replace(record, id=record_id)
        self._connections[record.student_id] = stored
        return stored

    def delete_connection(self, *, student_id: int) -> None:
        self._connections.pop(student_id, None)

    def list_calendar_event_links(
        self,
        *,
        student_id: int,
        calendar_id: str | None = None,
    ) -> list[OutlookCalendarEventLinkRecord]:
        records = [
            record
            for (candidate_student_id, _), record in self._calendar_links.items()
            if candidate_student_id == student_id
            and record.sync_status == "active"
            and (calendar_id is None or record.calendar_id == calendar_id)
        ]
        records.sort(key=lambda item: (item.source_instance_key, item.external_event_id))
        return records

    def upsert_calendar_event_links(
        self,
        *,
        links: list[OutlookCalendarEventLinkRecord],
    ) -> list[OutlookCalendarEventLinkRecord]:
        stored: list[OutlookCalendarEventLinkRecord] = []
        for link in links:
            key = (link.student_id, link.source_instance_key)
            existing = self._calendar_links.get(key)
            link_id = existing.id if existing and existing.id is not None else self._next_calendar_link_id
            if existing is None or existing.id is None:
                self._next_calendar_link_id += 1
            persisted = link if link.id is not None else replace(link, id=link_id)
            self._calendar_links[key] = persisted
            stored.append(persisted)
        return stored

    def mark_calendar_event_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int:
        marked = 0
        for source_instance_key in source_instance_keys:
            key = (student_id, source_instance_key)
            existing = self._calendar_links.get(key)
            if existing is None or existing.sync_status == "deleted":
                continue
            self._calendar_links[key] = replace(existing, sync_status="deleted")
            marked += 1
        return marked

    def list_todo_task_links(
        self,
        *,
        student_id: int,
        task_list_id: str | None = None,
    ) -> list[MicrosoftTodoTaskLinkRecord]:
        records = [
            record
            for (candidate_student_id, _), record in self._todo_links.items()
            if candidate_student_id == student_id
            and record.sync_status == "active"
            and (task_list_id is None or record.task_list_id == task_list_id)
        ]
        records.sort(key=lambda item: (item.source_instance_key, item.external_task_id))
        return records

    def upsert_todo_task_links(
        self,
        *,
        links: list[MicrosoftTodoTaskLinkRecord],
    ) -> list[MicrosoftTodoTaskLinkRecord]:
        stored: list[MicrosoftTodoTaskLinkRecord] = []
        for link in links:
            key = (link.student_id, link.source_instance_key)
            existing = self._todo_links.get(key)
            link_id = existing.id if existing and existing.id is not None else self._next_todo_link_id
            if existing is None or existing.id is None:
                self._next_todo_link_id += 1
            persisted = link if link.id is not None else replace(link, id=link_id)
            self._todo_links[key] = persisted
            stored.append(persisted)
        return stored

    def mark_todo_task_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int:
        marked = 0
        for source_instance_key in source_instance_keys:
            key = (student_id, source_instance_key)
            existing = self._todo_links.get(key)
            if existing is None or existing.sync_status == "deleted":
                continue
            self._todo_links[key] = replace(existing, sync_status="deleted")
            marked += 1
        return marked

    def get_student_institutional_email(
        self,
        *,
        student_id: int,
    ) -> str | None:
        return self._student_emails.get(student_id)

    def set_student_institutional_email(self, *, student_id: int, email: str) -> None:
        self._student_emails[student_id] = email


class PostgresMicrosoftGraphStateRepository:
    """Repositorio PostgreSQL para credenciales y links externos."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_connection(
        self,
        *,
        student_id: int,
    ) -> MicrosoftGraphConnectionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    tenant_id,
                    microsoft_user_id,
                    user_principal_name,
                    email,
                    display_name,
                    access_token,
                    refresh_token,
                    token_type,
                    scopes_json,
                    expires_at,
                    calendar_id,
                    todo_task_list_id,
                    auth_metadata
                FROM microsoft_graph_connections
                WHERE student_id = %s
                """,
                (student_id,),
            ).fetchone()
        return _connection_from_row(row) if row is not None else None

    def upsert_connection(
        self,
        *,
        record: MicrosoftGraphConnectionRecord,
    ) -> MicrosoftGraphConnectionRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO microsoft_graph_connections (
                    student_id,
                    tenant_id,
                    microsoft_user_id,
                    user_principal_name,
                    email,
                    display_name,
                    access_token,
                    refresh_token,
                    token_type,
                    scopes_json,
                    expires_at,
                    calendar_id,
                    todo_task_list_id,
                    auth_metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (student_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    microsoft_user_id = EXCLUDED.microsoft_user_id,
                    user_principal_name = EXCLUDED.user_principal_name,
                    email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    token_type = EXCLUDED.token_type,
                    scopes_json = EXCLUDED.scopes_json,
                    expires_at = EXCLUDED.expires_at,
                    calendar_id = COALESCE(EXCLUDED.calendar_id, microsoft_graph_connections.calendar_id),
                    todo_task_list_id = COALESCE(EXCLUDED.todo_task_list_id, microsoft_graph_connections.todo_task_list_id),
                    auth_metadata = EXCLUDED.auth_metadata,
                    updated_at = NOW()
                RETURNING
                    id,
                    student_id,
                    tenant_id,
                    microsoft_user_id,
                    user_principal_name,
                    email,
                    display_name,
                    access_token,
                    refresh_token,
                    token_type,
                    scopes_json,
                    expires_at,
                    calendar_id,
                    todo_task_list_id,
                    auth_metadata
                """,
                (
                    record.student_id,
                    record.tenant_id,
                    record.microsoft_user_id,
                    record.user_principal_name,
                    record.email,
                    record.display_name,
                    record.access_token,
                    record.refresh_token,
                    record.token_type,
                    json.dumps(list(record.scopes)),
                    record.expires_at,
                    record.calendar_id,
                    record.todo_task_list_id,
                    json.dumps(record.auth_metadata),
                ),
            ).fetchone()
            conn.commit()
        return _connection_from_row(row)

    def delete_connection(self, *, student_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM microsoft_graph_connections WHERE student_id = %s",
                (student_id,),
            )
            conn.commit()

    def list_calendar_event_links(
        self,
        *,
        student_id: int,
        calendar_id: str | None = None,
    ) -> list[OutlookCalendarEventLinkRecord]:
        filters = ["student_id = %s", "sync_status = 'active'"]
        params: list[object] = [student_id]
        if calendar_id is not None:
            filters.append("calendar_id = %s")
            params.append(calendar_id)
        query = f"""
            SELECT
                id,
                student_id,
                study_plan_event_instance_id,
                source_instance_key,
                calendar_id,
                external_event_id,
                external_change_key,
                sync_status,
                last_error,
                last_synced_at
            FROM outlook_calendar_event_links
            WHERE {' AND '.join(filters)}
            ORDER BY source_instance_key
        """
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_calendar_link_from_row(row) for row in rows]

    def upsert_calendar_event_links(
        self,
        *,
        links: list[OutlookCalendarEventLinkRecord],
    ) -> list[OutlookCalendarEventLinkRecord]:
        stored: list[OutlookCalendarEventLinkRecord] = []
        if not links:
            return stored
        with self._connect() as conn:
            for link in links:
                connection_id = _connection_id_for_student(conn, link.student_id)
                row = conn.execute(
                    """
                    INSERT INTO outlook_calendar_event_links (
                        student_id,
                        microsoft_graph_connection_id,
                        study_plan_event_instance_id,
                        source_instance_key,
                        calendar_id,
                        external_event_id,
                        external_change_key,
                        sync_status,
                        last_error,
                        last_synced_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW())
                    )
                    ON CONFLICT (student_id, source_instance_key) DO UPDATE SET
                        microsoft_graph_connection_id = EXCLUDED.microsoft_graph_connection_id,
                        study_plan_event_instance_id = EXCLUDED.study_plan_event_instance_id,
                        calendar_id = EXCLUDED.calendar_id,
                        external_event_id = EXCLUDED.external_event_id,
                        external_change_key = EXCLUDED.external_change_key,
                        sync_status = EXCLUDED.sync_status,
                        last_error = EXCLUDED.last_error,
                        last_synced_at = COALESCE(EXCLUDED.last_synced_at, NOW()),
                        updated_at = NOW()
                    RETURNING
                        id,
                        student_id,
                        study_plan_event_instance_id,
                        source_instance_key,
                        calendar_id,
                        external_event_id,
                        external_change_key,
                        sync_status,
                        last_error,
                        last_synced_at
                    """,
                    (
                        link.student_id,
                        connection_id,
                        link.study_plan_event_instance_id,
                        link.source_instance_key,
                        link.calendar_id,
                        link.external_event_id,
                        link.external_change_key,
                        link.sync_status,
                        link.last_error,
                        link.last_synced_at,
                    ),
                ).fetchone()
                stored.append(_calendar_link_from_row(row))
            conn.commit()
        return stored

    def mark_calendar_event_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int:
        if not source_instance_keys:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                """
                WITH updated AS (
                    UPDATE outlook_calendar_event_links
                    SET sync_status = 'deleted',
                        last_error = NULL,
                        last_synced_at = NOW(),
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND source_instance_key = ANY(%s)
                      AND sync_status <> 'deleted'
                    RETURNING id
                )
                SELECT COUNT(*) AS total FROM updated
                """,
                (student_id, list(source_instance_keys)),
            ).fetchone()
            conn.commit()
        return int(_row_value(row, "total", 0))

    def list_todo_task_links(
        self,
        *,
        student_id: int,
        task_list_id: str | None = None,
    ) -> list[MicrosoftTodoTaskLinkRecord]:
        filters = ["student_id = %s", "sync_status = 'active'"]
        params: list[object] = [student_id]
        if task_list_id is not None:
            filters.append("task_list_id = %s")
            params.append(task_list_id)
        query = f"""
            SELECT
                id,
                student_id,
                study_plan_event_instance_id,
                source_instance_key,
                task_list_id,
                external_task_id,
                sync_status,
                last_error,
                last_synced_at
            FROM microsoft_todo_task_links
            WHERE {' AND '.join(filters)}
            ORDER BY source_instance_key
        """
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_todo_link_from_row(row) for row in rows]

    def upsert_todo_task_links(
        self,
        *,
        links: list[MicrosoftTodoTaskLinkRecord],
    ) -> list[MicrosoftTodoTaskLinkRecord]:
        stored: list[MicrosoftTodoTaskLinkRecord] = []
        if not links:
            return stored
        with self._connect() as conn:
            for link in links:
                connection_id = _connection_id_for_student(conn, link.student_id)
                row = conn.execute(
                    """
                    INSERT INTO microsoft_todo_task_links (
                        student_id,
                        microsoft_graph_connection_id,
                        study_plan_event_instance_id,
                        source_instance_key,
                        task_list_id,
                        external_task_id,
                        sync_status,
                        last_error,
                        last_synced_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW())
                    )
                    ON CONFLICT (student_id, source_instance_key) DO UPDATE SET
                        microsoft_graph_connection_id = EXCLUDED.microsoft_graph_connection_id,
                        study_plan_event_instance_id = EXCLUDED.study_plan_event_instance_id,
                        task_list_id = EXCLUDED.task_list_id,
                        external_task_id = EXCLUDED.external_task_id,
                        sync_status = EXCLUDED.sync_status,
                        last_error = EXCLUDED.last_error,
                        last_synced_at = COALESCE(EXCLUDED.last_synced_at, NOW()),
                        updated_at = NOW()
                    RETURNING
                        id,
                        student_id,
                        study_plan_event_instance_id,
                        source_instance_key,
                        task_list_id,
                        external_task_id,
                        sync_status,
                        last_error,
                        last_synced_at
                    """,
                    (
                        link.student_id,
                        connection_id,
                        link.study_plan_event_instance_id,
                        link.source_instance_key,
                        link.task_list_id,
                        link.external_task_id,
                        link.sync_status,
                        link.last_error,
                        link.last_synced_at,
                    ),
                ).fetchone()
                stored.append(_todo_link_from_row(row))
            conn.commit()
        return stored

    def mark_todo_task_links_deleted(
        self,
        *,
        student_id: int,
        source_instance_keys: list[str],
    ) -> int:
        if not source_instance_keys:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                """
                WITH updated AS (
                    UPDATE microsoft_todo_task_links
                    SET sync_status = 'deleted',
                        last_error = NULL,
                        last_synced_at = NOW(),
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND source_instance_key = ANY(%s)
                      AND sync_status <> 'deleted'
                    RETURNING id
                )
                SELECT COUNT(*) AS total FROM updated
                """,
                (student_id, list(source_instance_keys)),
            ).fetchone()
            conn.commit()
        return int(_row_value(row, "total", 0))

    def get_student_institutional_email(
        self,
        *,
        student_id: int,
    ) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT institutional_email
                FROM students
                WHERE id = %s
                """,
                (student_id,),
            ).fetchone()
        return str(_row_value(row, "institutional_email")) if row else None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        psycopg, dict_row = _load_psycopg()
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
                yield conn
        except ImportError as exc:
            raise RepositoryConfigurationError(
                "psycopg no esta instalado; no pude conectar PostgreSQL."
            ) from exc
        except Exception as exc:  # pragma: no cover
            raise MicrosoftGraphStateRepositoryError(str(exc)) from exc


def build_microsoft_graph_state_repository(
    database_url: str,
) -> MicrosoftGraphStateRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return PostgresMicrosoftGraphStateRepository(database_url)


def _connection_from_row(row: Any) -> MicrosoftGraphConnectionRecord:
    return MicrosoftGraphConnectionRecord(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        tenant_id=str(_row_value(row, "tenant_id")),
        microsoft_user_id=_optional_str(_row_value(row, "microsoft_user_id")),
        user_principal_name=_optional_str(_row_value(row, "user_principal_name")),
        email=_optional_str(_row_value(row, "email")),
        display_name=_optional_str(_row_value(row, "display_name")),
        access_token=str(_row_value(row, "access_token")),
        refresh_token=_optional_str(_row_value(row, "refresh_token")),
        token_type=str(_row_value(row, "token_type")),
        scopes=tuple(str(item) for item in (_row_value(row, "scopes_json") or [])),
        expires_at=_row_value(row, "expires_at"),
        calendar_id=_optional_str(_row_value(row, "calendar_id")),
        todo_task_list_id=_optional_str(_row_value(row, "todo_task_list_id")),
        auth_metadata=dict(_row_value(row, "auth_metadata") or {}),
    )


def _calendar_link_from_row(row: Any) -> OutlookCalendarEventLinkRecord:
    return OutlookCalendarEventLinkRecord(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        study_plan_event_instance_id=(
            int(_row_value(row, "study_plan_event_instance_id"))
            if _row_value(row, "study_plan_event_instance_id") is not None
            else None
        ),
        source_instance_key=str(_row_value(row, "source_instance_key")),
        calendar_id=str(_row_value(row, "calendar_id")),
        external_event_id=str(_row_value(row, "external_event_id")),
        external_change_key=_optional_str(_row_value(row, "external_change_key")),
        sync_status=str(_row_value(row, "sync_status")),
        last_error=_optional_str(_row_value(row, "last_error")),
        last_synced_at=_row_value(row, "last_synced_at"),
    )


def _todo_link_from_row(row: Any) -> MicrosoftTodoTaskLinkRecord:
    return MicrosoftTodoTaskLinkRecord(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        study_plan_event_instance_id=(
            int(_row_value(row, "study_plan_event_instance_id"))
            if _row_value(row, "study_plan_event_instance_id") is not None
            else None
        ),
        source_instance_key=str(_row_value(row, "source_instance_key")),
        task_list_id=str(_row_value(row, "task_list_id")),
        external_task_id=str(_row_value(row, "external_task_id")),
        sync_status=str(_row_value(row, "sync_status")),
        last_error=_optional_str(_row_value(row, "last_error")),
        last_synced_at=_row_value(row, "last_synced_at"),
    )


def _connection_id_for_student(conn: Any, student_id: int) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM microsoft_graph_connections
        WHERE student_id = %s
        """,
        (student_id,),
    ).fetchone()
    if row is None:
        raise MicrosoftGraphStateRepositoryError(
            f"No encontré microsoft_graph_connections para student_id={student_id}."
        )
    return int(_row_value(row, "id"))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    mapping = {
        "id": 0,
        "student_id": 1,
        "tenant_id": 2,
        "microsoft_user_id": 3,
        "user_principal_name": 4,
        "email": 5,
        "display_name": 6,
        "access_token": 7,
        "refresh_token": 8,
        "token_type": 9,
        "scopes_json": 10,
        "expires_at": 11,
        "calendar_id": 12,
        "todo_task_list_id": 13,
        "auth_metadata": 14,
        "study_plan_event_instance_id": 2,
        "source_instance_key": 3,
        "external_event_id": 5,
        "external_change_key": 6,
        "sync_status": 7,
        "last_error": 8,
        "last_synced_at": 9,
        "task_list_id": 4,
        "external_task_id": 5,
        "institutional_email": 0,
        "total": 0,
    }
    index = mapping.get(key)
    if index is None or len(row) <= index:
        return default
    return row[index]


def _load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RepositoryConfigurationError(
            "psycopg no esta disponible en el entorno actual."
        ) from exc
    return psycopg, dict_row
