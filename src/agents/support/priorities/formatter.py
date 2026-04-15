"""Formateadores deterministas del subflujo de prioridades."""

from __future__ import annotations

from schemas.planning import SubjectItem


def build_priorities_prompt(
    subjects: list[SubjectItem],
    *,
    source: str,
    week_start: str | None = None,
    week_end: str | None = None,
) -> str:
    """Construye el prompt base para iniciar el snapshot semanal."""

    if source == "derived_from_schedule":
        intro = "Detecté estas materias a partir de tu horario fijo."
    elif source == "state.subjects":
        intro = "Ya tengo una base de materias en tu estado actual."
    else:
        intro = "Voy a afinar tus prioridades de la semana."

    lines = [
        "📚 Antes de armar tu plan semanal, revisemos tus prioridades de esta semana.",
        intro,
    ]
    if week_start and week_end:
        lines.append(f"Semana: {week_start} a {week_end}.")
    if subjects:
        lines.extend(["", "Materias detectadas:", *_numbered_subject_lines(subjects)])
    lines.extend(
        [
            "",
            "¿Quieres actualizarlas ahora?",
            "Responde: `Sí, actualizarlas` o `Después`.",
        ]
    )
    return "\n".join(lines)


def build_top_subjects_prompt(subjects: list[SubjectItem]) -> str:
    """Pide el ranking de importancia semanal."""

    expected = min(3, len(subjects))
    example = "3,1,2" if expected >= 3 else "1,2" if expected == 2 else "1"
    count_label = "número" if expected == 1 else "números"
    return "\n".join(
        [
            "📌 ¿Cuáles son las materias más importantes para ti esta semana?",
            *_numbered_subject_lines(subjects),
            "",
            f"Respóndeme con {expected} {count_label} en orden. Ejemplo: `{example}`.",
        ]
    )


def build_subject_urgency_prompt(
    subjects: list[SubjectItem],
    subject_number: int,
) -> str:
    """Pregunta por eventos próximos de una materia específica."""

    subject = subjects[subject_number - 1]
    return "\n".join(
        [
            f"⚠️ Materia {subject_number} de {len(subjects)}: {subject.nombre}",
            f"Carga detectada: {_format_weekly_load(subject.carga_semanal_min)}.",
            "",
            "¿Tienes algún quiz, parcial, entrega, exposición o actividad próxima de esta materia esta semana?",
            "",
            "Puedes responder natural, por ejemplo: `parcial viernes`, `entrega lunes` o `no`.",
        ]
    )


def build_difficult_subjects_prompt(subjects: list[SubjectItem]) -> str:
    """Pregunta por dificultad percibida semanal."""

    max_count = min(3, len(subjects))
    selection_hint = (
        f"Responde hasta {max_count} números separados por coma"
        if max_count > 1
        else "Responde con 1 número"
    )
    return "\n".join(
        [
            "🧩 ¿Cuáles son las materias que más se te están dificultando esta semana?",
            *_numbered_subject_lines(subjects),
            "",
            f"{selection_hint}, o `ninguna`.",
        ]
    )


def build_weekly_priority_summary_prompt(subjects: list[SubjectItem]) -> str:
    """Resume el snapshot semanal y pide confirmación."""

    grouped = {
        "alta": [subject.nombre for subject in subjects if subject.prioridad == "alta"],
        "media": [subject.nombre for subject in subjects if subject.prioridad == "media"],
        "baja": [subject.nombre for subject in subjects if subject.prioridad == "baja"],
    }
    lines = ["✅ Así queda tu prioridad semanal:"]
    for level in ("alta", "media", "baja"):
        names = ", ".join(grouped[level]) if grouped[level] else "ninguna"
        lines.append(f"- {level}: {names}")
    lines.extend(
        [
            "",
            "Base del cálculo: importancia semanal, urgencia por fecha, dificultad percibida y carga del horario.",
            "Si te parece bien, responde `confirmar` y paso al plan semanal. Si algo no cuadra, responde `editar`.",
        ]
    )
    return "\n".join(lines)


def build_priorities_invalid_prompt(error: str, subjects: list[SubjectItem], *, source: str) -> str:
    """Construye el re-prompt cuando la entrada no cumple el formato."""

    return f"{error}\n\n{build_priorities_prompt(subjects, source=source)}"


def build_priorities_processing_message(subjects: list[SubjectItem]) -> str:
    """Mensaje corto antes de recalcular el plan semanal."""

    if not subjects:
        return "Listo 💡 Ahora voy a armar tu plan semanal con la base actual."
    names = ", ".join(subject.nombre for subject in subjects[:3])
    suffix = "" if len(subjects) <= 3 else ", ..."
    return f"Listo 💡 Ahora voy a armar tu plan semanal priorizando: {names}{suffix}."


def _numbered_subject_lines(subjects: list[SubjectItem]) -> list[str]:
    if not subjects:
        return ["No tengo materias activas todavía."]
    return [
        f"{index}. {subject.nombre} ({_format_weekly_load(subject.carga_semanal_min)})"
        for index, subject in enumerate(subjects, start=1)
    ]


def _format_weekly_load(minutes: int | None) -> str:
    if minutes is None:
        return "sin minutos semanales detectados"
    return f"{int(minutes)} min/semana"
