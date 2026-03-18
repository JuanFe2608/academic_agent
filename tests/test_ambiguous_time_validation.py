"""Pruebas para aclaraciones de horarios ambiguos."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details.parsing import (
    parse_extracurricular_text,
)
from agents.support.nodes.parse_schedules_to_events.node import parse_schedules_to_events
from agents.support.state import AgentState


def test_parse_schedules_to_events_requests_am_pm_for_academic_text() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_text": "Lunes 9-10 Algebra"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "am o pm" in update["messages"][0].content.lower()


def test_parse_extracurricular_text_requests_am_pm_when_ambiguous() -> None:
    item, missing = parse_extracurricular_text(
        "Gym lunes y miercoles de 6 a 7",
        expected_is_variable=False,
    )

    assert item.nombre == "Gym"
    assert "aclarar AM o PM en el horario" in missing


def test_parse_schedules_to_events_accepts_one_sided_meridiem_when_safe() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_laboral_text": "Lunes de 5 a 6 am"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert len(update["events"]) == 1
    assert update["events"][0].inicio == "05:00"
    assert update["events"][0].fin == "06:00"


def test_parse_schedules_to_events_splits_overnight_work_ranges() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_laboral_text": "Lunes de 6 pm a 3 am"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert len(update["events"]) == 2
    assert update["events"][0].dia == "Lunes"
    assert update["events"][1].dia == "Martes"


def test_parse_schedules_to_events_requests_am_pm_for_work_text() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_laboral_text": "L-V 9-10"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "am o pm" in update["messages"][0].content.lower()
