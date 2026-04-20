"""Nodo fino para sincronizar pendientes accionables con Microsoft To Do."""

from agents.support.flows.sync.study_todo_sync import sync_study_todo_turn
from agents.support.state import AgentState


def sync_study_todo(state: AgentState) -> dict:
    """Delega el flujo confirmable de sync hacia To Do."""

    return sync_study_todo_turn(state)


__all__ = ["sync_study_todo"]
