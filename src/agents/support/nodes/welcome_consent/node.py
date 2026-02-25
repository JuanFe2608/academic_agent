"""Nodo de bienvenida y consentimiento."""

from __future__ import annotations

from datetime import datetime, timezone

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState

from .prompt import CONSENT_PROMPT, WELCOME_MESSAGE

_GREETING_KEYWORDS = (
    "hola",
    "buenas",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "hey",
    "hello",
)

def welcome_consent(state: AgentState) -> dict:
    """Solicita consentimiento y actualiza el estado segun respuesta."""
    messages = state.get("messages", [])
    if state.get("consent", {}).get("accepted"):
        if state.get("phase") == "consent":
            return {"phase": "profile", "awaiting_user_input": False}
        return {"awaiting_user_input": False}
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )

    updates: dict = {"phase": "consent"}
    if not has_new_input:
        if not state.get("welcome_sent", False):
            updates["messages"] = append_message(
                messages, "assistant", _welcome_with_consent()
            )
            updates["welcome_sent"] = True
        else:
            updates["messages"] = append_message(messages, "assistant", CONSENT_PROMPT)
        updates["awaiting_user_input"] = True
        return updates

    updates["user_message_count"] = current_count
    updates["awaiting_user_input"] = False

    updates["last_user_text"] = last_text
    consent_answer = parse_yes_no(last_text)
    normalized = normalize_text(last_text)
    if consent_answer is True:
        updates["consent"] = {
            "accepted": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        updates["phase"] = "profile"
        updates["welcome_sent"] = True
        updates["messages"] = append_message(
            messages, "assistant", "Gracias. Continuemos con tu perfil."
        )
        return updates

    if consent_answer is False:
        updates["consent"] = {
            "accepted": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        updates["phase"] = "end"
        updates["welcome_sent"] = True
        updates["messages"] = append_message(
            messages,
            "assistant",
            "Entendido. Sin consentimiento no puedo continuar.",
        )
        return updates

    if _is_greeting(normalized):
        if not state.get("welcome_sent", False):
            updates["messages"] = append_message(
                messages, "assistant", _welcome_with_consent()
            )
            updates["welcome_sent"] = True
        else:
            updates["messages"] = append_message(messages, "assistant", CONSENT_PROMPT)
        updates["awaiting_user_input"] = True
        return updates

    updates["messages"] = append_message(messages, "assistant", CONSENT_PROMPT)
    updates["awaiting_user_input"] = True
    return updates


def _is_greeting(text: str) -> bool:
    if not text:
        return False
    return any(keyword in text for keyword in _GREETING_KEYWORDS)


def _welcome_with_consent() -> str:
    return f"{WELCOME_MESSAGE}\n\n{CONSENT_PROMPT}"
