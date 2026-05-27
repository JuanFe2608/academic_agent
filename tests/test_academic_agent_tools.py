"""Pruebas de invariantes expuestas por tools ReAct."""

from __future__ import annotations

import json
from datetime import datetime as real_datetime
from unittest.mock import MagicMock

import agents.support.nodes.academic_agent.context as agent_context
from agents.support.nodes.academic_agent.node import (
    _empty_react_response_fallback,
    _merge_academic_activities,
)
from agents.support.nodes.academic_agent.tools import make_tools
from agents.support.state import AgentState
from schemas.planning import AcademicActivity
from schemas.scheduling import Event
from services.scheduling import WeeklyScheduleBlock


def _tool_by_name(tools: list, name: str):
    return next(tool for tool in tools if tool.name == name)


class _FrozenBogotaDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls(2026, 5, 3, 16, 15)
        return cls(2026, 5, 3, 11, 15, tzinfo=tz)


def _study_session(
    event_id: str = "study-fisica",
    *,
    dia: str = "Martes",
    inicio: str = "15:00",
    fin: str = "16:00",
    titulo: str = "Estudio · Fisica",
) -> Event:
    return Event(
        id=event_id,
        dia=dia,
        inicio=inicio,
        fin=fin,
        titulo=titulo,
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        timezone="America/Bogota",
    )


def _fixed_block(
    title: str = "Fisica II",
    *,
    day: str = "tuesday",
    start: str = "08:00",
    end: str = "10:00",
    block_type: str = "academic",
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type=block_type,
        title=title,
        day_of_week=day,
        start_time=start,
        end_time=end,
        source_text=f"{title} {day} {start}-{end}",
    )


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


def test_static_prompt_distinguishes_topic_study_from_study_method_only() -> None:
    instructions = agent_context._STATIC_INSTRUCTIONS.lower()

    assert "quiero estudiar" in instructions
    assert "temas clave" in instructions
    assert "técnica" in instructions or "tecnica" in instructions


def test_static_prompt_handles_yes_after_offered_study_technique_recommendation() -> None:
    instructions = agent_context._STATIC_INSTRUCTIONS.lower()

    assert "¿quieres que te recomiende una técnica" in instructions
    assert "si" in instructions
    assert "search_study_methods" in instructions


def test_static_prompt_routes_transport_and_blocked_time_to_constraints() -> None:
    instructions = agent_context._STATIC_INSTRUCTIONS.lower()

    assert "transporte" in instructions
    assert "bloquea esa hora" in instructions
    assert "unavailable_windows" in instructions
    assert "update_constraints" in instructions


def test_static_prompt_routes_single_session_moves_to_move_tool() -> None:
    instructions = agent_context._STATIC_INSTRUCTIONS.lower()

    assert "mueve la sesión de física" in instructions
    assert "move_study_session" in instructions
    assert "si no cabe" in instructions


def test_react_empty_response_uses_safe_fallback() -> None:
    assert "repetir tu solicitud" in _empty_react_response_fallback("", tool_updates={})
    assert "Procesé tu solicitud" in _empty_react_response_fallback(
        [{"type": "text", "text": "   "}],
        tool_updates={"academic_activities": []},
    )


def test_move_study_session_updates_plan_when_target_slot_is_available() -> None:
    state = AgentState(
        study_plan={"plan_events": [_study_session()]},
        schedule={"blocks": [_fixed_block(start="08:00", end="10:00")]},
    )
    move_session = _tool_by_name(make_tools(state), "move_study_session")

    result = json.loads(
        move_session.invoke(
            {
                "session_reference": "Fisica",
                "target_day": "martes",
                "target_start_time": "17:00",
            }
        )
    )

    moved = result["_state_update"]["study_plan"]["plan_events"][0]
    assert moved["dia"] == "Martes"
    assert moved["inicio"] == "17:00"
    assert moved["fin"] == "18:00"
    assert result["_state_update"]["study_plan"]["rules"]["last_manual_session_move"]["session_id"] == "study-fisica"


def test_move_study_session_rejects_busy_slot_and_proposes_alternatives() -> None:
    state = AgentState(
        study_plan={"plan_events": [_study_session()]},
        schedule={"blocks": [_fixed_block(start="17:00", end="18:00")]},
    )
    move_session = _tool_by_name(make_tools(state), "move_study_session")

    result = move_session.invoke(
        {
            "session_reference": "Fisica",
            "target_day": "martes",
            "target_start_time": "17:00",
        }
    )

    assert "No puedo mover" in result
    assert "se cruza con" in result
    assert "Alternativas disponibles" in result


def test_move_study_session_uses_source_day_inside_reference_to_disambiguate() -> None:
    state = AgentState(
        study_plan={
            "plan_events": [
                _study_session("fisica-tue", dia="Martes", inicio="15:00", fin="16:00"),
                _study_session("fisica-thu", dia="Jueves", inicio="15:00", fin="16:00"),
            ]
        },
    )
    move_session = _tool_by_name(make_tools(state), "move_study_session")

    result = json.loads(
        move_session.invoke(
            {
                "session_reference": "Fisica del martes",
                "target_day": "viernes",
                "target_start_time": "17:00",
            }
        )
    )

    moved_by_id = {
        event["id"]: event for event in result["_state_update"]["study_plan"]["plan_events"]
    }
    assert moved_by_id["fisica-tue"]["dia"] == "Viernes"
    assert moved_by_id["fisica-thu"]["dia"] == "Jueves"


def test_move_study_session_can_place_session_after_matching_class() -> None:
    state = AgentState(
        study_plan={"plan_events": [_study_session(dia="Miercoles", inicio="08:00", fin="09:00")]},
        schedule={"blocks": [_fixed_block(start="14:00", end="16:00")]},
    )
    move_session = _tool_by_name(make_tools(state), "move_study_session")

    result = json.loads(
        move_session.invoke(
            {
                "session_reference": "Fisica",
                "after_event_reference": "clase de fisica",
            }
        )
    )

    moved = result["_state_update"]["study_plan"]["plan_events"][0]
    assert moved["dia"] == "Martes"
    assert moved["inicio"] == "16:00"
    assert moved["fin"] == "17:00"


def test_add_schedule_block_normalizes_spanish_day_typo_and_multiple_days() -> None:
    add_block = _tool_by_name(make_tools(AgentState(timezone="America/Bogota")), "add_schedule_block")

    result = json.loads(
        add_block.invoke(
            {
                "title": "Curso Frances",
                "day": "Marte y viernes",
                "start_time": "15:00",
                "end_time": "19:30",
                "block_type": "extracurricular",
            }
        )
    )

    blocks = result["_state_update"]["schedule"]["blocks"]
    assert [block["day_of_week"] for block in blocks] == ["tuesday", "friday"]
    assert {block["title"] for block in blocks} == {"Curso Frances"}
    assert all(block["start_time"] == "15:00" and block["end_time"] == "19:30" for block in blocks)
    assert all("Marte" not in block["title"] for block in blocks)


def test_add_schedule_block_accepts_laboral_alias_and_all_days_except() -> None:
    add_block = _tool_by_name(make_tools(AgentState(timezone="America/Bogota")), "add_schedule_block")

    result = json.loads(
        add_block.invoke(
            {
                "title": "Trabajo",
                "day": "todos los dias menos viernes",
                "start_time": "4 pm",
                "end_time": "11 pm",
                "block_type": "laboral",
            }
        )
    )

    blocks = result["_state_update"]["schedule"]["blocks"]
    assert [block["day_of_week"] for block in blocks] == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "saturday",
        "sunday",
    ]
    assert {block["block_type"] for block in blocks} == {"work"}
    assert {block["title"] for block in blocks} == {"Trabajo"}
    assert all(block["start_time"] == "16:00" and block["end_time"] == "23:00" for block in blocks)


def test_update_schedule_block_normalizes_spanish_day_typo_before_persisting() -> None:
    state = AgentState(
        timezone="America/Bogota",
        schedule={"blocks": [_fixed_block(title="Fisica II", day="monday", start="08:00", end="10:00")]},
    )
    update_block = _tool_by_name(make_tools(state), "update_schedule_block")

    result = json.loads(
        update_block.invoke(
            {
                "block_reference": "Fisica",
                "day": "marte",
                "start_time": "3 pm",
                "end_time": "5 pm",
            }
        )
    )

    block = result["_state_update"]["schedule"]["blocks"][0]
    assert block["day_of_week"] == "tuesday"
    assert block["start_time"] == "15:00"
    assert block["end_time"] == "17:00"


def test_update_schedule_block_asks_only_missing_time_when_day_and_partial_time() -> None:
    state = AgentState(
        timezone="America/Bogota",
        schedule={"blocks": [_fixed_block(title="Fisica II", day="monday", start="08:00", end="10:00")]},
    )
    update_block = _tool_by_name(make_tools(state), "update_schedule_block")

    result = update_block.invoke(
        {
            "block_reference": "Fisica",
            "day": "martes",
            "start_time": "5 pm",
        }
    )

    assert "hora de fin" in result
    assert "nombre" not in result.lower()


def test_get_schedule_blocks_when_outlook_fixed_schedule_has_manual_drift(monkeypatch) -> None:
    reconciliation_service = MagicMock()
    reconciliation_service.reconcile_schedule_profile.return_value = MagicMock(
        reconciled=True,
        schedule_profile_id=9,
        drifted_count=1,
        missing_count=0,
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_outlook_fixed_schedule_reconciliation_service",
        lambda: reconciliation_service,
    )
    state = AgentState(
        student_profile={"persisted_student_id": 15},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "cal-1"},
        schedule={
            "persisted_profile_id": 9,
            "blocks": [_fixed_block(title="Fisica II", day="monday", start="08:00", end="10:00")],
        },
    )
    get_schedule = _tool_by_name(make_tools(state), "get_schedule")

    result = json.loads(get_schedule.invoke({}))

    assert "Detecté cambios manuales" in result["result"]
    assert result["_state_update"]["phase"] == "schedule_repair"
    assert result["_state_update"]["schedule"]["repair_stage"] == "awaiting_decision"


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


def test_sync_plan_to_calendar_asks_before_overwriting_manual_outlook_change(monkeypatch) -> None:
    materialization_service = MagicMock()
    materialization_service.materialize_plan_instances.return_value = MagicMock(
        materialized=True,
        materialized_instance_count=1,
        superseded_instance_count=0,
    )
    calendar_service = MagicMock()
    reconciliation_service = MagicMock()
    reconciliation_service.reconcile_student_calendar.return_value = MagicMock(
        reconciled=True,
        drifted_count=1,
        missing_count=0,
        findings=[
            MagicMock(
                status="drifted",
                title="Estudiar Bases de Datos",
                source_instance_key="study-plan:77:1",
            )
        ],
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_study_plan_materialization_service",
        lambda: materialization_service,
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_outlook_calendar_sync_service",
        lambda: calendar_service,
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_outlook_study_calendar_reconciliation_service",
        lambda: reconciliation_service,
    )
    state = AgentState(
        student_profile={"persisted_student_id": 15},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "cal-1"},
        study_plan={
            "persisted_profile_id": 77,
            "plan_events": [
                Event(
                    id="study-1",
                    dia="Lunes",
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

    result = json.loads(sync_calendar.invoke({}))

    assert "Detecté que editaste" in result["result"]
    assert result["_state_update"]["study_plan"]["rules"]["external_sync_status"] == "awaiting_manual_outlook_decision"
    calendar_service.sync_student_calendar.assert_not_called()


def test_sync_tasks_to_todo_asks_before_overwriting_manual_todo_change(monkeypatch) -> None:
    activity = AcademicActivity(
        activity_id="act-1",
        activity_type="proyecto",
        subject_name="Bases",
        activity_title="Entrega final",
        due_date="2026-05-10",
        status="pending",
        todo_task_id="todo-act-1",
    )
    state = AgentState(
        student_profile={"persisted_student_id": 7},
        calendar={"todo_task_list_id": "todo-list-1"},
        academic_activities=[activity],
    )
    sync_tool = _tool_by_name(make_tools(state), "sync_tasks_to_todo")
    todo_service = MagicMock()
    todo_service.sync_academic_activities_to_todo.return_value = MagicMock(
        synced=False,
        requires_confirmation=True,
        synced_activities=[activity],
        imported_completed_count=0,
        inbound_changes=[
            {
                "activity_id": "act-1",
                "activity_title": "Entrega final",
                "changed_fields": ["title", "due_date"],
                "todo_title": "[proyecto] Bases: Entrega ajustada",
                "todo_due_date": "2026-05-12",
            }
        ],
    )
    monkeypatch.setattr(
        "agents.support.dependencies.get_microsoft_todo_sync_service",
        lambda: todo_service,
    )

    result = json.loads(sync_tool.invoke({}))

    assert "Detecté cambios manuales en Microsoft To Do" in result["result"]
    assert "No los voy a sobrescribir" in result["result"]
    assert "Importar esos cambios" in result["result"]
    assert result["_state_update"]["academic_activities"][0]["activity_id"] == "act-1"
    todo_service.sync_academic_activities_to_todo.assert_called_once()
    _, kwargs = todo_service.sync_academic_activities_to_todo.call_args
    assert kwargs["import_manual_todo_changes"] is False
    assert kwargs["restore_manual_todo_changes"] is False


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
