"""Repositorio dedicado para actividades academicas puntuales."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url
from schemas.planning import AcademicActivity


class AcademicActivityRepositoryError(Exception):
    """Error base del repositorio de actividades academicas."""


@dataclass(frozen=True)
class PersistedAcademicActivity:
    """Actividad persistida con metadatos minimos."""

    activity: AcademicActivity


class AcademicActivityRepository(Protocol):
    """Contrato para CRUD durable de actividades puntuales."""

    def upsert_activity(
        self,
        *,
        student_id: int,
        activity: AcademicActivity | dict,
    ) -> PersistedAcademicActivity: ...

    def list_activities(
        self,
        *,
        student_id: int,
        include_deleted: bool = False,
    ) -> list[AcademicActivity]: ...

    def delete_activity(
        self,
        *,
        student_id: int,
        activity_id: str,
    ) -> PersistedAcademicActivity | None: ...


class InMemoryAcademicActivityRepository:
    """Repositorio en memoria para pruebas del flujo de actividades."""

    def __init__(self) -> None:
        self._activities: dict[int, dict[str, AcademicActivity]] = {}
        self._next_id = 1

    def upsert_activity(
        self,
        *,
        student_id: int,
        activity: AcademicActivity | dict,
    ) -> PersistedAcademicActivity:
        item = _ensure_academic_activity(activity)
        if item.persisted_activity_id is None:
            item = item.model_copy(update={"persisted_activity_id": self._next_id})
            self._next_id += 1
        self._activities.setdefault(student_id, {})[item.activity_id] = item
        return PersistedAcademicActivity(activity=item)

    def list_activities(
        self,
        *,
        student_id: int,
        include_deleted: bool = False,
    ) -> list[AcademicActivity]:
        items = list(self._activities.get(student_id, {}).values())
        if not include_deleted:
            items = [item for item in items if item.status != "deleted"]
        return _sort_academic_activities(items)

    def delete_activity(
        self,
        *,
        student_id: int,
        activity_id: str,
    ) -> PersistedAcademicActivity | None:
        current = self._activities.get(student_id, {}).get(activity_id)
        if current is None:
            return None
        updated = current.model_copy(update={"status": "deleted"})
        self._activities.setdefault(student_id, {})[activity_id] = updated
        return PersistedAcademicActivity(activity=updated)


class PostgresAcademicActivityRepository:
    """Repositorio PostgreSQL para actividades academicas puntuales."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def upsert_activity(
        self,
        *,
        student_id: int,
        activity: AcademicActivity | dict,
    ) -> PersistedAcademicActivity:
        item = _ensure_academic_activity(activity)
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO academic_activities (
                    student_id,
                    activity_uid,
                    subject_name,
                    activity_type,
                    activity_title,
                    due_date,
                    due_time,
                    estimated_effort_minutes,
                    priority_level,
                    difficulty_level,
                    status,
                    source_text
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (student_id, activity_uid)
                DO UPDATE SET
                    subject_name = EXCLUDED.subject_name,
                    activity_type = EXCLUDED.activity_type,
                    activity_title = EXCLUDED.activity_title,
                    due_date = EXCLUDED.due_date,
                    due_time = EXCLUDED.due_time,
                    estimated_effort_minutes = EXCLUDED.estimated_effort_minutes,
                    priority_level = EXCLUDED.priority_level,
                    difficulty_level = EXCLUDED.difficulty_level,
                    status = EXCLUDED.status,
                    source_text = EXCLUDED.source_text,
                    updated_at = NOW()
                RETURNING
                    id,
                    activity_uid,
                    subject_name,
                    activity_type,
                    activity_title,
                    due_date,
                    due_time,
                    estimated_effort_minutes,
                    priority_level,
                    difficulty_level,
                    status,
                    source_text,
                    created_at,
                    updated_at
                """,
                (
                    student_id,
                    item.activity_id,
                    item.subject_name,
                    item.activity_type,
                    item.activity_title,
                    item.due_date,
                    item.due_time,
                    item.estimated_effort_minutes,
                    item.priority_level,
                    item.difficulty_level,
                    item.status,
                    item.source_text,
                ),
            ).fetchone()
            conn.commit()
        return PersistedAcademicActivity(activity=_activity_from_row(row))

    def list_activities(
        self,
        *,
        student_id: int,
        include_deleted: bool = False,
    ) -> list[AcademicActivity]:
        status_filter = "" if include_deleted else "AND status <> 'deleted'"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    activity_uid,
                    subject_name,
                    activity_type,
                    activity_title,
                    due_date,
                    due_time,
                    estimated_effort_minutes,
                    priority_level,
                    difficulty_level,
                    status,
                    source_text,
                    created_at,
                    updated_at
                FROM academic_activities
                WHERE student_id = %s
                  {status_filter}
                ORDER BY due_date NULLS LAST, due_time NULLS LAST, subject_name, activity_type
                """,
                (student_id,),
            ).fetchall()
        return [_activity_from_row(row) for row in rows]

    def delete_activity(
        self,
        *,
        student_id: int,
        activity_id: str,
    ) -> PersistedAcademicActivity | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE academic_activities
                SET status = 'deleted',
                    updated_at = NOW()
                WHERE student_id = %s
                  AND activity_uid = %s
                  AND status <> 'deleted'
                RETURNING
                    id,
                    activity_uid,
                    subject_name,
                    activity_type,
                    activity_title,
                    due_date,
                    due_time,
                    estimated_effort_minutes,
                    priority_level,
                    difficulty_level,
                    status,
                    source_text,
                    created_at,
                    updated_at
                """,
                (student_id, activity_id),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return PersistedAcademicActivity(activity=_activity_from_row(row))

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise AcademicActivityRepositoryError(str(exc)) from exc


def build_academic_activity_repository(database_url: str) -> AcademicActivityRepository:
    """Construye el repositorio durable o falla explicitamente."""

    return PostgresAcademicActivityRepository(require_database_url(database_url))


def _ensure_academic_activity(raw_item: AcademicActivity | dict) -> AcademicActivity:
    if isinstance(raw_item, AcademicActivity):
        return raw_item.model_copy(deep=True)
    return AcademicActivity(**dict(raw_item))


def _sort_academic_activities(activities: list[AcademicActivity]) -> list[AcademicActivity]:
    return sorted(
        activities,
        key=lambda activity: (
            activity.status == "deleted",
            activity.due_date or "9999-12-31",
            activity.due_time or "23:59",
            str(activity.subject_name or "").lower(),
            str(activity.activity_title or "").lower(),
        ),
    )


def _activity_from_row(row: Any) -> AcademicActivity:
    if row is None:
        raise AcademicActivityRepositoryError("No se recibio fila de actividad persistida.")
    return AcademicActivity(
        persisted_activity_id=int(_row_value(row, "id")),
        activity_id=str(_row_value(row, "activity_uid")),
        subject_name=str(_row_value(row, "subject_name")),
        activity_type=str(_row_value(row, "activity_type")),
        activity_title=_optional_str(_row_value(row, "activity_title")),
        due_date=_date_str(_row_value(row, "due_date")),
        due_time=_time_str(_row_value(row, "due_time")),
        estimated_effort_minutes=_optional_int(_row_value(row, "estimated_effort_minutes")),
        priority_level=_optional_str(_row_value(row, "priority_level")),
        difficulty_level=_optional_int(_row_value(row, "difficulty_level")),
        status=str(_row_value(row, "status", "pending")),
        source_text=_optional_str(_row_value(row, "source_text")),
        created_at=_datetime_str(_row_value(row, "created_at")),
        updated_at=_datetime_str(_row_value(row, "updated_at")),
    )


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    order = {
        "id": 0,
        "activity_uid": 1,
        "subject_name": 2,
        "activity_type": 3,
        "activity_title": 4,
        "due_date": 5,
        "due_time": 6,
        "estimated_effort_minutes": 7,
        "priority_level": 8,
        "difficulty_level": 9,
        "status": 10,
        "source_text": 11,
        "created_at": 12,
        "updated_at": 13,
    }
    index = order.get(key)
    if index is None or index >= len(row):
        return default
    return row[index]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _time_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value)
    if len(text) >= 5:
        return text[:5]
    return text


def _datetime_str(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


__all__ = [
    "AcademicActivityRepository",
    "AcademicActivityRepositoryError",
    "InMemoryAcademicActivityRepository",
    "PersistedAcademicActivity",
    "PostgresAcademicActivityRepository",
    "build_academic_activity_repository",
]
