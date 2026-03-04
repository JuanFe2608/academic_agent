"""Nodo para preguntar por actividades extracurriculares."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    parse_yes_no,
)
from agents.support.state import AgentState

from .prompt import PROMPT, PROMPT_TYPE


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
            "extras_collect_stage": "awaiting_type",
            "extras_pending_is_variable": None,
            "phase": "extras",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                PROMPT_TYPE,
            ),
        }

    if answer is False:
        return {
            "extras_has_any": False,
            "extras_collect_stage": "done",
            "extras_pending_is_variable": None,
            "phase": "draft",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": False,
            "messages": append_message(messages, "assistant", "Perfecto, continuemos."),
        }

    return {
        "extras_has_any": state.get("extras_has_any"),
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT),
    }
