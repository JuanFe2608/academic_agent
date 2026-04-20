"""Pruebas de apoyo academico guiado y modo socratico."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_welcome
from agents.support.nodes.guided_academic_support import guided_academic_support
from agents.support.state import AgentState
from services.conversation.guided_academic_support import (
    build_guided_academic_support_result,
    is_guided_academic_support_message,
    is_socratic_mode_message,
)
from services.conversation.router import route_conversation_input


def test_guided_help_request_is_detected_without_allowing_solution() -> None:
    text = "Ayudame con este taller pero no me lo resuelvas"

    assert is_guided_academic_support_message(text) is True
    assert is_socratic_mode_message(text) is False

    result = build_guided_academic_support_result(text)

    assert result.detected is True
    assert result.intent == "request_guided_academic_help"
    assert result.requires_clarification is True
    assert result.missing_fields == ["subject_name", "topic"]
    assert "sin resolverla" in result.message


def test_guided_help_generates_checklist_when_context_is_complete() -> None:
    result = build_guided_academic_support_result(
        "Ayudame con el taller de Bases de datos sobre normalizacion, quiero saber por donde empiezo"
    )

    assert result.detected is True
    assert result.requires_clarification is False
    assert result.requires_follow_up is False
    assert result.output_kind == "guided_checklist"
    assert "Checklist inicial:" in result.message
    assert "Primera pregunta orientadora:" in result.message
    assert "resolverlo por ti" in result.message


def test_direct_deliverable_solution_request_is_rejected() -> None:
    result = build_guided_academic_support_result(
        "Redacta mi entrega final de bases de datos para copiar"
    )

    assert result.detected is True
    assert result.intent == "forbidden_evaluation_solution"
    assert result.output_kind == "policy_rejection"
    assert "respuesta final para copiar" in result.message


def test_socratic_mode_asks_bounded_questions_and_then_closes() -> None:
    first = build_guided_academic_support_result(
        "Modo socratico para taller de Calculo sobre derivadas"
    )
    second = build_guided_academic_support_result(
        "Debo derivar una funcion compuesta",
        pending_payload=first.pending_payload,
    )
    third = build_guided_academic_support_result(
        "Creo que debo usar regla de la cadena",
        pending_payload=second.pending_payload,
    )
    closed = build_guided_academic_support_result(
        "Intentaria verificar sustituyendo",
        pending_payload=third.pending_payload,
    )

    assert first.requires_follow_up is True
    assert first.turn_count == 1
    assert "Pregunta 1:" in first.message
    assert second.requires_follow_up is True
    assert second.turn_count == 2
    assert "Pregunta 2:" in second.message
    assert third.requires_follow_up is False
    assert third.turn_count == 3
    assert "Pregunta 3:" in third.message
    assert closed.output_kind == "socratic_limit_reached"
    assert "Cierro esta ronda socratica" in closed.message


def test_guided_academic_support_node_stores_pending_context() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Ayudame con este taller pero no me lo resuelvas")],
    )

    update = guided_academic_support(state)

    assert update["phase"] == "guided_academic_support"
    assert update["awaiting_user_input"] is True
    assert update["interaction"]["active_intent"] == "request_guided_academic_help"
    assert update["interaction"]["current_domain"] == "guided_academic_support"
    assert update["interaction"]["missing_fields_json"] == ["subject_name", "topic"]


def test_guided_academic_support_node_completes_pending_context() -> None:
    first_state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Ayudame con este taller pero no me lo resuelvas")],
    )
    first_update = guided_academic_support(first_state)
    second_state = AgentState(
        phase=first_update["phase"],
        awaiting_user_input=first_update["awaiting_user_input"],
        user_message_count=first_update["user_message_count"],
        last_user_text=first_update["last_user_text"],
        interaction=first_update["interaction"],
        messages=[
            *first_state.messages,
            *first_update["messages"],
            HumanMessage(
                content="Bases de datos, normalizacion, quiero saber por donde empiezo"
            ),
        ],
    )

    second_update = guided_academic_support(second_state)

    assert second_update["phase"] == "end"
    assert second_update["awaiting_user_input"] is False
    assert "Checklist inicial:" in second_update["messages"][0].content
    assert second_update["interaction"]["pending_action"] is None
    assert second_update["interaction"]["pending_entity_payload"]["last_allowed_output"] == "guided_checklist"


def test_router_sends_guided_help_to_node_but_preserves_calendar_active_block() -> None:
    guided = route_conversation_input(
        "Ayudame con este taller pero no me lo resuelvas",
        phase="end",
    )
    calendar_active = route_conversation_input(
        "modo socratico para taller de calculo sobre derivadas",
        phase="calendar_sync",
        interaction={
            "active_intent": "sync_study_calendar",
            "current_domain": "calendar_action",
        },
    )

    assert guided.intent == "request_guided_academic_help"
    assert guided.route_name == "guided_academic_support"
    assert calendar_active.action == "continue_active_block"
    assert calendar_active.route_name == "sync_study_calendar"


def test_graph_welcome_routes_guided_help_to_guided_node() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Ayudame con este taller pero no me lo resuelvas")],
    )

    assert _route_welcome(state) == "guided_academic_support"
