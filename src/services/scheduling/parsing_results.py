"""Contratos de resultados de parsing para scheduling."""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.scheduling import (
    ExtracurricularItem,
    PendingExtracurricularItem,
    PendingScheduleItem,
)
from services.scheduling.models import WeeklyScheduleBlock


class SectionPipelineResult(BaseModel):
    """Resultado unificado de una sección de horario."""

    blocks: list[WeeklyScheduleBlock] = Field(default_factory=list)
    clarifications: list[str] = Field(default_factory=list)
    pending_schedule_items: list[PendingScheduleItem] = Field(default_factory=list)
    extracurricular_items: list[ExtracurricularItem] = Field(default_factory=list)
    pending_extracurricular_items: list[PendingExtracurricularItem] = Field(
        default_factory=list
    )
    needs_clarification: bool = False
    parser_used: str | None = None


__all__ = ["SectionPipelineResult"]
