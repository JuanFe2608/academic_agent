"""Operaciones puras sobre bloques recurrentes de horario.

Estas funciones no conocen LangGraph ni el estado conversacional. Su objetivo
es encapsular mutaciones reutilizables sobre `WeeklyScheduleBlock` para que los
flows de `agents/support` dependan menos de lógica estructural dispersa.
"""

from __future__ import annotations

from services.scheduling.constants import ScheduleBlockType
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block


def current_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    block_type: ScheduleBlockType,
) -> list[WeeklyScheduleBlock]:
    """Retorna solo los bloques de una sección concreta del horario."""

    return [
        ensure_weekly_block(block)
        for block in existing
        if ensure_weekly_block(block).block_type == block_type
    ]


def merge_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Agrega bloques a una sección eliminando duplicados exactos."""

    merged = [ensure_weekly_block(block) for block in existing] + [
        ensure_weekly_block(block) for block in new_blocks
    ]
    return _dedupe_blocks(merged)


def replace_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    block_type: ScheduleBlockType,
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Reemplaza por completo una sección del horario."""

    kept = [
        ensure_weekly_block(block)
        for block in existing
        if ensure_weekly_block(block).block_type != block_type
    ]
    normalized_new = [ensure_weekly_block(block) for block in new_blocks]
    return _dedupe_blocks(kept + normalized_new)


def _dedupe_blocks(blocks: list[WeeklyScheduleBlock]) -> list[WeeklyScheduleBlock]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[WeeklyScheduleBlock] = []
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        key = (
            block.block_type,
            block.title.strip().lower(),
            block.day_of_week,
            block.start_time,
            block.end_time,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(block)
    return deduped


__all__ = [
    "current_section_blocks",
    "merge_section_blocks",
    "replace_section_blocks",
]
