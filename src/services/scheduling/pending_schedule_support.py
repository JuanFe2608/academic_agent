"""Soporte puro para pendientes académicos y laborales."""

from __future__ import annotations

from schemas.scheduling import PendingScheduleItem, ScheduleContextType


def coerce_pending_schedule_items(
    raw_items: list[PendingScheduleItem] | list[dict],
) -> list[PendingScheduleItem]:
    """Convierte pendientes académicos/laborales al tipo canónico."""

    return [
        item if isinstance(item, PendingScheduleItem) else PendingScheduleItem(**item)
        for item in raw_items
    ]


def build_schedule_pending_prompt(
    schedule_type: ScheduleContextType,
    pending_items: list[PendingScheduleItem] | list[dict],
    clarifications: list[str] | None = None,
) -> str:
    """Construye un prompt corto para pedir solo el dato faltante."""

    items = coerce_pending_schedule_items(pending_items)
    if not items:
        return "\n".join(
            str(item).strip()
            for item in (clarifications or [])
            if str(item).strip()
        )

    current = items[0]
    section_label = "horario académico" if schedule_type == "academic" else "horario laboral"
    title = current.title.strip() or ("Trabajo" if schedule_type == "work" else "bloque académico")
    missing_text = ", ".join(current.missing_fields) if current.missing_fields else "datos del horario"

    lines = [f"Necesito algunos datos para cerrar bien tu {section_label}: {title}: {missing_text}."]
    if missing_text == "aclarar AM o PM en el horario":
        lines.append("Puedes responder solo con lo que falta. Ejemplo: de 7 pm a 9 pm.")
    elif missing_text == "nombre de la materia o actividad":
        lines.append("Puedes responder solo con el nombre. Ejemplo: Algebra.")
    else:
        lines.append("Si prefieres, envíalo completo en formato: Dia(s) de HH:MM a HH:MM Nombre.")
    return "\n".join(lines)


__all__ = [
    "build_schedule_pending_prompt",
    "coerce_pending_schedule_items",
]
