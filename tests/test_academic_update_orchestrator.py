"""Tests del AcademicUpdateOrchestrator."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from repositories.planning.activity_repository import InMemoryAcademicActivityRepository
from schemas.planning import AcademicActivity
from services.planning.academic_activity_persistence_service import (
    AcademicActivityPersistenceService,
)
from services.planning.academic_update_orchestrator import (
    AcademicUpdateOrchestrator,
    PriorityComputeResult,
    reference_date,
    reference_datetime,
)


def _make_persistence_service() -> AcademicActivityPersistenceService:
    return AcademicActivityPersistenceService(InMemoryAcademicActivityRepository())


def _make_activity(**kwargs) -> AcademicActivity:
    defaults = dict(
        activity_id="act-1",
        activity_type="parcial",
        subject_name="Calculo",
        title="Parcial 1",
        due_date=str(date.today()),
        prioridad="alta",
        status="pending",
    )
    defaults.update(kwargs)
    return AcademicActivity(**defaults)


# ── reference_date / reference_datetime ─────────────────────────────────────

def test_reference_date_returns_date_object() -> None:
    result = reference_date("America/Bogota")
    assert isinstance(result, date)


def test_reference_date_fallback_on_invalid_timezone() -> None:
    result = reference_date("Invalid/Zone")
    assert isinstance(result, date)


def test_reference_datetime_returns_datetime_object() -> None:
    result = reference_datetime("America/Bogota")
    assert isinstance(result, datetime)


# ── load_activities ──────────────────────────────────────────────────────────

def test_load_activities_returns_local_when_not_empty() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    activity = _make_activity()

    result = orchestrator.load_activities(student_id=1, local_activities=[activity])

    assert len(result) == 1
    assert result[0].activity_id == "act-1"


def test_load_activities_falls_back_to_service_when_local_empty() -> None:
    repo = InMemoryAcademicActivityRepository()
    activity = _make_activity()
    repo.upsert_activity(student_id=42, activity=activity)
    svc = AcademicActivityPersistenceService(repo)
    orchestrator = AcademicUpdateOrchestrator(svc)

    result = orchestrator.load_activities(student_id=42, local_activities=[])

    assert len(result) == 1
    assert result[0].activity_id == "act-1"


def test_load_activities_returns_empty_when_no_student_id() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)

    result = orchestrator.load_activities(student_id=None, local_activities=[])

    assert result == []


def test_load_activities_returns_local_on_service_exception() -> None:
    svc = MagicMock()
    svc.list_activities.side_effect = RuntimeError("db error")
    orchestrator = AcademicUpdateOrchestrator(svc)

    result = orchestrator.load_activities(student_id=1, local_activities=[])

    assert result == []


# ── persist_activity ─────────────────────────────────────────────────────────

def test_persist_activity_upsert_stores_and_returns_persisted() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    activity = _make_activity()

    result = orchestrator.persist_activity(student_id=1, activity=activity, operation="create")

    assert result is not None
    assert result.persisted_activity_id is not None


def test_persist_activity_returns_none_when_activity_is_none() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)

    result = orchestrator.persist_activity(student_id=1, activity=None, operation="create")

    assert result is None


def test_persist_activity_returns_original_when_no_student_id() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    activity = _make_activity()

    result = orchestrator.persist_activity(student_id=None, activity=activity, operation="create")

    assert result is activity


def test_persist_activity_marks_persistence_error_on_exception() -> None:
    svc = MagicMock()
    svc.upsert_activity.side_effect = RuntimeError("connection lost")
    orchestrator = AcademicUpdateOrchestrator(svc)
    activity = _make_activity()

    result = orchestrator.persist_activity(student_id=1, activity=activity, operation="create")

    assert result.persistence_error == "connection lost"


# ── replace_activity ─────────────────────────────────────────────────────────

def test_replace_activity_replaces_matching_id() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    original = _make_activity(activity_id="act-1", activity_title="Parcial 1")
    updated = _make_activity(activity_id="act-1", activity_title="Parcial Actualizado")

    result = orchestrator.replace_activity([original], updated)

    assert len(result) == 1
    assert result[0].activity_title == "Parcial Actualizado"


def test_replace_activity_appends_when_id_not_found() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    existing = _make_activity(activity_id="act-1")
    new_one = _make_activity(activity_id="act-2")

    result = orchestrator.replace_activity([existing], new_one)

    assert len(result) == 2


# ── compute_priority_update ──────────────────────────────────────────────────

def test_compute_priority_update_returns_not_detected_on_unrelated_text() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)

    result = orchestrator.compute_priority_update(
        "hola como estas",
        subjects=[],
        schedule_blocks=[],
        academic_activities=[],
        study_profile={},
        ref_date=date.today(),
        timezone="America/Bogota",
        priorities_state={},
    )

    assert isinstance(result, PriorityComputeResult)
    assert result.detected is False


def test_compute_priority_update_from_activity_returns_not_detected_when_no_update_text() -> None:
    svc = _make_persistence_service()
    orchestrator = AcademicUpdateOrchestrator(svc)
    activity = _make_activity(activity_type="estudio_pendiente")

    result = orchestrator.compute_priority_update_from_activity(
        activity,
        subjects=[],
        schedule_blocks=[],
        academic_activities=[],
        study_profile={},
        ref_date=date.today(),
        timezone="America/Bogota",
        priorities_state={},
    )

    assert isinstance(result, PriorityComputeResult)
    assert result.detected is False
