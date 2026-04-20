"""Pruebas de persistencia de actividades academicas puntuales."""

from __future__ import annotations

from pathlib import Path

from repositories.planning.activity_repository import InMemoryAcademicActivityRepository
from schemas.planning import AcademicActivity
from services.planning import AcademicActivityPersistenceService


def test_in_memory_academic_activity_repository_upserts_lists_and_deletes() -> None:
    repository = InMemoryAcademicActivityRepository()
    service = AcademicActivityPersistenceService(repository)
    activity = AcademicActivity(
        activity_type="tarea",
        subject_name="Programacion",
        due_date="2026-04-21",
    )

    persisted = service.upsert_activity(student_id=7, activity=activity)
    listed = service.list_activities(student_id=7)
    deleted = service.delete_activity(
        student_id=7,
        activity_id=persisted.activity.activity_id,
    )
    listed_after_delete = service.list_activities(student_id=7)

    assert persisted.persisted is True
    assert persisted.activity.persisted_activity_id == 1
    assert listed.loaded is True
    assert listed.activities[0].subject_name == "Programacion"
    assert deleted.persisted is True
    assert deleted.activity.status == "deleted"
    assert listed_after_delete.activities == []


def test_academic_activities_migration_creates_dedicated_table() -> None:
    migration = Path("migrations/0019_academic_activities.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS academic_activities" in migration
    assert "UNIQUE (student_id, activity_uid)" in migration
    assert "'estudio_pendiente'" in migration
