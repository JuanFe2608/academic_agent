"""Repositorios para persistencia durable del tracking de sesiones."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class StudySessionTrackingRepositoryError(Exception):
    """Error base del repositorio de tracking."""


@dataclass(frozen=True)
class StudyPlanInstanceSnapshot:
    """Estado mínimo de una instancia materializada para tracking."""

    id: int
    student_id: int
    study_plan_profile_id: int
    status: str
    starts_at: datetime
    ends_at: datetime
    completion_pct: int | None
    completed_at: datetime | None
    timezone: str
    source_instance_key: str
    planned_date: date | None = None
    title: str = ""
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StudySessionMutation:
    """Cambio atómico sobre instancia + inserción de checkin."""

    student_id: int
    study_plan_event_instance_id: int
    checkin_type: str
    actor_type: str
    reported_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    completion_pct: int | None
    comprehension_score: int | None
    energy_score: int | None
    notes: str | None
    checkin_payload: dict[str, object]
    next_status: str | None = None
    instance_completion_pct: int | None = None
    instance_completed_at: datetime | None = None


@dataclass(frozen=True)
class RecordedStudySessionMutation:
    """Resultado de una transición o checkin persistido."""

    instance: StudyPlanInstanceSnapshot
    previous_status: str
    checkin_id: int


class StudySessionTrackingRepository(Protocol):
    """Contrato para consultar instancias y persistir tracking."""

    def get_instance(
        self,
        *,
        student_id: int,
        study_plan_event_instance_id: int,
    ) -> StudyPlanInstanceSnapshot | None: ...

    def apply_session_mutation(
        self,
        *,
        mutation: StudySessionMutation,
    ) -> RecordedStudySessionMutation: ...

    def list_candidate_instances(
        self,
        *,
        student_id: int,
        as_of: datetime,
        days_before: int,
        days_after: int,
        limit: int,
    ) -> list[StudyPlanInstanceSnapshot]: ...

    def mark_due_sessions_missed(
        self,
        *,
        student_id: int | None,
        as_of: datetime,
        grace_minutes: int,
        limit: int,
        actor_type: str,
    ) -> list[RecordedStudySessionMutation]: ...


class InMemoryStudySessionTrackingRepository:
    """Repositorio en memoria para pruebas del dominio de tracking."""

    def __init__(self, *, instances_repository: Any | None = None) -> None:
        self.instances_repository = instances_repository
        self._checkins_by_id: dict[int, dict[str, Any]] = {}
        self._next_checkin_id = 1

    def get_instance(
        self,
        *,
        student_id: int,
        study_plan_event_instance_id: int,
    ) -> StudyPlanInstanceSnapshot | None:
        if self.instances_repository is None:
            return None
        for payload in self.instances_repository._instances_by_key.values():
            if payload["student_id"] != student_id:
                continue
            if payload["id"] != study_plan_event_instance_id:
                continue
            return _snapshot_from_instance_payload(payload)
        return None

    def apply_session_mutation(
        self,
        *,
        mutation: StudySessionMutation,
    ) -> RecordedStudySessionMutation:
        if self.instances_repository is None:
            raise StudySessionTrackingRepositoryError(
                "No encontré un instances_repository en memoria para tracking."
            )

        target_payload: dict[str, Any] | None = None
        for payload in self.instances_repository._instances_by_key.values():
            if payload["student_id"] != mutation.student_id:
                continue
            if payload["id"] != mutation.study_plan_event_instance_id:
                continue
            target_payload = payload
            break

        if target_payload is None:
            raise StudySessionTrackingRepositoryError("No encontré la instancia solicitada.")

        previous_status = str(target_payload["status"])
        if mutation.next_status is not None:
            target_payload["status"] = mutation.next_status
            target_payload["completion_pct"] = mutation.instance_completion_pct
            target_payload["completed_at"] = mutation.instance_completed_at
            target_payload["updated_at"] = mutation.reported_at

        checkin_id = self._next_checkin_id
        self._next_checkin_id += 1
        self._checkins_by_id[checkin_id] = {
            "id": checkin_id,
            "student_id": mutation.student_id,
            "study_plan_event_instance_id": mutation.study_plan_event_instance_id,
            "checkin_type": mutation.checkin_type,
            "actor_type": mutation.actor_type,
            "reported_at": mutation.reported_at,
            "actual_start_at": mutation.actual_start_at,
            "actual_end_at": mutation.actual_end_at,
            "completion_pct": mutation.completion_pct,
            "comprehension_score": mutation.comprehension_score,
            "energy_score": mutation.energy_score,
            "notes": mutation.notes,
            "checkin_payload": dict(mutation.checkin_payload),
            "created_at": mutation.reported_at,
        }

        return RecordedStudySessionMutation(
            instance=_snapshot_from_instance_payload(target_payload),
            previous_status=previous_status,
            checkin_id=checkin_id,
        )

    def list_candidate_instances(
        self,
        *,
        student_id: int,
        as_of: datetime,
        days_before: int,
        days_after: int,
        limit: int,
    ) -> list[StudyPlanInstanceSnapshot]:
        if self.instances_repository is None:
            return []

        window_start = as_of - timedelta(days=max(0, int(days_before)))
        window_end = as_of + timedelta(days=max(0, int(days_after)))
        candidates: list[StudyPlanInstanceSnapshot] = []
        for payload in self.instances_repository._instances_by_key.values():
            if payload["student_id"] != student_id:
                continue
            if payload["status"] not in {"scheduled", "in_progress", "completed", "skipped", "missed"}:
                continue
            if payload["starts_at"] > window_end or payload["ends_at"] < window_start:
                continue
            candidates.append(_snapshot_from_instance_payload(payload))

        candidates.sort(key=lambda item: (item.starts_at, item.id))
        return candidates[: max(1, int(limit))]

    def mark_due_sessions_missed(
        self,
        *,
        student_id: int | None,
        as_of: datetime,
        grace_minutes: int,
        limit: int,
        actor_type: str,
    ) -> list[RecordedStudySessionMutation]:
        if self.instances_repository is None:
            return []

        due_rows: list[dict[str, Any]] = []
        threshold = timedelta(minutes=max(0, int(grace_minutes)))
        for payload in self.instances_repository._instances_by_key.values():
            if student_id is not None and payload["student_id"] != student_id:
                continue
            if payload["status"] not in {"scheduled", "in_progress"}:
                continue
            if payload["ends_at"] + threshold > as_of:
                continue
            due_rows.append(payload)

        due_rows.sort(key=lambda item: (item["ends_at"], item["id"]))
        recorded: list[RecordedStudySessionMutation] = []
        for payload in due_rows[: max(1, int(limit))]:
            mutation = StudySessionMutation(
                student_id=int(payload["student_id"]),
                study_plan_event_instance_id=int(payload["id"]),
                checkin_type="missed_confirmation",
                actor_type=actor_type,
                reported_at=as_of,
                actual_start_at=None,
                actual_end_at=None,
                completion_pct=0,
                comprehension_score=None,
                energy_score=None,
                notes=None,
                checkin_payload={
                    "grace_minutes": int(grace_minutes),
                    "previous_status": str(payload["status"]),
                },
                next_status="missed",
                instance_completion_pct=0,
                instance_completed_at=None,
            )
            recorded.append(self.apply_session_mutation(mutation=mutation))
        return recorded


class PostgresStudySessionTrackingRepository:
    """Repositorio PostgreSQL para transiciones y checkins."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_instance(
        self,
        *,
        student_id: int,
        study_plan_event_instance_id: int,
    ) -> StudyPlanInstanceSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    study_plan_profile_id,
                    status,
                    starts_at,
                    ends_at,
                    completion_pct,
                    completed_at,
                    timezone,
                    source_instance_key,
                    planned_date,
                    instance_payload
                FROM study_plan_event_instances
                WHERE student_id = %s
                  AND id = %s
                """,
                (student_id, study_plan_event_instance_id),
            ).fetchone()
        return _snapshot_from_row(row) if row is not None else None

    def apply_session_mutation(
        self,
        *,
        mutation: StudySessionMutation,
    ) -> RecordedStudySessionMutation:
        with self._connect() as conn:
            instance_row = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    study_plan_profile_id,
                    status,
                    starts_at,
                    ends_at,
                    completion_pct,
                    completed_at,
                    timezone,
                    source_instance_key,
                    planned_date,
                    instance_payload
                FROM study_plan_event_instances
                WHERE student_id = %s
                  AND id = %s
                FOR UPDATE
                """,
                (mutation.student_id, mutation.study_plan_event_instance_id),
            ).fetchone()
            if instance_row is None:
                raise StudySessionTrackingRepositoryError("No encontré la instancia solicitada.")

            previous_status = str(_row_value(instance_row, "status"))
            final_row = instance_row
            if mutation.next_status is not None:
                final_row = conn.execute(
                    """
                    UPDATE study_plan_event_instances
                    SET status = %s,
                        completion_pct = %s,
                        completed_at = %s,
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND id = %s
                    RETURNING
                        id,
                        student_id,
                        study_plan_profile_id,
                        status,
                        starts_at,
                        ends_at,
                        completion_pct,
                        completed_at,
                        timezone,
                        source_instance_key,
                        planned_date,
                        instance_payload
                    """,
                    (
                        mutation.next_status,
                        mutation.instance_completion_pct,
                        mutation.instance_completed_at,
                        mutation.student_id,
                        mutation.study_plan_event_instance_id,
                    ),
                ).fetchone()

            checkin_row = conn.execute(
                """
                INSERT INTO study_session_checkins (
                    student_id,
                    study_plan_event_instance_id,
                    checkin_type,
                    actor_type,
                    reported_at,
                    actual_start_at,
                    actual_end_at,
                    completion_pct,
                    comprehension_score,
                    energy_score,
                    notes,
                    checkin_payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                RETURNING id
                """,
                (
                    mutation.student_id,
                    mutation.study_plan_event_instance_id,
                    mutation.checkin_type,
                    mutation.actor_type,
                    mutation.reported_at,
                    mutation.actual_start_at,
                    mutation.actual_end_at,
                    mutation.completion_pct,
                    mutation.comprehension_score,
                    mutation.energy_score,
                    mutation.notes,
                    json.dumps(mutation.checkin_payload),
                ),
            ).fetchone()
            conn.commit()

        return RecordedStudySessionMutation(
            instance=_snapshot_from_row(final_row),
            previous_status=previous_status,
            checkin_id=int(_row_value(checkin_row, "id")),
        )

    def list_candidate_instances(
        self,
        *,
        student_id: int,
        as_of: datetime,
        days_before: int,
        days_after: int,
        limit: int,
    ) -> list[StudyPlanInstanceSnapshot]:
        window_start = as_of - timedelta(days=max(0, int(days_before)))
        window_end = as_of + timedelta(days=max(0, int(days_after)))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    student_id,
                    study_plan_profile_id,
                    status,
                    starts_at,
                    ends_at,
                    completion_pct,
                    completed_at,
                    timezone,
                    source_instance_key,
                    planned_date,
                    instance_payload
                FROM study_plan_event_instances
                WHERE student_id = %s
                  AND status IN ('scheduled', 'in_progress', 'completed', 'skipped', 'missed')
                  AND starts_at <= %s
                  AND ends_at >= %s
                ORDER BY starts_at, id
                LIMIT %s
                """,
                (
                    student_id,
                    window_end,
                    window_start,
                    max(1, int(limit)),
                ),
            ).fetchall()
        return [_snapshot_from_row(row) for row in rows]

    def mark_due_sessions_missed(
        self,
        *,
        student_id: int | None,
        as_of: datetime,
        grace_minutes: int,
        limit: int,
        actor_type: str,
    ) -> list[RecordedStudySessionMutation]:
        filters = [
            "status IN ('scheduled', 'in_progress')",
            "ends_at + (%s * INTERVAL '1 minute') <= %s",
        ]
        params: list[object] = [max(0, int(grace_minutes)), as_of]
        if student_id is not None:
            filters.append("student_id = %s")
            params.append(student_id)
        params.append(max(1, int(limit)))

        query = f"""
            SELECT
                id,
                student_id,
                study_plan_profile_id,
                status,
                starts_at,
                ends_at,
                completion_pct,
                completed_at,
                timezone,
                source_instance_key,
                planned_date,
                instance_payload
            FROM study_plan_event_instances
            WHERE {' AND '.join(filters)}
            ORDER BY ends_at, id
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """

        with self._connect() as conn:
            due_rows = conn.execute(query, tuple(params)).fetchall()
            recorded: list[RecordedStudySessionMutation] = []
            for row in due_rows:
                mutation = StudySessionMutation(
                    student_id=int(_row_value(row, "student_id")),
                    study_plan_event_instance_id=int(_row_value(row, "id")),
                    checkin_type="missed_confirmation",
                    actor_type=actor_type,
                    reported_at=as_of,
                    actual_start_at=None,
                    actual_end_at=None,
                    completion_pct=0,
                    comprehension_score=None,
                    energy_score=None,
                    notes=None,
                    checkin_payload={
                        "grace_minutes": int(grace_minutes),
                        "previous_status": str(_row_value(row, "status")),
                    },
                    next_status="missed",
                    instance_completion_pct=0,
                    instance_completed_at=None,
                )
                updated_row = conn.execute(
                    """
                    UPDATE study_plan_event_instances
                    SET status = 'missed',
                        completion_pct = 0,
                        completed_at = NULL,
                        updated_at = NOW()
                    WHERE student_id = %s
                      AND id = %s
                    RETURNING
                        id,
                        student_id,
                        study_plan_profile_id,
                        status,
                        starts_at,
                        ends_at,
                        completion_pct,
                        completed_at,
                        timezone,
                        source_instance_key,
                        planned_date,
                        instance_payload
                    """,
                    (
                        mutation.student_id,
                        mutation.study_plan_event_instance_id,
                    ),
                ).fetchone()
                checkin_row = conn.execute(
                    """
                    INSERT INTO study_session_checkins (
                        student_id,
                        study_plan_event_instance_id,
                        checkin_type,
                        actor_type,
                        reported_at,
                        completion_pct,
                        checkin_payload
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    RETURNING id
                    """,
                    (
                        mutation.student_id,
                        mutation.study_plan_event_instance_id,
                        mutation.checkin_type,
                        mutation.actor_type,
                        mutation.reported_at,
                        mutation.completion_pct,
                        json.dumps(mutation.checkin_payload),
                    ),
                ).fetchone()
                recorded.append(
                    RecordedStudySessionMutation(
                        instance=_snapshot_from_row(updated_row),
                        previous_status=str(_row_value(row, "status")),
                        checkin_id=int(_row_value(checkin_row, "id")),
                    )
                )
            conn.commit()
        return recorded

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover
            raise StudySessionTrackingRepositoryError(str(exc)) from exc


def build_study_session_tracking_repository(
    database_url: str,
) -> StudySessionTrackingRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    return PostgresStudySessionTrackingRepository(require_database_url(database_url))


def _snapshot_from_instance_payload(payload: dict[str, Any]) -> StudyPlanInstanceSnapshot:
    instance_payload = dict(payload.get("instance_payload") or {})
    return StudyPlanInstanceSnapshot(
        id=int(payload["id"]),
        student_id=int(payload["student_id"]),
        study_plan_profile_id=int(payload["study_plan_profile_id"]),
        status=str(payload["status"]),
        starts_at=payload["starts_at"],
        ends_at=payload["ends_at"],
        completion_pct=(
            int(payload["completion_pct"]) if payload["completion_pct"] is not None else None
        ),
        completed_at=payload["completed_at"],
        timezone=str(payload["timezone"]),
        source_instance_key=str(payload["source_instance_key"]),
        planned_date=payload.get("planned_date"),
        title=_title_from_payload(instance_payload),
        payload=instance_payload,
    )


def _snapshot_from_row(row: Any) -> StudyPlanInstanceSnapshot:
    payload = dict(_row_value(row, "instance_payload", {}) or {})
    return StudyPlanInstanceSnapshot(
        id=int(_row_value(row, "id")),
        student_id=int(_row_value(row, "student_id")),
        study_plan_profile_id=int(_row_value(row, "study_plan_profile_id")),
        status=str(_row_value(row, "status")),
        starts_at=_row_value(row, "starts_at"),
        ends_at=_row_value(row, "ends_at"),
        completion_pct=(
            int(_row_value(row, "completion_pct"))
            if _row_value(row, "completion_pct") is not None
            else None
        ),
        completed_at=_row_value(row, "completed_at"),
        timezone=str(_row_value(row, "timezone")),
        source_instance_key=str(_row_value(row, "source_instance_key")),
        planned_date=_row_value(row, "planned_date"),
        title=_title_from_payload(payload),
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
        "completion_pct": 6,
        "completed_at": 7,
        "timezone": 8,
        "source_instance_key": 9,
        "planned_date": 10,
        "instance_payload": 11,
    }
    index = mapping.get(key)
    if index is None or len(row) <= index:
        return default
    return row[index]


def _title_from_payload(payload: dict[str, Any]) -> str:
    event_payload = dict(payload.get("event") or {})
    return str(event_payload.get("titulo") or payload.get("title") or "Sesion de estudio")
