"""Nodo fino para replanificacion automatica controlada."""

from agents.support.flows.replanning.request_replan import handle_replan_turn
from agents.support.state import AgentState


def request_replan(state: AgentState) -> dict:
    """Delega el flujo de propuesta, confirmacion y aplicacion."""

    return handle_replan_turn(state)


__all__ = ["request_replan"]
