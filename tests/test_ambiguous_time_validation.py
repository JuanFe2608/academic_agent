"""Pruebas para deteccion de horarios ambiguos sin AM/PM."""

from __future__ import annotations

from agents.support.nodes.parse_schedules_to_events.node import parse_schedules_to_events
from agents.support.nodes.collect_extracurricular_details.node import parse_extracurricular_text
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
        "Gym, martes y lunes de 9-10",
        expected_is_variable=False,
    )

    assert item.nombre == "Gym"
    assert any("am o pm" in field.lower() for field in missing)


def test_parse_schedules_to_events_requests_am_pm_for_academic_text_with_minutes() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_text": "Lunes 9:00-10:00 Algebra"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "am o pm" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_requests_am_pm_for_work_text() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_laboral_text": "L-V 9-10"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario laboral" in update["messages"][0].content.lower()
    assert "am o pm" in update["messages"][0].content.lower()
