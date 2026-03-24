"""Nodo para normalizar horarios académicos y laborales a bloques semanales."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.nodes.request_schedules.prompt import (
    PROMPT_LABORAL,
    PROMPT_MORE_ACADEMIC,
    PROMPT_MORE_WORK,
)
from agents.support.scheduling.pipeline import parse_fixed_schedule_section
from agents.support.scheduling.render import blocks_to_events
from agents.support.scheduling import replace_section_blocks
from agents.support.scheduling.contextual_parser import build_schedule_pending_prompt
from agents.support.state import AgentState


def parse_schedules_to_events(state: AgentState) -> dict:
    """Normaliza entradas crudas y prepara los bloques base del horario."""

    raw_inputs = dict(state.get("raw_inputs", {}))
    messages = state.get("messages", [])
    schedule_state = dict(state.get("schedule", {}))
    existing_blocks = list(schedule_state.get("blocks", []))
    timezone = state.get("timezone", "America/Bogota")
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()
    capture_target = str(schedule_state.get("capture_target") or "").strip()

    academic_text = str(raw_inputs.get("horario_academico_text") or "").strip()
    work_text = str(raw_inputs.get("horario_laboral_text") or "").strip()

    if raw_inputs.get("horario_academico_img") and not academic_text:
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "Necesito tu horario académico por escrito para poder interpretarlo.",
            ),
        }

    if raw_inputs.get("horario_laboral_img") and not work_text:
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "Necesito tu horario laboral por escrito para poder interpretarlo.",
            ),
        }

    blocks = list(existing_blocks)
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
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": academic_result.pending_schedule_items,
            "work_pending_items": [],
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
                "capture_target": "academic",
                "capture_stage": "awaiting_input",
            },
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_schedule_pending_prompt("academic", academic_result.pending_schedule_items)
                if academic_result.pending_schedule_items
                else "\n".join(academic_result.clarifications),
            ),
        }

    if work_result and work_result.needs_clarification:
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": [],
            "work_pending_items": work_result.pending_schedule_items,
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
                "capture_target": "work",
                "capture_stage": "awaiting_input",
            },
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_schedule_pending_prompt("work", work_result.pending_schedule_items)
                if work_result.pending_schedule_items
                else "\n".join(work_result.clarifications),
            ),
        }

    if capture_target == "academic":
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": [],
            "work_pending_items": [],
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
                "capture_target": "academic",
                "capture_stage": "awaiting_more",
            },
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_MORE_ACADEMIC),
        }

    if capture_target == "work":
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": [],
            "work_pending_items": [],
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
                "capture_target": "work",
                "capture_stage": "awaiting_more",
            },
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_MORE_WORK),
        }

    if occupation == "ambos" and academic_text and not work_text:
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": [],
            "work_pending_items": [],
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
                "capture_target": "work",
                "capture_stage": "awaiting_input",
            },
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_LABORAL),
        }

    return {
        "raw_inputs": raw_inputs,
        "events": blocks_to_events(blocks),
        "academic_pending_items": [],
        "work_pending_items": [],
        "schedule": {
            **schedule_state,
            "blocks": blocks,
            "summary_text": None,
            "review_stage": "idle",
            "capture_target": None,
            "capture_stage": "idle",
            "conflicts": [],
            "correction_target": None,
            "pending_correction_text": None,
            "conflicts_accepted": False,
        },
        "phase": "extras",
        "awaiting_user_input": False,
    }
