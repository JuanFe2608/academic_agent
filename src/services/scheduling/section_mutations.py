"""Transformaciones puras reutilizables para secciones del horario.

Este módulo encapsula la parte de `schedule_review_service` y
`collect_extracurricular_details` que realmente pertenece al dominio de
scheduling: combinar bloques de una sección sin depender del estado del grafo.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.scheduling.block_operations import (
    current_section_blocks,
    merge_section_blocks,
    replace_section_blocks,
)
from services.scheduling.constants import ScheduleBlockType
from services.scheduling.models import WeeklyScheduleBlock


@dataclass(frozen=True)
class SectionMergeResult:
    """Resultado de fusionar bloques completos dentro de una sección."""

    target_blocks: list[WeeklyScheduleBlock]
    schedule_blocks: list[WeeklyScheduleBlock]


def append_section_blocks(
    existing_blocks: list[WeeklyScheduleBlock] | list[dict],
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Agrega nuevos bloques al horario conservando el resto de secciones."""

    return merge_section_blocks(existing_blocks, new_blocks)


def merge_completed_section_blocks(
    existing_blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
    completed_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> SectionMergeResult:
    """Fusiona bloques completados con la sección actual y la reemplaza."""

    merged_target_blocks = merge_section_blocks(
        current_section_blocks(existing_blocks, target),
        completed_blocks,
    )
    return SectionMergeResult(
        target_blocks=merged_target_blocks,
        schedule_blocks=replace_section_blocks(
            existing_blocks,
            target,
            merged_target_blocks,
        ),
    )


__all__ = [
    "SectionMergeResult",
    "append_section_blocks",
    "merge_completed_section_blocks",
]
