"""Pruebas basicas para el parser de horarios laborales."""

import pytest

from agents.support.scheduling.contextual_parser import parse_schedule_section_with_context
from agents.support.scheduling.pipeline import parse_fixed_schedule_section
from services.scheduling.text_parser import (
    extract_natural_schedule_components,
    parse_academic_schedule_text,
    parse_work_schedule_text,
)
from services.scheduling.validation import normalize_day, normalize_day_typos_in_text


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
        ("Lunes de 5 a 6 am", ["Lunes"], "05:00", "06:00"),
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


def test_extract_natural_schedule_components_handles_all_days_phrase():
    parsed = extract_natural_schedule_components(
        "Voy todos los dias al gym desde las 5 am hasta las 6 am"
    )

    assert parsed["days"] == [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
        "Sabado",
        "Domingo",
    ]
    assert parsed["is_all_days"] is True
    assert parsed["start"] == "05:00"
    assert parsed["end"] == "06:00"


def test_extract_natural_schedule_components_prioritizes_explicit_range_over_all_days_phrase() -> None:
    parsed = extract_natural_schedule_components(
        "Trabajo todos los dias de lunes a viernes de 7 am a 10 pm"
    )

    assert parsed["days"] == [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
    ]
    assert parsed["is_all_days"] is False
    assert parsed["start"] == "07:00"
    assert parsed["end"] == "22:00"


def test_extract_natural_schedule_components_tolerates_split_meridiem_typo() -> None:
    parsed = extract_natural_schedule_components(
        "Trabajo todos los dias de lunes a viernes de 7 a pm a 10 pm"
    )

    assert parsed["days"] == [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
    ]
    assert parsed["start"] == "19:00"
    assert parsed["end"] == "22:00"


def test_parse_work_schedule_text_accepts_whatsapp_meridiem_with_unicode_dash() -> None:
    events = parse_work_schedule_text("Lunes 7 p. m. – 10 p. m. Trabajo")

    assert len(events) == 1
    assert events[0].dia == "Lunes"
    assert events[0].inicio == "19:00"
    assert events[0].fin == "22:00"


def test_extract_natural_schedule_components_accepts_unicode_spaces_and_fullwidth_colon() -> None:
    parsed = extract_natural_schedule_components(
        "Trabajo lunes de 7\u202f：00 pm – 10\u202f：00 pm"
    )

    assert parsed["days"] == ["Lunes"]
    assert parsed["start"] == "19:00"
    assert parsed["end"] == "22:00"


def test_parse_work_schedule_text_splits_overnight_ranges_into_two_days():
    events = parse_work_schedule_text("Lunes de 6 pm a 3 am")

    assert len(events) == 2
    assert events[0].dia == "Lunes"
    assert events[0].inicio == "18:00"
    assert events[0].fin == "23:59"
    assert events[1].dia == "Martes"
    assert events[1].inicio == "00:00"
    assert events[1].fin == "03:00"


def test_normalize_day_accepts_weekend_plurals():
    assert normalize_day("sabados") == "Sabado"
    assert normalize_day("domingos") == "Domingo"


def test_normalize_day_typos_in_text_keeps_non_day_words() -> None:
    assert normalize_day_typos_in_text("Marketing y laboratorio") == "Marketing y laboratorio"
    assert normalize_day_typos_in_text("Marte y vierne") == "martes y viernes"


def test_compound_multi_subject_schedule_splits_correctly() -> None:
    """Texto con dos materias y dos rangos horarios en una sola línea."""
    result = parse_fixed_schedule_section(
        "Martes y jueves física 7am-9am y viernes inglés 10am-12am",
        "academic",
    )
    blocks = {(b.day_of_week, b.title, b.start_time, b.end_time) for b in result.blocks}
    assert ("tuesday", "Física", "07:00", "09:00") in blocks
    assert ("thursday", "Física", "07:00", "09:00") in blocks
    assert ("friday", "Inglés", "10:00", "12:00") in blocks
    assert len(result.blocks) == 3
    assert not result.needs_clarification


def test_12am_as_end_time_infers_noon_for_class_schedule() -> None:
    """'10am-12am' en un horario de clase debe inferir mediodía, no medianoche."""
    blocks, _, _ = parse_schedule_section_with_context("Física lunes 10am-12am", "academic")
    assert len(blocks) == 1
    assert blocks[0].end_time == "12:00"
    assert blocks[0].start_time == "10:00"


def test_8pm_to_12am_keeps_midnight_as_end() -> None:
    """'8pm-12am' es un bloque nocturno legítimo (mediodía no aplica)."""
    blocks, _, _ = parse_schedule_section_with_context("Trabajo lunes 8pm-12am", "academic")
    assert len(blocks) == 1
    assert blocks[0].start_time == "20:00"
    assert blocks[0].end_time == "00:00"


def test_compound_schedule_with_comma_separator() -> None:
    """Materias separadas por coma también se dividen correctamente."""
    result = parse_fixed_schedule_section(
        "Lunes matemáticas 8am-10am, miércoles química 14-16",
        "academic",
    )
    days_and_titles = {(b.day_of_week, b.title) for b in result.blocks}
    assert ("monday", "Matemáticas") in days_and_titles
    assert ("wednesday", "Química") in days_and_titles
