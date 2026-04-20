"""Snapshots seguros para observabilidad conversacional."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from schemas.channels import AggregatedInput
from schemas.conversation import (
    ConversationRouteDecision,
    InputClassification,
    InteractionState,
    ScopeDecision,
)

from .state_helpers import ensure_interaction_state


def build_router_audit_event(
    decision: ConversationRouteDecision,
    *,
    phase: str | None = None,
    interaction: InteractionState | dict[str, object] | None = None,
    event_name: str = "conversation.router_decision",
) -> dict[str, Any]:
    """Serializa una decision del router sin incluir texto crudo del estudiante."""

    active_interaction = ensure_interaction_state(interaction)
    return {
        "event": event_name,
        "phase": str(phase or "").strip() or None,
        "decision": {
            "intent": decision.intent,
            "domain": decision.domain,
            "action": decision.action,
            "route_name": decision.route_name,
            "confidence": decision.confidence,
            "priority": decision.priority,
            "reason": decision.reason,
            "preserves_active_block": decision.preserves_active_block,
            "interrupts_active_block": decision.interrupts_active_block,
            "missing_field_count": len(decision.missing_fields_json),
            "signals": list(decision.signals),
        },
        "active_block": _interaction_audit(active_interaction),
        "classification": _classification_audit(decision.classification),
        "scope": _scope_audit(decision.scope_decision),
    }


def build_buffer_audit_event(
    aggregated: AggregatedInput,
    *,
    event_name: str = "conversation.buffer_flush",
) -> dict[str, Any]:
    """Serializa un flush del buffer sin exponer texto, raw payloads ni media refs."""

    return {
        "event": event_name,
        "channel": aggregated.channel,
        "conversation_fingerprint": _fingerprint(aggregated.conversation_id),
        "sender_fingerprint": _fingerprint(aggregated.sender_id),
        "message_count": aggregated.message_count,
        "flush_reason": aggregated.flush_reason,
        "media_types": list(aggregated.media_types),
        "media_count": len(aggregated.media),
        "latest_message_fingerprint": _fingerprint(aggregated.latest_message_id or ""),
        "text_stats": text_audit_stats(aggregated.text),
        "classification": _classification_audit(aggregated.classification),
    }


def text_audit_stats(text: str | None) -> dict[str, Any]:
    """Resume texto sensible con estadisticas y huella, sin conservar contenido."""

    value = str(text or "")
    stripped = value.strip()
    return {
        "char_count": len(value),
        "line_count": len([line for line in value.splitlines() if line.strip()]),
        "word_count": len(re.findall(r"\b\w+\b", value, flags=re.UNICODE)),
        "has_digits": any(character.isdigit() for character in value),
        "looks_like_email": bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value)),
        "looks_like_phone": bool(re.search(r"\b\d{7,}\b", value)),
        "fingerprint": _fingerprint(stripped),
    }


def _classification_audit(classification: InputClassification) -> dict[str, Any]:
    return {
        "input_type": classification.input_type,
        "utility": classification.utility,
        "is_useful": classification.is_useful,
        "possible_intent": classification.possible_intent,
        "confidence": classification.confidence,
        "signals": list(classification.signals),
        "media_types": list(classification.media_types),
    }


def _scope_audit(scope: ScopeDecision | None) -> dict[str, Any] | None:
    if scope is None:
        return None
    return {
        "category": scope.category,
        "action": scope.action,
        "allowed": scope.allowed,
        "domain": scope.domain,
        "intent": scope.intent,
        "confidence": scope.confidence,
        "reason": scope.reason,
        "requires_human_support": scope.requires_human_support,
        "signals": list(scope.signals),
    }


def _interaction_audit(interaction: InteractionState) -> dict[str, Any]:
    return {
        "active_intent": interaction.active_intent,
        "current_domain": interaction.current_domain,
        "interaction_mode": interaction.interaction_mode,
        "pending_action": interaction.pending_action,
        "pending_entity_type": interaction.pending_entity_type,
        "pending_payload_keys": sorted(interaction.pending_entity_payload),
        "missing_field_count": len(interaction.missing_fields_json),
        "confirmation_pending": interaction.confirmation_pending,
        "has_last_confirmation_payload": interaction.last_confirmation_payload is not None,
        "last_confirmation_payload_keys": sorted(interaction.last_confirmation_payload or {}),
        "noise_turn_count": interaction.noise_turn_count,
        "has_aggregated_user_text": bool(interaction.aggregated_user_text),
        "router_confidence": interaction.router_confidence,
        "clarification_needed": interaction.clarification_needed,
        "is_waiting_for_oauth": interaction.is_waiting_for_oauth,
        "is_waiting_for_verification_code": interaction.is_waiting_for_verification_code,
        "current_step": interaction.current_step,
        "current_section": interaction.current_section,
    }


def _fingerprint(value: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:16]


__all__ = [
    "build_buffer_audit_event",
    "build_router_audit_event",
    "text_audit_stats",
]
