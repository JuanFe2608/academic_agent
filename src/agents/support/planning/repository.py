"""Repositorios para persistencia de materias priorizadas y planes semanales."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from agents.support.onboarding.repository import RepositoryConfigurationError
from agents.support.planning.state_helpers import ensure_study_plan_state
from agents.support.priorities.state_helpers import ensure_priorities_state, ensure_subject_items
from agents.support.state import PrioritiesState, StudyPlanState, SubjectItem, validate_event


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
                    result_payload,
                    is_current
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb, TRUE
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
                        origin
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            raise StudyPlanningRepositoryError(str(exc)) from exc



def build_study_planning_repository(database_url: str) -> StudyPlanningRepository:
    """Construye el repositorio PostgreSQL o falla explícitamente."""

    if not database_url:
        raise RepositoryConfigurationError(
            "ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGPORT/PGDATABASE/PGUSER no estan configurados."
        )
    return PostgresStudyPlanningRepository(database_url)



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


def _load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RepositoryConfigurationError(
            "psycopg no esta disponible en el entorno actual."
        ) from exc
    return psycopg, dict_row
