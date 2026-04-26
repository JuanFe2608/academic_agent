"""Contratos conversacionales operativos.

Este modulo define el estado minimo que permite al agente recordar el modo de
interaccion activo, la intencion en curso y los datos pendientes sin mezclar
esa responsabilidad con los campos legacy de runtime del grafo.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, field_validator

from schemas.common import BaseSchemaModel

ConversationInputType = Literal[
    "text",
    "emoji_only",
    "sticker_only",
    "image_only",
    "mixed",
    "audio",
    "document",
]
InputUtility = Literal[
    "useful",
    "noise",
    "confirmation",
    "command",
    "media",
    "sensitive",
]
ScopeCategory = Literal[
    "in_scope",
    "partially_in_scope",
    "redirectable_out_of_scope",
    "hard_out_of_scope",
    "human_support_case",
]
ScopeAction = Literal["normal", "limited", "redirect", "reject", "escalate"]
ConversationRouteAction = Literal[
    "route",
    "continue_active_block",
    "provide_missing_data",
    "confirm_action",
    "reject_action",
    "answer_policy",
    "ignore",
]


class InteractionState(BaseSchemaModel):
    """Estado conversacional operativo minimo del MVP Lara."""

    active_intent: str | None = None
    active_subflow: str | None = None
    current_domain: str | None = None
    interaction_mode: str = "guided"
    pending_action: str | None = None
    pending_entity_type: str | None = None
    pending_entity_payload: dict[str, Any] = Field(default_factory=dict)
    missing_fields_json: list[Any] = Field(default_factory=list)
    confirmation_pending: bool = False
    last_confirmation_payload: dict[str, Any] | None = None
    noise_turn_count: int = 0
    last_user_messages: list[str] = Field(default_factory=list)
    aggregated_user_text: str | None = None
    router_confidence: float | None = None
    clarification_needed: bool = False
    is_waiting_for_oauth: bool = False
    is_waiting_for_verification_code: bool = False
    current_step: str | None = None
    current_section: str | None = None

    @field_validator(
        "active_intent",
        "active_subflow",
        "current_domain",
        "pending_action",
        "pending_entity_type",
        "aggregated_user_text",
        "current_step",
        "current_section",
        mode="before",
    )
    @classmethod
    def _blank_string_as_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("interaction_mode", mode="before")
    @classmethod
    def _normalize_interaction_mode(cls, value: object) -> str:
        if value is None:
            return "guided"
        normalized = str(value).strip().lower()
        return normalized or "guided"

    @field_validator("pending_entity_payload", mode="before")
    @classmethod
    def _normalize_pending_payload(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    @field_validator("last_confirmation_payload", mode="before")
    @classmethod
    def _normalize_confirmation_payload(cls, value: object) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return dict(value)
        return None

    @field_validator("missing_fields_json", mode="before")
    @classmethod
    def _normalize_missing_fields(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        return value

    @field_validator("last_user_messages", mode="before")
    @classmethod
    def _normalize_last_user_messages(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item or "").strip()]
        return []

    @field_validator("noise_turn_count", mode="before")
    @classmethod
    def _normalize_noise_turn_count(cls, value: object) -> int:
        if value is None:
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @field_validator("router_confidence", mode="before")
    @classmethod
    def _normalize_router_confidence(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return min(1.0, max(0.0, confidence))


class InputClassification(BaseSchemaModel):
    """Resultado deterministico de clasificar un input agregado."""

    input_type: ConversationInputType = "text"
    utility: InputUtility = "useful"
    is_useful: bool = True
    possible_intent: str | None = None
    confidence: float = 0.0
    normalized_text: str = ""
    signals: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, confidence))

    @field_validator("signals", "media_types", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item or "").strip()]
        return []


class ScopeDecision(BaseSchemaModel):
    """Decision de politica de alcance para un input clasificado."""

    category: ScopeCategory
    action: ScopeAction
    allowed: bool
    domain: str
    intent: str
    confidence: float = 0.0
    reason: str = ""
    response_text: str | None = None
    requires_human_support: bool = False
    classification: InputClassification = Field(default_factory=InputClassification)
    signals: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, confidence))

    @field_validator("signals", mode="before")
    @classmethod
    def _normalize_signals(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item or "").strip()]
        return []


class ConversationRouteDecision(BaseSchemaModel):
    """Decision del router conversacional hibrido."""

    intent: str
    domain: str
    action: ConversationRouteAction
    route_name: str | None = None
    confidence: float = 0.0
    priority: int = 0
    reason: str = ""
    preserves_active_block: bool = False
    interrupts_active_block: bool = False
    classification: InputClassification = Field(default_factory=InputClassification)
    scope_decision: ScopeDecision | None = None
    missing_fields_json: list[Any] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, confidence))

    @field_validator("signals", "missing_fields_json", mode="before")
    @classmethod
    def _normalize_list(cls, value: object) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        return [value]


__all__ = [
    "ConversationRouteAction",
    "ConversationRouteDecision",
    "ConversationInputType",
    "InputClassification",
    "InputUtility",
    "InteractionState",
    "ScopeAction",
    "ScopeCategory",
    "ScopeDecision",
]
