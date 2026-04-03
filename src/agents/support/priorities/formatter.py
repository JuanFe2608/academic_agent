"""Formateadores deterministas del subflujo de prioridades."""

from __future__ import annotations

from agents.support.state import SubjectItem


def build_priorities_prompt(subjects: list[SubjectItem], *, source: str) -> str:
    """Construye el prompt base para capturar prioridades académicas."""

    if source == "derived_from_schedule":
        intro = "Detecté estas materias a partir de tu horario fijo."
    elif source == "state.subjects":
        intro = "Ya tengo una base de materias en tu estado actual."
    else:
        intro = "Voy a afinar las materias para tu plan semanal."

    lines = [
        "Antes de cerrar, quiero afinar tus prioridades académicas 🎯",
        intro,
    ]
    if subjects:
        lines.extend(["", "Materias actuales:"])
        for subject in subjects:
            urgency = subject.urgencia or "sin definir"
            load = (
                f"{subject.carga_semanal_min} min/sem"
                if subject.carga_semanal_min is not None
                else "carga sin definir"
            )
            lines.append(
                f"- {subject.nombre}: prioridad {subject.prioridad}, dificultad {subject.dificultad}/5, urgencia {urgency}, {load}."
            )
    lines.extend(
        [
            "",
            "Puedes responder de una de estas formas:",
            "1) Escribe `usar horario` para quedarnos con lo detectado.",
            "2) Escribe `omitir` para dejar este ajuste para después.",
            "3) Envíame tus materias reales, una por línea, así:",
            "Materia | prioridad | dificultad | urgencia | carga semanal",
            "Ejemplo:",
            "Cálculo | alta | 4 | alta | 4h",
            "Programación | media | 3 | media | 180",
        ]
    )
    return "\n".join(lines)


def build_priorities_invalid_prompt(error: str, subjects: list[SubjectItem], *, source: str) -> str:
    """Construye el re-prompt cuando la entrada no cumple el formato."""

    return f"{error}\n\n{build_priorities_prompt(subjects, source=source)}"


def build_priorities_processing_message(subjects: list[SubjectItem]) -> str:
    """Mensaje corto antes de recalcular el plan semanal."""

    if not subjects:
        return "Perfecto. Voy a recalcular tu plan semanal con la base actual."
    names = ", ".join(subject.nombre for subject in subjects[:3])
    suffix = "" if len(subjects) <= 3 else ", ..."
    return f"Perfecto. Voy a recalcular tu plan semanal con: {names}{suffix}."
