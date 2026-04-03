"""Helpers compartidos del subdominio extracurricular.

Agrupa coerción, merge y mensajes auxiliares usados tanto por scheduling como
por el flujo de captura de actividades extracurriculares.
"""

from __future__ import annotations

from agents.support.nodes.utils import normalize_text
from agents.support.state import (
    ExtracurricularItem,
    PendingExtracurricularItem,
)


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
    return " ".join(
        part for part in [item.nombre.strip(), days, hours] if part
    ).strip()


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


def build_extracurricular_reply_hint(item: PendingExtracurricularItem) -> str:
    """Construye la guía mínima para completar un pendiente extracurricular."""

    missing_text = ", ".join(item.missing_fields) if item.missing_fields else ""
    if missing_text == "hora de inicio y fin":
        return "Puedes responder solo con lo que falta. Ejemplo: de 7 am a 8 am."
    return "Si prefieres, envíala completa en formato: Actividad dia(s) de HH:MM a HH:MM."
