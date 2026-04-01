"""Adaptadores entre bloques recurrentes y el renderer semanal existente."""

from __future__ import annotations

from datetime import datetime

from agents.support.state import Event, new_event_id
from agents.support.tools.schedule_renderer import render_week_schedule

from .constants import BLOCK_TYPE_TO_EVENT_CATEGORY, DAY_LABELS
from .models import WeeklyScheduleBlock, ensure_weekly_block


def blocks_to_events(blocks: list[WeeklyScheduleBlock]) -> list[Event]:
    """Convierte bloques recurrentes al modelo visual actual de eventos."""

    events: list[Event] = []
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        category = BLOCK_TYPE_TO_EVENT_CATEGORY[block.block_type]
        spanish_day = DAY_LABELS[block.day_of_week]
        events.append(
            Event(
                id=new_event_id(),
                dia=spanish_day.replace("é", "e").replace("á", "a"),
                inicio=block.start_time,
                fin=block.end_time,
                titulo=block.title,
                tipo="confirmado",
                categoria=category,
                origen="schedule_block",
                timezone=block.timezone,
            )
        )
    return events


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
