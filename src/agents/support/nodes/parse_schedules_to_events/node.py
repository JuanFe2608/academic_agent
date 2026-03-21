"""Nodo para normalizar horarios académicos y laborales a bloques semanales."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.scheduling import normalize_schedule_section, replace_section_blocks
from agents.support.scheduling.contextual_parser import (
    build_schedule_pending_prompt,
    parse_schedule_section_with_context,
)
from agents.support.scheduling.render import blocks_to_events
from agents.support.state import AgentState


def parse_schedules_to_events(state: AgentState) -> dict:
    """Normaliza entradas crudas y prepara los bloques base del horario."""

    raw_inputs = dict(state.get("raw_inputs", {}))
    messages = state.get("messages", [])
    schedule_state = dict(state.get("schedule", {}))
    existing_blocks = list(schedule_state.get("blocks", []))
    timezone = state.get("timezone", "America/Bogota")
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()

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
    clarifications: list[str] = []
    academic_pending_items: list = []
    work_pending_items: list = []

    if academic_text:
        academic_context_blocks, academic_context_clarifications, academic_pending_items = (
            parse_schedule_section_with_context(
                academic_text,
                "academic",
                timezone=timezone,
            )
        )
        if academic_pending_items:
            blocks = replace_section_blocks(blocks, "academic", academic_context_blocks)
            clarifications.extend(academic_context_clarifications)
        else:
            academic_result = normalize_schedule_section(
                academic_text,
                "academic",
                timezone=timezone,
            )
            if academic_result.needs_clarification:
                if academic_context_blocks:
                    blocks = replace_section_blocks(blocks, "academic", academic_context_blocks)
                elif not academic_context_blocks:
                    clarifications.extend(academic_result.clarifications)
            else:
                blocks = replace_section_blocks(blocks, "academic", academic_result.blocks)

    if occupation == "ambos" or work_text:
        work_context_blocks, work_context_clarifications, work_pending_items = parse_schedule_section_with_context(
            work_text,
            "work",
            timezone=timezone,
        )
        if work_pending_items:
            blocks = replace_section_blocks(blocks, "work", work_context_blocks)
            clarifications.extend(work_context_clarifications)
        else:
            work_result = normalize_schedule_section(
                work_text,
                "work",
                timezone=timezone,
            )
            if work_result.needs_clarification:
                if work_context_blocks:
                    blocks = replace_section_blocks(blocks, "work", work_context_blocks)
                elif not work_context_blocks:
                    clarifications.extend(work_result.clarifications)
            else:
                blocks = replace_section_blocks(blocks, "work", work_result.blocks)

    if clarifications:
        prompt = "\n".join(dict.fromkeys(clarifications))
        if academic_pending_items:
            prompt = build_schedule_pending_prompt("academic", academic_pending_items)
        elif work_pending_items:
            prompt = build_schedule_pending_prompt("work", work_pending_items)
        return {
            "phase": "schedules",
            "raw_inputs": raw_inputs,
            "events": blocks_to_events(blocks),
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "schedule": {
                **schedule_state,
                "blocks": blocks,
                "summary_text": None,
                "review_stage": "idle",
            },
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                prompt,
            ),
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
            "conflicts": [],
            "correction_target": None,
            "pending_correction_text": None,
            "conflicts_accepted": False,
        },
        "phase": "extras",
        "awaiting_user_input": False,
    }
