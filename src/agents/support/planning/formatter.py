"""Formateadores deterministas del plan semanal de estudio."""

from __future__ import annotations

from schemas.planning import StudyPlanState, SubjectItem
from schemas.reminders import RemindersState


def build_study_plan_summary(
    subjects: list[SubjectItem],
    study_plan: StudyPlanState,
    *,
    reminders: RemindersState | dict | None = None,
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
    if study_plan.persisted_profile_id:
        lines.append("Plan guardado en tu perfil académico.")
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
    if rules.get("external_sync_requires_confirmation"):
        lines.extend(
            [
                "",
                "No he creado eventos en Outlook ni tareas en Microsoft To Do. Antes de hacerlo te pediré confirmación aparte.",
            ]
        )
    lines.extend(_operational_status_lines(study_plan, reminders))
    raw_guidance = rules.get("rag_session_guidance") or {}
    guidance = dict(raw_guidance) if isinstance(raw_guidance, dict) else {}
    if guidance.get("answer"):
        lines.extend(
            [
                "",
                "Guía sugerida para la primera sesión:",
                str(guidance["answer"]),
            ]
        )
        cautions = list(guidance.get("cautions") or [])
        if cautions:
            lines.append(f"Cuidado: {cautions[0]}")
    applied_guidance = _first_applied_method_guidance(rules.get("applied_method_guidance"))
    if applied_guidance:
        lines.extend(
            [
                "",
                "Método aplicado para una actividad prioritaria:",
                str(applied_guidance.get("summary") or ""),
            ]
        )
        steps = list(applied_guidance.get("steps") or [])
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps[:3], start=1))
    return "\n".join(lines)


def _operational_status_lines(
    study_plan: StudyPlanState,
    reminders: RemindersState | dict | None,
) -> list[str]:
    lines: list[str] = []
    if study_plan.materialization_error:
        lines.extend(
            [
                "",
                "No pude dejar listas las sesiones fechadas todavía. El plan queda guardado para reintentarlo luego.",
            ]
        )
        return lines

    if study_plan.materialized_instance_count is not None:
        count = int(study_plan.materialized_instance_count or 0)
        through = (
            f" hasta {study_plan.materialized_through_date}"
            if study_plan.materialized_through_date
            else ""
        )
        lines.extend(["", f"Sesiones materializadas: {count}{through}."])
        if study_plan.superseded_instance_count:
            lines.append(
                f"Reemplacé {study_plan.superseded_instance_count} sesiones futuras de un plan anterior."
            )

    reminder_state = _coerce_reminders(reminders)
    if reminder_state is None:
        return lines
    if reminder_state.last_dispatch_error:
        lines.extend(
            [
                "",
                "No pude activar recordatorios todavía. El plan queda guardado y se puede reintentar.",
            ]
        )
        return lines
    if reminder_state.last_sync_at:
        channels = _format_channels(reminder_state.policy.get("channels"))
        dispatches = int(reminder_state.created_dispatch_count or 0)
        policies = int(reminder_state.policy_count or len(reminder_state.persisted_policy_ids))
        lines.extend(
            [
                "",
                f"Recordatorios activados por {channels}: {policies} políticas, {dispatches} avisos pendientes nuevos.",
            ]
        )
    return lines


def _coerce_reminders(reminders: RemindersState | dict | None) -> RemindersState | None:
    if reminders is None:
        return None
    if isinstance(reminders, RemindersState):
        return reminders
    return RemindersState(**dict(reminders or {}))


def _format_channels(raw_channels: object) -> str:
    if isinstance(raw_channels, str):
        channels = [raw_channels]
    elif isinstance(raw_channels, (list, tuple, set)):
        channels = [str(channel) for channel in raw_channels]
    else:
        channels = ["in_app"]
    labels = {
        "in_app": "canal interno",
        "whatsapp": "WhatsApp",
        "email": "correo",
    }
    return ", ".join(labels.get(channel, channel) for channel in channels if channel) or "canal interno"


def _first_applied_method_guidance(raw_guidance: object) -> dict[str, object] | None:
    if not isinstance(raw_guidance, dict):
        return None
    items = raw_guidance.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    return dict(first) if isinstance(first, dict) else None
