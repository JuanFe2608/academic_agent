"""Adaptadores entre bloques recurrentes y el renderer semanal existente."""

from __future__ import annotations

from datetime import datetime

from agents.support.scheduling.schedule_renderer import render_week_schedule
from schemas.scheduling import Event
from services.scheduling.event_projection import blocks_to_schedule_events
from services.scheduling.models import WeeklyScheduleBlock


def blocks_to_events(blocks: list[WeeklyScheduleBlock]) -> list[Event]:
    """Convierte bloques recurrentes al modelo visual actual de eventos."""

    return blocks_to_schedule_events(blocks)


def render_recurring_schedule(
    blocks: list[WeeklyScheduleBlock],
    out_dir: str = "tmp",
    filename: str = "schedule.png",
    timezone_name: str = "America/Bogota",
    reference: datetime | None = None,
) -> str:
    """Renderiza bloques recurrentes reutilizando el renderer actual."""

    return render_week_schedule(
        blocks_to_events(blocks),
        out_dir=out_dir,
        filename=filename,
        timezone_name=timezone_name,
        reference=reference,
    )
