"""Pruebas del nuevo dominio de priorización académica."""

from __future__ import annotations

from schemas.planning import SubjectItem
from services.priorities import resolve_prioritized_subjects
from services.scheduling import WeeklyScheduleBlock


def _academic_block(
    day_of_week: str,
    start_time: str,
    end_time: str,
    title: str,
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        source_text=f"{title} {day_of_week} {start_time}-{end_time}",
    )


def test_resolve_prioritized_subjects_derives_catalog_from_schedule() -> None:
    blocks = [
        _academic_block("monday", "08:00", "10:00", "Calculo"),
        _academic_block("wednesday", "08:00", "11:00", "Programacion"),
    ]

    result = resolve_prioritized_subjects(
        schedule_blocks=blocks,
        subjects=[],
        primary_technique_id="pomodoro",
    )

    assert result.source == "derived_from_schedule"
    assert [subject.nombre for subject in result.subject_items] == ["Programacion", "Calculo"]
    assert result.subject_items[0].carga_semanal_min == 180
    assert result.subject_items[0].prioridad == "alta"
    assert result.prioritized_subjects[0].weekly_sessions >= 2


def test_resolve_prioritized_subjects_preserves_explicit_urgency_and_load() -> None:
    blocks = [_academic_block("monday", "08:00", "10:00", "Calculo")]
    subjects = [
        SubjectItem(
            nombre="Calculo",
            prioridad="media",
            dificultad=4,
            urgencia="alta",
            carga_semanal_min=240,
        ),
        SubjectItem(
            nombre="Historia",
            prioridad="alta",
            dificultad=2,
            urgencia="baja",
            carga_semanal_min=90,
        ),
    ]

    result = resolve_prioritized_subjects(
        schedule_blocks=blocks,
        subjects=subjects,
        primary_technique_id="repeticion_espaciada",
    )

    assert result.source == "state.subjects"
    assert result.subject_items[0].nombre == "Calculo"
    calculo = next(item for item in result.subject_items if item.nombre == "Calculo")
    assert calculo.urgencia == "alta"
    assert calculo.carga_semanal_min == 240
    prioritized = next(subject for subject in result.prioritized_subjects if subject.nombre == "Calculo")
    assert prioritized.weekly_sessions >= 3
    assert prioritized.preferred_days == ("monday",)
