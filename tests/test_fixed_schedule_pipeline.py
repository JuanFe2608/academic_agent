"""Pruebas del pipeline unificado para horario fijo."""

from __future__ import annotations

from agents.support.scheduling.conflicts import detect_schedule_conflicts
from agents.support.scheduling.pipeline import (
    parse_extracurricular_section,
    parse_fixed_schedule_section,
)


def test_parse_fixed_schedule_section_accepts_simple_academic_line_without_meridiem() -> None:
    result = parse_fixed_schedule_section(
        "Lunes - Cálculo - 7 a 9",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Cálculo", "monday", "07:00", "09:00"),
    ]


def test_parse_fixed_schedule_section_handles_work_range_with_natural_language() -> None:
    result = parse_fixed_schedule_section(
        "Trabajo todos los días de lunes a viernes de 7 am a 9 pm.",
        "work",
    )

    assert result.needs_clarification is False
    assert len(result.blocks) == 5
    assert all(block.title == "Trabajo" for block in result.blocks)
    assert all(block.start_time == "07:00" for block in result.blocks)
    assert all(block.end_time == "21:00" for block in result.blocks)


def test_parse_fixed_schedule_section_splits_multiple_classes_with_same_day_context() -> None:
    result = parse_fixed_schedule_section(
        "Los lunes tengo cálculo de 7 a 9 y luego física de 10 a 12",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Cálculo", "monday", "07:00", "09:00"),
        ("Física", "monday", "10:00", "12:00"),
    ]


def test_parse_fixed_schedule_section_splits_multiple_entries_with_distinct_days() -> None:
    result = parse_fixed_schedule_section(
        "martes 10-12 física y jueves 2-4 pm química",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Física", "tuesday", "10:00", "12:00"),
        ("Química", "thursday", "14:00", "16:00"),
    ]


def test_parse_fixed_schedule_section_accepts_compact_day_title_time_order() -> None:
    result = parse_fixed_schedule_section(
        "jueves laboratorio 18-21",
        "academic",
    )

    assert result.needs_clarification is False
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Laboratorio", "thursday", "18:00", "21:00"),
    ]


def test_parse_fixed_schedule_section_marks_missing_title() -> None:
    result = parse_fixed_schedule_section(
        "lunes 7-9",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.pending_schedule_items
    assert "nombre de la materia o actividad" in result.pending_schedule_items[0].missing_fields


def test_parse_fixed_schedule_section_marks_missing_time() -> None:
    result = parse_fixed_schedule_section(
        "miércoles 9 matemáticas",
        "academic",
    )

    assert result.needs_clarification is True
    assert result.pending_schedule_items
    assert "hora de inicio y fin" in result.pending_schedule_items[0].missing_fields


def test_parse_extracurricular_section_generates_clear_short_title() -> None:
    result = parse_extracurricular_section(
        "Voy de compras con mis amigas los sábados de 3 pm a 6 pm",
    )

    assert result.needs_clarification is False
    assert [item.nombre for item in result.extracurricular_items] == ["Compras con amigas"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in result.blocks] == [
        ("Compras con amigas", "saturday", "15:00", "18:00"),
    ]


def test_detect_schedule_conflicts_marks_internal_overlap() -> None:
    result = parse_fixed_schedule_section(
        "lunes matemáticas 7 a 9 y física 8 a 10",
        "academic",
    )

    updated_blocks, conflicts = detect_schedule_conflicts(result.blocks)

    assert len(conflicts) == 1
    assert conflicts[0].overlap_start == "08:00"
    assert conflicts[0].overlap_end == "09:00"
    assert all(block.has_conflict for block in updated_blocks)
    assert updated_blocks[0].metadata["conflicts"]
