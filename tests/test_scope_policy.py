"""Pruebas de politica de alcance del MVP Lara."""

from __future__ import annotations

from services.conversation.scope_policy import (
    decide_scope,
    render_scope_response,
    should_answer_scope_boundary,
)


def test_policy_allows_evaluation_planning_without_solving_it() -> None:
    decision = decide_scope("Ayudame a organizar mi parcial de calculo")

    assert decision.category == "in_scope"
    assert decision.action == "normal"
    assert decision.allowed is True
    assert decision.domain == "guided_academic_support"
    assert should_answer_scope_boundary(decision) is False


def test_policy_allows_microsoft_todo_sync_request() -> None:
    decision = decide_scope("Sincroniza mis pendientes de estudio con Microsoft To Do")

    assert decision.category == "in_scope"
    assert decision.action == "normal"
    assert decision.allowed is True
    assert decision.intent == "sync_study_todo"
    assert should_answer_scope_boundary(decision) is False


def test_policy_allows_applied_study_method_guidance() -> None:
    decision = decide_scope("Como preparo una exposicion de Bases de datos?")

    assert decision.allowed is True
    assert decision.domain == "study_method_recommendation"
    assert should_answer_scope_boundary(decision) is False


def test_policy_rejects_direct_evaluation_solution() -> None:
    decision = decide_scope("Resuelveme este quiz y dame la respuesta exacta")

    assert decision.category == "hard_out_of_scope"
    assert decision.action == "reject"
    assert decision.allowed is False
    assert decision.intent == "forbidden_evaluation_solution"
    assert should_answer_scope_boundary(decision) is True
    assert "No puedo resolver evaluaciones" in render_scope_response(decision)


def test_policy_rejects_direct_deliverable_for_copying() -> None:
    decision = decide_scope("Redacta mi entrega final de bases de datos para copiar")

    assert decision.category == "hard_out_of_scope"
    assert decision.allowed is False
    assert decision.intent == "forbidden_evaluation_solution"
    assert should_answer_scope_boundary(decision) is True


def test_policy_redirects_diffuse_academic_need() -> None:
    decision = decide_scope("Estoy muy perdido con todas mis materias")

    assert decision.category == "redirectable_out_of_scope"
    assert decision.action == "redirect"
    assert decision.intent == "redirect_to_academic_planning"
    assert "organizar esa carga academica" in render_scope_response(decision)


def test_policy_escalates_wellbeing_or_crisis_signal() -> None:
    decision = decide_scope("Me siento desbordado y no se con quien hablar")

    assert decision.category == "human_support_case"
    assert decision.action == "escalate"
    assert decision.requires_human_support is True
    assert decision.domain == "risk_or_wellbeing"
    assert "apoyo humano directo" in render_scope_response(decision)


def test_policy_rejects_generalist_requests() -> None:
    decision = decide_scope("Quien es Messi?")

    assert decision.category == "hard_out_of_scope"
    assert decision.action == "reject"
    assert decision.intent == "general_out_of_scope_request"
    assert "temas academicos" in render_scope_response(decision)


def test_policy_marks_sticker_as_redirectable_non_actionable_input() -> None:
    decision = decide_scope(media_types=["sticker"])

    assert decision.category == "redirectable_out_of_scope"
    assert decision.action == "redirect"
    assert decision.intent == "noise_or_smalltalk"
