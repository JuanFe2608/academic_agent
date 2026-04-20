"""Pruebas del estado conversacional operativo minimo."""

from __future__ import annotations

import pytest

from agents.support.state import AgentState
from schemas.conversation import InteractionState
from services.conversation.state_helpers import (
    ensure_interaction_state,
    interaction_state_to_update,
    reset_interaction_state,
    update_interaction_state,
)


def test_interaction_state_defaults_match_phase_1_contract() -> None:
    state = InteractionState()

    assert state.active_intent is None
    assert state.current_domain is None
    assert state.interaction_mode == "guided"
    assert state.pending_action is None
    assert state.pending_entity_type is None
    assert state.pending_entity_payload == {}
    assert state.missing_fields_json == []
    assert state.confirmation_pending is False
    assert state.last_confirmation_payload is None
    assert state.noise_turn_count == 0
    assert state.last_user_messages == []
    assert state.aggregated_user_text is None
    assert state.router_confidence is None
    assert state.clarification_needed is False
    assert state.is_waiting_for_oauth is False
    assert state.is_waiting_for_verification_code is False
    assert state.current_step is None
    assert state.current_section is None


def test_interaction_state_normalizes_operational_values() -> None:
    state = InteractionState(
        active_intent="  schedule_update  ",
        interaction_mode=" CONFIRMATION ",
        pending_entity_payload=None,
        missing_fields_json="fecha",
        noise_turn_count="-3",
        last_user_messages=[" hola ", "", "  cambia mi horario "],
        router_confidence="1.5",
        current_step="  ",
    )

    assert state.active_intent == "schedule_update"
    assert state.interaction_mode == "confirmation"
    assert state.pending_entity_payload == {}
    assert state.missing_fields_json == ["fecha"]
    assert state.noise_turn_count == 0
    assert state.last_user_messages == ["hola", "cambia mi horario"]
    assert state.router_confidence == 1.0
    assert state.current_step is None


def test_ensure_interaction_state_accepts_agent_state_and_payloads() -> None:
    agent_state = AgentState(
        interaction={"active_intent": "create_task", "router_confidence": 0.72}
    )

    assert ensure_interaction_state().interaction_mode == "guided"
    assert ensure_interaction_state(agent_state).active_intent == "create_task"
    assert ensure_interaction_state(agent_state.model_dump()).router_confidence == 0.72
    assert ensure_interaction_state({"active_intent": "smalltalk"}).active_intent == "smalltalk"


def test_interaction_state_to_update_targets_nested_graph_key() -> None:
    update = interaction_state_to_update({"active_intent": "weekly_planning"})

    assert set(update) == {"interaction"}
    assert update["interaction"]["active_intent"] == "weekly_planning"
    assert update["interaction"]["interaction_mode"] == "guided"


def test_update_interaction_state_validates_fields_and_returns_full_substate() -> None:
    update = update_interaction_state(
        {"interaction": {"active_intent": "schedule_update"}},
        confirmation_pending=True,
        pending_action="confirm_schedule_change",
    )

    assert set(update) == {"interaction"}
    assert update["interaction"]["active_intent"] == "schedule_update"
    assert update["interaction"]["confirmation_pending"] is True
    assert update["interaction"]["pending_action"] == "confirm_schedule_change"

    with pytest.raises(KeyError):
        update_interaction_state({}, unknown_field=True)


def test_reset_interaction_state_returns_defaults_with_optional_overrides() -> None:
    update = reset_interaction_state(current_domain="agenda", clarification_needed=True)

    assert set(update) == {"interaction"}
    assert update["interaction"]["active_intent"] is None
    assert update["interaction"]["current_domain"] == "agenda"
    assert update["interaction"]["clarification_needed"] is True
