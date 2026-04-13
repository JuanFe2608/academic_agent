"""Soporte puro para mensajes de pendientes extracurriculares."""

from __future__ import annotations

from schemas.scheduling import PendingExtracurricularItem
from services.scheduling.extracurricular_state import coerce_extracurricular_pending_items
from services.scheduling.heuristic_schedule_parsing import infer_title
from services.scheduling.pending_completion_support import clean_pending_display_label


def build_extracurricular_pending_prompt(
    pending_items: list[PendingExtracurricularItem] | list[dict],
) -> str:
    """Construye un prompt amigable para completar una actividad pendiente."""

    items = coerce_extracurricular_pending_items(pending_items)
    if not items:
        return (
            "🏃‍♂️ Envíame de nuevo la actividad con nombre, día o días y horario.\n"
            "Ejemplo: Lunes - Gimnasio - 18:00 a 19:00."
        )

    current = items[0]
    name = _display_pending_name(current)
    missing_text = _format_missing_fields(current.missing_fields)
    example = _build_example(current, name or "Actividad")

    lines = ["🏃‍♂️ Necesito algunos datos para cerrar bien esta actividad:"]
    if name:
        lines.append(name)
    lines.append(f"- Me falta: {missing_text}.")
    lines.append(
        f"📩 Puedes responder solo con lo que falta o enviármela de nuevo completa así: {example}."
    )
    return "\n".join(lines)


def build_extracurricular_reply_hint(item: PendingExtracurricularItem) -> str:
    """Construye una guía mínima coherente con el prompt de pendientes."""

    return build_extracurricular_pending_prompt([item])


def _display_pending_name(item: PendingExtracurricularItem) -> str:
    inferred = infer_title(
        str(item.raw_text or ""),
        default_title=str(item.nombre or "").strip(),
    ).strip()
    return clean_pending_display_label(inferred or str(item.nombre or "").strip())


def _format_missing_fields(missing_fields: list[str]) -> str:
    missing_text = ", ".join(str(field).strip() for field in missing_fields if str(field).strip())
    if missing_text == "nombre":
        return "nombre de la actividad"
    return missing_text or "algunos datos del horario"


def _build_example(item: PendingExtracurricularItem, name: str) -> str:
    day_label = _join_days(item.dias)
    if day_label:
        return f"{day_label} - {name} - 07:00 a 09:00"
    return f"Lunes - {name} - 07:00 a 09:00"


def _join_days(days: list[str]) -> str:
    cleaned = [str(day).strip() for day in days if str(day).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} y {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f" y {cleaned[-1]}"


__all__ = [
    "build_extracurricular_pending_prompt",
    "build_extracurricular_reply_hint",
]
