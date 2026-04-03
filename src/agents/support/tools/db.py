"""Factories de persistencia y servicios compartidos."""

from __future__ import annotations

from auth.microsoft_auth import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from agents.support.onboarding.service import OnboardingService, build_onboarding_service
from agents.support.personalization.service import (
    PersonalizationService,
    build_personalization_service,
)
from agents.support.planning.tracking_service import (
    StudySessionTrackingService,
    build_study_session_tracking_service,
)
from agents.support.reminders_service import (
    StudyPlanRemindersService,
    build_study_plan_reminders_service,
)
from agents.support.planning.materialization_service import (
    StudyPlanMaterializationService,
    build_study_plan_materialization_service,
)
from agents.support.planning.persistence_service import (
    StudyPlanningPersistenceService,
    build_study_planning_persistence_service,
)
from agents.support.scheduling.service import ScheduleService, build_schedule_service
from agents.support.tools.calendar_outlook import (
    OutlookCalendarSyncService,
    build_outlook_calendar_sync_service,
)
from agents.support.tools.db_config import database_url_from_env
from agents.support.tools.microsoft_graph_state_repository import (
    MicrosoftGraphStateRepository,
    build_microsoft_graph_state_repository,
)
from agents.support.tools.microsoft_todo import (
    MicrosoftTodoSyncService,
    build_microsoft_todo_sync_service,
)

_ONBOARDING_SERVICE: OnboardingService | None = None
_PERSONALIZATION_SERVICE: PersonalizationService | None = None
_SCHEDULE_SERVICE: ScheduleService | None = None
_STUDY_PLANNING_PERSISTENCE_SERVICE: StudyPlanningPersistenceService | None = None
_STUDY_PLAN_MATERIALIZATION_SERVICE: StudyPlanMaterializationService | None = None
_REMINDERS_SERVICE: StudyPlanRemindersService | None = None
_TRACKING_SERVICE: StudySessionTrackingService | None = None
_MICROSOFT_GRAPH_STATE_REPOSITORY: MicrosoftGraphStateRepository | None = None
_MICROSOFT_OAUTH_CLIENT: MicrosoftOAuthClient | None = None
_OUTLOOK_CALENDAR_SYNC_SERVICE: OutlookCalendarSyncService | None = None
_MICROSOFT_TODO_SYNC_SERVICE: MicrosoftTodoSyncService | None = None


def get_onboarding_service() -> OnboardingService:
    """Retorna una instancia reusable del servicio de onboarding."""

    global _ONBOARDING_SERVICE
    if _ONBOARDING_SERVICE is None:
        _ONBOARDING_SERVICE = build_onboarding_service()
    return _ONBOARDING_SERVICE


def set_onboarding_service(service: OnboardingService | None) -> None:
    """Permite inyectar un servicio durante pruebas."""

    global _ONBOARDING_SERVICE
    _ONBOARDING_SERVICE = service


def get_personalization_service() -> PersonalizationService:
    """Retorna una instancia reusable del servicio de personalizacion."""

    global _PERSONALIZATION_SERVICE
    if _PERSONALIZATION_SERVICE is None:
        _PERSONALIZATION_SERVICE = build_personalization_service()
    return _PERSONALIZATION_SERVICE


def set_personalization_service(service: PersonalizationService | None) -> None:
    """Permite inyectar un servicio de personalizacion durante pruebas."""

    global _PERSONALIZATION_SERVICE
    _PERSONALIZATION_SERVICE = service


def get_schedule_service() -> ScheduleService:
    """Retorna una instancia reusable del servicio de horarios."""

    global _SCHEDULE_SERVICE
    if _SCHEDULE_SERVICE is None:
        _SCHEDULE_SERVICE = build_schedule_service()
    return _SCHEDULE_SERVICE


def set_schedule_service(service: ScheduleService | None) -> None:
    """Permite inyectar un servicio de horarios durante pruebas."""

    global _SCHEDULE_SERVICE
    _SCHEDULE_SERVICE = service


def get_study_planning_persistence_service() -> StudyPlanningPersistenceService:
    """Retorna una instancia reusable del servicio de persistencia académica."""

    global _STUDY_PLANNING_PERSISTENCE_SERVICE
    if _STUDY_PLANNING_PERSISTENCE_SERVICE is None:
        _STUDY_PLANNING_PERSISTENCE_SERVICE = build_study_planning_persistence_service()
    return _STUDY_PLANNING_PERSISTENCE_SERVICE


def set_study_planning_persistence_service(
    service: StudyPlanningPersistenceService | None,
) -> None:
    """Permite inyectar persistencia de planning durante pruebas."""

    global _STUDY_PLANNING_PERSISTENCE_SERVICE
    _STUDY_PLANNING_PERSISTENCE_SERVICE = service


def get_study_plan_materialization_service() -> StudyPlanMaterializationService:
    """Retorna una instancia reusable del servicio de materializacion."""

    global _STUDY_PLAN_MATERIALIZATION_SERVICE
    if _STUDY_PLAN_MATERIALIZATION_SERVICE is None:
        _STUDY_PLAN_MATERIALIZATION_SERVICE = build_study_plan_materialization_service()
    return _STUDY_PLAN_MATERIALIZATION_SERVICE


def set_study_plan_materialization_service(
    service: StudyPlanMaterializationService | None,
) -> None:
    """Permite inyectar materializacion de instancias durante pruebas."""

    global _STUDY_PLAN_MATERIALIZATION_SERVICE
    _STUDY_PLAN_MATERIALIZATION_SERVICE = service


def get_reminders_service() -> StudyPlanRemindersService:
    """Retorna una instancia reusable del servicio de reminders."""

    global _REMINDERS_SERVICE
    if _REMINDERS_SERVICE is None:
        materialization_service = get_study_plan_materialization_service()
        _REMINDERS_SERVICE = build_study_plan_reminders_service(
            instances_repository=getattr(materialization_service, "repository", None)
        )
    return _REMINDERS_SERVICE


def set_reminders_service(service: StudyPlanRemindersService | None) -> None:
    """Permite inyectar el servicio de reminders durante pruebas."""

    global _REMINDERS_SERVICE
    _REMINDERS_SERVICE = service


def get_tracking_service() -> StudySessionTrackingService:
    """Retorna una instancia reusable del servicio de tracking."""

    global _TRACKING_SERVICE
    if _TRACKING_SERVICE is None:
        materialization_service = get_study_plan_materialization_service()
        _TRACKING_SERVICE = build_study_session_tracking_service(
            instances_repository=getattr(materialization_service, "repository", None)
        )
    return _TRACKING_SERVICE


def set_tracking_service(service: StudySessionTrackingService | None) -> None:
    """Permite inyectar el servicio de tracking durante pruebas."""

    global _TRACKING_SERVICE
    _TRACKING_SERVICE = service


def get_microsoft_graph_state_repository() -> MicrosoftGraphStateRepository:
    """Retorna el repositorio durable de conexiones y links Microsoft."""

    global _MICROSOFT_GRAPH_STATE_REPOSITORY
    if _MICROSOFT_GRAPH_STATE_REPOSITORY is None:
        _MICROSOFT_GRAPH_STATE_REPOSITORY = build_microsoft_graph_state_repository(
            database_url_from_env()
        )
    return _MICROSOFT_GRAPH_STATE_REPOSITORY


def set_microsoft_graph_state_repository(
    repository: MicrosoftGraphStateRepository | None,
) -> None:
    """Permite inyectar el repositorio Microsoft durante pruebas."""

    global _MICROSOFT_GRAPH_STATE_REPOSITORY
    _MICROSOFT_GRAPH_STATE_REPOSITORY = repository


def get_microsoft_oauth_client() -> MicrosoftOAuthClient:
    """Retorna un cliente OAuth Microsoft ligado a persistencia durable."""

    global _MICROSOFT_OAUTH_CLIENT
    if _MICROSOFT_OAUTH_CLIENT is None:
        state_repository = get_microsoft_graph_state_repository()
        _MICROSOFT_OAUTH_CLIENT = build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )
    return _MICROSOFT_OAUTH_CLIENT


def set_microsoft_oauth_client(client: MicrosoftOAuthClient | None) -> None:
    """Permite inyectar el cliente OAuth Microsoft durante pruebas."""

    global _MICROSOFT_OAUTH_CLIENT
    _MICROSOFT_OAUTH_CLIENT = client


def get_outlook_calendar_sync_service() -> OutlookCalendarSyncService:
    """Retorna el servicio reusable de sincronización Outlook."""

    global _OUTLOOK_CALENDAR_SYNC_SERVICE
    if _OUTLOOK_CALENDAR_SYNC_SERVICE is None:
        _OUTLOOK_CALENDAR_SYNC_SERVICE = build_outlook_calendar_sync_service(
            instances_repository=None,
            state_repository=get_microsoft_graph_state_repository(),
            auth_client=get_microsoft_oauth_client(),
        )
    return _OUTLOOK_CALENDAR_SYNC_SERVICE


def set_outlook_calendar_sync_service(
    service: OutlookCalendarSyncService | None,
) -> None:
    """Permite inyectar el sync service de Outlook durante pruebas."""

    global _OUTLOOK_CALENDAR_SYNC_SERVICE
    _OUTLOOK_CALENDAR_SYNC_SERVICE = service


def get_microsoft_todo_sync_service() -> MicrosoftTodoSyncService:
    """Retorna el servicio reusable de Microsoft To Do."""

    global _MICROSOFT_TODO_SYNC_SERVICE
    if _MICROSOFT_TODO_SYNC_SERVICE is None:
        _MICROSOFT_TODO_SYNC_SERVICE = build_microsoft_todo_sync_service(
            instances_repository=None,
            state_repository=get_microsoft_graph_state_repository(),
            auth_client=get_microsoft_oauth_client(),
        )
    return _MICROSOFT_TODO_SYNC_SERVICE


def set_microsoft_todo_sync_service(
    service: MicrosoftTodoSyncService | None,
) -> None:
    """Permite inyectar el sync service de To Do durante pruebas."""

    global _MICROSOFT_TODO_SYNC_SERVICE
    _MICROSOFT_TODO_SYNC_SERVICE = service
