"""Nodo dispatcher para el flujo completo de captura y confirmacion del horario."""

from __future__ import annotations

from agents.support.nodes.apply_schedule_correction.node import (
    apply_schedule_correction as _apply_schedule_correction,
)
from agents.support.nodes.ask_extracurricular.node import (
    ask_extracurricular as _ask_extracurricular,
)
from agents.support.nodes.build_draft_schedule.node import (
    build_draft_schedule as _build_draft_schedule,
)
from agents.support.nodes.collect_extracurricular_details.node import (
    collect_extracurricular_details as _collect_extracurricular_details,
)
from agents.support.nodes.parse_schedules_to_events.node import (
    parse_schedules_to_events as _parse_schedules_to_events,
)
from agents.support.nodes.persist_schedule.node import (
    persist_schedule as _persist_schedule,
)
from agents.support.nodes.render_schedule_preview.node import (
    render_schedule_preview as _render_schedule_preview,
)
from agents.support.nodes.request_schedules.node import (
    request_schedules as _request_schedules,
)
from agents.support.nodes.sync_fixed_schedule.node import (
    sync_fixed_schedule as _sync_fixed_schedule,
)
from agents.support.nodes.validate_schedule.node import (
    validate_schedule as _validate_schedule,
)
from agents.support.state import AgentState


def collect_schedule(state: AgentState) -> dict:
    """Despacha al paso correcto del flujo de horario según phase y sub-estado."""

    phase = state.conversation_state.phase
    if phase == "schedules":
        return _dispatch_schedules(state)
    if phase == "extras":
        return _dispatch_extras(state)
    if phase == "draft":
        return _build_draft_schedule(state)
    if phase == "validate":
        if not state.scheduling_state.schedule_preview.image_path:
            return _render_schedule_preview(state)
        return _validate_schedule(state)
    if phase == "schedule_edit":
        return _apply_schedule_correction(state)
    if phase == "schedule_persist":
        return _persist_schedule(state)
    if phase == "schedule_sync":
        return _sync_fixed_schedule(state)
    return _request_schedules(state)


def _dispatch_schedules(state: AgentState) -> dict:
    """Decide entre captura de texto o parseo según disponibilidad de datos."""

    scheduling = state.scheduling_state
    onboarding = state.onboarding_state
    conversation = state.conversation_state
    occupation = onboarding.student_profile.occupation
    raw_inputs = scheduling.raw_inputs
    academic_pending = scheduling.academic_pending_items
    work_pending = scheduling.work_pending_items
    capture_target = scheduling.schedule.capture_target

    if occupation and not academic_pending and not work_pending:
        if capture_target in {"academic", "work"} and not conversation.awaiting_user_input:
            return _parse_schedules_to_events(state)
        if (
            not conversation.awaiting_user_input
            and (raw_inputs.horario_academico_text or raw_inputs.horario_laboral_text)
            and not (occupation == "ambos" and not raw_inputs.horario_academico_text)
        ):
            return _parse_schedules_to_events(state)

    return _request_schedules(state)


def _dispatch_extras(state: AgentState) -> dict:
    """Despacha dentro del flujo de extracurriculares según extras_collect_stage."""

    stage = state.scheduling_state.extras_collect_stage
    if stage is None:
        return _ask_extracurricular(state)
    if stage == "done":
        return _build_draft_schedule(state)
    return _collect_extracurricular_details(state)
