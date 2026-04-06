"""Sincronización pura de secciones corregidas del horario."""

from __future__ import annotations

from dataclasses import dataclass

from schemas.scheduling import RawInputs, ScheduleContextType
from services.scheduling.block_operations import replace_section_blocks
from services.scheduling.models import WeeklyScheduleBlock
from services.scheduling.parsing_results import SectionPipelineResult
from services.scheduling.raw_input_sync import sync_schedule_blocks_to_raw_inputs
from services.scheduling.section_mutations import merge_completed_section_blocks


@dataclass(frozen=True)
class FixedSectionSyncResult:
    """Resultado canónico de sincronizar una sección fija corregida."""

    target_blocks: list[WeeklyScheduleBlock]
    schedule_blocks: list[WeeklyScheduleBlock]
    raw_inputs: RawInputs


def merge_completed_fixed_section(
    existing_blocks: list[WeeklyScheduleBlock] | list[dict],
    raw_inputs: RawInputs | dict | None,
    target: ScheduleContextType,
    completed_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> FixedSectionSyncResult:
    """Fusiona bloques completados en la sección objetivo y sincroniza `raw_inputs`."""

    merge_result = merge_completed_section_blocks(existing_blocks, target, completed_blocks)
    return FixedSectionSyncResult(
        target_blocks=merge_result.target_blocks,
        schedule_blocks=merge_result.schedule_blocks,
        raw_inputs=sync_schedule_blocks_to_raw_inputs(
            raw_inputs,
            target,
            merge_result.target_blocks,
        ),
    )


def replace_fixed_section(
    existing_blocks: list[WeeklyScheduleBlock] | list[dict],
    raw_inputs: RawInputs | dict | None,
    target: ScheduleContextType,
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> FixedSectionSyncResult:
    """Reemplaza una sección fija completa y sincroniza su texto canónico."""

    updated_schedule_blocks = replace_section_blocks(existing_blocks, target, new_blocks)
    return FixedSectionSyncResult(
        target_blocks=list(new_blocks),
        schedule_blocks=updated_schedule_blocks,
        raw_inputs=sync_schedule_blocks_to_raw_inputs(raw_inputs, target, new_blocks),
    )


def sync_fixed_section_result(
    existing_blocks: list[WeeklyScheduleBlock] | list[dict],
    raw_inputs: RawInputs | dict | None,
    target: ScheduleContextType,
    section_result: SectionPipelineResult,
) -> FixedSectionSyncResult:
    """Aplica el resultado parseado de una sección fija al horario canónico."""

    return replace_fixed_section(existing_blocks, raw_inputs, target, section_result.blocks)


__all__ = [
    "FixedSectionSyncResult",
    "merge_completed_fixed_section",
    "replace_fixed_section",
    "sync_fixed_section_result",
]
