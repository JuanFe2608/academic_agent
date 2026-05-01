"""Cobertura del dominio de actividades academicas puntuales."""

from __future__ import annotations

from datetime import date

from schemas.planning import SubjectItem
from services.planning.academic_activity_service import (
    apply_confirmed_academic_activity_operation,
    parse_academic_activity_request,
)


def test_parse_activity_create_extracts_core_slots_and_confirmation_payload() -> None:
    result = parse_academic_activity_request(
        "Tengo parcial de Calculo el viernes a las 8 pm, 2 horas prioridad alta dificultad 4",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )

    assert result.detected is True
    assert result.action == "create"
    assert result.requires_confirmation is True
    assert result.slots["activity_type"] == "parcial"
    assert result.slots["subject_name"] == "Calculo"
    assert result.slots["due_date"] == "2026-04-24"
    assert result.slots["due_time"] == "20:00"
    assert result.slots["estimated_effort_minutes"] == 120
    assert result.slots["priority_level"] == "alta"
    assert result.slots["difficulty_level"] == 4


def test_parse_activity_capture_merges_missing_subject_incrementally() -> None:
    first = parse_academic_activity_request(
        "Tengo parcial el viernes",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )
    second = parse_academic_activity_request(
        "Calculo",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
        pending_payload=first.pending_payload,
    )

    assert first.requires_clarification is True
    assert first.missing_fields == ["subject_name"]
    assert second.requires_confirmation is True
    assert second.confirmation_payload["operation"] == "create"
    assert second.confirmation_payload["activity"]["subject_name"] == "Calculo"


def test_apply_confirmed_activity_create_and_delete() -> None:
    parsed = parse_academic_activity_request(
        "Tengo entrega de Fisica mañana",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Fisica", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )

    created = apply_confirmed_academic_activity_operation(
        [],
        parsed.confirmation_payload,
        timezone="America/Bogota",
        reference_date=date(2026, 4, 18),
    )
    activity = created.activity
    assert activity is not None
    deleted = apply_confirmed_academic_activity_operation(
        created.activities,
        {
            "domain": "activity_management",
            "operation": "delete",
            "activity_id": activity.activity_id,
        },
        timezone="America/Bogota",
        reference_date=date(2026, 4, 18),
    )

    assert created.applied is True
    assert created.replan_required is True
    assert deleted.applied is True
    assert deleted.activities[0].status == "deleted"


def test_parse_activity_update_changes_due_date_after_confirmation() -> None:
    activity = apply_confirmed_academic_activity_operation(
        [],
        parse_academic_activity_request(
            "Tengo parcial de Calculo el viernes",
            existing_activities=[],
            subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
            reference_date=date(2026, 4, 18),
            timezone="America/Bogota",
        ).confirmation_payload,
        timezone="America/Bogota",
        reference_date=date(2026, 4, 18),
    ).activity
    assert activity is not None

    parsed_update = parse_academic_activity_request(
        "cambia el parcial de Calculo para el lunes",
        existing_activities=[activity],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )
    applied_update = apply_confirmed_academic_activity_operation(
        [activity],
        parsed_update.confirmation_payload,
        timezone="America/Bogota",
        reference_date=date(2026, 4, 18),
    )

    assert parsed_update.requires_confirmation is True
    assert parsed_update.confirmation_payload["operation"] == "update"
    assert applied_update.activity.due_date == "2026-04-20"


def test_parse_work_shift_is_not_academic_activity() -> None:
    result = parse_academic_activity_request(
        "tengo trabajo de 2 pm a 6 pm",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )

    assert result.detected is False


def test_parse_academic_work_assignment_still_detects_activity() -> None:
    result = parse_academic_activity_request(
        "tengo trabajo de Calculo para el viernes",
        existing_activities=[],
        subjects=[SubjectItem(nombre="Calculo", prioridad="media", dificultad=3)],
        reference_date=date(2026, 4, 18),
        timezone="America/Bogota",
    )

    assert result.detected is True
    assert result.action == "create"
    assert result.slots["activity_type"] == "entrega"
    assert result.slots["subject_name"] == "Calculo"
