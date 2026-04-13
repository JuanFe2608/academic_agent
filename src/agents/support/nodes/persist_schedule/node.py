"""Nodo para persistir el horario semanal recurrente."""

from __future__ import annotations

from datetime import date

from agents.support.dependencies import get_schedule_service
from agents.support.nodes.utils import append_message
from agents.support.state import AgentState


def persist_schedule(state: AgentState) -> dict:
    """Guarda el horario confirmado y deja el flujo listo para cierre."""

    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    schedule_end_date = _parse_schedule_end_date(schedule_state.get("schedule_end_date"))

    result = get_schedule_service().persist_schedule(
        student_id=profile.get("persisted_student_id"),
        occupation=str(profile.get("occupation") or ""),
        timezone=state.get("timezone", "America/Bogota"),
        summary_text=str(schedule_state.get("summary_text") or ""),
        blocks=list(schedule_state.get("blocks", [])),
        conflicts=list(schedule_state.get("conflicts", [])),
        conflicts_accepted=bool(schedule_state.get("conflicts_accepted")),
        schedule_end_date=schedule_end_date,
    )

    if result.persisted:
        return {
            "schedule": {
                **schedule_state,
                "persisted_profile_id": result.schedule_profile_id,
                "persistence_error": None,
                "schedule_end_date": (
                    result.schedule_end_date.isoformat()
                    if result.schedule_end_date is not None
                    else schedule_state.get("schedule_end_date")
                ),
            },
            "phase": "schedule_sync",
            "awaiting_user_input": False,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                "✅ Tu horario semanal quedó guardado correctamente.",
            ),
        }

    return {
        "schedule": {
            **schedule_state,
            "persistence_error": result.error_code,
        },
        "phase": "end",
        "awaiting_user_input": False,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            "No pude guardar el horario en la base de datos.\n"
            f"Detalle técnico: {result.detail or result.error_code or 'desconocido'}",
        ),
    }


def _parse_schedule_end_date(raw_value: object) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
