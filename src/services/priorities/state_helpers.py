"""Helpers tipados para `subjects` y `priorities` del agente."""

from __future__ import annotations

from schemas.planning import PrioritiesState, SubjectItem


def ensure_subject_item(raw_item: SubjectItem | dict) -> SubjectItem:
    """Coacciona una materia del estado al modelo canónico."""

    if isinstance(raw_item, SubjectItem):
        return raw_item.model_copy(deep=True)
    return SubjectItem(**dict(raw_item))


def ensure_subject_items(raw_items: list[SubjectItem | dict] | None) -> list[SubjectItem]:
    """Normaliza una colección de materias del agente."""

    return [ensure_subject_item(item) for item in list(raw_items or [])]


def subject_items_to_update(items: list[SubjectItem | dict] | None) -> list[SubjectItem]:
    """Serializa `subjects` conservando modelos Pydantic compatibles con el grafo."""

    return ensure_subject_items(items)


def ensure_priorities_state(
    raw_state: PrioritiesState | dict | None,
) -> PrioritiesState:
    """Coacciona el subestado `priorities` a su modelo canónico."""

    if isinstance(raw_state, PrioritiesState):
        return raw_state.model_copy(deep=True)
    return PrioritiesState(**dict(raw_state or {}))


def priorities_state_to_update(
    priorities_state: PrioritiesState | dict | None,
) -> dict[str, object]:
    """Serializa `priorities` para updates parciales del grafo."""

    normalized = ensure_priorities_state(priorities_state)
    return normalized.model_dump(mode="python")


def update_priorities_state(
    raw_state: PrioritiesState | dict | None,
    **changes: object,
) -> dict[str, object]:
    """Aplica cambios al subestado `priorities`."""

    normalized = ensure_priorities_state(raw_state)
    updated = normalized.model_copy(update=changes)
    return priorities_state_to_update(updated)
