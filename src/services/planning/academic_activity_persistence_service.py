"""Servicio de aplicacion para persistir actividades academicas puntuales."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from repositories.planning.activity_repository import (
    AcademicActivityRepository,
    AcademicActivityRepositoryError,
    InMemoryAcademicActivityRepository,
    build_academic_activity_repository,
)
from schemas.planning import AcademicActivity
from services.planning.academic_activity_service import ensure_academic_activity


@dataclass(frozen=True)
class PersistAcademicActivityResult:
    """Resultado de persistir una actividad puntual."""

    persisted: bool
    activity: AcademicActivity | None = None
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ListAcademicActivitiesResult:
    """Resultado de consultar actividades puntuales."""

    loaded: bool
    activities: list[AcademicActivity] = field(default_factory=list)
    error_code: str | None = None
    detail: str | None = None


class AcademicActivityPersistenceService:
    """Orquesta el CRUD durable de actividades academicas puntuales."""

    def __init__(self, repository: AcademicActivityRepository) -> None:
        self.repository = repository

    def upsert_activity(
        self,
        *,
        student_id: int | None,
        activity: AcademicActivity | dict,
    ) -> PersistAcademicActivityResult:
        if not student_id:
            return PersistAcademicActivityResult(
                persisted=False,
                activity=ensure_academic_activity(activity),
                error_code="missing_student_id",
                detail="No encontre el estudiante persistido para asociar la actividad.",
            )
        try:
            record = self.repository.upsert_activity(
                student_id=int(student_id),
                activity=ensure_academic_activity(activity),
            )
        except (AcademicActivityRepositoryError, RepositoryConfigurationError) as exc:
            return PersistAcademicActivityResult(
                persisted=False,
                activity=ensure_academic_activity(activity),
                error_code="academic_activity_persistence_error",
                detail=str(exc),
            )
        return PersistAcademicActivityResult(persisted=True, activity=record.activity)

    def list_activities(
        self,
        *,
        student_id: int | None,
        include_deleted: bool = False,
    ) -> ListAcademicActivitiesResult:
        if not student_id:
            return ListAcademicActivitiesResult(
                loaded=False,
                error_code="missing_student_id",
                detail="No encontre el estudiante persistido para consultar actividades.",
            )
        try:
            activities = self.repository.list_activities(
                student_id=int(student_id),
                include_deleted=include_deleted,
            )
        except (AcademicActivityRepositoryError, RepositoryConfigurationError) as exc:
            return ListAcademicActivitiesResult(
                loaded=False,
                error_code="academic_activity_persistence_error",
                detail=str(exc),
            )
        return ListAcademicActivitiesResult(loaded=True, activities=activities)

    def delete_activity(
        self,
        *,
        student_id: int | None,
        activity_id: str,
    ) -> PersistAcademicActivityResult:
        if not student_id:
            return PersistAcademicActivityResult(
                persisted=False,
                error_code="missing_student_id",
                detail="No encontre el estudiante persistido para eliminar la actividad.",
            )
        try:
            record = self.repository.delete_activity(
                student_id=int(student_id),
                activity_id=activity_id,
            )
        except (AcademicActivityRepositoryError, RepositoryConfigurationError) as exc:
            return PersistAcademicActivityResult(
                persisted=False,
                error_code="academic_activity_persistence_error",
                detail=str(exc),
            )
        if record is None:
            return PersistAcademicActivityResult(
                persisted=False,
                error_code="academic_activity_not_found",
                detail="No encontre la actividad en persistencia.",
            )
        return PersistAcademicActivityResult(persisted=True, activity=record.activity)


def build_academic_activity_persistence_service() -> AcademicActivityPersistenceService:
    """Construye el servicio segun el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_ACADEMIC_ACTIVITY_REPO", "").strip() == "1":
        return AcademicActivityPersistenceService(repository=InMemoryAcademicActivityRepository())
    return AcademicActivityPersistenceService(
        repository=build_academic_activity_repository(database_url_from_env())
    )


__all__ = [
    "AcademicActivityPersistenceService",
    "ListAcademicActivitiesResult",
    "PersistAcademicActivityResult",
    "build_academic_activity_persistence_service",
]
