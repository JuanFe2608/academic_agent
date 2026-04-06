"""Helpers tipados para el subestado conversacional/runtime del agente.

Estos helpers validan cambios contra la partición `conversation_state`, pero
devuelven updates parciales compatibles con el contrato plano actual de
LangGraph. No reenvían el estado completo por defecto para evitar duplicar
mensajes bajo el reducer `add_messages`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agents.support.state import AgentState

_CONVERSATION_FIELDS = set(AgentState.field_groups()["conversation"])


def ensure_conversation_state(
    raw_state: AgentState | Mapping[str, object] | None,
) -> Any:
    """Coacciona el runtime conversacional a su vista tipada actual."""

    if isinstance(raw_state, AgentState):
        return raw_state.conversation_state
    return AgentState(**dict(raw_state or {})).conversation_state


def conversation_state_to_update(
    raw_state: AgentState | Mapping[str, object] | None,
    *,
    include_messages: bool = False,
) -> dict[str, object]:
    """Serializa el subestado conversacional al contrato plano del grafo."""

    normalized = ensure_conversation_state(raw_state)
    payload: dict[str, object] = {}
    for field_name in AgentState.field_groups()["conversation"]:
        if field_name == "messages" and not include_messages:
            continue
        value = getattr(normalized, field_name)
        if field_name in {"messages", "errors", "last_user_images"}:
            payload[field_name] = list(value)
        else:
            payload[field_name] = value
    return payload


def update_conversation_state(
    raw_state: AgentState | Mapping[str, object] | None,
    **changes: object,
) -> dict[str, object]:
    """Valida cambios del runtime y devuelve solo los campos modificados."""

    if not changes:
        return {}

    unexpected = sorted(set(changes) - _CONVERSATION_FIELDS)
    if unexpected:
        joined = ", ".join(unexpected)
        raise KeyError(f"Campos runtime desconocidos: {joined}")

    normalized = ensure_conversation_state(raw_state)
    normalized_changes = dict(changes)
    for field_name in ("messages", "errors", "last_user_images"):
        if field_name in normalized_changes and normalized_changes[field_name] is not None:
            normalized_changes[field_name] = list(normalized_changes[field_name])

    data = normalized.model_dump(mode="python")
    data.update(normalized_changes)
    updated = normalized.__class__(**data)

    payload: dict[str, object] = {}
    for field_name in normalized_changes:
        value = getattr(updated, field_name)
        if field_name in {"messages", "errors", "last_user_images"}:
            payload[field_name] = list(value)
        else:
            payload[field_name] = value
    return payload


__all__ = [
    "conversation_state_to_update",
    "ensure_conversation_state",
    "update_conversation_state",
]
