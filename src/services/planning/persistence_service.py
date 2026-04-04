"""Servicio de aplicación para persistir materias, prioridades y plan semanal."""

from __future__ import annotations

import os
from dataclasses import dataclass

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from schemas.planning import PrioritiesState, StudyPlanState, SubjectItem
from schemas.scheduling import Event
from services.scheduling.validation import validate_event
from services.planning.state_helpers import ensure_study_plan_state
from services.priorities.state_helpers import ensure_priorities_state, ensure_subject_items

from repositories.planning.repository import (
    InMemoryStudyPlanningRepository,
    PersistedStudyPlanningSnapshot,
    StudyPlanningRepository,
    StudyPlanningRepositoryError,
    build_study_planning_repository,
)


@dataclass(frozen=True)
class PersistStudyPlanningSnapshotResult:
    """Resultado público de persistencia del snapshot académico."""

    persisted: bool
    priority_profile_id: int | None = None
    priority_version_number: int | None = None
    study_plan_profile_id: int | None = None
    study_plan_version_number: int | None = None
    subject_count: int = 0
    event_count: int = 0
    error_code: str | None = None
    detail: str | None = None


class StudyPlanningPersistenceService:
    """Orquesta la persistencia transaccional de priorities y study_plan."""

    def __init__(self, repository: StudyPlanningRepository) -> None:
        self.repository = repository

    def persist_snapshot(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        personalization_profile_id: int | None,
        priorities_state: PrioritiesState | dict | None,
        subjects: list[SubjectItem | dict] | None,
        study_plan: StudyPlanState | dict | None,
        timezone: str,
    ) -> PersistStudyPlanningSnapshotResult:
        if not student_id:
            return PersistStudyPlanningSnapshotResult(
                persisted=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para asociar priorities y study_plan.",
            )

        normalized_priorities = ensure_priorities_state(priorities_state)
        normalized_subjects = ensure_subject_items(subjects)
        normalized_plan = ensure_study_plan_state(study_plan)

        try:
            for event in normalized_plan.plan_events:
                validate_event(event if isinstance(event, Event) else event)
        except ValueError as exc:
            return PersistStudyPlanningSnapshotResult(
                persisted=False,
                error_code="invalid_study_plan",
                detail=str(exc),
            )

        try:
            record = self.repository.replace_student_planning_snapshot(
                student_id=student_id,
                schedule_profile_id=schedule_profile_id,
                personalization_profile_id=personalization_profile_id,
                priorities_state=normalized_priorities,
                subjects=normalized_subjects,
                study_plan=normalized_plan,
                timezone=timezone,
            )
        except (StudyPlanningRepositoryError, RepositoryConfigurationError) as exc:
            return PersistStudyPlanningSnapshotResult(
                persisted=False,
                error_code="study_planning_persistence_error",
                detail=str(exc),
            )

        return _success_result(record)



def build_study_planning_persistence_service() -> StudyPlanningPersistenceService:
    """Construye el servicio de persistencia académica según el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_PLANNING_REPO", "").strip() == "1":
        return StudyPlanningPersistenceService(repository=InMemoryStudyPlanningRepository())
    return StudyPlanningPersistenceService(
        repository=build_study_planning_repository(database_url_from_env())
    )



def _success_result(
    record: PersistedStudyPlanningSnapshot,
) -> PersistStudyPlanningSnapshotResult:
    return PersistStudyPlanningSnapshotResult(
        persisted=True,
        priority_profile_id=record.priority_profile_id,
        priority_version_number=record.priority_version_number,
        study_plan_profile_id=record.study_plan_profile_id,
        study_plan_version_number=record.study_plan_version_number,
        subject_count=record.subject_count,
        event_count=record.event_count,
    )
