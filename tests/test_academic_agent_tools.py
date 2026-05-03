"""Pruebas de invariantes expuestas por tools ReAct."""

from __future__ import annotations

from datetime import datetime as real_datetime
from unittest.mock import MagicMock

import agents.support.nodes.academic_agent.context as agent_context
from agents.support.nodes.academic_agent.node import _merge_academic_activities
from agents.support.nodes.academic_agent.tools import make_tools
from agents.support.state import AgentState
from schemas.planning import AcademicActivity
from schemas.scheduling import Event


def _tool_by_name(tools: list, name: str):
    return next(tool for tool in tools if tool.name == name)


class _FrozenBogotaDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls(2026, 5, 3, 16, 15)
        return cls(2026, 5, 3, 11, 15, tzinfo=tz)


def test_dynamic_context_uses_bogota_current_date(monkeypatch) -> None:
    monkeypatch.setattr(agent_context, "datetime", _FrozenBogotaDateTime)

    context = agent_context.build_dynamic_context(
        AgentState(timezone="America/Bogota")
    )

    assert "Hoy en Bogotá/Colombia es: Domingo 3 de mayo de 2026, 11:15" in context
    assert "Fecha ISO actual: 2026-05-03" in context
    assert "Zona horaria: America/Bogota" in context


def test_get_current_datetime_tool_uses_bogota_timezone(monkeypatch) -> None:
    monkeypatch.setattr(agent_context, "datetime", _FrozenBogotaDateTime)
    current_datetime = _tool_by_name(
        make_tools(AgentState(timezone="America/Bogota")),
        "get_current_datetime",
    )

    result = current_datetime.invoke({})

    assert "Domingo 3 de mayo de 2026, 11:15" in result
    assert "Fecha ISO: 2026-05-03" in result


def test_add_academic_activity_rejects_work_context() -> None:
    state = AgentState()
    add_activity = _tool_by_name(make_tools(state), "add_academic_activity")

    result = add_activity.invoke(
        {
            "subject": "Trabajo",
            "activity_type": "entrega",
            "title": "Turno de oficina",
            "due_date": "2026-05-01",
            "is_priority": False,
            "difficulty": 3,
        }
    )

    assert "actividad laboral o extracurricular" in result
    assert "add_schedule_block" in result


def test_add_academic_activity_allows_known_academic_subject_with_work_title() -> None:
    state = AgentState(
        subjects=[
            {
                "nombre": "Gestion de Proyectos",
                "prioridad": "media",
                "dificultad": 3,
            }
        ]
    )
    add_activity = _tool_by_name(make_tools(state), "add_academic_activity")

    result = add_activity.invoke(
        {
            "subject": "Gestion de Proyectos",
            "activity_type": "entrega",
            "title": "Trabajo final",
            "due_date": "2026-05-01",
            "is_priority": False,
            "difficulty": 3,
        }
    )

    assert "registr" in result.lower()


def test_get_pending_activities_includes_later_deadlines(monkeypatch) -> None:
    monkeypatch.setattr(agent_context, "datetime", _FrozenBogotaDateTime)
    state = AgentState(
        timezone="America/Bogota",
        academic_activities=[
            {
                "activity_type": "proyecto",
                "subject_name": "Ciberseguridad",
                "activity_title": "Proyecto final",
                "due_date": "2026-05-11",
                "priority_level": "media",
                "status": "pending",
            }
        ],
    )
    pending = _tool_by_name(make_tools(state), "get_pending_activities")

    result = pending.invoke({"days_ahead": 7})

    assert "Más adelante" in result
    assert "Proyecto final" in result
    assert "faltan 8 días" in result


def test_sync_plan_to_calendar_materializes_before_outlook_sync(monkeypatch) -> None:
    materialization_service = MagicMock()
    materialization_service.materialize_plan_instances.return_value = MagicMock(
        materialized=True,
        materialized_instance_count=1,
        superseded_instance_count=0,
    )
    calendar_service = MagicMock()
    calendar_service.sync_student_calendar.return_value = MagicMock(
        synced=True,
        upserted_count=1,
        deleted_count=0,
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_study_plan_materialization_service",
        lambda: materialization_service,
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_outlook_calendar_sync_service",
        lambda: calendar_service,
    )
    state = AgentState(
        student_profile={"persisted_student_id": 15},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "cal-1"},
        study_plan={
            "persisted_profile_id": 77,
            "plan_events": [
                Event(
                    id="study-1",
                    dia="monday",
                    inicio="08:00",
                    fin="09:00",
                    titulo="Estudiar Bases de Datos",
                    tipo="confirmado",
                    categoria="estudio",
                    origen="study_plan",
                    timezone="America/Bogota",
                )
            ],
        },
    )
    sync_calendar = _tool_by_name(make_tools(state), "sync_plan_to_calendar")

    result = sync_calendar.invoke({})

    assert "Sincronización completada" in result
    materialization_service.materialize_plan_instances.assert_called_once()
    calendar_service.sync_student_calendar.assert_called_once()
    assert calendar_service.sync_student_calendar.call_args.kwargs["study_plan_profile_id"] == 77


def test_hydration_activity_merge_keeps_durable_metadata() -> None:
    local = AcademicActivity(
        activity_id="act-1",
        activity_type="proyecto",
        subject_name="Ciberseguridad",
        activity_title="Proyecto final",
        due_date="2026-05-11",
        status="pending",
    )
    durable = local.model_copy(update={"todo_task_id": "todo-123"})
    other_local = AcademicActivity(
        activity_id="act-local",
        activity_type="tarea",
        subject_name="Bases",
        activity_title="Consulta",
        due_date="2026-05-12",
        status="pending",
    )

    merged = _merge_academic_activities(durable=[durable], local=[local, other_local])

    by_id = {activity.activity_id: activity for activity in merged}
    assert by_id["act-1"].todo_task_id == "todo-123"
    assert by_id["act-local"].activity_title == "Consulta"
