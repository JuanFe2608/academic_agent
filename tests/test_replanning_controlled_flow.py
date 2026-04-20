"""Cobertura de fase 15: replanificacion automatica controlada."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_handle_academic_update
from agents.support.dependencies import (
    set_study_planning_persistence_service,
    set_study_replanning_service,
)
from agents.support.flows.replanning.request_replan import handle_replan_turn
from agents.support.state import AgentState
from repositories.planning.repository import InMemoryStudyPlanningRepository
from repositories.planning.replan_repository import InMemoryStudyReplanRepository
from schemas.planning import Constraints, SubjectItem
from services.planning import (
    StudyPlanningPersistenceService,
    StudyReplanningService,
    build_initial_study_plan,
    study_plan_state_to_update,
)
from services.scheduling.models import ScheduleFlowState, WeeklyScheduleBlock


def _block(
    *,
    day: str = "monday",
    start: str = "08:00",
    end: str = "10:00",
    title: str = "Calculo",
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day,
        start_time=start,
        end_time=end,
        source_text=f"{title} {day} {start}-{end}",
        user_confirmed=True,
    )


def _subject(name: str = "Calculo") -> SubjectItem:
    return SubjectItem(
        nombre=name,
        prioridad="alta",
        dificultad=4,
        carga_semanal_min=120,
        is_priority_confirmed=True,
    )


def _planned_state() -> tuple[AgentState, object]:
    block = _block()
    subject = _subject()
    plan = build_initial_study_plan(
        schedule_blocks=[block],
        subjects=[subject],
        study_profile={"status": "completed", "top_techniques": ["pomodoro"]},
        constraints=Constraints(),
        timezone="America/Bogota",
    ).model_copy(update={"persisted_profile_id": 31, "version_number": 1})
    first_event = plan.plan_events[0]
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=1,
        last_user_text="No pude estudiar hoy",
        student_profile={"persisted_student_id": 7},
        schedule=ScheduleFlowState(blocks=[block], persisted_profile_id=12),
        subjects=[subject],
        study_profile={"status": "completed", "top_techniques": ["pomodoro"]},
        constraints=Constraints(),
        study_plan=study_plan_state_to_update(plan),
        messages=[HumanMessage(content="No pude estudiar hoy")],
        replan={
            "status": "pending",
            "trigger": "missed_study_session",
            "change_request": {
                "trigger": "missed_study_session",
                "study_plan_event_instance_id": 88,
                "study_plan_profile_id": 31,
                "source_event_id": first_event.id,
                "title": first_event.titulo,
                "planned_date": "2026-01-05",
            },
        },
    )
    return state, first_event


def _next_state(state: AgentState, update: dict, user_text: str) -> AgentState:
    payload = state.model_dump(mode="python")
    payload.update({key: value for key, value in update.items() if key != "messages"})
    payload["messages"] = list(state.messages) + list(update.get("messages") or []) + [
        HumanMessage(content=user_text)
    ]
    return AgentState(**payload)


def test_replan_service_generates_diff_for_missed_session() -> None:
    state, first_event = _planned_state()
    service = StudyReplanningService(repository=InMemoryStudyReplanRepository())

    result = service.propose_replan(
        student_id=7,
        current_study_plan=state.study_plan,
        schedule_blocks=list(state.schedule.blocks),
        subjects=list(state.subjects),
        academic_activities=[],
        study_profile=state.study_profile,
        constraints=state.constraints,
        timezone=state.timezone,
        replan_state=state.replan.model_dump(mode="python"),
    )

    assert result.proposed is True
    assert result.request_payload["replan_request_id"] == 1
    assert result.proposal_payload["proposal_number"] == 1
    assert result.impact_payload["moved_sessions"]
    moved = result.impact_payload["moved_sessions"][0]
    assert moved["title"] == first_event.titulo
    assert moved["from"] != moved["to"]
    assert "Confirmas que aplique" in result.prompt_text


def test_replan_node_requires_confirmation_before_applying_and_then_persists() -> None:
    state, first_event = _planned_state()
    replan_repository = InMemoryStudyReplanRepository()
    set_study_replanning_service(StudyReplanningService(repository=replan_repository))
    set_study_planning_persistence_service(
        StudyPlanningPersistenceService(InMemoryStudyPlanningRepository())
    )

    try:
        assert _route_handle_academic_update(state) == "request_replan"
        proposal_update = handle_replan_turn(state)
        assert proposal_update["phase"] == "replan"
        assert proposal_update["awaiting_user_input"] is True
        assert proposal_update["interaction"]["confirmation_pending"] is True
        assert proposal_update["replan"]["status"] == "proposed"
        assert "study_plan" not in proposal_update

        confirmation_state = _next_state(state, proposal_update, "si")
        applied_update = handle_replan_turn(confirmation_state)
    finally:
        set_study_replanning_service(None)
        set_study_planning_persistence_service(None)

    new_events = applied_update["study_plan"]["plan_events"]
    moved_event = next(event for event in new_events if event.titulo == first_event.titulo)

    assert applied_update["phase"] == "end"
    assert applied_update["awaiting_user_input"] is False
    assert applied_update["replan"]["status"] == "applied"
    assert applied_update["study_plan"]["persisted_profile_id"] == 1
    assert moved_event.dia != first_event.dia or moved_event.inicio != first_event.inicio
    assert replan_repository.requests[1]["status"] == "applied"
    assert replan_repository.applied_plans[1]["supersedes_study_plan_profile_id"] == 31
