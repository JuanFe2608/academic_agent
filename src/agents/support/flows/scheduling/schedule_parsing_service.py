"""Servicio de aplicación para parsear y normalizar horarios fijos.

Concentra la lógica de `parse_schedules_to_events` fuera del nodo LangGraph
sin alterar el contrato actual del estado ni las transiciones visibles del
flujo conversacional.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.support.nodes.utils import append_message
from agents.support.scheduling import replace_section_blocks
from agents.support.scheduling.pipeline import parse_fixed_schedule_section
from agents.support.scheduling.state_helpers import (
    ensure_raw_inputs,
    ensure_schedule_flow_state,
    raw_inputs_to_update,
    reset_schedule_review_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState
from services.scheduling.event_projection import sync_schedule_block_events
from services.scheduling.pending_schedule_support import build_schedule_pending_prompt
from services.scheduling.pending_slot_state import (
    clear_scheduling_pending_interaction,
    schedule_pending_interaction_update,
)


@dataclass(frozen=True)
class ScheduleParsingPrompts:
    """Prompt bundle para preservar la UX actual del parseo de horarios."""

    academic_text_required: str
    work_text_required: str
    work_request: str
    more_academic: str
    more_work: str


def handle_schedule_parsing_turn(
    state: AgentState,
    *,
    prompts: ScheduleParsingPrompts,
) -> dict:
    """Normaliza entradas crudas y decide el siguiente paso del flujo."""

    raw_inputs = ensure_raw_inputs(state.get("raw_inputs", {}))
    raw_inputs_update = raw_inputs_to_update(raw_inputs)
    messages = state.get("messages", [])
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    blocks = list(schedule_state.blocks)
    timezone = state.get("timezone", "America/Bogota")
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()
    capture_target = str(schedule_state.capture_target or "").strip()

    academic_text = str(raw_inputs.horario_academico_text or "").strip()
    work_text = str(raw_inputs.horario_laboral_text or "").strip()

    if raw_inputs.horario_academico_img and not academic_text:
        return _build_missing_text_update(
            raw_inputs_update,
            messages,
            prompts.academic_text_required,
        )

    if raw_inputs.horario_laboral_img and not work_text:
        return _build_missing_text_update(
            raw_inputs_update,
            messages,
            prompts.work_text_required,
        )

    academic_result = (
        parse_fixed_schedule_section(academic_text, "academic", timezone=timezone)
        if academic_text
        else None
    )
    work_result = (
        parse_fixed_schedule_section(work_text, "work", timezone=timezone)
        if work_text
        else None
    )

    if academic_result is not None:
        blocks = replace_section_blocks(blocks, "academic", academic_result.blocks)
    if work_result is not None:
        blocks = replace_section_blocks(blocks, "work", work_result.blocks)

    if academic_result and academic_result.needs_clarification:
        return _build_pending_section_update(
            state,
            raw_inputs_update,
            messages,
            schedule_state,
            blocks,
            target="academic",
            pending_items=academic_result.pending_schedule_items,
            clarifications=academic_result.clarifications,
        )

    if work_result and work_result.needs_clarification:
        return _build_pending_section_update(
            state,
            raw_inputs_update,
            messages,
            schedule_state,
            blocks,
            target="work",
            pending_items=work_result.pending_schedule_items,
            clarifications=work_result.clarifications,
        )

    if capture_target == "academic":
        return _build_more_prompt_update(
            state,
            raw_inputs_update,
            messages,
            schedule_state,
            blocks,
            target="academic",
            prompt=prompts.more_academic,
        )

    if capture_target == "work":
        return _build_more_prompt_update(
            state,
            raw_inputs_update,
            messages,
            schedule_state,
            blocks,
            target="work",
            prompt=prompts.more_work,
        )

    if occupation == "ambos" and academic_text and not work_text:
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs_update,
            "academic_pending_items": [],
            "work_pending_items": [],
            "schedule": update_schedule_flow_state(
                schedule_state,
                blocks=blocks,
                summary_text=None,
                review_stage="idle",
                capture_target="work",
                capture_stage="awaiting_input",
                conflicts=[],
                conflicts_accepted=False,
            ),
            "events": _events_for_blocks(state, blocks),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompts.work_request),
            **clear_scheduling_pending_interaction(state),
        }

    return {
        "raw_inputs": raw_inputs_update,
        "academic_pending_items": [],
        "work_pending_items": [],
        "schedule": reset_schedule_review_state(
            update_schedule_flow_state(
                schedule_state,
                blocks=blocks,
                capture_target=None,
                capture_stage="idle",
            ),
            blocks,
        ),
        "events": _events_for_blocks(state, blocks),
        "phase": "extras",
        "awaiting_user_input": False,
        **clear_scheduling_pending_interaction(state),
    }


def _build_missing_text_update(
    raw_inputs_update: dict[str, object],
    messages: list,
    prompt: str,
) -> dict:
    return {
        "phase": "schedules",
        "raw_inputs": raw_inputs_update,
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", prompt),
    }


def _build_pending_section_update(
    state: AgentState,
    raw_inputs_update: dict[str, object],
    messages: list,
    schedule_state: object,
    blocks: list,
    *,
    target: str,
    pending_items: list,
    clarifications: list[str],
) -> dict:
    prompt = (
        build_schedule_pending_prompt(target, pending_items)
        if pending_items
        else "\n".join(clarifications)
    )
    return {
        "phase": "schedules",
        "raw_inputs": raw_inputs_update,
        "academic_pending_items": pending_items if target == "academic" else [],
        "work_pending_items": pending_items if target == "work" else [],
        "schedule": update_schedule_flow_state(
            schedule_state,
            blocks=blocks,
            summary_text=None,
            review_stage="idle",
            capture_target=target,
            capture_stage="awaiting_input",
            conflicts=[],
            conflicts_accepted=False,
        ),
        "events": _events_for_blocks(state, blocks),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", prompt),
        **schedule_pending_interaction_update(
            state,
            academic_pending_items=pending_items if target == "academic" else [],
            work_pending_items=pending_items if target == "work" else [],
        ),
    }


def _build_more_prompt_update(
    state: AgentState,
    raw_inputs_update: dict[str, object],
    messages: list,
    schedule_state: object,
    blocks: list,
    *,
    target: str,
    prompt: str,
) -> dict:
    return {
        "phase": "schedules",
        "raw_inputs": raw_inputs_update,
        "academic_pending_items": [],
        "work_pending_items": [],
        "schedule": update_schedule_flow_state(
            schedule_state,
            blocks=blocks,
            summary_text=None,
            review_stage="idle",
            capture_target=target,
            capture_stage="awaiting_more",
            conflicts=[],
            conflicts_accepted=False,
        ),
        "events": _events_for_blocks(state, blocks),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", prompt),
        **clear_scheduling_pending_interaction(state),
    }


def _events_for_blocks(state: AgentState, blocks: list) -> list:
    return sync_schedule_block_events(
        list(state.get("events", [])),
        blocks,
    )
