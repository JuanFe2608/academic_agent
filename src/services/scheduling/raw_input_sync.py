"""Sincronización estable entre bloques recurrentes y `RawInputs`.

Estas utilidades mantienen el contrato textual usado por el grafo, pero viven
en la capa de servicios para que la sincronización de secciones corregidas no
dependa de módulos de `agents/support`.
"""

from __future__ import annotations

from schemas.scheduling import RawInputs, ScheduleContextType
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block

_ENGLISH_TO_SPANISH = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miercoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sabado",
    "sunday": "Domingo",
}


def ensure_raw_inputs(raw_inputs: RawInputs | dict | None) -> RawInputs:
    """Coacciona entradas crudas al modelo canónico."""

    if isinstance(raw_inputs, RawInputs):
        return raw_inputs.model_copy(deep=True)
    return RawInputs(**dict(raw_inputs or {}))


def serialize_blocks_for_schedule_type(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    schedule_type: ScheduleContextType,
) -> str:
    """Serializa bloques de una sección al texto estable usado en `raw_inputs`."""

    normalized = [
        block if isinstance(block, WeeklyScheduleBlock) else WeeklyScheduleBlock(**block)
        for block in blocks
        if ensure_weekly_block(block).block_type == schedule_type
    ]
    normalized.sort(key=lambda block: (block.day_of_week, block.start_time, block.title))

    lines: list[str] = []
    for block in normalized:
        day = _ENGLISH_TO_SPANISH.get(block.day_of_week, block.day_of_week)
        if schedule_type == "work":
            lines.append(f"{day} {block.start_time}-{block.end_time}")
        else:
            lines.append(f"{day} {block.start_time}-{block.end_time} {block.title}".strip())
    return "\n".join(lines)


def sync_schedule_blocks_to_raw_inputs(
    raw_inputs: RawInputs | dict | None,
    target: ScheduleContextType,
    blocks: list[WeeklyScheduleBlock] | list[dict],
) -> RawInputs:
    """Actualiza la sección textual correspondiente desde bloques normalizados."""

    updated = ensure_raw_inputs(raw_inputs)
    serialized = serialize_blocks_for_schedule_type(blocks, target)
    field_name = (
        "horario_academico_text" if target == "academic" else "horario_laboral_text"
    )
    return updated.model_copy(update={field_name: serialized or None})


__all__ = [
    "ensure_raw_inputs",
    "serialize_blocks_for_schedule_type",
    "sync_schedule_blocks_to_raw_inputs",
]
