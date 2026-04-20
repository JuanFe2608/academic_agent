"""Nodo para mostrar las tareas y actividades academicas pendientes."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.state import AgentState

_PRIORITY_EMOJI = {"alta": "🔴", "media": "🟡", "baja": "🟢"}
_PRIORITY_LABEL = {"alta": "Alta prioridad", "media": "Prioridad media", "baja": "Prioridad baja"}
_PRIORITY_ORDER = ["alta", "media", "baja"]
_TYPE_LABELS = {
    "parcial": "Parcial",
    "quiz": "Quiz",
    "tarea": "Tarea",
    "taller": "Taller",
    "entrega": "Entrega",
    "exposicion": "Exposición",
    "proyecto": "Proyecto",
    "estudio_pendiente": "Estudio pendiente",
}


def view_tasks(state: AgentState) -> dict:
    """Muestra actividades academicas pendientes agrupadas por prioridad."""

    messages = state.get("messages", [])
    activities = list(state.get("academic_activities", []))

    return {
        "phase": "running",
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            _format_tasks(activities),
        ),
    }


def _format_tasks(activities: list) -> str:
    pending = [a for a in activities if _activity_status(a) == "pending"]
    completed = [a for a in activities if _activity_status(a) == "completed"]

    if not pending and not completed:
        return (
            "No tienes actividades académicas registradas todavía. 📝\n\n"
            "Puedes decirme algo como:\n"
            "- \"Tengo parcial de cálculo el viernes\"\n"
            "- \"Agrega entrega de programación para el jueves\""
        )

    lines = ["Estas son tus actividades académicas 📝\n"]

    by_priority: dict[str, list] = {p: [] for p in _PRIORITY_ORDER}
    no_priority: list = []
    for activity in pending:
        priority = _activity_priority(activity)
        if priority in by_priority:
            by_priority[priority].append(activity)
        else:
            no_priority.append(activity)

    has_pending = False
    for priority in _PRIORITY_ORDER:
        group = by_priority[priority]
        if not group:
            continue
        has_pending = True
        emoji = _PRIORITY_EMOJI[priority]
        label = _PRIORITY_LABEL[priority]
        lines.append(f"{emoji} *{label}*")
        for activity in group:
            lines.append(_format_activity_line(activity))
        lines.append("")

    if no_priority:
        has_pending = True
        lines.append("⚪ *Sin prioridad definida*")
        for activity in no_priority:
            lines.append(_format_activity_line(activity))
        lines.append("")

    if not has_pending:
        lines.append("No tienes pendientes activos. ✅\n")

    if completed:
        recent = completed[-3:]
        lines.append("🟢 *Completadas recientemente*")
        for activity in recent:
            lines.append(f"✅ {_activity_display_name(activity)}")
        lines.append("")

    lines.append(
        "¿Quieres que convierta alguna de estas actividades en bloques de estudio en tu calendario? 📅"
    )
    return "\n".join(lines).strip()


def _format_activity_line(activity) -> str:
    name = _activity_display_name(activity)
    due = _activity_due(activity)
    return f"❌ {name}{due}"


def _activity_display_name(activity) -> str:
    activity_type = _get(activity, "activity_type", "")
    subject = _get(activity, "subject_name", "")
    title = _get(activity, "activity_title", "")
    type_label = _TYPE_LABELS.get(str(activity_type), str(activity_type).capitalize())
    if title and title != subject:
        return f"{type_label} de {subject} — {title}"
    return f"{type_label} de {subject}"


def _activity_due(activity) -> str:
    due_date = _get(activity, "due_date", "")
    if due_date:
        return f" — {due_date}"
    return ""


def _activity_status(activity) -> str:
    return str(_get(activity, "status", "pending"))


def _activity_priority(activity) -> str:
    return str(_get(activity, "priority_level", "") or "")


def _get(obj, key: str, default=""):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
