"""Pruebas del flujo LangGraph para caracterizacion academica."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.dependencies import (
    set_outlook_fixed_schedule_sync_service,
    set_personalization_service,
    set_schedule_service,
)
from agents.support.agent import _route_collect_schedule
from agents.support.agent import build_agent
from agents.support.nodes.collect_study_profile.node import collect_study_profile
from agents.support.nodes.collect_study_profile_tiebreaker.node import (
    collect_study_profile_tiebreaker,
)
from agents.support.nodes.persist_schedule.node import persist_schedule
from agents.support.nodes.persist_study_profile.node import persist_study_profile
from agents.support.nodes.sync_fixed_schedule.node import sync_fixed_schedule
from agents.support.state import AgentState
from repositories.personalization.repository import InMemoryPersonalizationRepository
from repositories.scheduling.repository import InMemoryScheduleRepository
from services.personalization import PersonalizationConfig, PersonalizationService
from services.scheduling import ScheduleService, WeeklyScheduleBlock


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


class _FixedScheduleSyncServiceStub:
    def sync_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        calendar_state: dict | None = None,
        calendar_id: str | None = None,
    ):
        class _Result:
            synced = True
            synced_event_map = {}

        return _Result()


def test_personalization_feature_flag_off_keeps_current_behavior(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
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

        assert update["phase"] == "schedule_sync"
        assert _route_collect_schedule(next_state) == "collect_schedule"
    finally:
        set_schedule_service(None)


def test_personalization_feature_flag_on_routes_after_persist_schedule(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
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
        sync_update = sync_fixed_schedule(next_state)
        synced_state = _apply_update(next_state, sync_update)

        assert _route_collect_schedule(next_state) == "collect_schedule"
        assert _route_collect_schedule(synced_state) == "end"
        assert sync_update["phase"] == "study_profile"
        assert sync_update["awaiting_user_input"] is True
        assert len(sync_update["messages"]) == 2
        assert "También guardé tu horario fijo en Outlook" in sync_update["messages"][0].content
        assert "Pregunta 1/10" in sync_update["messages"][1].content
        assert "Vamos a activar tu Radar de estudio" in sync_update["messages"][1].content
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_schedule_service(None)
        set_personalization_service(None)


def test_graph_sends_outlook_confirmation_and_radar_question_in_same_turn(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=InMemoryPersonalizationRepository(),
        )
    )
    try:
        graph = build_agent(checkpointer=None)
        result = graph.invoke(
            AgentState(
                phase="schedule_sync",
                awaiting_user_input=False,
                user_message_count=1,
                last_user_text="30 06 26",
                student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
                schedule={
                    "persisted_profile_id": 9,
                    "blocks": [_block()],
                    "summary_text": "resumen",
                    "conflicts": [],
                    "schedule_end_date": "2026-06-30",
                },
                calendar={"calendar_id": "calendar-1"},
                messages=[HumanMessage(content="30 06 26")],
            )
        )

        assistant_messages = [message.content for message in result["messages"] if message.type == "ai"]

        assert any(
            "También guardé tu horario fijo en Outlook hasta el 30/06/2026" in content
            for content in assistant_messages
        )
        radar_messages = [
            content for content in assistant_messages
            if "Vamos a activar tu Radar de estudio" in content
        ]
        assert len(radar_messages) == 1
        assert "Pregunta 1/10" in radar_messages[0]
        assert result["phase"] == "study_profile"
        assert result["awaiting_user_input"] is True
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_personalization_service(None)


def test_collect_study_profile_reprompts_on_invalid_answer(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
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
        assert "Necesito que me respondas solo con un número del 0 al 3" in update["messages"][0].content
    finally:
        set_personalization_service(None)


def test_personalization_flow_collects_answers_and_persists_result(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    personalization_repository = InMemoryPersonalizationRepository()
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=personalization_repository,
        )
    )
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        state = _apply_update(state, persist_schedule(state))
        assert _route_collect_schedule(state) == "collect_schedule"
        state = _apply_update(state, sync_fixed_schedule(state))
        assert state.phase == "study_profile"
        assert state.awaiting_user_input is True
        assert "Vamos a activar tu Radar de estudio" in state.messages[-1].content

        for answer in ["3", "3", "2", "2", "1", "1", "0", "2", "1", "1"]:
            state = _add_user_message(state, answer)
            state = _apply_update(state, collect_study_profile(state))

        assert state.phase == "study_profile" and state.study_profile.get("status") == "completed"
        assert state.study_profile.status == "completed"
        assert state.study_profile.completed_at is not None
        assert state.study_profile.top_techniques == [
            "pomodoro",
            "feynman",
            "repeticion_espaciada",
        ]

        state = _apply_update(state, persist_study_profile(state))

        assert state.phase == "end"
        assert state.study_profile.persisted_profile_id == 1
        final_message = state.messages[-1].content
        assert "Listo, ya identifiqué cómo puedes estudiar de forma más efectiva" in final_message
        assert "Iniciar tus sesiones con bloques claros" in final_message
        assert "Tus técnicas más recomendadas en este momento son:" not in final_message
        assert "Ahora voy a usar este resultado" not in final_message
        saved_profile = personalization_repository._profiles[15]
        assert saved_profile["questionnaire_version"] == "v3"
        assert saved_profile["scoring_version"] == "v3"
        assert len(saved_profile["answers"]) == 10
        assert len(saved_profile["scores"]) == 8
        assert saved_profile["top_techniques"] == [
            "pomodoro",
            "feynman",
            "repeticion_espaciada",
        ]
        assert saved_profile["result_payload"]["confidence"] == "alta"
        assert saved_profile["result_payload"]["signals"][0]["signal_id"] == "start_and_focus_friction"
        assert saved_profile["scores"][0]["raw_score"] == 600
        assert saved_profile["scores"][0]["max_score"] == 600
        assert saved_profile["scores"][0]["normalized_score"] == 1.0
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_schedule_service(None)
        set_personalization_service(None)


def test_personalization_flow_enters_tiebreaker_and_refines_result(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW", raising=False)
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", "1")
    set_schedule_service(ScheduleService(repository=InMemoryScheduleRepository()))
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    personalization_repository = InMemoryPersonalizationRepository()
    set_personalization_service(
        PersonalizationService(
            config=PersonalizationConfig(enabled=True),
            repository=personalization_repository,
        )
    )
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        state = _apply_update(state, persist_schedule(state))
        state = _apply_update(state, sync_fixed_schedule(state))
        assert "Vamos a activar tu Radar de estudio" in state.messages[-1].content

        for answer in ["3", "3", "2", "2", "1", "1", "0", "3", "1", "1"]:
            state = _add_user_message(state, answer)
            state = _apply_update(state, collect_study_profile(state))

        assert state.phase == "study_profile" and state.study_profile.get("status") == "tiebreaker_collecting"
        assert state.study_profile.status == "tiebreaker_collecting"
        assert state.study_profile.tiebreaker["assessment"]["needs_tiebreaker"] is True

        state = _apply_update(state, collect_study_profile_tiebreaker(state))
        assert "3 preguntas adicionales" in state.messages[-1].content
        assert "señales bastante parejas" in state.messages[-1].content
        assert "respuestas fueron bastante uniformes" not in state.messages[-1].content
        assert "Progreso 1/3: 🟩⬜⬜" in state.messages[-1].content

        for answer in ["1", "4", "4"]:
            state = _add_user_message(state, answer)
            state = _apply_update(state, collect_study_profile_tiebreaker(state))

        assert state.phase == "study_profile" and state.study_profile.get("status") == "completed"
        assert state.study_profile.tiebreaker["status"] == "completed"
        assert state.study_profile.tiebreaker["confidence_before"] == "baja"
        assert state.study_profile.tiebreaker["confidence_after"] == "alta"
        assert state.study_profile.top_techniques == [
            "pomodoro",
            "feynman",
            "repeticion_espaciada",
        ]

        state = _apply_update(state, persist_study_profile(state))

        assert state.phase == "end"
        assert "Listo, ya identifiqué cómo puedes estudiar de forma más efectiva" in state.messages[-1].content
        assert "Tus técnicas más recomendadas en este momento son:" not in state.messages[-1].content
        assert "Con tus respuestas extra" not in state.messages[-1].content
        saved_profile = personalization_repository._profiles[15]
        assert len(saved_profile["answers"]) == 13
        assert saved_profile["result_payload"]["tiebreaker"]["status"] == "completed"
        assert saved_profile["result_payload"]["tiebreaker"]["confidence_after"] == "alta"
        assert saved_profile["result_payload"]["tiebreaker"]["assessment"]["activation_reasons"] == [
            "low_gap_between_top_scores"
        ]
        assert saved_profile["result_payload"]["top_techniques"] == [
            "pomodoro",
            "feynman",
            "repeticion_espaciada",
        ]
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_schedule_service(None)
        set_personalization_service(None)
