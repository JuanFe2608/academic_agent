"""Servicio de persistencia para horarios recurrentes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from .models import ScheduleConflict, WeeklyScheduleBlock
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    PersistedScheduleProfileRecord,
    ScheduleRepository,
    ScheduleRepositoryError,
    build_schedule_repository,
)

_VALID_DAY_OF_WEEK: frozenset[str] = frozenset(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
)
_VALID_BLOCK_TYPES: frozenset[str] = frozenset(["academic", "work", "extracurricular"])


def _block_field(block: Any, name: str) -> str:
    if isinstance(block, dict):
        return str(block.get(name) or "").strip()
    return str(getattr(block, name, "") or "").strip()


def _validate_block(block: Any) -> str | None:
    """Returns a friendly error description if the block is invalid, else None."""
    day = _block_field(block, "day_of_week").lower()
    if day not in _VALID_DAY_OF_WEEK:
        title = _block_field(block, "title") or "bloque sin nombre"
        start = _block_field(block, "start_time")
        end = _block_field(block, "end_time")
        time_range = f" {start}-{end}" if start and end else ""
        return f"'{title}'{time_range} (día no reconocido: {day!r})"
    btype = _block_field(block, "block_type").lower()
    if btype not in _VALID_BLOCK_TYPES:
        title = _block_field(block, "title") or "bloque sin nombre"
        return f"'{title}' (tipo desconocido: {btype!r})"
    return None


@dataclass(frozen=True)
class PersistScheduleResult:
    """Resultado de guardar el horario del estudiante."""

    persisted: bool
    schedule_profile_id: int | None = None
    block_count: int = 0
    schedule_end_date: date | None = None
    error_code: str | None = None
    detail: str | None = None
    invalid_blocks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleProfileLookupResult:
    """Resultado de consultar el horario actual persistido."""

    found: bool
    profile: PersistedScheduleProfileRecord | None = None
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ScheduleBlocksLookupResult:
    """Resultado de consultar bloques del horario actual."""

    found: bool
    profile: PersistedScheduleProfileRecord | None = None
    blocks: list[Any] | None = None
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class UpdateScheduleEndDateResult:
    """Resultado de actualizar la fecha límite de un horario fijo."""

    updated: bool
    profile: PersistedScheduleProfileRecord | None = None
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
        schedule_end_date: date | None = None,
    ) -> PersistScheduleResult:
        if not student_id:
            return PersistScheduleResult(
                persisted=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para asociar el horario.",
            )

        valid_blocks: list[Any] = []
        invalid_descriptions: list[str] = []
        for block in blocks:
            error = _validate_block(block)
            if error is None:
                valid_blocks.append(block)
            else:
                invalid_descriptions.append(error)

        if not valid_blocks:
            return PersistScheduleResult(
                persisted=False,
                error_code="no_valid_blocks",
                detail="No hay bloques válidos para persistir.",
                invalid_blocks=tuple(invalid_descriptions),
            )

        try:
            record = self.repository.replace_student_schedule(
                student_id=student_id,
                occupation=occupation,
                timezone=timezone,
                summary_text=summary_text,
                blocks=valid_blocks,
                conflicts=conflicts,
                conflicts_accepted=conflicts_accepted,
                schedule_end_date=schedule_end_date,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return PersistScheduleResult(
                persisted=False,
                error_code="schedule_persistence_error",
                detail=str(exc),
                invalid_blocks=tuple(invalid_descriptions),
            )
        return PersistScheduleResult(
            persisted=True,
            schedule_profile_id=record.schedule_profile_id,
            block_count=record.block_count,
            schedule_end_date=record.schedule_end_date,
            invalid_blocks=tuple(invalid_descriptions),
        )

    def get_current_schedule_profile(
        self,
        *,
        student_id: int | None,
    ) -> ScheduleProfileLookupResult:
        if not student_id:
            return ScheduleProfileLookupResult(
                found=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para consultar el horario.",
            )
        try:
            profile = self.repository.get_current_schedule_profile(student_id=int(student_id))
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return ScheduleProfileLookupResult(
                found=False,
                error_code="schedule_lookup_error",
                detail=str(exc),
            )
        if profile is None:
            return ScheduleProfileLookupResult(found=False)
        return ScheduleProfileLookupResult(found=True, profile=profile)

    def list_current_schedule_blocks(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None = None,
    ) -> ScheduleBlocksLookupResult:
        if not student_id:
            return ScheduleBlocksLookupResult(
                found=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para consultar bloques del horario.",
            )
        try:
            profile = self.repository.get_current_schedule_profile(student_id=int(student_id))
            if profile is None:
                return ScheduleBlocksLookupResult(found=False)
            blocks = self.repository.list_student_schedule_blocks(
                student_id=int(student_id),
                schedule_profile_id=schedule_profile_id or profile.id,
                only_current_profile=True,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return ScheduleBlocksLookupResult(
                found=False,
                error_code="schedule_blocks_lookup_error",
                detail=str(exc),
            )
        return ScheduleBlocksLookupResult(
            found=True,
            profile=profile,
            blocks=list(blocks),
        )

    def update_schedule_end_date(
        self,
        *,
        schedule_profile_id: int | None,
        schedule_end_date: date | None,
    ) -> UpdateScheduleEndDateResult:
        if not schedule_profile_id:
            return UpdateScheduleEndDateResult(
                updated=False,
                error_code="missing_schedule_profile_id",
                detail="No encontré el perfil horario actual para renovar la fecha límite.",
            )
        try:
            profile = self.repository.update_schedule_end_date(
                schedule_profile_id=int(schedule_profile_id),
                schedule_end_date=schedule_end_date,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return UpdateScheduleEndDateResult(
                updated=False,
                error_code="schedule_end_date_update_error",
                detail=str(exc),
            )
        return UpdateScheduleEndDateResult(updated=True, profile=profile)


def build_schedule_service() -> ScheduleService:
    """Construye el servicio de horarios según el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_SCHEDULE_REPO", "").strip() == "1":
        return ScheduleService(repository=InMemoryScheduleRepository())
    return ScheduleService(repository=build_schedule_repository(database_url_from_env()))
