"""Nodo para preguntar por actividades extracurriculares."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    parse_yes_no,
)
from agents.support.state import AgentState

from .prompt import PROMPT
from ..collect_extracurricular_details.prompt import PROMPT_DETAILS


def ask_extracurricular(state: AgentState) -> dict:
    """Pregunta si existen actividades extracurriculares."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    answer = parse_yes_no(last_text) if has_new_input else None

    if answer is True:
        return {
            "extras_has_any": True,
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": None,
            "extras_pending_items": [],
            "phase": "extras",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                PROMPT_DETAILS,
            ),
        }

    if answer is False:
        return {
            "extras_has_any": False,
            "extras_collect_stage": "done",
            "extras_pending_is_variable": None,
            "extras_pending_items": [],
            "phase": "draft",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Voy a revisar el horario con lo que ya me compartiste.",
            ),
        }

    return {
        "extras_has_any": state.get("extras_has_any"),
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT),
    }
