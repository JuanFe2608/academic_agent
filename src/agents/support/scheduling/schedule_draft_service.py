"""Servicio de aplicación para consolidar el draft del horario semanal.

Centraliza la detección de cruces, la generación del resumen y la preparación
del estado previo a la revisión final, manteniendo intacto el contrato actual
del grafo.
"""

from __future__ import annotations

from agents.support.scheduling import (
    build_schedule_summary,
    detect_schedule_conflicts,
)
from agents.support.scheduling.render import blocks_to_events
from agents.support.state import AgentState

from .state_helpers import ensure_schedule_flow_state, update_schedule_flow_state


def build_schedule_draft_turn(state: AgentState) -> dict:
    """Ordena bloques, detecta cruces y prepara el resumen del draft."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    blocks = list(schedule_state.blocks)
    updated_blocks, conflicts = detect_schedule_conflicts(blocks)
    summary_text = build_schedule_summary(updated_blocks)

    return {
        "schedule": update_schedule_flow_state(
            schedule_state,
            blocks=updated_blocks,
            conflicts=conflicts,
            summary_text=summary_text,
            review_stage="idle",
        ),
        "events": blocks_to_events(updated_blocks),
        "schedule_preview": {"text": summary_text, "image_path": None},
        "events_validated": False,
        "phase": "validate",
    }
