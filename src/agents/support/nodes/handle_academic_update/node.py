"""Nodo fino para cambios academicos puntuales fuera del flujo semanal."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.dependencies import (
    get_academic_activity_persistence_service,
    get_tracking_service,
)
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.conversation.state_helpers import ensure_interaction_state, update_interaction_state
from services.planning import (
    active_academic_activities,
    apply_confirmed_academic_activity_operation,
    apply_study_session_tracking_text,
    coerce_academic_activities,
    is_study_session_tracking_message,
    parse_academic_activity_request,
    priority_update_text_for_activity,
)
from services.priorities import (
    apply_academic_event_update,
    current_week_bounds,
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)


def handle_academic_update(state: AgentState) -> dict:
    """Gestiona actividades puntuales y senales academicas sin cuestionario semanal."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    timezone = state.get("timezone", "America/Bogota")
    reference_date = _reference_date(timezone)
    interaction = ensure_interaction_state(state)
    activities = _load_activities_for_state(state)

    confirmation_payload = dict(interaction.last_confirmation_payload or {})
    if interaction.confirmation_pending and confirmation_payload.get("domain") == "activity_management":
        return _handle_activity_confirmation(
            state,
            activities=activities,
            payload=confirmation_payload,
            last_text=last_text,
            current_count=current_count,
            timezone=timezone,
            reference_date=reference_date,
        )

    if (
        is_study_session_tracking_message(last_text)
        or (
            interaction.current_domain == "session_tracking"
            and bool(interaction.missing_fields_json)
        )
    ):
        tracking_result = apply_study_session_tracking_text(
            last_text,
            student_id=_student_id(state),
            tracking_service=get_tracking_service(),
            timezone=timezone,
            interaction_payload=dict(interaction.pending_entity_payload or {}),
            as_of=_reference_datetime(timezone),
        )
        if tracking_result.detected:
            return _tracking_result_update(
                state,
                result=tracking_result,
                current_count=current_count,
                last_text=last_text,
            )

    pending_payload = (
        dict(interaction.pending_entity_payload or {})
        if interaction.current_domain == "activity_management"
        else {}
    )
    activity_result = parse_academic_activity_request(
        last_text,
        existing_activities=activities,
        subjects=list(state.get("subjects", [])),
        reference_date=reference_date,
        timezone=timezone,
        pending_payload=pending_payload,
    )
    if activity_result.detected:
        return _activity_result_update(
            state,
            result=activity_result,
            current_count=current_count,
            last_text=last_text,
        )

    return _legacy_priority_update(
        state,
        last_text=last_text,
        current_count=current_count,
        timezone=timezone,
        reference_date=reference_date,
    )


def _legacy_priority_update(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    timezone: str,
    reference_date,
) -> dict:
    """Conserva el ajuste de prioridades usado antes de la fase 9."""

    messages = state.get("messages", [])
    week_start, week_end = current_week_bounds(reference_date)
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        academic_activities=list(state.get("academic_activities", [])),
        primary_technique_id=_primary_technique_id(study_profile),
        reference_date=reference_date,
    )
    current_subjects = subject_items_to_update(priorities.subject_items)
    result = apply_academic_event_update(
        subjects=current_subjects,
        text=last_text,
        reference_date=reference_date,
        timezone=timezone,
    )
    if not result.detected:
        return {
            "subjects": current_subjects,
            "phase": "end",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    update = {
        "subjects": subject_items_to_update(result.subjects or current_subjects),
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed" if result.event_type == "academic_deadline" else "collecting",
            prompt_version="v2",
            source="event_update",
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft={"event_update": result.payload},
        ),
        "replan": _build_replan_state(state, result),
        "phase": "end",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": bool(result.requires_clarification),
        "messages": append_message(messages, "assistant", result.message),
    }
    return update


def _activity_result_update(
    state: AgentState,
    *,
    result,
    current_count: int,
    last_text: str,
) -> dict:
    messages = state.get("messages", [])
    base = {
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", result.message),
    }
    if result.action == "list":
        return {
            **base,
            "academic_activities": active_academic_activities(result.activities),
            "phase": "end",
            "awaiting_user_input": False,
            **_clear_activity_interaction(state),
        }
    if result.requires_clarification:
        return {
            **base,
            "phase": "academic_activity_management",
            "awaiting_user_input": True,
            **_pending_activity_interaction(
                state,
                payload=result.pending_payload,
                missing_fields=result.missing_fields,
            ),
        }
    if result.requires_confirmation:
        return {
            **base,
            "phase": "academic_activity_management",
            "awaiting_user_input": True,
            **_confirmation_activity_interaction(state, result.confirmation_payload),
        }
    return {
        **base,
        "phase": "end",
        "awaiting_user_input": False,
        **_clear_activity_interaction(state),
    }


def _tracking_result_update(
    state: AgentState,
    *,
    result,
    current_count: int,
    last_text: str,
) -> dict[str, object]:
    messages = state.get("messages", [])
    base = {
        "phase": "academic_activity_management" if result.requires_clarification else "end",
        "awaiting_user_input": bool(result.requires_clarification),
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", result.message),
    }
    interaction_update = (
        _pending_tracking_interaction(
            state,
            payload=result.pending_payload,
            missing_fields=result.missing_fields,
        )
        if result.requires_clarification
        else _tracking_memory_interaction(state, result.pending_payload)
    )
    replan_update = _tracking_replan_update(state, result)
    return {
        **base,
        **replan_update,
        **interaction_update,
    }


def _handle_activity_confirmation(
    state: AgentState,
    *,
    activities,
    payload: dict[str, object],
    last_text: str,
    current_count: int,
    timezone: str,
    reference_date,
) -> dict:
    messages = state.get("messages", [])
    decision = parse_yes_no(last_text)
    if decision is False:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", "Listo, no hice cambios."),
            **_clear_activity_interaction(state),
        }
    if decision is not True:
        return {
            "phase": "academic_activity_management",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                "Necesito que confirmes con si o no para aplicar ese cambio.",
            ),
            **_confirmation_activity_interaction(state, payload),
        }

    applied = apply_confirmed_academic_activity_operation(
        activities,
        payload,
        timezone=timezone,
        reference_date=reference_date,
    )
    updated_activities = applied.activities
    persisted_activity = _persist_activity_if_possible(
        state,
        applied.activity,
        operation=applied.action,
    )
    if persisted_activity is not None:
        updated_activities = _replace_activity(updated_activities, persisted_activity)

    priority_update = {}
    if applied.activity is not None and applied.action in {"create", "update"}:
        priority_update = _priority_update_from_activity(
            state,
            persisted_activity or applied.activity,
            reference_date=reference_date,
            timezone=timezone,
        )

    replan_update = _activity_replan_update(
        state,
        applied,
        priority_update.get("replan"),
    )
    return {
        "academic_activities": updated_activities,
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", applied.message),
        **priority_update,
        **replan_update,
        **_clear_activity_interaction(state),
    }


def _priority_update_from_activity(
    state: AgentState,
    activity,
    *,
    reference_date,
    timezone: str,
) -> dict[str, object]:
    update_text = priority_update_text_for_activity(activity)
    if not update_text:
        return {}
    week_start, week_end = current_week_bounds(reference_date)
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        academic_activities=[
            *list(state.get("academic_activities", [])),
            activity,
        ],
        primary_technique_id=_primary_technique_id(study_profile),
        reference_date=reference_date,
    )
    current_subjects = subject_items_to_update(priorities.subject_items)
    result = apply_academic_event_update(
        subjects=current_subjects,
        text=update_text,
        reference_date=reference_date,
        timezone=timezone,
    )
    if not result.detected or result.requires_clarification:
        return {}
    return {
        "subjects": subject_items_to_update(result.subjects or current_subjects),
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed",
            prompt_version="v2",
            source="event_update",
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft={"event_update": result.payload},
        ),
        "replan": _build_replan_state(state, result),
    }


def _activity_replan_update(state: AgentState, applied, priority_replan) -> dict[str, object]:
    if priority_replan:
        return {"replan": priority_replan}
    if not applied.replan_required:
        return {}
    replan = dict(state.get("replan", {}))
    replan["trigger"] = "academic_activity"
    replan["change_request"] = dict(applied.payload)
    replan["pending_prompt"] = None
    return {"replan": replan}


def _load_activities_for_state(state: AgentState):
    local = coerce_academic_activities(state.get("academic_activities", []))
    if local:
        return local
    student_id = _student_id(state)
    if not student_id:
        return local
    try:
        result = get_academic_activity_persistence_service().list_activities(
            student_id=student_id,
            include_deleted=True,
        )
    except Exception:
        return local
    if result.loaded:
        return result.activities
    return local


def _persist_activity_if_possible(
    state: AgentState,
    activity,
    *,
    operation: str,
):
    if activity is None:
        return None
    student_id = _student_id(state)
    if not student_id:
        return activity
    try:
        service = get_academic_activity_persistence_service()
        if operation == "delete":
            result = service.delete_activity(
                student_id=student_id,
                activity_id=activity.activity_id,
            )
            if not result.persisted:
                result = service.upsert_activity(student_id=student_id, activity=activity)
        else:
            result = service.upsert_activity(student_id=student_id, activity=activity)
    except Exception as exc:
        return activity.model_copy(update={"persistence_error": str(exc)})
    if result.persisted and result.activity is not None:
        return result.activity
    return activity.model_copy(update={"persistence_error": result.error_code or result.detail})


def _replace_activity(activities, replacement):
    updated = []
    found = False
    for activity in coerce_academic_activities(activities):
        if activity.activity_id == replacement.activity_id:
            updated.append(replacement)
            found = True
        else:
            updated.append(activity)
    if not found:
        updated.append(replacement)
    return updated


def _student_id(state: AgentState) -> int | None:
    profile = state.get("student_profile", {})
    if hasattr(profile, "persisted_student_id"):
        return profile.persisted_student_id
    if isinstance(profile, dict):
        value = profile.get("persisted_student_id")
        return int(value) if value else None
    return None


def _confirmation_activity_interaction(state: AgentState, payload: dict[str, object]) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent="register_academic_activity",
        current_domain="activity_management",
        interaction_mode="confirmation",
        pending_action=f"confirm_{payload.get('operation') or 'activity'}",
        pending_entity_type="academic_activity",
        pending_entity_payload=payload,
        missing_fields_json=[],
        confirmation_pending=True,
        last_confirmation_payload=payload,
        clarification_needed=False,
        current_step="awaiting_confirmation",
        current_section="academic_activity",
    )


def _pending_activity_interaction(
    state: AgentState,
    *,
    payload: dict[str, object],
    missing_fields: list[str],
) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent="register_academic_activity",
        current_domain="activity_management",
        interaction_mode="guided",
        pending_action=f"complete_{payload.get('operation') or 'activity'}",
        pending_entity_type="academic_activity",
        pending_entity_payload=payload,
        missing_fields_json=missing_fields,
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=True,
        current_step="awaiting_missing_fields",
        current_section="academic_activity",
    )


def _clear_activity_interaction(state: AgentState) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=None,
        current_domain="activity_management",
        interaction_mode="guided",
        pending_action=None,
        pending_entity_type=None,
        pending_entity_payload={},
        missing_fields_json=[],
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=False,
        current_step=None,
        current_section=None,
    )


def _pending_tracking_interaction(
    state: AgentState,
    *,
    payload: dict[str, object],
    missing_fields: list[str],
) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent="track_study_session",
        current_domain="session_tracking",
        interaction_mode="guided",
        pending_action=f"complete_{payload.get('tracking_action') or 'tracking'}",
        pending_entity_type="study_session",
        pending_entity_payload=payload,
        missing_fields_json=missing_fields,
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=True,
        current_step="awaiting_study_session_reference",
        current_section="session_tracking",
    )


def _tracking_memory_interaction(
    state: AgentState,
    payload: dict[str, object],
) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=None,
        current_domain="session_tracking",
        interaction_mode="guided",
        pending_action=None,
        pending_entity_type=None,
        pending_entity_payload=dict(payload or {}),
        missing_fields_json=[],
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=False,
        current_step=None,
        current_section=None,
    )


def _primary_technique_id(study_profile: dict) -> str | None:
    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _build_replan_state(state: AgentState, result) -> dict[str, object]:
    replan = dict(state.get("replan", {}))
    if not result.replan_required:
        return replan
    replan["trigger"] = str(result.payload.get("trigger") or result.event_type or "user_request")
    replan["change_request"] = dict(result.payload)
    replan["pending_prompt"] = result.message if result.requires_clarification else None
    return replan


def _tracking_replan_update(state: AgentState, result) -> dict[str, object]:
    if not getattr(result, "replan_required", False):
        return {}
    payload = dict(getattr(result, "replan_payload", {}) or {})
    replan = dict(state.get("replan", {}))
    replan["trigger"] = str(payload.get("trigger") or "study_session_tracking")
    replan["change_request"] = payload
    replan["pending_prompt"] = result.message
    return {"replan": replan}


def _reference_date(timezone: str):
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).date()
    except Exception:
        return datetime.now().date()


def _reference_datetime(timezone: str):
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota")))
    except Exception:
        return datetime.now()
