"""Nodo para mostrar la agenda semanal del estudiante con imagen del horario."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState

_DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAY_LABELS = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}
_BLOCK_TYPE_EMOJI = {
    "academic": "📚",
    "work": "💼",
    "extracurricular": "⚽",
}


def view_weekly_agenda(state: AgentState) -> dict:
    """Muestra la agenda semanal organizada por dia con imagen del horario."""

    messages = state.get("messages", [])
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    blocks = [b for b in schedule_state.blocks if getattr(b, "is_active", True)]
    timezone = str(state.get("timezone", "America/Bogota"))

    content = _build_agenda_content(blocks, timezone)

    return {
        "phase": "running",
        "awaiting_user_input": False,
        "messages": append_message(messages, "assistant", content),
    }


# ---------------------------------------------------------------------------
# Content builder — image preferida, texto de respaldo
# ---------------------------------------------------------------------------


def _build_agenda_content(blocks: list, timezone: str) -> str | list:
    """Devuelve contenido multimodal (imagen + texto) o solo texto si la imagen falla."""
    if not blocks:
        return (
            "No tienes actividades registradas en tu horario fijo todavía. 📅\n\n"
            "Puedes pedirme que agreguemos actividades o que organicemos tu semana."
        )

    caption = _build_caption(blocks)

    try:
        from agents.support.scheduling.render import build_rendered_schedule_message_content
        content, _ = build_rendered_schedule_message_content(
            caption,
            blocks,
            timezone_name=timezone,
        )
        return content
    except Exception:
        # Fallback a texto si el renderer falla (PIL no disponible, etc.)
        return _format_weekly_agenda_text(blocks)


def _build_caption(blocks: list) -> str:
    """Caption corto para la imagen del horario (max ~300 chars)."""
    total = len(blocks)
    days_with_blocks = len({getattr(b, "day_of_week", "") for b in blocks if getattr(b, "day_of_week", "")})
    return (
        f"🗓️ Tu horario semanal — {total} bloque{'s' if total != 1 else ''} "
        f"en {days_with_blocks} día{'s' if days_with_blocks != 1 else ''}.\n\n"
        "¿Quieres organizar bloques de estudio en los espacios libres? 📚"
    )


# ---------------------------------------------------------------------------
# Fallback texto
# ---------------------------------------------------------------------------


def _format_weekly_agenda_text(blocks: list) -> str:
    if not blocks:
        return (
            "No tienes actividades registradas en tu horario fijo todavía. 📅\n\n"
            "Puedes pedirme que agreguemos actividades o que organicemos tu semana."
        )

    by_day: dict[str, list] = {day: [] for day in _DAY_ORDER}
    for block in blocks:
        day = getattr(block, "day_of_week", None)
        if day in by_day:
            by_day[day].append(block)

    for day in _DAY_ORDER:
        by_day[day].sort(key=lambda b: getattr(b, "start_time", ""))

    lines = ["🗓️ Tu horario semanal\n"]
    has_any = False
    for day in _DAY_ORDER:
        day_blocks = by_day[day]
        label = _DAY_LABELS[day]
        lines.append(f"*{label}*")
        if not day_blocks:
            lines.append("Sin actividades registradas")
        else:
            has_any = True
            for block in day_blocks:
                emoji = _BLOCK_TYPE_EMOJI.get(getattr(block, "block_type", ""), "✅")
                title = getattr(block, "title", "Actividad")
                start = getattr(block, "start_time", "")
                end = getattr(block, "end_time", "")
                lines.append(f"{emoji} {title} — {start} a {end}")
        lines.append("")

    if has_any:
        lines.append("¿Quieres que te ayude a organizar bloques de estudio en los espacios libres? 📚")
    return "\n".join(lines).strip()
