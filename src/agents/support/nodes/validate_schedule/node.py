"""Nodo LangGraph para revisar y confirmar el horario semanal."""

from __future__ import annotations

from agents.support.nodes.utils import detect_new_input
from agents.support.flows.scheduling.schedule_review_service import (
    handle_schedule_review_turn,
)
from agents.support.state import AgentState


def validate_schedule(state: AgentState) -> dict:
    """Lee el turno actual y delega la revisión del horario al servicio."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    return handle_schedule_review_turn(
        state,
        has_new_input=has_new_input,
        last_text=last_text,
        current_count=current_count,
    )
