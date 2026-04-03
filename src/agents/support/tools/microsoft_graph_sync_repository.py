"""Repositorio de lectura para sincronización con Microsoft Graph."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Protocol

from agents.support.onboarding.repository import RepositoryConfigurationError


class MicrosoftGraphSyncRepositoryError(Exception):
    """Error base del repositorio de lectura para Graph."""


@dataclass(frozen=True)
class MicrosoftSyncableStudyInstance:
    """Instancia del plan preparada para Calendar o To Do."""

    id: int
    student_id: int
    study_plan_profile_id: int
    status: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    source_instance_key: str
    title: str
    payload: dict[str, object]


class MicrosoftGraphSyncRepository(Protocol):
    """Contrato de lectura para instancias sincronizables."""

    def list_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int | None = None,
    ) -> list[MicrosoftSyncableStudyInstance]: ...


class InMemoryMicrosoftGraphSyncRepository:
    """Repositorio en memoria basado en instancias materializadas."""

    def __init__(self, *, instances_repository: Any | None = None) -> None:
        self.instances_repository = instances_repository

    def list_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int | None = None,
    ) -> list[MicrosoftSyncableStudyInstance]:
        if self.instances_repository is None:
            return []

        results: list[MicrosoftSyncableStudyInstance] = []
        for payload in self.instances_repository._instances_by_key.values():
            if payload["student_id"] != student_id:
                continue
            if (
                study_plan_profile_id is not None
                and payload["study_plan_profile_id"] != study_plan_profile_id
            ):
                continue
            results.append(_syncable_instance_from_payload(payload))

        results.sort(key=lambda item: (item.starts_at, item.id))
        return results


class PostgresMicrosoftGraphSyncRepository:
    """Repositorio PostgreSQL de lectura para sincronización externa."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int | None = None,
    ) -> list[MicrosoftSyncableStudyInstance]:
        filters = ["student_id = %s"]
        params: list[object] = [student_id]
        if study_plan_profile_id is not None:
            filters.append("study_plan_profile_id = %s")
            params.append(study_plan_profile_id)

        query = f"""
            SELECT
                id,
                student_id,
                study_plan_profile_id,
                status,
                starts_at,
                ends_at,
                timezone,
                source_instance_key,
                instance_payload
            FROM study_plan_event_instances
            WHERE {' AND '.join(filters)}
            ORDER BY starts_at, id
        """

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_syncable_instance_from_row(row) for row in rows]

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
            raise MicrosoftGraphSyncRepositoryError(str(exc)) from exc


def build_microsoft_graph_sync_repository(
    database_url: str,
) -> MicrosoftGraphSyncRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return PostgresMicrosoftGraphSyncRepository(database_url)


def _syncable_instance_from_payload(payload: dict[str, Any]) -> MicrosoftSyncableStudyInstance:
    raw_payload = dict(payload.get("instance_payload") or {})
    event_payload = dict(raw_payload.get("event") or {})
    title = str(event_payload.get("titulo") or raw_payload.get("title") or "Sesion de estudio")
    return MicrosoftSyncableStudyInstance(
        id=int(payload["id"]),
        student_id=int(payload["student_id"]),
        study_plan_profile_id=int(payload["study_plan_profile_id"]),
        status=str(payload["status"]),
        starts_at=payload["starts_at"],
        ends_at=payload["ends_at"],
        timezone=str(payload["timezone"]),
        source_instance_key=str(payload["source_instance_key"]),
        title=title,
        payload=raw_payload,
    )


def _syncable_instance_from_row(row: Any) -> MicrosoftSyncableStudyInstance:
    payload = dict(_row_value(row, "instance_payload", {}) or {})
    event_payload = dict(payload.get("event") or {})
    title = str(event_payload.get("titulo") or payload.get("title") or "Sesion de estudio")
    return MicrosoftSyncableStudyInstance(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        study_plan_profile_id=int(_row_value(row, "study_plan_profile_id")),
        status=str(_row_value(row, "status")),
        starts_at=_row_value(row, "starts_at"),
        ends_at=_row_value(row, "ends_at"),
        timezone=str(_row_value(row, "timezone")),
        source_instance_key=str(_row_value(row, "source_instance_key")),
        title=title,
        payload=payload,
    )


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    mapping = {
        "id": 0,
        "student_id": 1,
        "study_plan_profile_id": 2,
        "status": 3,
        "starts_at": 4,
        "ends_at": 5,
        "timezone": 6,
        "source_instance_key": 7,
        "instance_payload": 8,
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
