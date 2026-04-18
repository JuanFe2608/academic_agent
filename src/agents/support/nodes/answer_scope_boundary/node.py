"""Nodo para responder mensajes fuera del alcance academico del agente."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState

_SCOPE_BOUNDARY_MESSAGE = (
    "Estoy enfocada en ayudarte con temas académicos: agenda, plan de estudio, "
    "recordatorios, replanificación y técnicas de estudio 📚\n\n"
    "No puedo responder sobre temas generales como personajes públicos, noticias o entretenimiento. "
    "Puedes preguntarme, por ejemplo: qué es Pomodoro, cómo aplicar Feynman, cómo organizar una semana "
    "de estudio o cómo ajustar tu plan para un parcial."
)


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

    return {
        "phase": "end",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(messages, "assistant", _SCOPE_BOUNDARY_MESSAGE),
    }


__all__ = ["answer_scope_boundary"]
