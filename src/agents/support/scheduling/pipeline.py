"""Pipeline común para parsear, normalizar y validar secciones de horario."""

from __future__ import annotations

import re

from services.scheduling.extracurricular_parsing import (
    parse_extracurricular_items_with_context,
)
from services.scheduling.constants import ScheduleBlockType
from services.scheduling.models import WeeklyScheduleBlock
from services.scheduling.parsing_results import SectionPipelineResult

from .contextual_parser import parse_schedule_section_with_context
from .normalizer import normalize_schedule_section, replace_section_blocks

# Marcadores de imagen que WhatsApp / la universidad insertan en el texto copiado.
# Caso 1 — línea completa: "Image\n" o "Imagen\n" se eliminan totalmente.
# Caso 2 — inline: "Cálculo Image" → "Cálculo" (el nombre de la materia queda intacto).
_IMAGE_MARKER_RE = re.compile(
    r"^\s*(image|imagen|photo|foto|picture|captura|screenshot)s?\s*$",
    re.IGNORECASE,
)
_IMAGE_INLINE_RE = re.compile(
    r"\s*\b(image|imagen|photo|foto|picture|captura|screenshot)s?\b\s*",
    re.IGNORECASE,
)


def _clean_schedule_text(text: str) -> str:
    """Elimina marcadores de imagen (standalone e inline) y colapsa blancos redundantes."""
    lines = []
    for line in str(text or "").splitlines():
        if _IMAGE_MARKER_RE.match(line):
            continue
        cleaned_line = _IMAGE_INLINE_RE.sub(" ", line).strip()
        if cleaned_line:
            lines.append(cleaned_line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_fixed_schedule_section(
    text: str,
    schedule_type: ScheduleBlockType,
    *,
    timezone: str = "America/Bogota",
) -> SectionPipelineResult:
    """Parsea una sección académica o laboral con el mismo pipeline."""

    cleaned = _clean_schedule_text(text)

    context_blocks, context_clarifications, pending_items = parse_schedule_section_with_context(
        cleaned,
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

    normalized = normalize_schedule_section(cleaned, schedule_type, timezone=timezone)
    if normalized.needs_clarification:
        if context_blocks and not pending_items:
            return SectionPipelineResult(
                blocks=context_blocks,
                clarifications=[],
                needs_clarification=False,
                parser_used="contextual",
            )
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

    cleaned = _clean_schedule_text(text)
    normalized = normalize_schedule_section(
        cleaned,
        "extracurricular",
        timezone=timezone,
    )
    items, missing, pending_items = parse_extracurricular_items_with_context(
        cleaned,
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
