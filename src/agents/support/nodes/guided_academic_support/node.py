"""Nodo fino para apoyo academico guiado y modo socratico."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from services.conversation import (
    GUIDED_SUPPORT_DOMAIN,
    build_guided_academic_support_result,
    ensure_interaction_state,
    update_interaction_state,
)


def guided_academic_support(state: AgentState) -> dict:
    """Adapta el servicio guiado al estado LangGraph."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    interaction = ensure_interaction_state(state)
    pending_payload = (
        dict(interaction.pending_entity_payload or {})
        if interaction.current_domain == GUIDED_SUPPORT_DOMAIN
        else {}
    )
    result = build_guided_academic_support_result(
        last_text,
        pending_payload=pending_payload,
        study_profile=dict(state.get("study_profile") or {}),
    )
    if not result.detected:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
        }

    if result.requires_clarification:
        return {
            "phase": "guided_academic_support",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", result.message),
            **_pending_guided_interaction(state, result),
        }

    if result.requires_follow_up:
        return {
            "phase": "guided_academic_support",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", result.message),
            **_follow_up_guided_interaction(state, result),
        }

    return {
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", result.message),
        **_completed_guided_interaction(state, result),
    }


def _pending_guided_interaction(state: AgentState, result) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=result.intent,
        current_domain=GUIDED_SUPPORT_DOMAIN,
        interaction_mode=result.interaction_mode,
        pending_action="complete_guided_academic_context",
        pending_entity_type="guided_academic_activity",
        pending_entity_payload=result.pending_payload,
        missing_fields_json=result.missing_fields,
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=True,
        current_step="awaiting_guided_context",
        current_section="guided_academic_support",
    )


def _follow_up_guided_interaction(state: AgentState, result) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=result.intent,
        current_domain=GUIDED_SUPPORT_DOMAIN,
        interaction_mode=result.interaction_mode,
        pending_action="continue_socratic_mode",
        pending_entity_type="guided_academic_activity",
        pending_entity_payload=result.pending_payload,
        missing_fields_json=[],
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=False,
        current_step="awaiting_socratic_answer",
        current_section="guided_academic_support",
    )


def _completed_guided_interaction(state: AgentState, result) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=result.intent,
        current_domain=GUIDED_SUPPORT_DOMAIN,
        interaction_mode=result.interaction_mode,
        pending_action=None,
        pending_entity_type=None,
        pending_entity_payload={
            "last_allowed_output": result.output_kind,
            "slots": result.slots,
            "turn_count": result.turn_count,
        },
        missing_fields_json=[],
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=False,
        current_step=None,
        current_section="guided_academic_support",
    )


__all__ = ["guided_academic_support"]
