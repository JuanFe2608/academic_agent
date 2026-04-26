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
from services.conversation.text_normalization import normalize_text


_GREETING_TOKENS = frozenset({
    "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "hey", "saludos", "que tal", "como estas", "como estan",
})

_GREETING_RESPONSE = (
    "¡Hola! ¿En qué puedo apoyarte hoy? 😊\n\n"
    "Puedo ayudarte a:\n"
    "- Registrar o revisar tus actividades pendientes (parciales, tareas, entregas)\n"
    "- Organizar tu semana de estudio\n"
    "- Recomendarte cómo preparar una evaluación según tu técnica"
)

_UNDETECTED_FALLBACK = (
    "Para ayudarte bien, cuéntame qué tienes pendiente esta semana. 📋\n\n"
    "Por ejemplo:\n"
    "- \"Tengo parcial de Cálculo el viernes\"\n"
    "- \"Quiero organizar mis horas de estudio\"\n"
    "- \"¿Cómo aplico pomodoro para un parcial?\""
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

    # Saludos antes de llamar al servicio — evita enviar el fallback de "sin contexto"
    # para mensajes que son simplemente una apertura de conversación.
    normalized = normalize_text(last_text or "")
    if _is_pure_greeting(normalized):
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", _GREETING_RESPONSE),
        }

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
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                _UNDETECTED_FALLBACK,
            ),
        }

    if result.requires_clarification:
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", result.message),
            **_pending_guided_interaction(state, result),
        }

    if result.requires_follow_up:
        return {
            "phase": "running",
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
        active_subflow="guided_academic_support",
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
        active_subflow="guided_academic_support",
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
        active_subflow=None,
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


def _is_pure_greeting(normalized: str) -> bool:
    """Detecta saludos simples sin contenido académico adicional (máx 3 palabras)."""
    words = normalized.split()
    return len(words) <= 3 and any(token in normalized for token in _GREETING_TOKENS)


__all__ = ["guided_academic_support"]
