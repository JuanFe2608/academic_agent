"""Pruebas basicas para el parser de horarios laborales."""

import pytest

from agents.support.tools.schedule_parser import parse_work_schedule_text


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
    ],
)
def test_parse_work_schedule_text(text, expected_days, start, end):
    """Valida cantidad de eventos y normalizacion de campos."""
    events = parse_work_schedule_text(text)

    assert len(events) == len(expected_days)
    assert [event["dia"] for event in events] == expected_days
    assert all(event["inicio"] == start for event in events)
    assert all(event["fin"] == end for event in events)
    assert all(event["categoria"] == "laboral" for event in events)
    assert all(event["titulo"] == "Trabajo" for event in events)


def test_parse_invalid_text():
    with pytest.raises(ValueError):
        parse_work_schedule_text("No tengo horario fijo")
