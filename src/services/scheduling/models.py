"""Modelos canónicos del horario recurrente semanal."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field

from .constants import (
    CorrectionTarget,
    DayOfWeek,
    EditableScheduleField,
    ScheduleBlockType,
    ScheduleCaptureStage,
    ScheduleRepairStage,
    ScheduleRenewalStage,
    ScheduleReviewStage,
)


def new_block_id() -> str:
    """Retorna un identificador estable para bloques de horario."""

    return str(uuid.uuid4())


def new_conflict_id() -> str:
    """Retorna un identificador estable para conflictos de horario."""

    return str(uuid.uuid4())


class WeeklyScheduleBlock(BaseModel):
    """Bloque semanal fijo listo para persistencia y render."""

    block_id: str = Field(default_factory=new_block_id)
    block_type: ScheduleBlockType
    title: str
    original_title: Optional[str] = None
    normalized_title: Optional[str] = None
    day_of_week: DayOfWeek
    start_time: str
    end_time: str
    frequency: str = "weekly"
    timezone: str = "America/Bogota"
    source_text: str
    confidence: Optional[float] = None
    ambiguity_flags: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    is_active: bool = True
    user_confirmed: bool = False
    has_conflict: bool = False
    conflict_accepted: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class ScheduleConflict(BaseModel):
    """Cruce detectado entre dos bloques semanales."""

    conflict_id: str = Field(default_factory=new_conflict_id)
    day_of_week: DayOfWeek
    left_block_id: str
    right_block_id: str
    left_title: str
    right_title: str
    left_type: ScheduleBlockType
    right_type: ScheduleBlockType
    overlap_start: str
    overlap_end: str
    accepted: bool = False


class NormalizedScheduleResult(BaseModel):
    """Resultado de normalización de una sección del horario."""

    blocks: list[WeeklyScheduleBlock] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifications: list[str] = Field(default_factory=list)
    parser_used: Optional[str] = None


class ScheduleFlowState(BaseModel):
    """Estado operativo del flujo de horarios dentro del grafo."""

    blocks: list[WeeklyScheduleBlock] = Field(default_factory=list)
    conflicts: list[ScheduleConflict] = Field(default_factory=list)
    summary_text: Optional[str] = None
    review_stage: ScheduleReviewStage = "idle"
    capture_target: Optional[ScheduleBlockType] = None
    capture_stage: ScheduleCaptureStage = "idle"
    correction_target: Optional[CorrectionTarget] = None
    editing_block_id: Optional[str] = None
    editing_block_ids: list[str] = Field(default_factory=list)
    editing_field: Optional[EditableScheduleField] = None
    pending_correction_text: Optional[str] = None
    conflicts_accepted: bool = False
    schedule_end_date: Optional[str] = None
    persisted_profile_id: Optional[int] = None
    persistence_error: Optional[str] = None
    renewal_stage: ScheduleRenewalStage = "idle"
    repair_stage: ScheduleRepairStage = "idle"


def ensure_weekly_block(block: WeeklyScheduleBlock | dict) -> WeeklyScheduleBlock:
    """Coacciona dicts del estado a WeeklyScheduleBlock."""

    if isinstance(block, WeeklyScheduleBlock):
        return block
    return WeeklyScheduleBlock(**block)


def ensure_schedule_conflict(
    conflict: ScheduleConflict | dict,
) -> ScheduleConflict:
    """Coacciona dicts del estado a ScheduleConflict."""

    if isinstance(conflict, ScheduleConflict):
        return conflict
    return ScheduleConflict(**conflict)
