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

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False


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
    assert update["events"][0].inicio == "18:00"
    assert update["events"][0].fin == "23:59"
    assert update["events"][1].dia == "Martes"
    assert update["events"][1].inicio == "00:00"
    assert update["events"][1].fin == "03:00"


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
