"""Formateadores del subflujo de prioridades."""

from __future__ import annotations

from datetime import date

from schemas.planning import SubjectItem

_DAY_NAMES = {
    "Monday": "lunes",
    "Tuesday": "martes",
    "Wednesday": "miércoles",
    "Thursday": "jueves",
    "Friday": "viernes",
    "Saturday": "sábado",
    "Sunday": "domingo",
}


def build_auto_priority_prompt(
    subjects: list[SubjectItem],
    *,
    week_start: str | None = None,
    week_end: str | None = None,
) -> str:
    """Muestra el orden de prioridades calculado automáticamente y pide contexto abierto."""

    lines = ["📚 Organicé tus materias para esta semana según tu horario y actividades registradas."]
    if week_start and week_end:
        lines.append(f"Semana: {week_start} a {week_end}.")
    if subjects:
        lines.extend(["", "Orden de prioridades:"])
        for index, subject in enumerate(subjects, start=1):
            justification = _subject_justification(subject)
            lines.append(f"{index}. {subject.nombre} — {justification}")
    lines.extend(
        [
            "",
            "¿Hay algo que no haya captado? Por ejemplo: un quiz nuevo, una entrega que aún no registré, o algo que cambió esta semana.",
            'Si ya está todo bien, responde "listo".',
        ]
    )
    return "\n".join(lines)


def build_priorities_processing_message(subjects: list[SubjectItem]) -> str:
    """Mensaje corto antes de recalcular el plan semanal."""

    if not subjects:
        return "Listo 💡 Ahora voy a armar tu plan semanal con la base actual."
    names = ", ".join(subject.nombre for subject in subjects[:3])
    suffix = "" if len(subjects) <= 3 else ", ..."
    return f"Listo 💡 Ahora voy a armar tu plan semanal priorizando: {names}{suffix}."


def _subject_justification(subject: SubjectItem) -> str:
    """Construye una línea de justificación concisa para una materia."""

    if subject.urgency_type and subject.urgency_due_at:
        label = _activity_label(subject.urgency_type)
        formatted_date = _format_due_date(subject.urgency_due_at)
        return f"{label} el {formatted_date}" if formatted_date else f"{label} próximo"
    if subject.urgencia == "alta":
        return "actividad urgente esta semana"
    if subject.urgencia == "media":
        return "actividad próxima"
    if subject.carga_semanal_min:
        return f"repaso preventivo ({subject.carga_semanal_min} min/semana)"
    return "incluida en tu horario"


def _activity_label(activity_type: str) -> str:
    return {
        "parcial": "parcial",
        "quiz": "quiz",
        "tarea": "entrega de tarea",
        "taller": "taller",
        "entrega": "entrega",
        "exposicion": "exposición",
        "proyecto": "entrega de proyecto",
        "estudio_pendiente": "sesión pendiente",
    }.get(activity_type, activity_type)


def _format_due_date(due_at: str | None) -> str | None:
    if not due_at:
        return None
    try:
        parsed = date.fromisoformat(str(due_at).strip()[:10])
        day_name = _DAY_NAMES.get(parsed.strftime("%A"), parsed.strftime("%A").lower())
        return f"{day_name} {parsed.day}/{parsed.month}"
    except ValueError:
        return None
