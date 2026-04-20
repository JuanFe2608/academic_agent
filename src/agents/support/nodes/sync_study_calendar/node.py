"""Nodo fino para sincronizar sesiones de estudio con Outlook."""

from agents.support.flows.sync.study_calendar_sync import sync_study_calendar_turn
from agents.support.state import AgentState


def sync_study_calendar(state: AgentState) -> dict:
    """Delega el flujo confirmable de sync de calendario."""

    return sync_study_calendar_turn(state)


__all__ = ["sync_study_calendar"]
