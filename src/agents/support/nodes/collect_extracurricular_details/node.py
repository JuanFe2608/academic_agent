"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    parse_yes_no,
)
from agents.support.scheduling import merge_section_blocks, normalize_schedule_section
from agents.support.state import AgentState

from .prompt import (
    PROMPT_DETAILS,
    PROMPT_MORE,
)
from .parsing import parse_extracurricular_items, parse_extracurricular_text


def collect_extracurricular_details(state: AgentState) -> dict:
    """Recolecta actividades extracurriculares y avanza al draft."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    stage = state.get("extras_collect_stage") or "awaiting_type"
    pending_is_variable = state.get("extras_pending_is_variable")

    if stage == "awaiting_more":
        answer = parse_yes_no(last_text) if has_new_input else None
        if answer is False:
            return {
                "extras_collect_stage": "done",
                "extras_pending_is_variable": None,
                "phase": "draft",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": False,
                "messages": append_message(
                    messages,
                    "assistant",
                    "Listo. Voy a preparar el resumen de tu horario.",
                ),
            }
        if answer is True or (has_new_input and last_text and answer is None):
            if answer is True:
                return {
                    "extras_collect_stage": "awaiting_details",
                    "extras_pending_is_variable": None,
                    "phase": "extras",
                    "user_message_count": current_count,
                    "last_user_text": last_text,
                    "awaiting_user_input": True,
                    "messages": append_message(messages, "assistant", PROMPT_DETAILS),
                }
            stage = "awaiting_details"
        else:
            return {
                "extras_collect_stage": "awaiting_more",
                "phase": "extras",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_MORE),
            }

    if stage in (None, "awaiting_type"):
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_DETAILS),
        }

    if not has_new_input or not last_text:
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_DETAILS),
        }

    result = normalize_schedule_section(
        last_text,
        "extracurricular",
        timezone=state.get("timezone", "America/Bogota"),
    )
    if result.needs_clarification:
        prompt = PROMPT_DETAILS + "\n" + "\n".join(result.clarifications)
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    items, _ = parse_extracurricular_items(last_text, expected_is_variable=pending_is_variable)
    extracurricular = list(state.get("extracurricular", []))
    extracurricular.extend(items)
    schedule_state = dict(state.get("schedule", {}))
    schedule_blocks = merge_section_blocks(
        list(schedule_state.get("blocks", [])),
        result.blocks,
    )
    return {
        "extracurricular": extracurricular,
        "schedule": {
            **schedule_state,
            "blocks": schedule_blocks,
            "summary_text": None,
            "review_stage": "idle",
            "conflicts": [],
        },
        "extras_collect_stage": "awaiting_more",
        "extras_pending_is_variable": None,
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }
