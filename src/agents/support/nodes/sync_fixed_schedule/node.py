"""Nodo para sincronizar el horario fijo confirmado hacia Outlook."""

from __future__ import annotations

from datetime import date

from agents.support.dependencies import get_outlook_fixed_schedule_sync_service
from agents.support.nodes.utils import append_message
from agents.support.state import AgentState
from services.scheduling import format_schedule_end_date


def sync_fixed_schedule(state: AgentState) -> dict:
    """Sincroniza a Outlook sin bloquear la continuidad del flujo principal."""

    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    calendar_state = dict(state.get("calendar", {}))

    result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=schedule_state.get("persisted_profile_id"),
        calendar_state=calendar_state,
        calendar_id=calendar_state.get("calendar_id"),
    )

    if result.synced:
        return {
            "calendar": {
                **calendar_state,
                "provider": "outlook",
                "authorized": True,
                "synced_event_map": dict(result.synced_event_map),
            },
            "phase": "study_profile",
            "awaiting_user_input": False,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                (
                    "✅ También guardé tu horario fijo en Outlook "
                    f"hasta el {format_schedule_end_date(_parse_schedule_end_date(schedule_state))}."
                ),
            ),
        }

    message = (
        "Tu horario quedó guardado en el sistema, pero no pude sincronizarlo con Outlook.\n"
        f"Detalle técnico: {result.detail or result.error_code or 'desconocido'}"
    )
    return {
        "calendar": {
            **calendar_state,
            "provider": calendar_state.get("provider") or "outlook",
            "synced_event_map": dict(result.synced_event_map),
        },
        "phase": "study_profile",
        "awaiting_user_input": False,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            message,
        ),
    }


def _parse_schedule_end_date(schedule_state: dict) -> date | None:
    raw_value = str(schedule_state.get("schedule_end_date") or "").strip()
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None
