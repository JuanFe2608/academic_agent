"""Pruebas del flujo LangGraph para caracterizacion academica."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_after_persist_schedule
from agents.support.nodes.collect_study_profile.node import collect_study_profile
from agents.support.nodes.persist_schedule.node import persist_schedule
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from agents.support.personalization.config import PersonalizationConfig
from agents.support.personalization.repository import InMemoryPersonalizationRepository
from agents.support.personalization.service import PersonalizationService
from agents.support.scheduling.models import WeeklyScheduleBlock
from agents.support.scheduling.repository import InMemoryScheduleRepository
from agents.support.scheduling.service import ScheduleService
from agents.support.state import AgentState
from agents.support.tools.db import (
    set_personalization_service,
    set_schedule_service,
)


def _block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="06:00",
        end_time="08:00",
        source_text="Lunes calculo 6-8",
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


def _add_user_message(state: AgentState, text: str) -> AgentState:
    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=text))
    payload = state.model_dump()
    payload["messages"] = messages
    return AgentState(**payload)


def test_personalization_feature_flag_off_keeps_current_behavior(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", raising=False)
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        update = persist_schedule(state)
        next_state = _apply_update(state, update)

        assert update["phase"] == "sync"
        assert _route_after_persist_schedule(next_state) == "end"
    finally:
        set_schedule_service(None)


def test_personalization_feature_flag_on_routes_after_persist_schedule(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=InMemoryPersonalizationRepository(),
        )
    )
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        update = persist_schedule(state)
        next_state = _apply_update(state, update)

        assert _route_after_persist_schedule(next_state) == "collect_study_profile"

        question_update = collect_study_profile(next_state)

        assert question_update["phase"] == "study_profile"
        assert "Pregunta 1 de 10" in question_update["messages"][0].content
    finally:
        set_schedule_service(None)
        set_personalization_service(None)


def test_collect_study_profile_reprompts_on_invalid_answer(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=InMemoryPersonalizationRepository(),
        )
    )
    try:
        state = AgentState(
            phase="study_profile",
            awaiting_user_input=True,
            user_message_count=0,
            study_profile={"status": "collecting", "current_question_index": 0},
            messages=[HumanMessage(content="hola")],
        )

        update = collect_study_profile(state)

        assert update["phase"] == "study_profile"
        assert update["awaiting_user_input"] is True
        assert "Necesito que respondas solo con un numero entre 0 y 3" in update["messages"][0].content
    finally:
        set_personalization_service(None)


def test_personalization_flow_collects_answers_and_persists_result(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=InMemoryPersonalizationRepository(),
        )
    )
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        state = _apply_update(state, persist_schedule(state))
        assert _route_after_persist_schedule(state) == "collect_study_profile"

        state = _apply_update(state, collect_study_profile(state))
        assert state.phase == "study_profile"
        assert state.awaiting_user_input is True

        for answer in ["3", "3", "2", "2", "1", "1", "0", "3", "1", "1"]:
            state = _add_user_message(state, answer)
            state = _apply_update(state, collect_study_profile(state))

        assert state.phase == "study_profile_persist"
        assert state.study_profile.status == "completed"
        assert state.study_profile.top_techniques == [
            "pomodoro",
            "repeticion_espaciada",
            "feynman",
        ]

        state = _apply_update(state, persist_study_profile(state))

        assert state.phase == "end"
        assert state.study_profile.persisted_profile_id == 1
        assert "Tecnica principal: Pomodoro." in state.messages[-1].content
    finally:
        set_schedule_service(None)
        set_personalization_service(None)
