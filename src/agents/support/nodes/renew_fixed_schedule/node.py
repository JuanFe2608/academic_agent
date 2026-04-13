"""Nodo para renovar un horario fijo ya expirado."""

from __future__ import annotations

from agents.support.flows.scheduling.fixed_schedule_renewal_service import (
    handle_fixed_schedule_renewal_turn,
)
from agents.support.nodes.utils import detect_new_input
from agents.support.state import AgentState


def renew_fixed_schedule(state: AgentState) -> dict:
    """Orquesta el subflujo conversacional de renovación del horario fijo."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    return handle_fixed_schedule_renewal_turn(
        state,
        has_new_input=has_new_input,
        last_text=last_text,
        current_count=current_count,
    )
