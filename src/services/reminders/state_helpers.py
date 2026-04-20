"""Helpers tipados para el subestado `reminders`."""

from __future__ import annotations

from schemas.reminders import RemindersState


def ensure_reminders_state(raw_state: RemindersState | dict | None) -> RemindersState:
    """Coacciona el subestado `reminders` a su modelo canónico."""

    if isinstance(raw_state, RemindersState):
        return raw_state.model_copy(deep=True)
    return RemindersState(**dict(raw_state or {}))


def reminders_state_to_update(
    reminders_state: RemindersState | dict | None,
) -> dict[str, object]:
    """Serializa `RemindersState` conservando su contrato con el grafo."""

    normalized = ensure_reminders_state(reminders_state)
    return {
        "enabled": normalized.enabled,
        "policy": dict(normalized.policy),
        "persisted_policy_ids": list(normalized.persisted_policy_ids),
        "policy_count": normalized.policy_count,
        "schedulable_instance_count": normalized.schedulable_instance_count,
        "created_dispatch_count": normalized.created_dispatch_count,
        "canceled_dispatch_count": normalized.canceled_dispatch_count,
        "last_dispatch_error": normalized.last_dispatch_error,
        "last_sync_at": normalized.last_sync_at,
    }


def update_reminders_state(
    raw_state: RemindersState | dict | None,
    **changes: object,
) -> dict[str, object]:
    """Aplica cambios al subestado `reminders` sin romper el contrato actual."""

    normalized = ensure_reminders_state(raw_state)
    updated = normalized.model_copy(update=changes)
    return reminders_state_to_update(updated)
