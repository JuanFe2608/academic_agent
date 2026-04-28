"""Handlers de flujo multi-turno para actualizaciones académicas puntuales."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, parse_yes_no
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.conversation.state_helpers import update_interaction_state
from services.planning import (
    active_academic_activities,
    apply_confirmed_academic_activity_operation,
    apply_study_session_tracking_text,
    is_study_session_tracking_message,
    parse_academic_activity_request,
)
from services.planning.academic_update_orchestrator import reference_datetime


def handle_activity_confirmation(
    state: AgentState,
    *,
    activities: list,
    payload: dict,
    last_text: str,
    current_count: int,
    timezone: str,
    ref_date,
    student_id: int | None,
    orchestrator,
) -> dict:
    """Gestiona la confirmación del usuario para operaciones con actividades académicas."""
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
            "phase": "running",
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
        reference_date=ref_date,
    )
    updated_activities = applied.activities
    persisted_activity = orchestrator.persist_activity(
        student_id,
        applied.activity,
        operation=applied.action,
    )
    if persisted_activity is not None:
        updated_activities = orchestrator.replace_activity(updated_activities, persisted_activity)

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    priority_result = (
        orchestrator.compute_priority_update_from_activity(
            persisted_activity or applied.activity,
            subjects=list(state.get("subjects", [])),
            schedule_blocks=list(schedule_state.blocks),
            academic_activities=list(state.get("academic_activities", [])),
            study_profile=dict(state.get("study_profile", {})),
            ref_date=ref_date,
            timezone=timezone,
            priorities_state=dict(state.get("priorities", {})),
        )
        if applied.activity is not None and applied.action in {"create", "update"}
        else None
    )

    update: dict = {
        "academic_activities": updated_activities,
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", applied.message),
        **_clear_activity_interaction(state),
    }
    if priority_result is not None and priority_result.detected:
        update["subjects"] = priority_result.subjects
        update["priorities"] = priority_result.priorities
        if priority_result.replan is not None:
            update["replan"] = priority_result.replan
    else:
        update.update(_activity_replan_update(state, applied, None))
    return update


def try_handle_session_tracking(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    timezone: str,
    interaction,
    student_id: int | None,
    tracking_service,
) -> dict | None:
    """Intenta procesar un mensaje de seguimiento de sesión. Retorna None si no aplica."""
    if not (
        is_study_session_tracking_message(last_text)
        or (
            interaction.current_domain == "session_tracking"
            and bool(interaction.missing_fields_json)
        )
    ):
        return None

    tracking_result = apply_study_session_tracking_text(
        last_text,
        student_id=student_id,
        tracking_service=tracking_service,
        timezone=timezone,
        interaction_payload=dict(interaction.pending_entity_payload or {}),
        as_of=reference_datetime(timezone),
    )
    if not tracking_result.detected:
        return None

    return _tracking_result_update(
        state,
        result=tracking_result,
        current_count=current_count,
        last_text=last_text,
    )


def try_handle_activity_request(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    ref_date,
    timezone: str,
    activities: list,
    interaction,
) -> dict | None:
    """Intenta procesar una solicitud de actividad académica. Retorna None si no aplica."""
    pending_payload = (
        dict(interaction.pending_entity_payload or {})
        if interaction.current_domain == "activity_management"
        else {}
    )
    activity_result = parse_academic_activity_request(
        last_text,
        existing_activities=activities,
        subjects=list(state.get("subjects", [])),
        reference_date=ref_date,
        timezone=timezone,
        pending_payload=pending_payload,
    )
    if not activity_result.detected:
        return None

    return _activity_result_update(
        state,
        result=activity_result,
        current_count=current_count,
        last_text=last_text,
    )


def handle_priority_update(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    timezone: str,
    ref_date,
    orchestrator,
) -> dict:
    """Aplica actualización de prioridades a partir de texto libre del usuario."""
    messages = state.get("messages", [])
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))

    result = orchestrator.compute_priority_update(
        last_text,
        subjects=list(state.get("subjects", [])),
        schedule_blocks=list(schedule_state.blocks),
        academic_activities=list(state.get("academic_activities", [])),
        study_profile=dict(state.get("study_profile", {})),
        ref_date=ref_date,
        timezone=timezone,
        priorities_state=dict(state.get("priorities", {})),
    )

    if not result.detected:
        return {
            "subjects": result.subjects,
            "phase": "end",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    update: dict = {
        "subjects": result.subjects,
        "priorities": result.priorities,
        "phase": "end",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": bool(result.requires_clarification),
        "messages": append_message(messages, "assistant", result.message),
    }
    if result.replan is not None:
        update["replan"] = result.replan
    return update


# ---------------------------------------------------------------------------
# Builders de estado de interacción
# ---------------------------------------------------------------------------

def _confirmation_activity_interaction(state: AgentState, payload: dict) -> dict:
    return update_interaction_state(
        state,
        active_intent="register_academic_activity",
        active_subflow="academic_update",
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
    payload: dict,
    missing_fields: list,
) -> dict:
    return update_interaction_state(
        state,
        active_intent="register_academic_activity",
        active_subflow="academic_update",
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


def _clear_activity_interaction(state: AgentState) -> dict:
    return update_interaction_state(
        state,
        active_intent=None,
        active_subflow=None,
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
    payload: dict,
    missing_fields: list,
) -> dict:
    return update_interaction_state(
        state,
        active_intent="track_study_session",
        active_subflow="academic_update",
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


def _tracking_memory_interaction(state: AgentState, payload: dict) -> dict:
    return update_interaction_state(
        state,
        active_intent=None,
        active_subflow=None,
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


# ---------------------------------------------------------------------------
# Builders de actualizaciones de resultado (estado parcial para LangGraph)
# ---------------------------------------------------------------------------

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
            "phase": "running",
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
            "phase": "running",
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
) -> dict:
    messages = state.get("messages", [])
    base = {
        "phase": "running" if result.requires_clarification else "end",
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
    return {
        **base,
        **_tracking_replan_update(state, result),
        **interaction_update,
    }


def _activity_replan_update(state: AgentState, applied, priority_replan) -> dict:
    if priority_replan:
        return {"replan": priority_replan}
    if not applied.replan_required:
        return {}
    replan = dict(state.get("replan", {}))
    replan["trigger"] = "academic_activity"
    replan["change_request"] = dict(applied.payload)
    replan["pending_prompt"] = None
    return {"replan": replan}


def _tracking_replan_update(state: AgentState, result) -> dict:
    if not getattr(result, "replan_required", False):
        return {}
    payload = dict(getattr(result, "replan_payload", {}) or {})
    replan = dict(state.get("replan", {}))
    replan["trigger"] = str(payload.get("trigger") or "study_session_tracking")
    replan["change_request"] = payload
    replan["pending_prompt"] = result.message
    return {"replan": replan}
