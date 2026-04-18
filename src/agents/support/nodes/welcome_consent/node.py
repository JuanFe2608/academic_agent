"""Nodo de bienvenida y consentimiento."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage

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

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_WELCOME_IMAGE_PATH = (
    _PROJECT_ROOT / "assets" / "whatsapp" / "saludando con un brazo cruzado.png"
)

def welcome_consent(state: AgentState) -> dict:
    """Solicita consentimiento y actualiza el estado segun respuesta."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )

    if state.get("user_status") == "out_of_scope":
        return _restart_after_out_of_scope(
            state,
            messages,
            has_new_input,
            last_text,
            current_count,
        )

    if state.get("consent", {}).get("accepted"):
        if state.get("phase") == "consent":
            return {"phase": "profile", "awaiting_user_input": False}
        return {"awaiting_user_input": False}

    updates: dict = {"phase": "consent"}
    if not has_new_input:
        if not state.get("welcome_sent", False):
            updates["messages"] = _welcome_sequence()
            updates["welcome_sent"] = True
        else:
            updates["messages"] = append_message(messages, "assistant", CONSENT_PROMPT)
        updates["awaiting_user_input"] = True
        return updates

    updates["user_message_count"] = current_count
    updates["awaiting_user_input"] = False
    updates["last_user_text"] = last_text

    if not state.get("welcome_sent", False):
        updates["messages"] = _welcome_sequence()
        updates["welcome_sent"] = True
        updates["awaiting_user_input"] = True
        return updates

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
            updates["messages"] = _welcome_sequence()
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


def _welcome_sequence() -> list[BaseMessage]:
    """Construye mensajes separados para que WhatsApp los envie en orden."""
    return [
        AIMessage(content=WELCOME_MESSAGE),
        AIMessage(content=[_welcome_image_block()]),
        AIMessage(content=CONSENT_PROMPT),
    ]


def _welcome_image_block() -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": str(_WELCOME_IMAGE_PATH)}}


def _restart_after_out_of_scope(
    state: AgentState,
    messages: list,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
) -> dict:
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    return state.restart_payload_for_new_attempt(
        messages=_welcome_sequence(),
        user_message_count=current_count,
        last_user_text=last_text,
    )
