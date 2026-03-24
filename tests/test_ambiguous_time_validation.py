"""Pruebas para supuestos horarios y casos incompletos."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details.parsing import (
    parse_extracurricular_text,
)
from agents.support.nodes.parse_schedules_to_events.node import parse_schedules_to_events
from agents.support.state import AgentState


def test_parse_schedules_to_events_assumes_military_time_for_academic_text() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_text": "Lunes 9-10 Algebra"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    assert update["events"][0].inicio == "09:00"
    assert update["events"][0].fin == "10:00"


def test_parse_extracurricular_text_assumes_military_time_when_no_meridiem() -> None:
    item, missing = parse_extracurricular_text(
        "Gym lunes y miercoles de 6 a 7",
        expected_is_variable=False,
    )

    assert item.nombre == "Gimnasio"
    assert missing == []
    assert item.hora_inicio == "06:00"
    assert item.hora_fin == "07:00"


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


def test_parse_schedules_to_events_assumes_military_time_for_work_text() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_laboral_text": "L-V 9-10"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    assert update["events"][0].inicio == "09:00"
    assert update["events"][0].fin == "10:00"


def test_parse_schedules_to_events_marks_missing_time_as_incomplete() -> None:
    state = AgentState(
        phase="schedules",
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        raw_inputs={"horario_academico_text": "Miércoles 9 Matemáticas"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "hora de inicio y fin" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_marks_missing_title_as_incomplete() -> None:
    state = AgentState(
        phase="schedules",
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        raw_inputs={"horario_academico_text": "Lunes 7-9"},
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "nombre de la materia o actividad" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_accepts_military_time_from_university_email() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={
            "horario_academico_text": (
                "DATA SCIENCE FUNDAMENTALS\n"
                "3.0 créditos, Grupo D-740\n"
                "LUN,MAR,MIE 06:00:00-07:00:00, LUN,MAR,MIE 06:00:00-07:00:00,"
            )
        },
    )

    update = parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert len(update["events"]) == 3
    assert update["events"][0].inicio == "06:00"
    assert update["events"][0].fin == "07:00"
