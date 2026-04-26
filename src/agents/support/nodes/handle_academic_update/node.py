"""Nodo fino para cambios académicos puntuales fuera del flujo semanal."""

from __future__ import annotations

from agents.support.dependencies import get_academic_update_orchestrator, get_tracking_service
from agents.support.flows.academic_update import (
    handle_activity_confirmation,
    handle_priority_update,
    try_handle_activity_request,
    try_handle_session_tracking,
)
from agents.support.nodes.utils import detect_new_input
from agents.support.state import AgentState
from services.conversation.state_helpers import ensure_interaction_state
from services.planning.academic_update_orchestrator import reference_date


def handle_academic_update(state: AgentState) -> dict:
    """Gestiona actividades puntuales y señales académicas sin cuestionario semanal."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    timezone = state.get("timezone", "America/Bogota")
    ref_date = reference_date(timezone)
    interaction = ensure_interaction_state(state)
    orchestrator = get_academic_update_orchestrator()
    student_id = _student_id(state)
    activities = orchestrator.load_activities(student_id, state.get("academic_activities", []))

    confirmation_payload = dict(interaction.last_confirmation_payload or {})
    if interaction.confirmation_pending and confirmation_payload.get("domain") == "activity_management":
        return handle_activity_confirmation(
            state,
            activities=activities,
            payload=confirmation_payload,
            last_text=last_text,
            current_count=current_count,
            timezone=timezone,
            ref_date=ref_date,
            student_id=student_id,
            orchestrator=orchestrator,
        )

    tracking = try_handle_session_tracking(
        state,
        last_text=last_text,
        current_count=current_count,
        timezone=timezone,
        interaction=interaction,
        student_id=student_id,
        tracking_service=get_tracking_service(),
    )
    if tracking is not None:
        return tracking

    activity = try_handle_activity_request(
        state,
        last_text=last_text,
        current_count=current_count,
        ref_date=ref_date,
        timezone=timezone,
        activities=activities,
        interaction=interaction,
    )
    if activity is not None:
        return activity

    return handle_priority_update(
        state,
        last_text=last_text,
        current_count=current_count,
        timezone=timezone,
        ref_date=ref_date,
        orchestrator=orchestrator,
    )


def _student_id(state: AgentState) -> int | None:
    profile = state.get("student_profile", {})
    if hasattr(profile, "persisted_student_id"):
        return profile.persisted_student_id
    if isinstance(profile, dict):
        value = profile.get("persisted_student_id")
        return int(value) if value else None
    return None
