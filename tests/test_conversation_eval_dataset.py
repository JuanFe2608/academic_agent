"""Dataset minimo de regresion conversacional para fase 20."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from schemas.channels import BufferedMessage
from services.channels.message_buffer import MessageBuffer
from services.conversation import (
    build_buffer_audit_event,
    build_router_audit_event,
    route_conversation_input,
)


@dataclass(frozen=True)
class ConversationScenario:
    name: str
    text: str
    phase: str = "end"
    interaction: dict[str, object] = field(default_factory=dict)
    expected_intent: str = ""
    expected_domain: str = ""
    expected_action: str = "route"
    expected_route: str | None = None


ROUTER_EVAL_DATASET = [
    ConversationScenario(
        name="actividad_puntual",
        text="Tengo parcial de calculo el viernes",
        expected_intent="register_academic_activity",
        expected_domain="activity_management",
        expected_route="handle_academic_update",
    ),
    ConversationScenario(
        name="tracking_sesion",
        text="Ya termine la sesion de calculo",
        expected_intent="track_study_session",
        expected_domain="session_tracking",
        expected_route="handle_academic_update",
    ),
    ConversationScenario(
        name="replanificacion",
        text="Replanifica mi semana de estudio",
        expected_intent="request_replan",
        expected_domain="replanning",
        expected_route="request_replan",
    ),
    ConversationScenario(
        name="sync_outlook",
        text="Sincroniza mis sesiones de estudio con Outlook",
        expected_intent="sync_study_calendar",
        expected_domain="calendar_action",
        expected_route="sync_study_calendar",
    ),
    ConversationScenario(
        name="sync_todo",
        text="Sincroniza mis pendientes de estudio con Microsoft To Do",
        expected_intent="sync_study_todo",
        expected_domain="todo_action",
        expected_route="sync_study_todo",
    ),
    ConversationScenario(
        name="guia_academica",
        text="Ayudame con este taller pero no me lo resuelvas",
        expected_intent="request_guided_academic_help",
        expected_domain="guided_academic_support",
        expected_route="guided_academic_support",
    ),
    ConversationScenario(
        name="modo_socratico",
        text="Modo socratico para taller de Calculo sobre derivadas",
        expected_intent="enter_socratic_mode",
        expected_domain="guided_academic_support",
        expected_route="guided_academic_support",
    ),
    ConversationScenario(
        name="rechazo_quiz",
        text="Resuelveme este quiz y dame la respuesta exacta",
        expected_intent="out_of_scope_request",
        expected_domain="out_of_scope",
        expected_action="answer_policy",
        expected_route="answer_scope_boundary",
    ),
    ConversationScenario(
        name="bienestar",
        text="Me siento desbordado y no se con quien hablar",
        expected_intent="wellbeing_or_crisis_signal",
        expected_domain="risk_or_wellbeing",
        expected_action="answer_policy",
        expected_route="answer_scope_boundary",
    ),
    ConversationScenario(
        name="dato_faltante",
        text="viernes",
        phase="running",
        interaction={
            "active_intent": "register_academic_activity",
            "current_domain": "activity_management",
            "missing_fields_json": ["due_date"],
        },
        expected_intent="provide_missing_data",
        expected_domain="activity_management",
        expected_action="provide_missing_data",
        expected_route="handle_academic_update",
    ),
    ConversationScenario(
        name="confirmacion",
        text="si",
        phase="running",
        interaction={
            "active_intent": "sync_study_calendar",
            "current_domain": "calendar_action",
            "confirmation_pending": True,
        },
        expected_intent="confirm_action",
        expected_domain="calendar_action",
        expected_action="confirm_action",
        expected_route="sync_study_calendar",
    ),
    ConversationScenario(
        name="bloque_activo_preserva_calendario",
        text="Modo socratico para taller de Calculo sobre derivadas",
        phase="running",
        interaction={
            "active_intent": "sync_study_calendar",
            "current_domain": "calendar_action",
        },
        expected_intent="sync_study_calendar",
        expected_domain="calendar_action",
        expected_action="continue_active_block",
        expected_route="sync_study_calendar",
    ),
]


def test_router_eval_dataset_matches_expected_decisions() -> None:
    mismatches: list[str] = []

    for scenario in ROUTER_EVAL_DATASET:
        decision = route_conversation_input(
            scenario.text,
            phase=scenario.phase,
            interaction=scenario.interaction,
        )
        actual = (
            decision.intent,
            decision.domain,
            decision.action,
            decision.route_name,
        )
        expected = (
            scenario.expected_intent,
            scenario.expected_domain,
            scenario.expected_action,
            scenario.expected_route,
        )
        if actual != expected:
            mismatches.append(f"{scenario.name}: expected={expected!r} actual={actual!r}")

    assert mismatches == []


def test_router_audit_event_explains_decision_without_raw_text() -> None:
    text = "Tengo parcial de calculo el viernes"
    decision = route_conversation_input(text, phase="end")

    event = build_router_audit_event(decision, phase="end")
    serialized = str(event).lower()

    assert event["event"] == "conversation.router_decision"
    assert event["decision"]["intent"] == "register_academic_activity"
    assert event["decision"]["reason"] == "new_intent_detection"
    assert event["classification"]["possible_intent"] == "manage_academic_activity"
    assert "tengo parcial" not in serialized
    assert "calculo" not in serialized


def test_buffer_audit_event_keeps_payload_safe() -> None:
    buffer = MessageBuffer(flush_timeout_seconds=30)
    received_at = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)

    buffer.add_message(
        BufferedMessage(
            conversation_id="573001112233",
            sender_id="573001112233",
            message_id="msg-1",
            text="Soy Andres Gomez",
            received_at=received_at,
        )
    )
    buffer.add_message(
        BufferedMessage(
            conversation_id="573001112233",
            sender_id="573001112233",
            message_id="msg-2",
            text="codigo 67000921",
            received_at=received_at,
        )
    )
    aggregated = buffer.flush("573001112233", reason="manual")

    assert aggregated is not None
    event = build_buffer_audit_event(aggregated)
    serialized = str(event).lower()

    assert event["event"] == "conversation.buffer_flush"
    assert event["message_count"] == 2
    assert event["text_stats"]["has_digits"] is True
    assert event["text_stats"]["looks_like_phone"] is True
    assert event["conversation_fingerprint"] is not None
    assert "andres" not in serialized
    assert "67000921" not in serialized
    assert "573001112233" not in serialized
