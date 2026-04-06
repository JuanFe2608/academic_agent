"""Pipeline común para parsear, normalizar y validar secciones de horario."""

from __future__ import annotations

from services.scheduling.extracurricular_parsing import (
    parse_extracurricular_items_with_context,
)
from services.scheduling.constants import ScheduleBlockType
from services.scheduling.models import WeeklyScheduleBlock
from services.scheduling.parsing_results import SectionPipelineResult

from .contextual_parser import parse_schedule_section_with_context
from .normalizer import normalize_schedule_section, replace_section_blocks


def parse_fixed_schedule_section(
    text: str,
    schedule_type: ScheduleBlockType,
    *,
    timezone: str = "America/Bogota",
) -> SectionPipelineResult:
    """Parsea una sección académica o laboral con el mismo pipeline."""

    context_blocks, context_clarifications, pending_items = parse_schedule_section_with_context(
        text,
        schedule_type,  # type: ignore[arg-type]
        timezone=timezone,
    )
    if pending_items:
        return SectionPipelineResult(
            blocks=context_blocks,
            clarifications=_unique(context_clarifications),
            pending_schedule_items=pending_items,
            needs_clarification=True,
            parser_used="contextual_pending",
        )

    normalized = normalize_schedule_section(text, schedule_type, timezone=timezone)
    if normalized.needs_clarification:
        blocks = context_blocks if context_blocks else normalized.blocks
        clarifications = context_clarifications or normalized.clarifications
        return SectionPipelineResult(
            blocks=blocks,
            clarifications=_unique(clarifications),
            needs_clarification=True,
            parser_used=normalized.parser_used or "deterministic",
        )

    preferred_blocks = context_blocks
    if len(normalized.blocks) > len(context_blocks):
        preferred_blocks = normalized.blocks
    return SectionPipelineResult(
        blocks=preferred_blocks,
        clarifications=[],
        needs_clarification=False,
        parser_used=normalized.parser_used or "deterministic",
    )


def parse_extracurricular_section(
    text: str,
    *,
    timezone: str = "America/Bogota",
    expected_is_variable: bool | None = False,
) -> SectionPipelineResult:
    """Parsea una sección extracurricular con el mismo contrato."""

    normalized = normalize_schedule_section(
        text,
        "extracurricular",
        timezone=timezone,
    )
    items, missing, pending_items = parse_extracurricular_items_with_context(
        text,
        expected_is_variable=expected_is_variable,
    )
    clarifications = normalized.clarifications
    if missing and not clarifications:
        clarifications = [
            "Necesito algunos datos para cerrar bien las actividades extracurriculares: "
            + ", ".join(missing)
            + "."
        ]
    return SectionPipelineResult(
        blocks=normalized.blocks,
        clarifications=_unique(clarifications),
        extracurricular_items=items,
        pending_extracurricular_items=pending_items,
        needs_clarification=normalized.needs_clarification,
        parser_used=normalized.parser_used,
    )


def replace_blocks_for_section(
    existing_blocks: list[WeeklyScheduleBlock],
    block_type: ScheduleBlockType,
    section_result: SectionPipelineResult,
) -> list[WeeklyScheduleBlock]:
    """Reemplaza bloques de una sección usando el resultado del pipeline."""

    return replace_section_blocks(existing_blocks, block_type, section_result.blocks)


def _unique(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(str(value).strip() for value in values if str(value).strip())]
