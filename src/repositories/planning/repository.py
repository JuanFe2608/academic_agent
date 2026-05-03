"""Repositorios para persistencia de materias priorizadas y planes semanales."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url
from schemas.planning import PrioritiesState, StudyPlanState, SubjectItem
from services.scheduling.validation import validate_event


class StudyPlanningRepositoryError(Exception):
    """Error base del repositorio de planificación académica."""


@dataclass(frozen=True)
class PersistedStudyPlanningSnapshot:
    """Resultado mínimo de persistencia del snapshot académico."""

    priority_profile_id: int
    priority_version_number: int
    study_plan_profile_id: int
    study_plan_version_number: int
    subject_count: int
    event_count: int


@dataclass(frozen=True)
class CurrentStudyPlanningSnapshot:
    """Snapshot vigente de prioridades y plan de estudio de un estudiante."""

    priority_profile_id: int | None
    priority_version_number: int | None
    study_plan_profile_id: int | None
    study_plan_version_number: int | None
    priorities_state: PrioritiesState | None
    subjects: list[SubjectItem]
    study_plan: StudyPlanState | None


class StudyPlanningRepository(Protocol):
    """Contrato para versionar prioridades, materias y plan semanal."""

    def replace_student_planning_snapshot(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None,
        personalization_profile_id: int | None,
        priorities_state: PrioritiesState | dict,
        subjects: list[SubjectItem | dict],
        study_plan: StudyPlanState | dict,
        timezone: str,
    ) -> PersistedStudyPlanningSnapshot: ...

    def get_current_student_planning_snapshot(
        self,
        *,
        student_id: int,
    ) -> CurrentStudyPlanningSnapshot | None: ...


class InMemoryStudyPlanningRepository:
    """Repositorio en memoria para pruebas del dominio de planificación."""

    def __init__(self) -> None:
        self._priority_profiles: dict[int, dict[str, Any]] = {}
        self._priority_history: dict[int, list[dict[str, Any]]] = {}
        self._study_plan_profiles: dict[int, dict[str, Any]] = {}
        self._study_plan_history: dict[int, list[dict[str, Any]]] = {}
        self._next_priority_profile_id = 1
        self._next_study_plan_profile_id = 1

    def replace_student_planning_snapshot(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None,
        personalization_profile_id: int | None,
        priorities_state: PrioritiesState | dict,
        subjects: list[SubjectItem | dict],
        study_plan: StudyPlanState | dict,
        timezone: str,
    ) -> PersistedStudyPlanningSnapshot:
        normalized_priorities = ensure_priorities_state(priorities_state)
        normalized_subjects = ensure_subject_items(subjects)
        normalized_plan = ensure_study_plan_state(study_plan)
        for event in normalized_plan.plan_events:
            validate_event(event)

        priority_version = len(self._priority_history.get(student_id, [])) + 1
        priority_profile_id = self._next_priority_profile_id
        self._next_priority_profile_id += 1

        current_priority = self._priority_profiles.get(student_id)
        if current_priority is not None:
            current_priority["is_current"] = False
            current_priority["status"] = "superseded"

        priority_payload = {
            "id": priority_profile_id,
            "student_id": student_id,
            "schedule_profile_id": schedule_profile_id,
            "personalization_profile_id": personalization_profile_id,
            "version_number": priority_version,
            "status": normalized_priorities.status,
            "source": normalized_priorities.source,
            "prompt_version": normalized_priorities.prompt_version,
            "week_start": normalized_priorities.week_start,
            "week_end": normalized_priorities.week_end,
            "snapshot_kind": _snapshot_kind(normalized_priorities),
            "confirmed_at": (
                normalized_subjects[0].updated_from_flow_at
                if normalized_priorities.status == "completed" and normalized_subjects
                else None
            ),
            "update_reason": _update_reason(normalized_priorities),
            "result_payload": _payload_with_persistence_metadata(
                normalized_priorities,
                persisted_profile_id=priority_profile_id,
                version_number=priority_version,
            ),
            "subjects": [subject.model_dump(mode="python") for subject in normalized_subjects],
            "is_current": True,
        }
        self._priority_profiles[student_id] = priority_payload
        self._priority_history.setdefault(student_id, []).append(priority_payload)

        plan_version = len(self._study_plan_history.get(student_id, [])) + 1
        study_plan_profile_id = self._next_study_plan_profile_id
        self._next_study_plan_profile_id += 1

        current_plan = self._study_plan_profiles.get(student_id)
        if current_plan is not None:
            current_plan["is_current"] = False
            current_plan["status"] = "superseded"

        plan_payload = {
            "id": study_plan_profile_id,
            "student_id": student_id,
            "schedule_profile_id": schedule_profile_id,
            "personalization_profile_id": personalization_profile_id,
            "priority_profile_id": priority_profile_id,
            "version_number": plan_version,
            "status": str(normalized_plan.rules.get("status") or "generated"),
            "planner_version": str(
                normalized_plan.rules.get("planner_version") or "study_planner_v1"
            ),
            "timezone": timezone,
            "rules": dict(normalized_plan.rules),
            "result_payload": _payload_with_persistence_metadata(
                normalized_plan,
                persisted_profile_id=study_plan_profile_id,
                version_number=plan_version,
            ),
            "plan_events": [event.model_dump(mode="python") for event in normalized_plan.plan_events],
            "is_current": True,
        }
        self._study_plan_profiles[student_id] = plan_payload
        self._study_plan_history.setdefault(student_id, []).append(plan_payload)

        return PersistedStudyPlanningSnapshot(
            priority_profile_id=priority_profile_id,
            priority_version_number=priority_version,
            study_plan_profile_id=study_plan_profile_id,
            study_plan_version_number=plan_version,
            subject_count=len(normalized_subjects),
            event_count=len(normalized_plan.plan_events),
        )

    def get_current_student_planning_snapshot(
        self,
        *,
        student_id: int,
    ) -> CurrentStudyPlanningSnapshot | None:
        priority = self._priority_profiles.get(student_id)
        plan = self._study_plan_profiles.get(student_id)
        if priority is None and plan is None:
            return None
        priorities_state = None
        subjects: list[SubjectItem] = []
        if priority is not None:
            priorities_state = ensure_priorities_state(priority.get("result_payload"))
            subjects = ensure_subject_items(priority.get("subjects", []))
        study_plan = ensure_study_plan_state(plan.get("result_payload")) if plan is not None else None
        return CurrentStudyPlanningSnapshot(
            priority_profile_id=int(priority["id"]) if priority is not None else None,
            priority_version_number=int(priority["version_number"]) if priority is not None else None,
            study_plan_profile_id=int(plan["id"]) if plan is not None else None,
            study_plan_version_number=int(plan["version_number"]) if plan is not None else None,
            priorities_state=priorities_state,
            subjects=subjects,
            study_plan=study_plan,
        )


class PostgresStudyPlanningRepository:
    """Repositorio PostgreSQL para prioridades, materias y plan semanal."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def replace_student_planning_snapshot(
        self,
        *,
        student_id: int,
        schedule_profile_id: int | None,
        personalization_profile_id: int | None,
        priorities_state: PrioritiesState | dict,
        subjects: list[SubjectItem | dict],
        study_plan: StudyPlanState | dict,
        timezone: str,
    ) -> PersistedStudyPlanningSnapshot:
        normalized_priorities = ensure_priorities_state(priorities_state)
        normalized_subjects = ensure_subject_items(subjects)
        normalized_plan = ensure_study_plan_state(study_plan)
        for event in normalized_plan.plan_events:
            validate_event(event)

        planner_status = str(normalized_plan.rules.get("status") or "generated")
        planner_version = str(
            normalized_plan.rules.get("planner_version") or "study_planner_v1"
        )

        with self._connect() as conn:
            priority_version_row = conn.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) AS current_version
                FROM study_priority_profiles
                WHERE student_id = %s
                """,
                (student_id,),
            ).fetchone()
            priority_version = int(_row_value(priority_version_row, "current_version", 0)) + 1

            plan_version_row = conn.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) AS current_version
                FROM study_plan_profiles
                WHERE student_id = %s
                """,
                (student_id,),
            ).fetchone()
            study_plan_version = int(_row_value(plan_version_row, "current_version", 0)) + 1

            conn.execute(
                """
                UPDATE study_priority_profiles
                SET is_current = FALSE,
                    status = 'superseded',
                    updated_at = NOW()
                WHERE student_id = %s
                  AND is_current = TRUE
                """,
                (student_id,),
            )

            priority_row = conn.execute(
                """
                INSERT INTO study_priority_profiles (
                    student_id,
                    schedule_profile_id,
                    personalization_profile_id,
                    version_number,
                    status,
                    source,
                    prompt_version,
                    week_start,
                    week_end,
                    snapshot_kind,
                    confirmed_at,
                    update_reason,
                    result_payload,
                    is_current
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, TRUE
                )
                RETURNING id, version_number
                """,
                (
                    student_id,
                    schedule_profile_id,
                    personalization_profile_id,
                    priority_version,
                    normalized_priorities.status,
                    normalized_priorities.source,
                    normalized_priorities.prompt_version,
                    normalized_priorities.week_start,
                    normalized_priorities.week_end,
                    _snapshot_kind(normalized_priorities),
                    (
                        normalized_subjects[0].updated_from_flow_at
                        if normalized_priorities.status == "completed" and normalized_subjects
                        else None
                    ),
                    _update_reason(normalized_priorities),
                    json.dumps(
                        _payload_with_persistence_metadata(
                            normalized_priorities,
                            persisted_profile_id=None,
                            version_number=priority_version,
                        )
                    ),
                ),
            ).fetchone()
            priority_profile_id = _row_value(priority_row, "id")
            persisted_priority_version = _row_value(
                priority_row,
                "version_number",
                priority_version,
            )
            conn.execute(
                """
                UPDATE study_priority_profiles
                SET result_payload = %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps(
                        _payload_with_persistence_metadata(
                            normalized_priorities,
                            persisted_profile_id=int(priority_profile_id),
                            version_number=int(persisted_priority_version),
                        )
                    ),
                    priority_profile_id,
                ),
            )

            for position, subject in enumerate(normalized_subjects, start=1):
                conn.execute(
                    """
                    INSERT INTO study_priority_subjects (
                        priority_profile_id,
                        position,
                        subject_name,
                        priority,
                        difficulty,
                        urgency,
                        weekly_load_min,
                        origin,
                        importance_rank_selected_by_student,
                        perceived_difficulty,
                        urgency_type,
                        urgency_due_at,
                        computed_priority_score,
                        priority_source,
                        is_priority_confirmed,
                        updated_from_flow_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        priority_profile_id,
                        position,
                        subject.nombre,
                        subject.prioridad,
                        int(subject.dificultad),
                        subject.urgencia,
                        subject.carga_semanal_min,
                        subject.origen,
                        subject.importance_rank_selected_by_student,
                        subject.perceived_difficulty,
                        subject.urgency_type,
                        subject.urgency_due_at,
                        subject.computed_priority_score,
                        subject.priority_source,
                        subject.is_priority_confirmed,
                        subject.updated_from_flow_at,
                    ),
                )

            conn.execute(
                """
                UPDATE study_plan_profiles
                SET is_current = FALSE,
                    status = 'superseded',
                    updated_at = NOW()
                WHERE student_id = %s
                  AND is_current = TRUE
                """,
                (student_id,),
            )

            plan_row = conn.execute(
                """
                INSERT INTO study_plan_profiles (
                    student_id,
                    schedule_profile_id,
                    personalization_profile_id,
                    priority_profile_id,
                    version_number,
                    status,
                    planner_version,
                    timezone,
                    rules,
                    result_payload,
                    is_current
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, TRUE
                )
                RETURNING id, version_number
                """,
                (
                    student_id,
                    schedule_profile_id,
                    personalization_profile_id,
                    priority_profile_id,
                    study_plan_version,
                    planner_status,
                    planner_version,
                    timezone,
                    json.dumps(dict(normalized_plan.rules)),
                    json.dumps(
                        _payload_with_persistence_metadata(
                            normalized_plan,
                            persisted_profile_id=None,
                            version_number=study_plan_version,
                        )
                    ),
                ),
            ).fetchone()
            study_plan_profile_id = _row_value(plan_row, "id")
            persisted_plan_version = _row_value(
                plan_row,
                "version_number",
                study_plan_version,
            )
            conn.execute(
                """
                UPDATE study_plan_profiles
                SET result_payload = %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps(
                        _payload_with_persistence_metadata(
                            normalized_plan,
                            persisted_profile_id=int(study_plan_profile_id),
                            version_number=int(persisted_plan_version),
                        )
                    ),
                    study_plan_profile_id,
                ),
            )

            for position, event in enumerate(normalized_plan.plan_events, start=1):
                conn.execute(
                    """
                    INSERT INTO study_plan_events (
                        study_plan_profile_id,
                        position,
                        source_event_id,
                        day_label,
                        start_time,
                        end_time,
                        title,
                        event_type,
                        category,
                        origin,
                        priority,
                        difficulty,
                        timezone,
                        event_payload
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    """,
                    (
                        study_plan_profile_id,
                        position,
                        event.id,
                        event.dia,
                        event.inicio,
                        event.fin,
                        event.titulo,
                        event.tipo,
                        event.categoria,
                        event.origen,
                        event.prioridad,
                        event.dificultad,
                        event.timezone,
                        json.dumps(event.model_dump(mode="python")),
                    ),
                )

            conn.commit()

        return PersistedStudyPlanningSnapshot(
            priority_profile_id=int(priority_profile_id),
            priority_version_number=int(persisted_priority_version),
            study_plan_profile_id=int(study_plan_profile_id),
            study_plan_version_number=int(persisted_plan_version),
            subject_count=len(normalized_subjects),
            event_count=len(normalized_plan.plan_events),
        )

    def get_current_student_planning_snapshot(
        self,
        *,
        student_id: int,
    ) -> CurrentStudyPlanningSnapshot | None:
        with self._connect() as conn:
            priority_row = conn.execute(
                """
                SELECT id, version_number, result_payload
                FROM study_priority_profiles
                WHERE student_id = %s
                  AND is_current = TRUE
                ORDER BY version_number DESC, id DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
            plan_row = conn.execute(
                """
                SELECT id, version_number, result_payload
                FROM study_plan_profiles
                WHERE student_id = %s
                  AND is_current = TRUE
                ORDER BY version_number DESC, id DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
            if priority_row is None and plan_row is None:
                return None

            subjects: list[SubjectItem] = []
            if priority_row is not None:
                subject_rows = conn.execute(
                    """
                    SELECT
                        subject_name,
                        priority,
                        difficulty,
                        urgency,
                        weekly_load_min,
                        origin,
                        importance_rank_selected_by_student,
                        perceived_difficulty,
                        urgency_type,
                        urgency_due_at,
                        computed_priority_score,
                        priority_source,
                        is_priority_confirmed,
                        updated_from_flow_at
                    FROM study_priority_subjects
                    WHERE priority_profile_id = %s
                    ORDER BY position ASC
                    """,
                    (_row_get(priority_row, "id", 0),),
                ).fetchall()
                subjects = [
                    SubjectItem(
                        nombre=str(_row_get(row, "subject_name", 0)),
                        prioridad=str(_row_get(row, "priority", 1)),
                        dificultad=int(_row_get(row, "difficulty", 2)),
                        urgencia=_row_get(row, "urgency", 3),
                        carga_semanal_min=_row_get(row, "weekly_load_min", 4),
                        origen=_row_get(row, "origin", 5),
                        importance_rank_selected_by_student=_row_get(
                            row,
                            "importance_rank_selected_by_student",
                            6,
                        ),
                        perceived_difficulty=_row_get(row, "perceived_difficulty", 7),
                        urgency_type=_row_get(row, "urgency_type", 8),
                        urgency_due_at=_iso_or_raw(_row_get(row, "urgency_due_at", 9)),
                        computed_priority_score=(
                            float(_row_get(row, "computed_priority_score", 10))
                            if _row_get(row, "computed_priority_score", 10) is not None
                            else None
                        ),
                        priority_source=_row_get(row, "priority_source", 11),
                        is_priority_confirmed=bool(_row_get(row, "is_priority_confirmed", 12)),
                        updated_from_flow_at=_iso_or_raw(_row_get(row, "updated_from_flow_at", 13)),
                    )
                    for row in subject_rows
                ]

        priorities_state = (
            ensure_priorities_state(_row_get(priority_row, "result_payload", 2))
            if priority_row is not None
            else None
        )
        study_plan = (
            ensure_study_plan_state(_row_get(plan_row, "result_payload", 2))
            if plan_row is not None
            else None
        )
        return CurrentStudyPlanningSnapshot(
            priority_profile_id=int(_row_get(priority_row, "id", 0)) if priority_row is not None else None,
            priority_version_number=int(_row_get(priority_row, "version_number", 1)) if priority_row is not None else None,
            study_plan_profile_id=int(_row_get(plan_row, "id", 0)) if plan_row is not None else None,
            study_plan_version_number=int(_row_get(plan_row, "version_number", 1)) if plan_row is not None else None,
            priorities_state=priorities_state,
            subjects=subjects,
            study_plan=study_plan,
        )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - cubre errores reales de psycopg
            raise StudyPlanningRepositoryError(str(exc)) from exc



def build_study_planning_repository(database_url: str) -> StudyPlanningRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    return PostgresStudyPlanningRepository(require_database_url(database_url))



def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if key == "id":
        return row[0]
    if key == "version_number":
        return row[1] if len(row) > 1 else default
    if key == "current_version":
        return row[0]
    return default


def _row_get(row: Any, key: str, index: int, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def _iso_or_raw(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _payload_with_persistence_metadata(
    state: PrioritiesState | StudyPlanState,
    *,
    persisted_profile_id: int | None,
    version_number: int,
) -> dict[str, Any]:
    return state.model_copy(
        update={
            "persisted_profile_id": persisted_profile_id,
            "version_number": version_number,
        }
    ).model_dump(mode="python")


def _snapshot_kind(priorities: PrioritiesState) -> str:
    source = str(priorities.source or "")
    if source == "event_update":
        return "event_update"
    if source == "legacy_manual":
        return "legacy"
    if source in {"derived_from_schedule", "fallback"}:
        return "schedule_base"
    return "weekly"


def _update_reason(priorities: PrioritiesState) -> str | None:
    draft = dict(priorities.draft or {})
    event_update = draft.get("event_update")
    if isinstance(event_update, dict):
        trigger = event_update.get("trigger")
        return str(trigger) if trigger else None
    return None


def ensure_subject_item(raw_item: SubjectItem | dict) -> SubjectItem:
    if isinstance(raw_item, SubjectItem):
        return raw_item.model_copy(deep=True)
    return SubjectItem(**dict(raw_item))


def ensure_subject_items(raw_items: list[SubjectItem | dict] | None) -> list[SubjectItem]:
    return [ensure_subject_item(item) for item in list(raw_items or [])]


def ensure_priorities_state(raw_state: PrioritiesState | dict | None) -> PrioritiesState:
    if isinstance(raw_state, PrioritiesState):
        return raw_state.model_copy(deep=True)
    return PrioritiesState(**dict(raw_state or {}))


def ensure_study_plan_state(raw_state: StudyPlanState | dict | None) -> StudyPlanState:
    if isinstance(raw_state, StudyPlanState):
        return raw_state.model_copy(deep=True)
    return StudyPlanState(**dict(raw_state or {}))
