"""Formato conversacional resumido para bloques y conflictos."""

from __future__ import annotations

from collections import defaultdict

from .constants import DAY_LABELS, DAY_ORDER
from .models import (
    ScheduleConflict,
    WeeklyScheduleBlock,
    ensure_schedule_conflict,
    ensure_weekly_block,
)


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
            f"{conflict.overlap_start}-{conflict.overlap_end} se cruza con {conflict.right_title}."
        )
    lines.append("")
    lines.append(
        "No es lo más recomendable para una buena planificación. "
        "¿Quieres dejarlo así o prefieres corregirlo?"
    )
    return "\n".join(lines)
