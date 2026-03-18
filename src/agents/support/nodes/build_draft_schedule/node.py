"""Nodo para consolidar bloques, conflictos y vista resumida del horario."""

from __future__ import annotations

from agents.support.scheduling import (
    build_schedule_summary,
    detect_schedule_conflicts,
)
from agents.support.scheduling.render import blocks_to_events
from agents.support.state import AgentState


def build_draft_schedule(state: AgentState) -> dict:
    """Ordena bloques, detecta cruces y prepara render y persistencia."""

    schedule_state = dict(state.get("schedule", {}))
    blocks = list(schedule_state.get("blocks", []))
    updated_blocks, conflicts = detect_schedule_conflicts(blocks)
    summary_text = build_schedule_summary(updated_blocks)

    return {
        "schedule": {
            **schedule_state,
            "blocks": updated_blocks,
            "conflicts": conflicts,
            "summary_text": summary_text,
            "review_stage": "idle",
        },
        "events": blocks_to_events(updated_blocks),
        "schedule_preview": {"text": summary_text, "image_path": None},
        "events_validated": False,
        "phase": "validate",
    }
