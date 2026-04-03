"""Formateadores deterministas del plan semanal de estudio."""

from __future__ import annotations

from agents.support.state import StudyPlanState, SubjectItem


def build_study_plan_summary(
    subjects: list[SubjectItem],
    study_plan: StudyPlanState,
) -> str:
    """Construye un resumen textual del plan semanal generado."""

    rules = dict(study_plan.rules or {})
    primary_name = str(rules.get("primary_technique_name") or "tu técnica principal")
    unscheduled_requests = list(rules.get("unscheduled_requests") or [])
    lines = [
        "Listo. Ya actualicé tu plan semanal inicial 📚",
        f"Técnica base: {primary_name}.",
        f"Sesiones sugeridas: {len(study_plan.plan_events)}.",
    ]
    if subjects:
        lines.extend(["", "Materias priorizadas:"])
        for subject in subjects[:5]:
            urgency = subject.urgencia or "sin definir"
            load = (
                f"{subject.carga_semanal_min} min/sem"
                if subject.carga_semanal_min is not None
                else "carga sin definir"
            )
            lines.append(
                f"- {subject.nombre}: prioridad {subject.prioridad}, dificultad {subject.dificultad}/5, urgencia {urgency}, {load}."
            )
    if unscheduled_requests:
        lines.extend(
            [
                "",
                f"Quedaron {len(unscheduled_requests)} sesiones sin ubicar por las restricciones actuales.",
            ]
        )
    elif study_plan.plan_events:
        lines.extend(["", "Ya quedó una base semanal lista para la siguiente iteración del plan."])
    else:
        lines.extend(["", "Todavía no pude ubicar sesiones válidas con las restricciones actuales."])
    return "\n".join(lines)
