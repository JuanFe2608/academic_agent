"""Nodo LangGraph para aplicar correcciones por sección al horario."""

from __future__ import annotations

from agents.support.flows.scheduling.schedule_review_service import (
    apply_schedule_correction_turn,
)
from agents.support.state import AgentState


def apply_schedule_correction(state: AgentState) -> dict:
    """Delega la corrección de una sección del horario al servicio de revisión."""

    return apply_schedule_correction_turn(state)
