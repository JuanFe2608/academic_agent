"""Proyección estable entre bloques recurrentes y eventos de agenda.

`schedule.blocks` es la fuente de verdad del horario fijo. Los eventos planos
se derivan de bloques bajo demanda; nunca se persisten en el estado del grafo.
"""

from __future__ import annotations

from schemas.scheduling import Event
from services.scheduling.constants import BLOCK_TYPE_TO_EVENT_CATEGORY, DAY_LABELS
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block

# Mapeo inverso: nombre español (sin tilde) → día en inglés
_SPANISH_LOWER_TO_ENGLISH: dict[str, str] = {
    "lunes": "monday",
    "martes": "tuesday",
    "miercoles": "wednesday",
    "jueves": "thursday",
    "viernes": "friday",
    "sabado": "saturday",
    "domingo": "sunday",
}

# Mapeo inverso: categoría de evento → block_type
_EVENT_CATEGORY_TO_BLOCK_TYPE: dict[str, str] = {
    v: k for k, v in BLOCK_TYPE_TO_EVENT_CATEGORY.items()
}

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


def event_block_id(event: Event | dict) -> str | None:
    """Extrae el block_id de un evento schedule_block, o None si no aplica."""
    if isinstance(event, dict):
        event_id = str(event.get("id") or "")
    else:
        event_id = str(getattr(event, "id", "") or "")
    prefix = SCHEDULE_BLOCK_EVENT_ID_PREFIX + ":"
    return event_id[len(prefix):] if event_id.startswith(prefix) else None


def event_to_schedule_block(event: Event | dict) -> WeeklyScheduleBlock | None:
    """Convierte un Event plano (académico o laboral) a WeeklyScheduleBlock.

    Retorna None si el evento es extracurricular o no convertible.
    """
    if isinstance(event, dict):
        categoria = str(event.get("categoria") or "")
        dia = str(event.get("dia") or "")
        inicio = str(event.get("inicio") or "")
        fin = str(event.get("fin") or "")
        titulo = str(event.get("titulo") or "")
        tz = str(event.get("timezone") or "America/Bogota")
    else:
        categoria = str(getattr(event, "categoria", "") or "")
        dia = str(getattr(event, "dia", "") or "")
        inicio = str(getattr(event, "inicio", "") or "")
        fin = str(getattr(event, "fin", "") or "")
        titulo = str(getattr(event, "titulo", "") or "")
        tz = str(getattr(event, "timezone", "America/Bogota") or "America/Bogota")

    block_type = _EVENT_CATEGORY_TO_BLOCK_TYPE.get(categoria)
    if not block_type or block_type == "extracurricular":
        return None

    day_of_week = _SPANISH_LOWER_TO_ENGLISH.get(
        dia.lower().strip().replace("é", "e").replace("á", "a").replace("ó", "o")
    )
    if not day_of_week:
        return None

    return WeeklyScheduleBlock(
        day_of_week=day_of_week,
        start_time=inicio,
        end_time=fin,
        title=titulo,
        block_type=block_type,
        timezone=tz,
        source_text=f"{titulo} {dia} {inicio}-{fin}",
    )


def events_to_schedule_blocks(
    events: list[Event | dict],
    block_type: str,
) -> list[WeeklyScheduleBlock]:
    """Convierte eventos de un tipo concreto a WeeklyScheduleBlocks."""
    result = []
    for event in events:
        block = event_to_schedule_block(event)
        if block is not None and block.block_type == block_type:
            result.append(block)
    return result


def _ensure_event(raw_event: Event | dict) -> Event:
    if isinstance(raw_event, Event):
        return raw_event.model_copy(deep=True)
    return Event(**dict(raw_event))


__all__ = [
    "SCHEDULE_BLOCK_EVENT_ID_PREFIX",
    "SCHEDULE_BLOCK_EVENT_ORIGIN",
    "build_schedule_block_event",
    "blocks_to_schedule_events",
    "event_block_id",
    "event_to_schedule_block",
    "events_to_schedule_blocks",
    "schedule_block_event_id",
    "sync_schedule_block_events",
]
