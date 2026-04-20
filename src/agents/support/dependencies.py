"""Acceso explícito a dependencias compartidas del runtime del agente.

La composición real sigue viviendo en `bootstrap.container`. Este módulo solo
expone una frontera semánticamente correcta para nodos, flujos y pruebas del
agente, evitando el service locator legado bajo `tools/db.py`.
"""

from __future__ import annotations

from bootstrap.container import get_app_container


def get_onboarding_service() -> OnboardingService:
    """Retorna una instancia reusable del servicio de onboarding."""

    return get_app_container().get_onboarding_service()


def set_onboarding_service(service: OnboardingService | None) -> None:
    """Permite inyectar un servicio durante pruebas."""

    get_app_container().set_onboarding_service(service)


def get_personalization_service() -> PersonalizationService:
    """Retorna una instancia reusable del servicio de personalización."""

    return get_app_container().get_personalization_service()


def set_personalization_service(service: PersonalizationService | None) -> None:
    """Permite inyectar un servicio de personalización durante pruebas."""

    get_app_container().set_personalization_service(service)


def get_schedule_service() -> ScheduleService:
    """Retorna una instancia reusable del servicio de horarios."""

    return get_app_container().get_schedule_service()


def set_schedule_service(service: ScheduleService | None) -> None:
    """Permite inyectar un servicio de horarios durante pruebas."""

    get_app_container().set_schedule_service(service)


def get_study_planning_persistence_service() -> StudyPlanningPersistenceService:
    """Retorna una instancia reusable del servicio de persistencia académica."""

    return get_app_container().get_study_planning_persistence_service()


def set_study_planning_persistence_service(
    service: StudyPlanningPersistenceService | None,
) -> None:
    """Permite inyectar persistencia de planning durante pruebas."""

    get_app_container().set_study_planning_persistence_service(service)


def get_study_replanning_service() -> StudyReplanningService:
    """Retorna una instancia reusable del servicio de replanificacion."""

    return get_app_container().get_study_replanning_service()


def set_study_replanning_service(service: StudyReplanningService | None) -> None:
    """Permite inyectar replanificacion durante pruebas."""

    get_app_container().set_study_replanning_service(service)


def get_academic_activity_persistence_service() -> AcademicActivityPersistenceService:
    """Retorna una instancia reusable de persistencia de actividades."""

    return get_app_container().get_academic_activity_persistence_service()


def set_academic_activity_persistence_service(
    service: AcademicActivityPersistenceService | None,
) -> None:
    """Permite inyectar persistencia de actividades durante pruebas."""

    get_app_container().set_academic_activity_persistence_service(service)


def get_study_plan_materialization_service() -> StudyPlanMaterializationService:
    """Retorna una instancia reusable del servicio de materialización."""

    return get_app_container().get_study_plan_materialization_service()


def set_study_plan_materialization_service(
    service: StudyPlanMaterializationService | None,
) -> None:
    """Permite inyectar materialización de instancias durante pruebas."""

    get_app_container().set_study_plan_materialization_service(service)


def get_reminders_service() -> StudyPlanRemindersService:
    """Retorna una instancia reusable del servicio de reminders."""

    return get_app_container().get_reminders_service()


def set_reminders_service(service: StudyPlanRemindersService | None) -> None:
    """Permite inyectar el servicio de reminders durante pruebas."""

    get_app_container().set_reminders_service(service)


def get_tracking_service() -> StudySessionTrackingService:
    """Retorna una instancia reusable del servicio de tracking."""

    return get_app_container().get_tracking_service()


def set_tracking_service(service: StudySessionTrackingService | None) -> None:
    """Permite inyectar el servicio de tracking durante pruebas."""

    get_app_container().set_tracking_service(service)


def get_study_recommendation_service() -> StudyRecommendationService:
    """Retorna el servicio reusable de recomendaciones de estudio."""

    return get_app_container().get_study_recommendation_service()


def set_study_recommendation_service(
    service: StudyRecommendationService | None,
) -> None:
    """Permite inyectar recomendaciones de estudio durante pruebas."""

    get_app_container().set_study_recommendation_service(service)


def get_microsoft_graph_state_repository() -> MicrosoftGraphStateRepository:
    """Retorna el repositorio durable de conexiones y links Microsoft."""

    return get_app_container().get_microsoft_graph_state_repository()


def set_microsoft_graph_state_repository(
    repository: MicrosoftGraphStateRepository | None,
) -> None:
    """Permite inyectar el repositorio Microsoft durante pruebas."""

    get_app_container().set_microsoft_graph_state_repository(repository)


def get_microsoft_oauth_client() -> MicrosoftOAuthClient:
    """Retorna un cliente OAuth Microsoft ligado a persistencia durable."""

    return get_app_container().get_microsoft_oauth_client()


def set_microsoft_oauth_client(client: MicrosoftOAuthClient | None) -> None:
    """Permite inyectar el cliente OAuth Microsoft durante pruebas."""

    get_app_container().set_microsoft_oauth_client(client)


def get_microsoft_oauth_flow_service() -> MicrosoftOAuthFlowService:
    """Retorna el flujo OAuth Microsoft bloqueante del onboarding."""

    return get_app_container().get_microsoft_oauth_flow_service()


def set_microsoft_oauth_flow_service(
    service: MicrosoftOAuthFlowService | None,
) -> None:
    """Permite inyectar el flujo OAuth Microsoft durante pruebas."""

    get_app_container().set_microsoft_oauth_flow_service(service)


def get_outlook_calendar_sync_service() -> OutlookCalendarSyncService:
    """Retorna el servicio reusable de sincronización Outlook."""

    return get_app_container().get_outlook_calendar_sync_service()


def set_outlook_calendar_sync_service(
    service: OutlookCalendarSyncService | None,
) -> None:
    """Permite inyectar el sync service de Outlook durante pruebas."""

    get_app_container().set_outlook_calendar_sync_service(service)


def get_outlook_fixed_schedule_sync_service() -> OutlookFixedScheduleSyncService:
    """Retorna el servicio reusable de sincronización del horario fijo."""

    return get_app_container().get_outlook_fixed_schedule_sync_service()


def set_outlook_fixed_schedule_sync_service(
    service: OutlookFixedScheduleSyncService | None,
) -> None:
    """Permite inyectar el sync service del horario fijo en pruebas."""

    get_app_container().set_outlook_fixed_schedule_sync_service(service)


def get_outlook_fixed_schedule_repair_service() -> OutlookFixedScheduleRepairService:
    """Retorna el servicio reusable de reparación del horario fijo en Outlook."""

    return get_app_container().get_outlook_fixed_schedule_repair_service()


def set_outlook_fixed_schedule_repair_service(
    service: OutlookFixedScheduleRepairService | None,
) -> None:
    """Permite inyectar el repair service del horario fijo en pruebas."""

    get_app_container().set_outlook_fixed_schedule_repair_service(service)


def get_microsoft_todo_sync_service() -> MicrosoftTodoSyncService:
    """Retorna el servicio reusable de Microsoft To Do."""

    return get_app_container().get_microsoft_todo_sync_service()


def set_microsoft_todo_sync_service(
    service: MicrosoftTodoSyncService | None,
) -> None:
    """Permite inyectar el sync service de To Do durante pruebas."""

    get_app_container().set_microsoft_todo_sync_service(service)


__all__ = [
    "get_academic_activity_persistence_service",
    "get_microsoft_graph_state_repository",
    "get_microsoft_oauth_client",
    "get_microsoft_oauth_flow_service",
    "get_microsoft_todo_sync_service",
    "get_onboarding_service",
    "get_outlook_calendar_sync_service",
    "get_outlook_fixed_schedule_repair_service",
    "get_outlook_fixed_schedule_sync_service",
    "get_personalization_service",
    "get_reminders_service",
    "get_schedule_service",
    "get_study_plan_materialization_service",
    "get_study_planning_persistence_service",
    "get_study_replanning_service",
    "get_study_recommendation_service",
    "get_tracking_service",
    "set_academic_activity_persistence_service",
    "set_microsoft_graph_state_repository",
    "set_microsoft_oauth_client",
    "set_microsoft_oauth_flow_service",
    "set_microsoft_todo_sync_service",
    "set_onboarding_service",
    "set_outlook_calendar_sync_service",
    "set_outlook_fixed_schedule_repair_service",
    "set_outlook_fixed_schedule_sync_service",
    "set_personalization_service",
    "set_reminders_service",
    "set_schedule_service",
    "set_study_plan_materialization_service",
    "set_study_planning_persistence_service",
    "set_study_replanning_service",
    "set_study_recommendation_service",
    "set_tracking_service",
]
