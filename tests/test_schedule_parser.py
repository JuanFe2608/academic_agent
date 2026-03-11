"""Pruebas basicas para el parser de horarios laborales."""

import pytest

from agents.support.tools.schedule_parser import (
    parse_academic_schedule_text,
    parse_work_schedule_text,
)


@pytest.mark.parametrize(
    ("text", "expected_days", "start", "end"),
    [
        (
            "Trabajo de lunes a viernes de 7am a 4pm",
            ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"],
            "07:00",
            "16:00",
        ),
        (
            "L-V 07:00-16:00",
            ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"],
            "07:00",
            "16:00",
        ),
        ("Sabados 8:00-12:00", ["Sabado"], "08:00", "12:00"),
        ("Sabado 8am-12pm", ["Sabado"], "08:00", "12:00"),
        ("Lunes 19:00-22:00", ["Lunes"], "19:00", "22:00"),
        ("Martes de 7:30 am a 9:00 am", ["Martes"], "07:30", "09:00"),
        ("Trabajo todos los dias de 05:00 a 06:00", ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"], "05:00", "06:00"),
    ],
)
def test_parse_work_schedule_text(text, expected_days, start, end):
    """Valida cantidad de eventos y normalizacion de campos."""
    events = parse_work_schedule_text(text)

    assert len(events) == len(expected_days)
    assert [event.dia for event in events] == expected_days
    assert all(event.inicio == start for event in events)
    assert all(event.fin == end for event in events)
    assert all(event.categoria == "laboral" for event in events)
    assert all(event.titulo == "Trabajo" for event in events)


def test_parse_invalid_text():
    with pytest.raises(ValueError):
        parse_work_schedule_text("No tengo horario fijo")


def test_parse_work_schedule_multiline_day_entries():
    text = "Lunes 07:00-16:00 Trabajo\nMiercoles de 5 am a 6 am Trabajo"
    events = parse_work_schedule_text(text)

    assert len(events) == 2
    assert events[0].dia == "Lunes"
    assert events[0].inicio == "07:00"
    assert events[0].fin == "16:00"
    assert events[1].dia == "Miercoles"
    assert events[1].inicio == "05:00"
    assert events[1].fin == "06:00"


def test_parse_work_schedule_keeps_zero_padded_morning_hours_literal():
    events = parse_work_schedule_text("Lunes 05:00-06:00")

    assert len(events) == 1
    assert events[0].inicio == "05:00"
    assert events[0].fin == "06:00"


def test_parse_academic_schedule_accepts_am_pm_literal():
    events = parse_academic_schedule_text("Lunes de 5 am a 6 am Gym")

    assert len(events) == 1
    assert events[0].dia == "Lunes"
    assert events[0].inicio == "05:00"
    assert events[0].fin == "06:00"
    assert events[0].titulo == "Gym"
