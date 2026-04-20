"""Nodo fino para captura conversacional de prioridades académicas."""

from __future__ import annotations

from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.flows.priorities.priority_capture_service import (
    handle_priorities_turn,
)
from agents.support.priorities.config import is_post_radar_flow_enabled
from agents.support.state import AgentState


def collect_priorities(state: AgentState) -> dict:
    """Lee estado, delega al servicio y devuelve el update final."""

    update = handle_priorities_turn(state)
    priorities_state = dict(update.get("priorities") or state.get("priorities", {}))
    status = priorities_state.get("status")
    if update.get("phase") == "study_plan" and is_post_radar_flow_enabled():
        return update
    if update.get("phase") == "study_plan" or status == "skipped":
        return persist_planning_snapshot_for_update(state, update)
    return update
