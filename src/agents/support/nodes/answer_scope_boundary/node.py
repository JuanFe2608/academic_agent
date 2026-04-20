"""Nodo para responder mensajes fuera del alcance academico del agente."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from services.conversation.scope_policy import decide_scope, render_scope_response
from services.conversation.state_helpers import update_interaction_state


def answer_scope_boundary(state: AgentState) -> dict:
    """Responde sin reiniciar el flujo cuando llega una consulta fuera del alcance."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    decision = decide_scope(last_text)
    interaction_update = update_interaction_state(
        state,
        active_intent=decision.intent,
        current_domain=decision.domain,
        router_confidence=decision.confidence,
        clarification_needed=decision.action == "redirect",
    )

    return {
        "phase": "end",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(messages, "assistant", render_scope_response(decision)),
        **interaction_update,
    }


__all__ = ["answer_scope_boundary"]
