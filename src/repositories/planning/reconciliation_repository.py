"""Repositorio de reconciliación de sesiones de estudio modificadas en Outlook."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class ReconciliationRepositoryError(Exception):
    """Error base del repositorio de reconciliación."""


class ReconciliationRepository(Protocol):
    """Contrato para persistir y consultar cambios detectados en Outlook Calendar."""

    def upsert_pending(
        self,
        *,
        student_id: str,
        instance_id: str,
        outlook_event_id: str,
        drift_kind: str,
        session_title: str | None,
        original_start: datetime | None,
        original_end: datetime | None,
        new_start: datetime | None,
        new_end: datetime | None,
    ) -> str | None: ...

    def list_pending_for_student(self, student_id: str) -> list[dict[str, Any]]: ...

    def resolve(self, reconciliation_id: str, resolution: str) -> bool: ...

    def get_pending_by_id(self, reconciliation_id: str) -> dict[str, Any] | None: ...


class InMemoryReconciliationRepository:
    """Repositorio en memoria para pruebas del dominio de reconciliación."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._key_to_id: dict[tuple[str, str, str], str] = {}

    def upsert_pending(
        self,
        *,
        student_id: str,
        instance_id: str,
        outlook_event_id: str,
        drift_kind: str,
        session_title: str | None,
        original_start: datetime | None,
        original_end: datetime | None,
        new_start: datetime | None,
        new_end: datetime | None,
    ) -> str | None:
        key = (student_id, instance_id, drift_kind)
        if key in self._key_to_id:
            return None
        new_id = str(uuid.uuid4())
        self._store[new_id] = {
            "id": new_id,
            "student_id": student_id,
            "instance_id": instance_id,
            "outlook_event_id": outlook_event_id,
            "drift_kind": drift_kind,
            "session_title": session_title,
            "original_start": original_start,
            "original_end": original_end,
            "new_start": new_start,
            "new_end": new_end,
            "notified_at": datetime.now(),
            "resolved_at": None,
            "resolution": None,
        }
        self._key_to_id[key] = new_id
        return new_id

    def list_pending_for_student(self, student_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._store.values()
            if row["student_id"] == student_id
        ]

    def resolve(self, reconciliation_id: str, resolution: str) -> bool:
        row = self._store.get(reconciliation_id)
        if row is None:
            return False
        row["resolved_at"] = datetime.now()
        row["resolution"] = resolution
        return True

    def get_pending_by_id(self, reconciliation_id: str) -> dict[str, Any] | None:
        row = self._store.get(reconciliation_id)
        return dict(row) if row is not None else None


class PostgresReconciliationRepository:
    """Repositorio PostgreSQL para reconciliación de sesiones de estudio."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def upsert_pending(
        self,
        *,
        student_id: str,
        instance_id: str,
        outlook_event_id: str,
        drift_kind: str,
        session_title: str | None,
        original_start: datetime | None,
        original_end: datetime | None,
        new_start: datetime | None,
        new_end: datetime | None,
    ) -> str | None:
        with self._connect() as conn:
            insert_result = conn.execute(
                """
                INSERT INTO study_session_reconciliation_pending (
                    student_id, instance_id, outlook_event_id, drift_kind,
                    session_title, original_start, original_end, new_start, new_end
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (student_id, instance_id, drift_kind) DO NOTHING
                """,
                (
                    student_id, instance_id, outlook_event_id, drift_kind,
                    session_title, original_start, original_end, new_start, new_end,
                ),
            )
            was_inserted = insert_result.rowcount > 0
            if not was_inserted:
                conn.commit()
                return None
            row = conn.execute(
                """
                SELECT id FROM study_session_reconciliation_pending
                WHERE student_id = %s AND instance_id = %s AND drift_kind = %s
                """,
                (student_id, instance_id, drift_kind),
            ).fetchone()
            conn.commit()
        return str(row[0]) if row else None

    def list_pending_for_student(self, student_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, student_id, instance_id, outlook_event_id, drift_kind,
                       session_title, original_start, original_end,
                       new_start, new_end, notified_at, resolved_at, resolution
                FROM study_session_reconciliation_pending
                WHERE student_id = %s
                ORDER BY notified_at DESC
                """,
                (student_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def resolve(self, reconciliation_id: str, resolution: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE study_session_reconciliation_pending
                SET resolved_at = NOW(), resolution = %s
                WHERE id = %s::uuid AND resolved_at IS NULL
                RETURNING id
                """,
                (resolution, reconciliation_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def get_pending_by_id(self, reconciliation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, student_id, instance_id, outlook_event_id, drift_kind,
                       session_title, original_start, original_end,
                       new_start, new_end, notified_at, resolved_at, resolution
                FROM study_session_reconciliation_pending
                WHERE id = %s::uuid
                """,
                (reconciliation_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:
            raise ReconciliationRepositoryError(str(exc)) from exc


def build_reconciliation_repository(database_url: str) -> ReconciliationRepository:
    """Construye el repositorio PostgreSQL de reconciliación."""

    return PostgresReconciliationRepository(require_database_url(database_url))


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    keys = (
        "id", "student_id", "instance_id", "outlook_event_id", "drift_kind",
        "session_title", "original_start", "original_end",
        "new_start", "new_end", "notified_at", "resolved_at", "resolution",
    )
    if isinstance(row, dict):
        return {k: row.get(k) for k in keys}
    return {k: (str(row[i]) if i == 0 else row[i]) for i, k in enumerate(keys)}
