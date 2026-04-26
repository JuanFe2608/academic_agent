"""Nodo de entrada puro — no modifica estado, solo activa el routing."""

from __future__ import annotations

from agents.support.state import AgentState


def entry_node(state: AgentState) -> dict:
    return {}
