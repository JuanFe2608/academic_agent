"""Nodo fino para recolectar el perfil base del estudiante."""

from agents.support.flows.onboarding.collect_profile import collect_profile as _collect_profile
from agents.support.nodes.confirm_profile.node import confirm_profile as _confirm_profile
from agents.support.nodes.persist_profile.node import persist_profile as _persist_profile
from agents.support.state import AgentState


def collect_profile(state: AgentState) -> dict:
    """Despacha al paso correcto del ciclo de perfil según profile_stage."""

    profile_stage = state.onboarding_state.onboarding.profile_stage or "collecting"
    if profile_stage == "confirming":
        return _confirm_profile(state)
    if profile_stage == "persisting":
        return _persist_profile(state)
    return _collect_profile(state)


__all__ = ["collect_profile"]
