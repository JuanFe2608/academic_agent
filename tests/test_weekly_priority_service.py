"""Cobertura del MVP semanal, diario y por eventos de prioridades."""

from __future__ import annotations

from datetime import date

from schemas.planning import SubjectItem
from services.planning import build_daily_focus, parse_daily_completion_response
from services.priorities import (
    UrgencyDetail,
    apply_academic_event_update,
    build_weekly_priorities,
    calculate_weekly_priority_score,
    parse_number_selection,
    parse_priority_command,
    parse_urgency_details,
)


def _subject(name: str, load: int = 120) -> SubjectItem:
    return SubjectItem(
        nombre=name,
        prioridad="media",
        dificultad=3,
        urgencia=None,
        carga_semanal_min=load,
        origen="derived_from_schedule",
    )


def test_parse_ranked_top3_accepts_ordered_numbers() -> None:
    parsed = parse_number_selection(
        "3,1,2",
        subject_count=4,
        min_count=3,
        max_count=3,
        ordered=True,
    )

    assert parsed.is_valid is True
    assert parsed.numbers == [3, 1, 2]


def test_parse_selection_handles_none_use_schedule_skip_and_duplicates() -> None:
    none_selection = parse_number_selection(
        "ninguna",
        subject_count=4,
        min_count=0,
        max_count=4,
        allow_none=True,
    )
    duplicate = parse_number_selection(
        "2,2",
        subject_count=4,
        min_count=1,
        max_count=3,
    )

    assert none_selection.is_valid is True
    assert none_selection.numbers == []
    assert parse_priority_command("usar horario") == "usar_horario"
    assert parse_priority_command("Después") == "usar_horario"
    assert parse_priority_command("omitir") == "omitir"
    assert parse_priority_command("no") == "no"
    assert duplicate.is_valid is False
    assert "repetidas" in (duplicate.error or "")


def test_parse_subject_urgency_accepts_natural_detail_with_default_subject() -> None:
    parsed = parse_urgency_details(
        "parcial viernes",
        subject_count=3,
        reference_date=date(2026, 4, 13),
        timezone="America/Bogota",
        required_subject_numbers=[2],
        default_subject_number=2,
    )

    assert parsed.is_valid is True
    assert parsed.details[0].subject_number == 2
    assert parsed.details[0].urgency_type == "parcial"
    assert parsed.details[0].due_at == "2026-04-17T23:59:00-05:00"


def test_weekly_priority_snapshot_scores_rank_urgency_and_difficulty() -> None:
    result = build_weekly_priorities(
        subjects=[
            _subject("Calculo", 240),
            _subject("Programacion", 180),
            _subject("Fisica", 120),
        ],
        importance_order=[3, 1, 2],
        urgency_details=[
            UrgencyDetail(
                subject_number=2,
                urgency_type="parcial",
                due_at="2026-04-17T23:59:00-05:00",
                raw_text="2 parcial viernes",
            )
        ],
        difficult_subject_numbers=[2, 3],
        reference_date=date(2026, 4, 13),
        timezone="America/Bogota",
    )

    programacion = next(subject for subject in result.subjects if subject.nombre == "Programacion")
    fisica = next(subject for subject in result.subjects if subject.nombre == "Fisica")

    assert programacion.urgency_type == "parcial"
    assert programacion.urgency_due_at == "2026-04-17T23:59:00-05:00"
    assert programacion.perceived_difficulty == 4
    assert fisica.importance_rank_selected_by_student == 1
    assert result.summary["source"] == "weekly_flow"
    assert all(subject.is_priority_confirmed for subject in result.subjects)


def test_priority_score_expires_due_dates() -> None:
    active = calculate_weekly_priority_score(
        student_rank=1,
        urgency_due_at="2026-04-14T23:59:00-05:00",
        urgency_type="parcial",
        weekly_load_min=180,
        perceived_difficulty=4,
        reference_date=date(2026, 4, 13),
    )
    expired = calculate_weekly_priority_score(
        student_rank=None,
        urgency_due_at="2026-04-10T23:59:00-05:00",
        urgency_type="parcial",
        weekly_load_min=180,
        perceived_difficulty=None,
        reference_date=date(2026, 4, 13),
    )

    assert active.level == "alta"
    assert active.urgency_level == "alta"
    assert expired.urgency_level is None
    assert expired.score < active.score


def test_academic_event_update_recalculates_only_affected_subject() -> None:
    subjects = [
        _subject("Calculo", 180).model_copy(
            update={
                "importance_rank_selected_by_student": 1,
                "computed_priority_score": 0.55,
                "is_priority_confirmed": True,
            }
        ),
        _subject("Programacion", 120).model_copy(
            update={
                "importance_rank_selected_by_student": 2,
                "computed_priority_score": 0.45,
                "is_priority_confirmed": True,
            }
        ),
    ]

    result = apply_academic_event_update(
        subjects=subjects,
        text="Tengo parcial de calculo el viernes",
        reference_date=date(2026, 4, 13),
        timezone="America/Bogota",
    )

    calculo = next(subject for subject in result.subjects if subject.nombre == "Calculo")
    programacion = next(subject for subject in result.subjects if subject.nombre == "Programacion")

    assert result.detected is True
    assert result.event_type == "academic_deadline"
    assert calculo.urgency_type == "parcial"
    assert calculo.priority_source == "event_update"
    assert programacion.urgency_type is None


def test_daily_accompaniment_does_not_restart_weekly_flow() -> None:
    focus = build_daily_focus(
        plan_instances=[
            {
                "id": 1,
                "planned_date": "2026-04-13",
                "starts_at": "2026-04-13T18:00:00-05:00",
                "title": "Estudio Calculo",
                "status": "scheduled",
            }
        ],
        subjects=[
            _subject("Calculo", 180).model_copy(update={"computed_priority_score": 0.8})
        ],
        study_profile={"status": "completed", "top_techniques": ["pomodoro"]},
        today=date(2026, 4, 13),
    )
    partial = parse_daily_completion_response("a medias 50%")
    missed = parse_daily_completion_response("no pude estudiar hoy")

    assert focus.should_send is True
    assert focus.payload["does_not_rerun_weekly_priorities"] is True
    assert "Calculo" in focus.message
    assert partial.completion_pct == 50
    assert partial.replan_signal is True
    assert missed.status == "skipped"
    assert missed.replan_signal is True
