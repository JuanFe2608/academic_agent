"""Proyección estable entre bloques recurrentes y eventos de agenda.

`events` sigue existiendo por compatibilidad, pero la porción con
`origen="schedule_block"` debe converger con `schedule.blocks`. Este módulo
fija esa relación con IDs determinísticos y permite resincronizar solo esa
slice sin tocar eventos de otros dominios.
"""

from __future__ import annotations

from schemas.scheduling import Event
from services.scheduling.constants import BLOCK_TYPE_TO_EVENT_CATEGORY, DAY_LABELS
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block

SCHEDULE_BLOCK_EVENT_ORIGIN = "schedule_block"
SCHEDULE_BLOCK_EVENT_ID_PREFIX = "schedule-block"


def schedule_block_event_id(block: WeeklyScheduleBlock | dict) -> str:
    """Deriva un ID estable del bloque recurrente canónico."""

    normalized = ensure_weekly_block(block)
    return f"{SCHEDULE_BLOCK_EVENT_ID_PREFIX}:{normalized.block_id}"


def build_schedule_block_event(block: WeeklyScheduleBlock | dict) -> Event:
    """Convierte un bloque recurrente al evento visual canónico."""

    normalized = ensure_weekly_block(block)
    category = BLOCK_TYPE_TO_EVENT_CATEGORY[normalized.block_type]
    spanish_day = DAY_LABELS[normalized.day_of_week]
    return Event(
        id=schedule_block_event_id(normalized),
        dia=spanish_day.replace("é", "e").replace("á", "a"),
        inicio=normalized.start_time,
        fin=normalized.end_time,
        titulo=normalized.title,
        tipo="confirmado",
        categoria=category,
        origen=SCHEDULE_BLOCK_EVENT_ORIGIN,
        timezone=normalized.timezone,
    )


def blocks_to_schedule_events(
    blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[Event]:
    """Proyecta bloques recurrentes a eventos compatibles con el grafo."""

    return [build_schedule_block_event(block) for block in blocks]


def sync_schedule_block_events(
    existing_events: list[Event] | list[dict],
    blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[Event]:
    """Reemplaza solo la porción derivada desde `schedule.blocks`.

    Conserva eventos de otros dominios, por ejemplo study plan o cambios
    directos de replanning.
    """

    preserved_events = [
        event
        for event in (_ensure_event(item) for item in existing_events)
        if event.origen != SCHEDULE_BLOCK_EVENT_ORIGIN
    ]
    return blocks_to_schedule_events(blocks) + preserved_events


def _ensure_event(raw_event: Event | dict) -> Event:
    if isinstance(raw_event, Event):
        return raw_event.model_copy(deep=True)
    return Event(**dict(raw_event))


__all__ = [
    "SCHEDULE_BLOCK_EVENT_ID_PREFIX",
    "SCHEDULE_BLOCK_EVENT_ORIGIN",
    "build_schedule_block_event",
    "blocks_to_schedule_events",
    "schedule_block_event_id",
    "sync_schedule_block_events",
]
