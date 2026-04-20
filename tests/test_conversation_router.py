"""Pruebas del router conversacional hibrido."""

from __future__ import annotations

from services.conversation.router import route_conversation_input


def test_router_routes_end_phase_academic_activity_to_update_node() -> None:
    decision = route_conversation_input("Tengo parcial de calculo mañana", phase="end")

    assert decision.intent == "register_academic_activity"
    assert decision.domain == "activity_management"
    assert decision.route_name == "handle_academic_update"
    assert decision.action == "route"


def test_router_routes_study_session_tracking_to_update_node() -> None:
    decision = route_conversation_input("Ya termine la sesion de calculo", phase="end")

    assert decision.intent == "track_study_session"
    assert decision.domain == "session_tracking"
    assert decision.route_name == "handle_academic_update"
    assert decision.action == "route"


def test_router_routes_explicit_replan_request_to_replan_node() -> None:
    decision = route_conversation_input("Replanifica mi semana de estudio", phase="end")

    assert decision.intent == "request_replan"
    assert decision.domain == "replanning"
    assert decision.route_name == "request_replan"
    assert decision.action == "route"


def test_router_routes_study_calendar_sync_to_calendar_node() -> None:
    decision = route_conversation_input(
        "Sincroniza mis sesiones de estudio con Outlook",
        phase="end",
    )

    assert decision.intent == "sync_study_calendar"
    assert decision.domain == "calendar_action"
    assert decision.route_name == "sync_study_calendar"
    assert decision.action == "route"


def test_router_routes_study_todo_sync_to_todo_node() -> None:
    decision = route_conversation_input(
        "Sincroniza mis pendientes de estudio con Microsoft To Do",
        phase="end",
    )

    assert decision.intent == "sync_study_todo"
    assert decision.domain == "todo_action"
    assert decision.route_name == "sync_study_todo"
    assert decision.action == "route"


def test_router_routes_weekly_prioritization_request_to_priorities_node() -> None:
    decision = route_conversation_input("Quiero priorizar mis materias esta semana", phase="end")

    assert decision.intent == "request_weekly_prioritization"
    assert decision.domain == "prioritization"
    assert decision.route_name == "collect_priorities"
    assert decision.action == "route"


def test_router_routes_end_phase_study_method_question_to_recommendation_node() -> None:
    decision = route_conversation_input("Que es Pomodoro y cuando conviene?", phase="end")

    assert decision.intent == "request_study_method_recommendation"
    assert decision.domain == "study_method_recommendation"
    assert decision.route_name == "answer_study_recommendation"


def test_router_routes_applied_method_question_to_recommendation_not_activity_crud() -> None:
    decision = route_conversation_input(
        "Como preparo una exposicion de Bases de datos?",
        phase="end",
    )

    assert decision.intent == "request_study_method_recommendation"
    assert decision.domain == "study_method_recommendation"
    assert decision.route_name == "answer_study_recommendation"


def test_router_routes_socratic_mode_to_guided_support_node() -> None:
    decision = route_conversation_input(
        "Modo socratico para taller de Calculo sobre derivadas",
        phase="end",
    )

    assert decision.intent == "enter_socratic_mode"
    assert decision.domain == "guided_academic_support"
    assert decision.route_name == "guided_academic_support"


def test_router_keeps_plain_activity_with_method_word_as_activity_crud() -> None:
    decision = route_conversation_input(
        "Tengo tarea de metodos numericos manana",
        phase="end",
    )

    assert decision.intent == "register_academic_activity"
    assert decision.route_name == "handle_academic_update"


def test_router_routes_phase_8_fixed_schedule_management_intents() -> None:
    view = route_conversation_input("mostrar mi horario fijo", phase="end")
    update = route_conversation_input(
        "cambiar mi clase de Calculo a viernes 10:00-12:00",
        phase="end",
    )
    delete = route_conversation_input("eliminar trabajo del lunes", phase="end")

    assert view.intent == "view_fixed_schedule"
    assert view.domain == "schedule_management"
    assert view.route_name == "manage_fixed_schedule"
    assert update.intent == "update_fixed_schedule"
    assert update.route_name == "manage_fixed_schedule"
    assert delete.intent == "delete_fixed_schedule_item"
    assert delete.route_name == "manage_fixed_schedule"


def test_router_routes_out_of_scope_and_wellbeing_to_policy_boundary() -> None:
    out_of_scope = route_conversation_input("Quien es Messi?", phase="end")
    wellbeing = route_conversation_input(
        "Me siento desbordado y no se con quien hablar",
        phase="end",
    )

    assert out_of_scope.intent == "out_of_scope_request"
    assert out_of_scope.route_name == "answer_scope_boundary"
    assert out_of_scope.priority == 2
    assert wellbeing.intent == "wellbeing_or_crisis_signal"
    assert wellbeing.domain == "risk_or_wellbeing"
    assert wellbeing.route_name == "answer_scope_boundary"
    assert wellbeing.priority == 1


def test_router_interprets_confirmation_pending_before_new_intent() -> None:
    yes_decision = route_conversation_input(
        "si",
        phase="validate",
        interaction={
            "confirmation_pending": True,
            "current_domain": "schedule_management",
        },
    )
    no_decision = route_conversation_input(
        "no",
        phase="validate",
        interaction={
            "confirmation_pending": True,
            "current_domain": "schedule_management",
        },
    )

    assert yes_decision.intent == "confirm_action"
    assert yes_decision.action == "confirm_action"
    assert yes_decision.preserves_active_block is True
    assert yes_decision.route_name == "validate_schedule"
    assert no_decision.intent == "reject_action"
    assert no_decision.action == "reject_action"


def test_router_treats_pending_missing_field_as_missing_data_not_new_intent() -> None:
    decision = route_conversation_input(
        "viernes",
        phase="study_plan",
        interaction={
            "active_intent": "register_academic_activity",
            "current_domain": "activity_management",
            "missing_fields_json": ["fecha"],
        },
    )

    assert decision.intent == "provide_missing_data"
    assert decision.action == "provide_missing_data"
    assert decision.domain == "activity_management"
    assert decision.preserves_active_block is True
    assert decision.missing_fields_json == ["fecha"]


def test_router_does_not_mix_critical_command_with_pending_capture() -> None:
    decision = route_conversation_input(
        "borra esa actividad",
        phase="study_plan",
        interaction={
            "active_intent": "register_academic_activity",
            "current_domain": "activity_management",
            "missing_fields_json": ["fecha"],
        },
    )

    assert decision.intent == "register_academic_activity"
    assert decision.action == "route"
    assert decision.route_name == "handle_academic_update"
    assert decision.interrupts_active_block is True
    assert decision.preserves_active_block is False


def test_router_keeps_contextual_smalltalk_inside_active_block() -> None:
    decision = route_conversation_input(
        "gracias",
        phase="schedules",
        interaction={
            "active_intent": "capture_fixed_schedule",
            "current_domain": "schedule_management",
            "missing_fields_json": ["hora_fin"],
        },
    )

    assert decision.intent == "smalltalk_contextual"
    assert decision.action == "continue_active_block"
    assert decision.route_name == "request_schedules"
    assert decision.preserves_active_block is True
