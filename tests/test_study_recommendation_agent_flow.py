"""Agent-level integration tests for study recommendation service usage."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_welcome
from agents.support.dependencies import set_study_recommendation_service
from agents.support.nodes.answer_scope_boundary import answer_scope_boundary
from agents.support.nodes.answer_study_recommendation import answer_study_recommendation
from agents.support.state import AgentState
from schemas.rag import StudyRecommendationResult


class _StudyRecommendationServiceStub:
    status = SimpleNamespace(ready=True)

    def __init__(self) -> None:
        self.queries = []

    def answer_query(self, query):
        self.queries.append(query)
        return StudyRecommendationResult(
            answer="Pomodoro organiza el estudio en bloques cortos con pausas.",
            recommended_techniques=["pomodoro"],
            source_chunks=["technique.pomodoro::answer"],
            confidence="media",
            groundedness_notes=["sources:cited"],
        )


def test_end_phase_routes_direct_study_question_to_rag_service_node() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Que es Pomodoro y cuando conviene?")],
    )

    assert _route_welcome(state) == "answer_study_recommendation"


def test_end_phase_routes_applied_method_question_to_recommendation_node() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Como estudio para parcial de Calculo en 60 minutos?")],
    )

    assert _route_welcome(state) == "answer_study_recommendation"


def test_end_phase_routes_direct_study_question_when_counter_is_already_current() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=1,
        last_user_text="Ya quedo el plan",
        messages=[HumanMessage(content="Que es Pomodoro?")],
    )

    assert _route_welcome(state) == "answer_study_recommendation"


def test_answer_study_recommendation_uses_service_and_preserves_state_boundary() -> None:
    service = _StudyRecommendationServiceStub()
    set_study_recommendation_service(service)
    try:
        state = AgentState(
            phase="end",
            awaiting_user_input=False,
            user_message_count=0,
            study_profile={
                "top_techniques": ["pomodoro"],
                "weakness_tags": ["procrastination"],
            },
            messages=[HumanMessage(content="Que es Pomodoro?")],
        )

        update = answer_study_recommendation(state)

        assert update["phase"] == "end"
        assert update["awaiting_user_input"] is False
        assert update["user_message_count"] == 1
        assert update["last_user_text"] == "Que es Pomodoro?"
        assert "Pomodoro organiza" in update["messages"][0].content
        assert service.queries[0].query_text == "Que es Pomodoro?"
        assert service.queries[0].top_techniques == ["pomodoro"]
        assert service.queries[0].student_signals == ["procrastination"]
    finally:
        set_study_recommendation_service(None)


def test_answer_study_recommendation_returns_applied_activity_steps() -> None:
    service = _StudyRecommendationServiceStub()
    set_study_recommendation_service(service)
    try:
        state = AgentState(
            phase="end",
            awaiting_user_input=False,
            user_message_count=0,
            study_profile={
                "top_techniques": ["pomodoro"],
                "weakness_tags": ["procrastination"],
            },
            messages=[
                HumanMessage(content="Como estudio para parcial de Calculo en 60 minutos?")
            ],
        )

        update = answer_study_recommendation(state)

        assert update["phase"] == "end"
        assert "Pasos sugeridos:" in update["messages"][0].content
        assert "Pomodoro" in update["messages"][0].content
        assert service.queries[0].intent == "adapt_method"
        assert service.queries[0].top_techniques == ["pomodoro"]
        assert service.queries[0].subject_name == "Calculo"
        assert service.queries[0].available_minutes == 60
    finally:
        set_study_recommendation_service(None)


def test_academic_update_keeps_precedence_over_study_recommendation_route() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Tengo parcial de calculo mañana")],
    )

    assert _route_welcome(state) == "handle_academic_update"


def test_end_phase_routes_out_of_scope_question_to_scope_boundary() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=1,
        last_user_text="Que es Feynman?",
        messages=[
            HumanMessage(content="Que es Feynman?"),
            HumanMessage(content="Quien es Messi?"),
        ],
    )

    assert _route_welcome(state) == "answer_scope_boundary"


def test_end_phase_routes_forbidden_evaluation_solution_to_scope_boundary() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Resuelveme este quiz y dame la respuesta exacta")],
    )

    assert _route_welcome(state) == "answer_scope_boundary"


def test_scope_boundary_answers_and_updates_last_user_text() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=1,
        last_user_text="Que es Feynman?",
        messages=[
            HumanMessage(content="Que es Feynman?"),
            HumanMessage(content="Quien es Messi?"),
        ],
    )

    update = answer_scope_boundary(state)

    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert update["user_message_count"] == 2
    assert update["last_user_text"] == "Quien es Messi?"
    assert "temas academicos" in update["messages"][0].content
    assert "No puedo responder sobre temas generales" in update["messages"][0].content
    assert update["interaction"]["active_intent"] == "general_out_of_scope_request"
    assert update["interaction"]["current_domain"] == "out_of_scope"


def test_scope_boundary_rejects_forbidden_evaluation_solution_with_allowed_alternative() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="Hazme la tarea completa")],
    )

    update = answer_scope_boundary(state)

    assert update["phase"] == "end"
    assert update["last_user_text"] == "Hazme la tarea completa"
    assert "No puedo resolver evaluaciones" in update["messages"][0].content
    assert "guiarte con preguntas" in update["messages"][0].content
    assert update["interaction"]["active_intent"] == "forbidden_evaluation_solution"
