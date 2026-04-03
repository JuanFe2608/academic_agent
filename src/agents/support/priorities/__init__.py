"""API pública del dominio de priorización académica."""

from .config import PrioritiesConfig, is_priorities_enabled, load_priorities_config
from .state_helpers import (
    ensure_priorities_state,
    ensure_subject_item,
    ensure_subject_items,
    priorities_state_to_update,
    subject_items_to_update,
    update_priorities_state,
)
from .subject_prioritization_service import (
    PrioritizationResult,
    PrioritizedSubject,
    resolve_prioritized_subjects,
)

__all__ = [
    "PrioritizationResult",
    "PrioritizedSubject",
    "PrioritiesConfig",
    "ensure_priorities_state",
    "ensure_subject_item",
    "ensure_subject_items",
    "is_priorities_enabled",
    "load_priorities_config",
    "priorities_state_to_update",
    "resolve_prioritized_subjects",
    "subject_items_to_update",
    "update_priorities_state",
]
