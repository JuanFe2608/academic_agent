"""Nodo para validar el horario con el usuario."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState

from .prompt import PROMPT_CONFIRM, PROMPT_MODIFY


def validate_schedule(state: AgentState) -> dict:
    """Solicita confirmacion y registra solicitudes de cambio."""
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
            "events_validated": True,
            "phase": "sync",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Gracias. Guardare este horario."
            ),
        }

    if answer is False:
        change_request = _build_change_request(last_text)
        if not change_request:
            return {
                "events_validated": False,
                "phase": "validate",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_MODIFY),
            }

        replan = dict(state.get("replan", {}))
        replan["change_request"] = change_request
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Entendido, aplicare los cambios."
            ),
        }

    return {
        "events_validated": state.get("events_validated", False),
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_CONFIRM),
    }


def _build_change_request(text: str) -> dict | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    if re.search(r"\b1\b", normalized) or "personal" in normalized or "perfil" in normalized:
        return {"type": "manual_edit", "target": "info_personal", "details": text.strip()}
    if re.search(r"\b2\b", normalized) or "horario" in normalized or "trabajo" in normalized:
        return {"type": "manual_edit", "target": "horario", "details": text.strip()}
    if re.search(r"\b3\b", normalized) or "extracurricular" in normalized or "actividad" in normalized:
        return {"type": "manual_edit", "target": "extracurricular", "details": text.strip()}
    return None
