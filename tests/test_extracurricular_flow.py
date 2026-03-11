"""Pruebas del flujo por pasos de actividades extracurriculares."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.ask_extracurricular.node import ask_extracurricular
from agents.support.nodes.collect_extracurricular_details.node import collect_extracurricular_details
from agents.support.state import AgentState


def test_ask_extracurricular_yes_moves_to_type_stage() -> None:
    state = AgentState(
        phase="extras",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="si")],
    )

    update = ask_extracurricular(state)

    assert update["extras_collect_stage"] == "awaiting_details"
    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is True


def test_collect_extracurricular_requests_free_text_details() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
    )

    update = collect_extracurricular_details(state)

    assert update["extras_collect_stage"] == "awaiting_details"
    assert "texto libre" in update["messages"][0].content.lower()


def test_collect_extracurricular_details_adds_item_and_moves_to_more(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.nodes.collect_extracurricular_details.node.llm_normalize_extracurricular_items",
        lambda _text: None,
    )
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        extras_pending_is_variable=False,
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Natacion, martes y jueves 18:00-19:00")],
    )

    update = collect_extracurricular_details(state)

    assert update["extras_collect_stage"] == "awaiting_more"
    assert update["extras_pending_is_variable"] is None
    assert len(update["extracurricular"]) == 1
    assert update["extracurricular"][0].es_variable is False
    assert update["extracurricular"][0].hora_inicio == "18:00"
    assert update["extracurricular"][0].hora_fin == "19:00"


def test_collect_extracurricular_awaiting_more_no_uses_preview_message() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="no")],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "draft"
    assert update["awaiting_user_input"] is False
    message = update["messages"][0].content.lower()
    assert "vista previa" in message
    assert "continuemos con el horario" not in message
