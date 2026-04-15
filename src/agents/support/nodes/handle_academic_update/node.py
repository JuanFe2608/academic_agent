"""Nodo fino para cambios academicos puntuales fuera del flujo semanal."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.priorities import (
    apply_academic_event_update,
    current_week_bounds,
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)


def handle_academic_update(state: AgentState) -> dict:
    """Aplica una actualizacion puntual sin rehacer el cuestionario semanal."""

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
    week_start, week_end = current_week_bounds(reference_date)
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        primary_technique_id=_primary_technique_id(study_profile),
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

    next_phase = "study_plan" if result.event_type == "academic_deadline" and result.replan_required else "end"
    response = result.message
    if next_phase == "study_plan":
        response = f"{response} Voy a ajustar solo el plan afectado."

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
        "phase": next_phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": bool(result.requires_clarification),
        "messages": append_message(messages, "assistant", response),
    }
    if result.event_type == "academic_deadline":
        return persist_planning_snapshot_for_update(state, update)
    return update


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


def _reference_date(timezone: str):
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).date()
    except Exception:
        return datetime.now().date()
