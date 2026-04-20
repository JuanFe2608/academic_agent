"""Pruebas del nuevo dominio de priorización académica."""

from __future__ import annotations

from datetime import date

from schemas.planning import AcademicActivity, SubjectItem
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


def test_resolve_prioritized_subjects_merges_pending_activities_without_duplicates() -> None:
    blocks = [_academic_block("monday", "08:00", "10:00", "Calculo")]
    activities = [
        AcademicActivity(
            activity_type="parcial",
            subject_name="Calculo",
            activity_title="Parcial de Calculo",
            due_date="2026-04-20",
            estimated_effort_minutes=120,
        ),
        AcademicActivity(
            activity_type="quiz",
            subject_name="Programacion",
            activity_title="Quiz de Programacion",
            due_date="2026-04-21",
            estimated_effort_minutes=60,
        ),
    ]

    result = resolve_prioritized_subjects(
        schedule_blocks=blocks,
        subjects=[],
        academic_activities=activities,
        primary_technique_id="pomodoro",
        reference_date=date(2026, 4, 18),
    )

    names = [subject.nombre for subject in result.subject_items]
    assert result.source == "derived_from_schedule"
    assert names.count("Calculo") == 1
    assert "Programacion" in names

    calculo = next(subject for subject in result.subject_items if subject.nombre == "Calculo")
    programacion = next(subject for subject in result.subject_items if subject.nombre == "Programacion")

    assert calculo.urgencia == "alta"
    assert calculo.urgency_type == "parcial"
    assert calculo.carga_semanal_min == 240
    assert programacion.origen == "academic_activity"
    assert programacion.urgency_type == "quiz"
