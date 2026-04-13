"""Utilidades puras para el subestado de actividades extracurriculares."""

from __future__ import annotations

from collections import defaultdict

from schemas.scheduling import ExtracurricularItem, PendingExtracurricularItem
from services.scheduling.constants import DAY_LABELS, DAY_ORDER
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from services.scheduling.activity_matching import normalize_text


def coerce_extracurricular_pending_items(
    raw_items: list[PendingExtracurricularItem] | list[dict],
) -> list[PendingExtracurricularItem]:
    """Convierte pendientes extracurriculares al tipo canónico."""

    return [
        item
        if isinstance(item, PendingExtracurricularItem)
        else PendingExtracurricularItem(**item)
        for item in raw_items
    ]


def merge_extracurricular_items(
    existing: list[ExtracurricularItem] | list[dict],
    new_items: list[ExtracurricularItem],
) -> list[ExtracurricularItem]:
    """Fusiona actividades evitando duplicados evidentes."""

    merged: list[ExtracurricularItem] = []
    seen: set[tuple[str, tuple[str, ...], str, str, bool]] = set()
    for raw_item in list(existing) + list(new_items):
        item = (
            raw_item
            if isinstance(raw_item, ExtracurricularItem)
            else ExtracurricularItem(**raw_item)
        )
        key = (
            normalize_text(item.nombre),
            tuple(item.dias),
            str(item.hora_inicio or ""),
            str(item.hora_fin or ""),
            bool(item.es_variable),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def build_extracurricular_item_source_text(item: ExtracurricularItem) -> str:
    """Serializa una actividad completa a texto estable para re-normalización."""

    days = ", ".join(item.dias) if item.dias else ""
    hours = ""
    if item.hora_inicio and item.hora_fin:
        hours = f"{item.hora_inicio}-{item.hora_fin}"
    return " ".join(part for part in [item.nombre.strip(), days, hours] if part).strip()


def build_extracurricular_items_source_text(
    items: list[ExtracurricularItem],
) -> str:
    """Serializa varias actividades completas para re-normalizarlas como bloques."""

    lines = [
        build_extracurricular_item_source_text(item)
        for item in items
        if item.dias and item.hora_inicio and item.hora_fin
    ]
    return "\n".join(line for line in lines if line)


def build_extracurricular_items_from_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[ExtracurricularItem]:
    """Reconstruye actividades extracurriculares a partir de bloques fijos."""

    grouped: dict[tuple[str, str, str], list[WeeklyScheduleBlock]] = defaultdict(list)
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        if block.block_type != "extracurricular":
            continue
        grouped[(block.title, block.start_time, block.end_time)].append(block)

    items: list[ExtracurricularItem] = []
    for (title, start_time, end_time), grouped_blocks in grouped.items():
        ordered_blocks = sorted(
            grouped_blocks,
            key=lambda item: DAY_ORDER.index(item.day_of_week),
        )
        spanish_days = [DAY_LABELS[item.day_of_week] for item in ordered_blocks]
        detail = (
            f"{', '.join(spanish_days)} {start_time}-{end_time}"
            if spanish_days
            else f"{start_time}-{end_time}"
        )
        items.append(
            ExtracurricularItem(
                nombre=title,
                es_variable=False,
                detalle=detail,
                dias=spanish_days,
                hora_inicio=start_time,
                hora_fin=end_time,
            )
        )
    return items


__all__ = [
    "build_extracurricular_items_from_blocks",
    "build_extracurricular_item_source_text",
    "build_extracurricular_items_source_text",
    "coerce_extracurricular_pending_items",
    "merge_extracurricular_items",
]
