"""Cobertura del flujo event-driven conectado al grafo."""

from __future__ import annotations

from datetime import date, datetime as real_datetime

from langchain_core.messages import HumanMessage

import services.planning.materialization_service as materialization_module
from agents.support.agent import _route_handle_academic_update, _route_entry
from agents.support.dependencies import (
    set_academic_activity_persistence_service,
    set_tracking_service,
)
from agents.support.nodes.handle_academic_update import handle_academic_update
from agents.support.state import AgentState
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.activity_repository import InMemoryAcademicActivityRepository
from repositories.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from schemas.planning import AcademicActivity, SubjectItem
from schemas.scheduling import Event
from services.planning import (
    AcademicActivityPersistenceService,
    StudyPlanMaterializationService,
    StudySessionTrackingService,
)


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


def _next_state(state: AgentState, update: dict, next_user_text: str) -> AgentState:
    data = state.model_dump(mode="python")
    messages = list(state.messages)
    messages.extend(update.get("messages") or [])
    messages.append(HumanMessage(content=next_user_text))
    data.update({key: value for key, value in update.items() if key != "messages"})
    data["messages"] = messages
    return AgentState(**data)


def _study_event(day: str, title: str, source_id: str) -> Event:
    return Event(
        id=source_id,
        dia=day,
        inicio="18:00",
        fin="18:25",
        titulo=title,
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        prioridad="alta",
        dificultad=4,
        timezone="America/Bogota",
    )


def _tracking_service_with_materialized_session(monkeypatch):
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    materialization_service.materialize_plan_instances(
        student_id=7,
        study_plan_profile_id=31,
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    return (
        StudySessionTrackingService(repository=tracking_repository),
        instances_repository,
        tracking_repository,
    )


def test_end_phase_routes_academic_deadline_to_event_update() -> None:
    set_academic_activity_persistence_service(
        AcademicActivityPersistenceService(InMemoryAcademicActivityRepository())
    )
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        student_profile={"persisted_student_id": 7},
        subjects=[
            SubjectItem(
                nombre="Calculo",
                prioridad="media",
                dificultad=3,
                urgencia=None,
                carga_semanal_min=180,
                importance_rank_selected_by_student=1,
                computed_priority_score=0.55,
                is_priority_confirmed=True,
            )
        ],
        messages=[HumanMessage(content="Tengo parcial de calculo mañana")],
    )

    assert _route_entry(state) == "handle_academic_update"

    try:
        update = handle_academic_update(state)
        assert update["phase"] == "running"
        assert update["interaction"]["confirmation_pending"] is True

        confirmation_state = _next_state(state, update, "si")
        final_update = handle_academic_update(confirmation_state)
    finally:
        set_academic_activity_persistence_service(None)

    next_state = AgentState(
        **{
            **confirmation_state.model_dump(mode="python"),
            **{k: v for k, v in final_update.items() if k != "messages"},
        }
    )

    assert final_update["phase"] == "end"
    assert final_update["academic_activities"][0].activity_type == "parcial"
    assert final_update["academic_activities"][0].persisted_activity_id == 1
    assert final_update["subjects"][0].urgency_type == "parcial"
    assert final_update["subjects"][0].urgencia == "alta"
    assert final_update["replan"]["trigger"] == "academic_deadline"
    assert _route_handle_academic_update(next_state) == "end"


def test_academic_activity_missing_subject_uses_incremental_capture(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.nodes.handle_academic_update.node._reference_date",
        lambda timezone: date(2026, 4, 18),
    )
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        messages=[HumanMessage(content="Tengo parcial el viernes")],
    )

    first_update = handle_academic_update(state)
    second_state = _next_state(state, first_update, "Calculo")
    second_update = handle_academic_update(second_state)

    assert first_update["phase"] == "running"
    assert first_update["interaction"]["missing_fields_json"] == ["subject_name"]
    assert second_update["phase"] == "running"
    assert second_update["interaction"]["confirmation_pending"] is True
    assert second_update["interaction"]["last_confirmation_payload"]["activity"]["due_date"] == "2026-04-24"


def test_delete_academic_activity_requires_confirmation() -> None:
    activity = AcademicActivity(
        activity_type="parcial",
        subject_name="Calculo",
        due_date="2026-04-24",
    )
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        academic_activities=[activity],
        messages=[HumanMessage(content="Borra el parcial de Calculo")],
    )

    first_update = handle_academic_update(state)
    confirmation_state = _next_state(state, first_update, "si")
    final_update = handle_academic_update(confirmation_state)

    assert first_update["interaction"]["confirmation_pending"] is True
    assert first_update["interaction"]["last_confirmation_payload"]["operation"] == "delete"
    assert final_update["phase"] == "end"
    assert final_update["academic_activities"][0].status == "deleted"


def test_list_academic_activities_renders_pending_items() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        academic_activities=[
            AcademicActivity(
                activity_type="quiz",
                subject_name="Fisica",
                due_date="2026-04-20",
            )
        ],
        messages=[HumanMessage(content="listar actividades pendientes")],
    )

    update = handle_academic_update(state)

    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "Actividades pendientes" in update["messages"][0].content
    assert "quiz de Fisica" in update["messages"][0].content


def test_end_phase_routes_and_tracks_completed_study_session(monkeypatch) -> None:
    service, instances_repository, tracking_repository = _tracking_service_with_materialized_session(
        monkeypatch
    )
    set_tracking_service(service)
    monkeypatch.setattr(
        "agents.support.nodes.handle_academic_update.node._reference_datetime",
        lambda timezone: real_datetime.fromisoformat("2026-01-05T19:00:00-05:00"),
    )
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        student_profile={"persisted_student_id": 7},
        messages=[HumanMessage(content="Ya termine la sesion de calculo")],
    )

    try:
        assert _route_entry(state) == "handle_academic_update"
        update = handle_academic_update(state)
    finally:
        set_tracking_service(None)

    instance_payload = next(iter(instances_repository._instances_by_key.values()))
    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "completada" in update["messages"][0].content
    assert update["interaction"]["pending_entity_payload"]["last_study_session_instance_id"] == int(
        instance_payload["id"]
    )
    assert instance_payload["status"] == "completed"
    checkin = next(iter(tracking_repository._checkins_by_id.values()))
    assert checkin["checkin_type"] == "complete"


def test_academic_update_tracks_missed_session_and_sets_replan(monkeypatch) -> None:
    service, instances_repository, _tracking_repository = _tracking_service_with_materialized_session(
        monkeypatch
    )
    set_tracking_service(service)
    monkeypatch.setattr(
        "agents.support.nodes.handle_academic_update.node._reference_datetime",
        lambda timezone: real_datetime.fromisoformat("2026-01-05T19:00:00-05:00"),
    )
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        student_profile={"persisted_student_id": 7},
        messages=[HumanMessage(content="No pude estudiar hoy")],
    )

    try:
        update = handle_academic_update(state)
    finally:
        set_tracking_service(None)

    instance_payload = next(iter(instances_repository._instances_by_key.values()))
    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "perdida" in update["messages"][0].content
    assert update["replan"]["trigger"] == "missed_study_session"
    assert update["replan"]["change_request"]["study_plan_event_instance_id"] == int(
        instance_payload["id"]
    )
    assert instance_payload["status"] == "missed"
