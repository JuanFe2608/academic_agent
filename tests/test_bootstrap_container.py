"""Pruebas de compatibilidad para el bootstrap compartido."""

from __future__ import annotations

from agents.support.dependencies import (
    get_schedule_service,
    set_schedule_service,
)
from bootstrap.container import AppContainer, get_app_container, reset_app_container
from bootstrap.settings import database_url_from_env as bootstrap_database_url_from_env
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.scheduling.repository import InMemoryScheduleRepository
from services.planning import StudySessionTrackingService
from services.reminders import StudyPlanRemindersService
from services.scheduling import ScheduleService


def test_bootstrap_settings_database_url_from_env_uses_env(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", raising=False)
    monkeypatch.setenv(
        "ACADEMIC_AGENT_DATABASE_URL",
        "postgresql://app:secret@localhost:5432/academic_agent_db",
    )

    assert (
        bootstrap_database_url_from_env()
        == "postgresql://app:secret@localhost:5432/academic_agent_db"
    )


def test_agent_dependencies_delegate_to_container_override() -> None:
    reset_app_container()
    service = ScheduleService(repository=InMemoryScheduleRepository())

    try:
        set_schedule_service(service)

        assert get_schedule_service() is service
        assert get_app_container().get_schedule_service() is service
    finally:
        set_schedule_service(None)
        reset_app_container()


def test_container_reuses_materialization_repository_for_dependent_services(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_PLAN_INSTANCES_REPO", "1")
    monkeypatch.setenv("ACADEMIC_AGENT_USE_IN_MEMORY_REMINDERS_REPO", "1")
    monkeypatch.setenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_SESSION_TRACKING_REPO", "1")

    container = AppContainer()
    materialization_service = container.get_study_plan_materialization_service()
    reminders_service = container.get_reminders_service()
    tracking_service = container.get_tracking_service()

    assert isinstance(materialization_service.repository, InMemoryStudyPlanInstancesRepository)
    assert isinstance(reminders_service, StudyPlanRemindersService)
    assert isinstance(tracking_service, StudySessionTrackingService)
    assert reminders_service.repository.instances_repository is materialization_service.repository
    assert tracking_service.repository.instances_repository is materialization_service.repository
