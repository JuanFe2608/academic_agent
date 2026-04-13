"""Soporte puro para pendientes académicos y laborales."""

from __future__ import annotations

from schemas.scheduling import PendingScheduleItem, ScheduleContextType
from services.scheduling.heuristic_schedule_parsing import infer_title
from services.scheduling.pending_completion_support import clean_pending_display_label


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
    title = _display_pending_title(current, schedule_type)
    missing_text = _format_missing_fields(schedule_type, current.missing_fields)
    example = _build_example(schedule_type, current, title)
    article = "esta" if schedule_type == "academic" else "este"
    subject_label = "materia" if schedule_type == "academic" else "horario laboral"
    pronoun = "Envíamela" if schedule_type == "academic" else "Envíamelo"

    lines = [
        f"{_emoji_for_schedule_type(schedule_type)} Necesito algunos datos para cerrar bien {article} {subject_label}:"
    ]
    if title:
        lines.append(title)
    lines.append(f"- Me falta: {missing_text}.")
    if missing_text == "AM o PM en el horario":
        lines.append(
            f"🕒 Puedes responder solo con ese dato o {pronoun.lower()} de nuevo completa así: {example}."
        )
    elif missing_text == "nombre de la materia":
        lines.append("📝 Puedes responder solo con el nombre. Ejemplo: Cálculo.")
    else:
        lines.append(
            f"📩 {pronoun} de nuevo completa así: {example}."
        )
    return "\n".join(lines)


def _display_pending_title(
    item: PendingScheduleItem,
    schedule_type: ScheduleContextType,
) -> str:
    if schedule_type == "work":
        return "Trabajo"
    inferred = infer_title(
        str(item.raw_text or ""),
        default_title=str(item.title or "").strip(),
    ).strip()
    return clean_pending_display_label(inferred or str(item.title or "").strip())


def _format_missing_fields(
    schedule_type: ScheduleContextType,
    missing_fields: list[str],
) -> str:
    missing_text = ", ".join(str(field).strip() for field in missing_fields if str(field).strip())
    if missing_text == "nombre de la materia o actividad":
        return "nombre de la materia" if schedule_type == "academic" else "nombre del horario"
    if missing_text == "aclarar AM o PM en el horario":
        return "AM o PM en el horario"
    return missing_text or "algunos datos del horario"


def _build_example(
    schedule_type: ScheduleContextType,
    item: PendingScheduleItem,
    title: str,
) -> str:
    example_title = title or ("Trabajo" if schedule_type == "work" else "Materia")
    if schedule_type == "work":
        return "Lunes a viernes - Trabajo - 07:00 a 18:00"
    day_label = _join_days(item.days)
    if day_label:
        return f"{day_label} - {example_title} - 07:00 a 09:00"
    return f"Lunes - {example_title} - 07:00 a 09:00"


def _join_days(days: list[str]) -> str:
    cleaned = [str(day).strip() for day in days if str(day).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} y {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f" y {cleaned[-1]}"


def _emoji_for_schedule_type(schedule_type: ScheduleContextType) -> str:
    return "📚" if schedule_type == "academic" else "💼"


__all__ = [
    "build_schedule_pending_prompt",
    "coerce_pending_schedule_items",
]
