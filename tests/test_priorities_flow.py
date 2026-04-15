"""Pruebas del subflujo conversacional de prioridades académicas."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.dependencies import set_personalization_service
from agents.support.agent import _route_collect_priorities, _route_persist_study_profile
from agents.support.nodes.build_study_plan.node import build_study_plan
from agents.support.nodes.collect_priorities.node import collect_priorities
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from agents.support.state import AgentState
from repositories.personalization.repository import InMemoryPersonalizationRepository
from services.personalization import (
    PersonalizationConfig,
    PersonalizationService,
    get_questions,
)
from services.scheduling import WeeklyScheduleBlock


def _academic_block(day_of_week: str, title: str) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time="08:00",
        end_time="10:00",
        source_text=f"{title} {day_of_week} 08:00-10:00",
    )


def _apply_update(state: AgentState, update: dict) -> AgentState:
    payload = state.model_dump()
    updates = dict(update)
    if "messages" in updates:
        messages = list(state.get("messages", []))
        messages.extend(updates.get("messages") or [])
        payload["messages"] = messages
        updates.pop("messages", None)
    payload.update(updates)
    return AgentState(**payload)


def _with_user_message(state: AgentState, text: str) -> AgentState:
    payload = state.model_dump()
    payload["messages"] = list(state.get("messages", [])) + [HumanMessage(content=text)]
    return AgentState(**payload)


def _completed_profile_payload() -> dict[str, object]:
    repository = InMemoryPersonalizationRepository()
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=repository,
    )
    answers = {
        question.question_id: answer
        for question, answer in zip(
            get_questions(),
            [3, 3, 2, 2, 1, 1, 0, 3, 1, 1],
            strict=True,
        )
    }
    payload = service.evaluate_answers(answers).model_dump(mode="python")
    payload["completed_at"] = "2026-01-01T08:00:00-05:00"
    return payload


def test_priorities_feature_flag_routes_after_persist_study_profile(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    personalization_service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    set_personalization_service(personalization_service)
    try:
        state = AgentState(
            phase="study_profile_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "persisted_profile_id": 9,
                "blocks": [_academic_block("monday", "Calculo")],
                "summary_text": "resumen",
                "conflicts": [],
            },
            study_profile=_completed_profile_payload(),
        )

        update = persist_study_profile(state)
        next_state = _apply_update(state, update)

        assert update["phase"] == "priorities"
        assert _route_persist_study_profile(next_state) == "collect_priorities"

        prompt_update = collect_priorities(next_state)
        assert prompt_update["phase"] == "priorities"
        assert prompt_update["awaiting_user_input"] is True
        prompt = prompt_update["messages"][0].content
        assert "Sí, actualizarlas" in prompt
        assert "Después" in prompt
        assert "usar horario" not in prompt
        assert "omitir" not in prompt
        assert "Calculo" in prompt
        assert "120 min/semana" in prompt
    finally:
        set_personalization_service(None)


def test_collect_priorities_accepts_manual_subjects_and_rebuilds_plan(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    state = AgentState(
        phase="priorities",
        awaiting_user_input=True,
        user_message_count=0,
        priorities={"status": "collecting", "source": "derived_from_schedule"},
        schedule={
            "blocks": [
                _academic_block("monday", "Calculo"),
                _academic_block("wednesday", "Programacion"),
            ]
        },
        study_profile={"top_techniques": ["pomodoro", "feynman"]},
        messages=[
            HumanMessage(
                content=(
                    "Calculo | alta | 5 | alta | 4h\n"
                    "Programacion | media | 3 | media | 180"
                )
            )
        ],
    )

    update = collect_priorities(state)
    next_state = _apply_update(state, update)

    assert update["phase"] == "study_plan"
    assert update["subjects"][0].nombre == "Calculo"
    assert update["subjects"][0].urgencia == "alta"
    assert update["subjects"][0].carga_semanal_min == 240
    assert _route_collect_priorities(next_state) == "build_study_plan"

    plan_update = build_study_plan(next_state)
    assert plan_update["phase"] == "end"
    assert plan_update["study_plan"]["rules"]["subjects_source"] == "state.subjects"
    assert len(plan_update["study_plan"]["plan_events"]) >= 2
    assert "Calculo" in plan_update["messages"][0].content


def test_collect_priorities_supports_use_schedule_command(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    state = AgentState(
        phase="priorities",
        awaiting_user_input=True,
        user_message_count=0,
        priorities={"status": "collecting", "source": "derived_from_schedule"},
        schedule={
            "blocks": [
                _academic_block("monday", "Calculo"),
                _academic_block("wednesday", "Programacion"),
            ]
        },
        study_profile={"top_techniques": ["repeticion_espaciada"]},
        messages=[HumanMessage(content="usar horario")],
    )

    update = collect_priorities(state)
    next_state = _apply_update(state, update)

    assert update["phase"] == "study_plan"
    assert len(update["subjects"]) == 2
    assert update["priorities"]["status"] == "completed"

    plan_update = build_study_plan(next_state)
    assert plan_update["phase"] == "end"
    assert plan_update["study_plan"]["rules"]["subjects_source"] == "state.subjects"
    assert plan_update["study_plan"]["rules"]["spacing_days"] == 2


def test_collect_priorities_supports_visible_later_option(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    state = AgentState(
        phase="priorities",
        awaiting_user_input=True,
        user_message_count=0,
        priorities={"status": "collecting", "source": "derived_from_schedule"},
        schedule={
            "blocks": [
                _academic_block("monday", "Calculo"),
                _academic_block("wednesday", "Programacion"),
            ]
        },
        study_profile={"top_techniques": ["repeticion_espaciada"]},
        messages=[HumanMessage(content="Después")],
    )

    update = collect_priorities(state)
    next_state = _apply_update(state, update)

    assert update["phase"] == "study_plan"
    assert len(update["subjects"]) == 2
    assert update["priorities"]["status"] == "completed"
    assert _route_collect_priorities(next_state) == "build_study_plan"


def test_collect_priorities_guides_weekly_snapshot_until_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", "1")
    state = AgentState(
        phase="priorities",
        awaiting_user_input=False,
        user_message_count=0,
        priorities={"status": "collecting", "source": "derived_from_schedule"},
        schedule={
            "blocks": [
                _academic_block("monday", "Calculo"),
                _academic_block("wednesday", "Programacion"),
                _academic_block("friday", "Fisica"),
            ]
        },
        study_profile={"top_techniques": ["pomodoro", "feynman"]},
        messages=[],
    )

    update = collect_priorities(state)
    state = _apply_update(state, update)
    assert update["priorities"]["capture_stage"] == "ask_update"
    assert "prioridades de esta semana" in update["messages"][0].content
    assert "120 min/semana" in update["messages"][0].content

    update = collect_priorities(_with_user_message(state, "si"))
    state = _apply_update(_with_user_message(state, "si"), update)
    assert update["priorities"]["capture_stage"] == "ask_top3"

    update = collect_priorities(_with_user_message(state, "3,1,2"))
    state = _apply_update(_with_user_message(state, "3,1,2"), update)
    assert update["priorities"]["capture_stage"] == "ask_urgent_subjects"
    assert update["priorities"]["draft"]["importance_order"] == [3, 1, 2]
    assert "Materia 1 de 3" in update["messages"][0].content

    update = collect_priorities(_with_user_message(state, "no"))
    state = _apply_update(_with_user_message(state, "no"), update)
    assert update["priorities"]["capture_stage"] == "ask_urgent_subjects"
    assert update["priorities"]["draft"]["urgency_subject_index"] == 2
    assert "Materia 2 de 3" in update["messages"][0].content

    update = collect_priorities(_with_user_message(state, "parcial viernes"))
    state = _apply_update(_with_user_message(state, "parcial viernes"), update)
    assert update["priorities"]["capture_stage"] == "ask_urgent_subjects"
    assert update["priorities"]["draft"]["urgency_subject_index"] == 3
    assert update["priorities"]["draft"]["urgency_details"][0]["subject_number"] == 2

    update = collect_priorities(_with_user_message(state, "no"))
    state = _apply_update(_with_user_message(state, "no"), update)
    assert update["priorities"]["capture_stage"] == "ask_difficult_subjects"

    update = collect_priorities(_with_user_message(state, "2,3"))
    state = _apply_update(_with_user_message(state, "2,3"), update)
    assert update["priorities"]["capture_stage"] == "confirm_summary"
    assert any(subject.computed_priority_score is not None for subject in update["subjects"])
    assert "prioridad semanal" in update["messages"][0].content

    update = collect_priorities(_with_user_message(state, "confirmar"))
    next_state = _apply_update(_with_user_message(state, "confirmar"), update)

    assert update["phase"] == "study_plan"
    assert update["priorities"]["status"] == "completed"
    assert update["priorities"]["capture_stage"] is None
    assert _route_collect_priorities(next_state) == "build_study_plan"
