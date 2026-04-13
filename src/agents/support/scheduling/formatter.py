"""Formato conversacional resumido para bloques y conflictos."""

from __future__ import annotations

from collections import defaultdict

from services.scheduling.constants import DAY_LABELS, DAY_ORDER, ScheduleBlockType
from services.scheduling.models import (
    ScheduleConflict,
    WeeklyScheduleBlock,
    ensure_schedule_conflict,
    ensure_weekly_block,
)

_TYPE_LABELS = {
    "academic": "académico",
    "work": "laboral",
    "extracurricular": "extracurricular",
}


def build_schedule_summary(blocks: list[WeeklyScheduleBlock]) -> str:
    """Construye un resumen corto ordenado por día."""

    if not blocks:
        return "🗓️ Aún no tengo bloques suficientes para mostrar un horario."

    grouped: dict[str, list[WeeklyScheduleBlock]] = defaultdict(list)
    normalized_blocks = [ensure_weekly_block(block) for block in blocks]
    for block in sorted(normalized_blocks, key=lambda item: (DAY_ORDER.index(item.day_of_week), item.start_time, item.title.lower())):
        grouped[block.day_of_week].append(block)

    lines = ["🗓️ Esto fue lo que entendí de tu horario semanal:"]
    for day in DAY_ORDER:
        for block in grouped.get(day, []):
            lines.append(
                f"- {DAY_LABELS[day]}: {block.title} — {block.start_time}-{block.end_time}"
            )
    return "\n".join(lines)


def build_conflict_message(conflicts: list[ScheduleConflict]) -> str:
    """Construye un mensaje breve con los cruces detectados."""

    if not conflicts:
        return ""

    lines = ["⚠️ Encontré cruces en tu horario:"]
    for raw_conflict in conflicts:
        conflict = ensure_schedule_conflict(raw_conflict)
        lines.append(
            f"- {DAY_LABELS[conflict.day_of_week]}: {conflict.left_title} "
            f"({_TYPE_LABELS.get(conflict.left_type, conflict.left_type)}) "
            f"{conflict.overlap_start}-{conflict.overlap_end} se cruza con "
            f"{conflict.right_title} ({_TYPE_LABELS.get(conflict.right_type, conflict.right_type)})."
        )
    lines.append("")
    lines.append(
        "No es lo más recomendable para una buena planificación."
    )
    lines.append("(Escribe el número de la opción que quieres elegir)")
    lines.append("1. Sí, dejarlo así")
    lines.append("2. No, quiero corregirlo")
    return "\n".join(lines)


def build_section_summary(
    blocks: list[WeeklyScheduleBlock],
    block_type: ScheduleBlockType,
) -> str:
    """Construye un resumen corto de una sola sección del horario."""

    normalized_blocks = [
        ensure_weekly_block(block)
        for block in blocks
        if ensure_weekly_block(block).block_type == block_type
    ]
    normalized_blocks.sort(
        key=lambda item: (DAY_ORDER.index(item.day_of_week), item.start_time, item.title.lower())
    )
    if not normalized_blocks:
        return "No tengo registros para esa sección todavía."

    section_label = {
        "academic": "Horario académico actual:",
        "work": "Horario laboral actual:",
        "extracurricular": "Actividades extracurriculares actuales:",
    }[block_type]
    lines = [section_label]
    for block in normalized_blocks:
        lines.append(
            f"- {DAY_LABELS[block.day_of_week]}: {block.title} — {block.start_time}-{block.end_time}"
        )
    return "\n".join(lines)
