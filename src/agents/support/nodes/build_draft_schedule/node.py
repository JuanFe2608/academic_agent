"""Nodo LangGraph para consolidar el draft del horario."""

from __future__ import annotations

from agents.support.scheduling.schedule_draft_service import build_schedule_draft_turn
from agents.support.state import AgentState


def build_draft_schedule(state: AgentState) -> dict:
    """Delegates draft consolidation to the scheduling application service."""

    return build_schedule_draft_turn(state)
