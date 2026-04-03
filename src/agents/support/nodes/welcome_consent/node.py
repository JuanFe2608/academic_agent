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


def _restart_after_out_of_scope(
    state: AgentState,
    messages: list,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
) -> dict:
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    fresh = AgentState(timezone=state.get("timezone", "America/Bogota"))
    return {
        "phase": "consent",
        "user_status": "start",
        "welcome_sent": True,
        "awaiting_user_input": True,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "last_user_images": [],
        "errors": [],
        "consent": fresh.consent.model_dump(),
        "student_profile": fresh.student_profile.model_dump(),
        "onboarding": fresh.onboarding.model_dump(),
        "raw_inputs": fresh.raw_inputs.model_dump(),
        "extras_has_any": None,
        "extras_collect_stage": None,
        "extras_pending_is_variable": None,
        "extras_pending_items": [],
        "academic_pending_items": [],
        "work_pending_items": [],
        "extracurricular": [],
        "events": [],
        "events_validated": False,
        "schedule_preview": fresh.schedule_preview.model_dump(),
        "schedule": fresh.schedule.model_dump(),
        "calendar": fresh.calendar.model_dump(),
        "subjects": [],
        "study_profile": fresh.study_profile.model_dump(),
        "priorities": fresh.priorities.model_dump(),
        "study_plan": fresh.study_plan.model_dump(),
        "replan": fresh.replan.model_dump(),
        "reminders": fresh.reminders.model_dump(),
        "profile_edit_target": None,
        "messages": append_message(messages, "assistant", _welcome_with_consent()),
    }
