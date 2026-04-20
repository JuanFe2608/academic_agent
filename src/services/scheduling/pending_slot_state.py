"""Puente entre pendientes de scheduling y estado conversacional operativo."""

from __future__ import annotations

from schemas.scheduling import PendingExtracurricularItem, PendingScheduleItem
from services.conversation.state_helpers import update_interaction_state
from services.scheduling.extracurricular_state import coerce_extracurricular_pending_items
from services.scheduling.pending_schedule_support import coerce_pending_schedule_items


def schedule_pending_interaction_update(
    raw_state: object,
    *,
    academic_pending_items: list[PendingScheduleItem] | list[dict],
    work_pending_items: list[PendingScheduleItem] | list[dict],
) -> dict[str, object]:
    """Refleja el primer pendiente académico/laboral en `interaction`."""

    academic_items = coerce_pending_schedule_items(academic_pending_items)
    work_items = coerce_pending_schedule_items(work_pending_items)
    target = "academic" if academic_items else "work" if work_items else None
    items = academic_items if academic_items else work_items

    if target is None or not items:
        return clear_scheduling_pending_interaction(raw_state)

    current = items[0]
    missing = _normalized_missing_fields(current.missing_fields)
    return update_interaction_state(
        raw_state,
        active_intent="capture_fixed_schedule",
        current_domain="schedule_management",
        pending_action="complete_fixed_schedule_item",
        pending_entity_type="fixed_schedule_item",
        pending_entity_payload={
            "schedule_type": target,
            "title": current.title,
            "days": list(current.days),
            "raw_text": current.raw_text,
            "missing_fields": list(current.missing_fields),
        },
        missing_fields_json=missing,
        clarification_needed=True,
        current_section=target,
    )


def extracurricular_pending_interaction_update(
    raw_state: object,
    *,
    pending_items: list[PendingExtracurricularItem] | list[dict],
) -> dict[str, object]:
    """Refleja el primer pendiente extracurricular en `interaction`."""

    items = coerce_extracurricular_pending_items(pending_items)
    if not items:
        return clear_scheduling_pending_interaction(raw_state)

    current = items[0]
    missing = _normalized_missing_fields(current.missing_fields)
    return update_interaction_state(
        raw_state,
        active_intent="capture_extracurricular_activity",
        current_domain="schedule_management",
        pending_action="complete_extracurricular_item",
        pending_entity_type="extracurricular_item",
        pending_entity_payload={
            "name": current.nombre,
            "days": list(current.dias),
            "raw_text": current.raw_text,
            "is_variable": current.es_variable,
            "missing_fields": list(current.missing_fields),
        },
        missing_fields_json=missing,
        clarification_needed=True,
        current_section="extracurricular",
    )


def clear_scheduling_pending_interaction(raw_state: object) -> dict[str, object]:
    """Limpia solo los campos operativos asociados a pendientes de scheduling."""

    return update_interaction_state(
        raw_state,
        pending_action=None,
        pending_entity_type=None,
        pending_entity_payload={},
        missing_fields_json=[],
        clarification_needed=False,
        current_section=None,
    )


def _normalized_missing_fields(missing_fields: list[str]) -> list[str]:
    return [
        _normalize_missing_field(field)
        for field in missing_fields
        if str(field or "").strip()
    ]


def _normalize_missing_field(field: str) -> str:
    normalized = str(field or "").strip().lower()
    mapping = {
        "dia o dias exactos": "day",
        "hora de inicio y fin": "time_range",
        "nombre de la materia o actividad": "title",
        "nombre": "name",
        "detalle": "detail",
        "aclarar am o pm en el horario": "meridiem",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


__all__ = [
    "clear_scheduling_pending_interaction",
    "extracurricular_pending_interaction_update",
    "schedule_pending_interaction_update",
]
