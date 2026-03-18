"""Nodo para recalcular solo la sección corregida del horario."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details.parsing import (
    parse_extracurricular_items,
)
from agents.support.nodes.utils import append_message, normalize_text
from agents.support.scheduling import normalize_schedule_section, replace_section_blocks
from agents.support.state import AgentState


def apply_schedule_correction(state: AgentState) -> dict:
    """Reemplaza una sola sección del horario sin reiniciar onboarding."""

    schedule_state = dict(state.get("schedule", {}))
    target = str(schedule_state.get("correction_target") or "").strip()
    text = str(schedule_state.get("pending_correction_text") or "").strip()
    timezone = state.get("timezone", "America/Bogota")
    blocks = list(schedule_state.get("blocks", []))

    if target == "extracurricular" and normalize_text(text) in {
        "ninguna",
        "ninguna actividad",
        "no",
        "no tengo",
    }:
        updated_blocks = replace_section_blocks(blocks, "extracurricular", [])
        return {
            "schedule": {
                **schedule_state,
                "blocks": updated_blocks,
                "summary_text": None,
                "review_stage": "idle",
                "correction_target": None,
                "pending_correction_text": None,
                "conflicts": [],
                "conflicts_accepted": False,
            },
            "extracurricular": [],
            "extras_has_any": False,
            "phase": "draft",
            "awaiting_user_input": False,
        }

    result = normalize_schedule_section(text, target or "academic", timezone=timezone)
    if result.needs_clarification:
        return {
            "schedule": {
                **schedule_state,
                "review_stage": "awaiting_correction_payload",
            },
            "phase": "validate",
            "awaiting_user_input": True,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                "\n".join(result.clarifications),
            ),
        }

    updated_schedule_blocks = replace_section_blocks(
        blocks,
        target or "academic",
        result.blocks,
    )
    update: dict[str, object] = {
        "schedule": {
            **schedule_state,
            "blocks": updated_schedule_blocks,
            "summary_text": None,
            "review_stage": "idle",
            "correction_target": None,
            "pending_correction_text": None,
            "conflicts": [],
            "conflicts_accepted": False,
        },
        "phase": "draft",
        "awaiting_user_input": False,
    }
    if target == "academic":
        raw_inputs = dict(state.get("raw_inputs", {}))
        raw_inputs["horario_academico_text"] = text
        update["raw_inputs"] = raw_inputs
    elif target == "work":
        raw_inputs = dict(state.get("raw_inputs", {}))
        raw_inputs["horario_laboral_text"] = text
        update["raw_inputs"] = raw_inputs
    elif target == "extracurricular":
        items, _ = parse_extracurricular_items(text, expected_is_variable=False)
        update["extracurricular"] = items
        update["extras_has_any"] = bool(items)
    return update
