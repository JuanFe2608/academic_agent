"""Nodo para gestion conversacional del horario fijo."""

from agents.support.flows.scheduling.fixed_schedule_management_service import (
    handle_fixed_schedule_management_turn,
)
from agents.support.state import AgentState


def manage_fixed_schedule(state: AgentState) -> dict:
    """Consulta, modifica o elimina bloques del horario fijo confirmado."""

    return handle_fixed_schedule_management_turn(state)


__all__ = ["manage_fixed_schedule"]
