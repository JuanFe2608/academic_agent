"""Contratos de disponibilidad real para sesiones de estudio."""

from __future__ import annotations

import json

from agents.support.nodes.academic_agent.tools import make_tools
from agents.support.state import AgentState
from schemas.planning import Constraints, SubjectItem
from schemas.scheduling import Event
from services.planning import build_initial_study_plan
from services.scheduling import WeeklyScheduleBlock


def _tool_by_name(tools: list, name: str):
    return next(tool for tool in tools if tool.name == name)


def _academic_block(
    day_of_week: str,
    start_time: str,
    end_time: str,
    title: str = "Calculo",
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        source_text=f"{title} {day_of_week} {start_time}-{end_time}",
    )


def _study_event(day: str = "Lunes", start: str = "06:00", end: str = "06:25") -> Event:
    return Event(
        id="study-1",
        dia=day,
        inicio=start,
        fin=end,
        titulo="Estudio · Calculo",
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        timezone="America/Bogota",
    )


def _minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)


def test_constraints_support_structured_unavailable_windows_for_transport() -> None:
    constraints = Constraints(
        unavailable_windows=[
            {
                "day": "monday",
                "start_time": "06:00",
                "end_time": "07:00",
                "reason": "transporte",
            }
        ]
    )

    assert constraints.unavailable_windows[0]["reason"] == "transporte"


def test_study_planner_treats_unavailable_windows_as_busy_time() -> None:
    plan = build_initial_study_plan(
        schedule_blocks=[_academic_block("monday", "08:00", "10:00")],
        subjects=[SubjectItem(nombre="Calculo", prioridad="alta", dificultad=3)],
        study_profile={"top_techniques": ["pomodoro"]},
        constraints={
            "preferred_study_start": "06:00",
            "preferred_study_end": "08:00",
            "unavailable_windows": [
                {
                    "day": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "reason": "transporte",
                }
            ],
        },
        timezone="America/Bogota",
    )

    assert plan.plan_events
    for event in plan.plan_events:
        if event.dia != "Lunes":
            continue
        event_start = _minutes(event.inicio)
        event_end = _minutes(event.fin)
        assert event_end <= _minutes("06:00") or event_start >= _minutes("07:00")


def test_update_constraints_accepts_unavailable_transport_windows_and_replans() -> None:
    state = AgentState(
        constraints=Constraints(),
        study_plan={"plan_events": [_study_event()]},
    )
    update_constraints = _tool_by_name(make_tools(state), "update_constraints")

    result = update_constraints.invoke(
        {
            "unavailable_windows": [
                {
                    "days": "lunes a viernes",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "reason": "transporte",
                }
            ]
        }
    )

    payload = json.loads(result)
    constraints = payload["_state_update"]["constraints"]
    assert len(constraints["unavailable_windows"]) == 5
    assert constraints["unavailable_windows"][0] == {
        "day": "monday",
        "start_time": "06:00",
        "end_time": "07:00",
        "reason": "transporte",
    }
    assert payload["_state_update"]["replan"]["trigger"] == "availability_change"
