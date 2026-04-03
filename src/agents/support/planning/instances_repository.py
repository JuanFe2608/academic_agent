"""Repositorios para materializar ocurrencias fechadas del plan semanal."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterator, Protocol

from agents.support.onboarding.repository import RepositoryConfigurationError

_PROTECTED_INSTANCE_STATUSES = {"completed", "skipped", "missed", "in_progress"}


class StudyPlanInstancesRepositoryError(Exception):
    """Error base del repositorio de instancias materializadas."""


@dataclass(frozen=True)
class PersistedPlanEventReference:
    """Identidad persistida de un evento semanal dentro de un perfil."""

    event_id: int
    position: int
    source_event_id: str


@dataclass(frozen=True)
class MaterializedStudyPlanInstance:
    """Ocurrencia concreta lista para persistencia."""

    study_plan_event_id: int
    source_instance_key: str
    planned_date: date
    starts_at: datetime
    ends_at: datetime
    timezone: str
    instance_payload: dict[str, object]


@dataclass(frozen=True)
class SyncStudyPlanInstancesResult:
    """Resultado mínimo del sync de instancias materializadas."""

    materialized_instance_count: int
    superseded_instance_count: int


class StudyPlanInstancesRepository(Protocol):
    """Contrato para resolver eventos persistidos y sincronizar instancias."""

    def get_persisted_plan_event_map(
        self,
        *,
        study_plan_profile_id: int,
        plan_event_keys: list[tuple[int, str]],
    ) -> dict[tuple[int, str], PersistedPlanEventReference]: ...

    def sync_materialized_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
        active_from: datetime,
        instances: list[MaterializedStudyPlanInstance],
    ) -> SyncStudyPlanInstancesResult: ...


class InMemoryStudyPlanInstancesRepository:
    """Repositorio en memoria para pruebas del dominio de instancias."""

    def __init__(self) -> None:
        self._plan_event_refs: dict[tuple[int, int, str], PersistedPlanEventReference] = {}
        self._instances_by_key: dict[str, dict[str, Any]] = {}
        self._next_event_id = 1
        self._next_instance_id = 1

    def get_persisted_plan_event_map(
        self,
        *,
        study_plan_profile_id: int,
        plan_event_keys: list[tuple[int, str]],
    ) -> dict[tuple[int, str], PersistedPlanEventReference]:
        resolved: dict[tuple[int, str], PersistedPlanEventReference] = {}
        for position, source_event_id in plan_event_keys:
            key = (study_plan_profile_id, position, source_event_id)
            reference = self._plan_event_refs.get(key)
            if reference is None:
                reference = PersistedPlanEventReference(
                    event_id=self._next_event_id,
                    position=position,
                    source_event_id=source_event_id,
                )
                self._next_event_id += 1
                self._plan_event_refs[key] = reference
            resolved[(position, source_event_id)] = reference
        return resolved

    def sync_materialized_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
        active_from: datetime,
        instances: list[MaterializedStudyPlanInstance],
    ) -> SyncStudyPlanInstancesResult:
        superseded = 0
        for payload in self._instances_by_key.values():
            if payload["student_id"] != student_id:
                continue
            if payload["study_plan_profile_id"] == study_plan_profile_id:
                continue
            if payload["status"] != "scheduled":
                continue
            if payload["starts_at"] < active_from:
                continue
            payload["status"] = "superseded"
            payload["updated_at"] = datetime.now(tz=active_from.tzinfo)
            superseded += 1

        for instance in instances:
            existing = self._instances_by_key.get(instance.source_instance_key)
            if existing is None:
                existing = {
                    "id": self._next_instance_id,
                    "student_id": student_id,
                    "study_plan_profile_id": study_plan_profile_id,
                    "study_plan_event_id": instance.study_plan_event_id,
                    "source_instance_key": instance.source_instance_key,
                    "planned_date": instance.planned_date,
                    "starts_at": instance.starts_at,
                    "ends_at": instance.ends_at,
                    "timezone": instance.timezone,
                    "status": "scheduled",
                    "source": "materialized_plan",
                    "completion_pct": None,
                    "completed_at": None,
                    "instance_payload": dict(instance.instance_payload),
                    "created_at": datetime.now(tz=instance.starts_at.tzinfo),
                    "updated_at": datetime.now(tz=instance.starts_at.tzinfo),
                }
                self._instances_by_key[instance.source_instance_key] = existing
                self._next_instance_id += 1
                continue

            protected = existing["status"] in _PROTECTED_INSTANCE_STATUSES
            existing.update(
                {
                    "student_id": student_id,
                    "study_plan_profile_id": study_plan_profile_id,
                    "study_plan_event_id": instance.study_plan_event_id,
                    "planned_date": instance.planned_date,
                    "starts_at": instance.starts_at,
                    "ends_at": instance.ends_at,
                    "timezone": instance.timezone,
                    "source": "materialized_plan",
                    "instance_payload": dict(instance.instance_payload),
                    "updated_at": datetime.now(tz=instance.starts_at.tzinfo),
                }
            )
            if not protected:
                existing["status"] = "scheduled"
                existing["completion_pct"] = None
                existing["completed_at"] = None

        return SyncStudyPlanInstancesResult(
            materialized_instance_count=len(instances),
            superseded_instance_count=superseded,
        )


class PostgresStudyPlanInstancesRepository:
    """Repositorio PostgreSQL para ocurrencias materializadas."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_persisted_plan_event_map(
        self,
        *,
        study_plan_profile_id: int,
        plan_event_keys: list[tuple[int, str]],
    ) -> dict[tuple[int, str], PersistedPlanEventReference]:
        requested_keys = set(plan_event_keys)
        if not requested_keys:
            return {}

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, position, source_event_id
                FROM study_plan_events
                WHERE study_plan_profile_id = %s
                ORDER BY position
                """,
                (study_plan_profile_id,),
            ).fetchall()

        resolved: dict[tuple[int, str], PersistedPlanEventReference] = {}
        for row in rows:
            position = int(_row_value(row, "position"))
            source_event_id = str(_row_value(row, "source_event_id"))
            key = (position, source_event_id)
            if key not in requested_keys:
                continue
            resolved[key] = PersistedPlanEventReference(
                event_id=int(_row_value(row, "id")),
                position=position,
                source_event_id=source_event_id,
            )
        return resolved

    def sync_materialized_instances(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
        active_from: datetime,
        instances: list[MaterializedStudyPlanInstance],
    ) -> SyncStudyPlanInstancesResult:
        with self._connect() as conn:
            superseded_row = conn.execute(
                """
                WITH superseded AS (
                    UPDATE study_plan_event_instances
                    SET status = 'superseded',
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND study_plan_profile_id <> %s
                      AND status = 'scheduled'
                      AND starts_at >= %s
                    RETURNING 1
                )
                SELECT COUNT(*) AS total FROM superseded
                """,
                (
                    student_id,
                    study_plan_profile_id,
                    active_from,
                ),
            ).fetchone()
            superseded_count = int(_row_value(superseded_row, "total", 0))

            for instance in instances:
                conn.execute(
                    """
                    INSERT INTO study_plan_event_instances (
                        student_id,
                        study_plan_profile_id,
                        study_plan_event_id,
                        source_instance_key,
                        planned_date,
                        starts_at,
                        ends_at,
                        timezone,
                        status,
                        source,
                        completion_pct,
                        completed_at,
                        instance_payload
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        'scheduled', 'materialized_plan', NULL, NULL, %s::jsonb
                    )
                    ON CONFLICT (source_instance_key) DO UPDATE
                    SET student_id = EXCLUDED.student_id,
                        study_plan_profile_id = EXCLUDED.study_plan_profile_id,
                        study_plan_event_id = EXCLUDED.study_plan_event_id,
                        planned_date = EXCLUDED.planned_date,
                        starts_at = EXCLUDED.starts_at,
                        ends_at = EXCLUDED.ends_at,
                        timezone = EXCLUDED.timezone,
                        source = EXCLUDED.source,
                        instance_payload = EXCLUDED.instance_payload,
                        status = CASE
                            WHEN study_plan_event_instances.status = ANY(%s)
                                THEN study_plan_event_instances.status
                            ELSE EXCLUDED.status
                        END,
                        completion_pct = CASE
                            WHEN study_plan_event_instances.status = ANY(%s)
                                THEN study_plan_event_instances.completion_pct
                            ELSE EXCLUDED.completion_pct
                        END,
                        completed_at = CASE
                            WHEN study_plan_event_instances.status = ANY(%s)
                                THEN study_plan_event_instances.completed_at
                            ELSE EXCLUDED.completed_at
                        END,
                        updated_at = NOW()
                    """,
                    (
                        student_id,
                        study_plan_profile_id,
                        instance.study_plan_event_id,
                        instance.source_instance_key,
                        instance.planned_date,
                        instance.starts_at,
                        instance.ends_at,
                        instance.timezone,
                        json.dumps(instance.instance_payload),
                        list(_PROTECTED_INSTANCE_STATUSES),
                        list(_PROTECTED_INSTANCE_STATUSES),
                        list(_PROTECTED_INSTANCE_STATUSES),
                    ),
                )

            conn.commit()

        return SyncStudyPlanInstancesResult(
            materialized_instance_count=len(instances),
            superseded_instance_count=superseded_count,
        )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        psycopg, dict_row = _load_psycopg()
        try:
            with psycopg.connect(
                self.database_url,
                row_factory=dict_row,
            ) as conn:
                yield conn
        except ImportError as exc:
            raise RepositoryConfigurationError(
                "psycopg no esta instalado; no pude conectar PostgreSQL."
            ) from exc
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyPlanInstancesRepositoryError(str(exc)) from exc


def build_study_plan_instances_repository(database_url: str) -> StudyPlanInstancesRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return PostgresStudyPlanInstancesRepository(database_url)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if key == "id":
        return row[0]
    if key == "position":
        return row[1] if len(row) > 1 else default
    if key == "source_event_id":
        return row[2] if len(row) > 2 else default
    if key == "total":
        return row[0]
    return default


def _load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RepositoryConfigurationError(
            "psycopg no esta disponible en el entorno actual."
        ) from exc
    return psycopg, dict_row
