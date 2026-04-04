"""Servicio de persistencia para horarios recurrentes."""

from __future__ import annotations

import os
from dataclasses import dataclass

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from .models import ScheduleConflict, WeeklyScheduleBlock
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    ScheduleRepository,
    ScheduleRepositoryError,
    build_schedule_repository,
)


@dataclass(frozen=True)
class PersistScheduleResult:
    """Resultado de guardar el horario del estudiante."""

    persisted: bool
    schedule_profile_id: int | None = None
    block_count: int = 0
    error_code: str | None = None
    detail: str | None = None


class ScheduleService:
    """Orquesta persistencia de horarios recurrentes."""

    def __init__(self, repository: ScheduleRepository) -> None:
        self.repository = repository

    def persist_schedule(
        self,
        student_id: int | None,
        occupation: str,
        timezone: str,
        summary_text: str,
        blocks: list[WeeklyScheduleBlock],
        conflicts: list[ScheduleConflict],
        conflicts_accepted: bool,
    ) -> PersistScheduleResult:
        if not student_id:
            return PersistScheduleResult(
                persisted=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para asociar el horario.",
            )
        if not blocks:
            return PersistScheduleResult(
                persisted=False,
                error_code="empty_schedule",
                detail="No hay bloques válidos para persistir.",
            )
        try:
            record = self.repository.replace_student_schedule(
                student_id=student_id,
                occupation=occupation,
                timezone=timezone,
                summary_text=summary_text,
                blocks=blocks,
                conflicts=conflicts,
                conflicts_accepted=conflicts_accepted,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return PersistScheduleResult(
                persisted=False,
                error_code="schedule_persistence_error",
                detail=str(exc),
            )
        return PersistScheduleResult(
            persisted=True,
            schedule_profile_id=record.schedule_profile_id,
            block_count=record.block_count,
        )


def build_schedule_service() -> ScheduleService:
    """Construye el servicio de horarios según el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_SCHEDULE_REPO", "").strip() == "1":
        return ScheduleService(repository=InMemoryScheduleRepository())
    return ScheduleService(repository=build_schedule_repository(database_url_from_env()))
