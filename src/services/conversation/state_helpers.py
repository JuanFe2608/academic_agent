"""Helpers para el subestado conversacional operativo.

Los helpers trabajan sobre la clave top-level ``interaction`` del contrato
actual de LangGraph. Mantienen la validacion fuera de los nodos y no aplican
reglas de negocio del router.
"""

from __future__ import annotations

from collections.abc import Mapping

from schemas.conversation import InteractionState

_INTERACTION_FIELDS = set(InteractionState.model_fields)


def ensure_interaction_state(raw_state: object | None = None) -> InteractionState:
    """Coacciona cualquier payload compatible a ``InteractionState``."""

    if isinstance(raw_state, InteractionState):
        return raw_state
    if raw_state is None:
        return InteractionState()

    interaction_view = getattr(raw_state, "interaction_state", None)
    if isinstance(interaction_view, InteractionState):
        return interaction_view

    interaction_value = getattr(raw_state, "interaction", None)
    if interaction_value is not None:
        return ensure_interaction_state(interaction_value)

    if isinstance(raw_state, Mapping):
        data = dict(raw_state)
        if "interaction" in data:
            return ensure_interaction_state(data.get("interaction"))
        return InteractionState(**data)

    model_dump = getattr(raw_state, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="python")
        if isinstance(data, Mapping):
            return ensure_interaction_state(data)

    return InteractionState()


def interaction_state_to_update(raw_state: object | None = None) -> dict[str, object]:
    """Serializa el subestado operativo al formato de update del grafo."""

    return {"interaction": ensure_interaction_state(raw_state).model_dump(mode="python")}


def update_interaction_state(raw_state: object | None = None, **changes: object) -> dict[str, object]:
    """Valida cambios del subestado operativo y devuelve un update parcial."""

    if not changes:
        return {}

    unexpected = sorted(set(changes) - _INTERACTION_FIELDS)
    if unexpected:
        joined = ", ".join(unexpected)
        raise KeyError(f"Campos de interaccion desconocidos: {joined}")

    data = ensure_interaction_state(raw_state).model_dump(mode="python")
    data.update(changes)
    return interaction_state_to_update(InteractionState(**data))


def reset_interaction_state(**overrides: object) -> dict[str, object]:
    """Construye un update de reset para la interaccion operativa."""

    if overrides:
        return update_interaction_state(InteractionState(), **overrides)
    return interaction_state_to_update()


__all__ = [
    "ensure_interaction_state",
    "interaction_state_to_update",
    "reset_interaction_state",
    "update_interaction_state",
]
