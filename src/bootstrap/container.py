"""Composition root explicito para servicios compartidos del agente."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from services.onboarding.service import OnboardingService, build_onboarding_service
from services.personalization.service import (
    PersonalizationService,
    build_personalization_service,
)
from services.planning.materialization_service import (
    StudyPlanMaterializationService,
    build_study_plan_materialization_service,
)
from services.planning.academic_activity_persistence_service import (
    AcademicActivityPersistenceService,
    build_academic_activity_persistence_service,
)
from services.planning.academic_update_orchestrator import (
    AcademicUpdateOrchestrator,
    build_academic_update_orchestrator,
)
from services.planning.study_plan_enrichment_service import (
    StudyPlanEnrichmentService,
    build_study_plan_enrichment_service,
)
from services.planning.persistence_service import (
    StudyPlanningPersistenceService,
    build_study_planning_persistence_service,
)
from services.planning.replanning_service import (
    StudyReplanningService,
    build_study_replanning_service,
)
from services.planning.tracking_service import (
    StudySessionTrackingService,
    build_study_session_tracking_service,
)
from services.reminders.service import (
    StudyPlanRemindersService,
    build_study_plan_reminders_service,
)
from services.scheduling.service import ScheduleService, build_schedule_service
from services.study_recommendations.service import (
    StudyRecommendationService,
    build_study_recommendation_service,
)
from services.sync.outlook_calendar_sync_service import (
    OutlookCalendarSyncService,
    build_outlook_calendar_sync_service,
)
from services.sync.outlook_fixed_schedule_sync_service import (
    OutlookFixedScheduleSyncService,
    build_outlook_fixed_schedule_sync_service,
)
from services.sync.outlook_fixed_schedule_repair_service import (
    OutlookFixedScheduleRepairService,
    build_outlook_fixed_schedule_repair_service,
)
from services.sync.microsoft_oauth_flow_service import (
    MicrosoftOAuthFlowService,
    build_microsoft_oauth_flow_service,
)
from repositories.microsoft_graph.state_repository import (
    MicrosoftGraphStateRepository,
    build_microsoft_graph_state_repository,
)
from services.sync.microsoft_todo_sync_service import (
    MicrosoftTodoSyncService,
    build_microsoft_todo_sync_service,
)
from services.sync.outlook_one_time_event_service import (
    OutlookOneTimeEventService,
    build_outlook_one_time_event_service,
)

from .settings import BootstrapSettings, database_url_from_env, load_bootstrap_settings

T = TypeVar("T")


class AppContainer:
    """Container simple y explicito para wiring compartido del runtime."""

    def __init__(
        self,
        *,
        settings_loader: Callable[[], BootstrapSettings] | None = None,
    ) -> None:
        self._settings_loader = settings_loader or load_bootstrap_settings
        self._instances: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}

    @property
    def settings(self) -> BootstrapSettings:
        """Retorna settings actualizados desde el entorno."""

        return self._settings_loader()

    def get_onboarding_service(self) -> OnboardingService:
        return self._get_or_build("onboarding_service", build_onboarding_service)

    def set_onboarding_service(self, service: OnboardingService | None) -> None:
        self._set_override("onboarding_service", service)

    def get_personalization_service(self) -> PersonalizationService:
        return self._get_or_build("personalization_service", build_personalization_service)

    def set_personalization_service(self, service: PersonalizationService | None) -> None:
        self._set_override("personalization_service", service)

    def get_schedule_service(self) -> ScheduleService:
        return self._get_or_build("schedule_service", build_schedule_service)

    def set_schedule_service(self, service: ScheduleService | None) -> None:
        self._set_override("schedule_service", service)

    def get_study_planning_persistence_service(self) -> StudyPlanningPersistenceService:
        return self._get_or_build(
            "study_planning_persistence_service",
            build_study_planning_persistence_service,
        )

    def set_study_planning_persistence_service(
        self,
        service: StudyPlanningPersistenceService | None,
    ) -> None:
        self._set_override("study_planning_persistence_service", service)

    def get_study_replanning_service(self) -> StudyReplanningService:
        return self._get_or_build(
            "study_replanning_service",
            build_study_replanning_service,
        )

    def set_study_replanning_service(
        self,
        service: StudyReplanningService | None,
    ) -> None:
        self._set_override("study_replanning_service", service)

    def get_academic_activity_persistence_service(self) -> AcademicActivityPersistenceService:
        return self._get_or_build(
            "academic_activity_persistence_service",
            build_academic_activity_persistence_service,
        )

    def set_academic_activity_persistence_service(
        self,
        service: AcademicActivityPersistenceService | None,
    ) -> None:
        self._set_override("academic_activity_persistence_service", service)

    def get_academic_update_orchestrator(self) -> AcademicUpdateOrchestrator:
        return self._get_or_build(
            "academic_update_orchestrator",
            self._build_academic_update_orchestrator,
        )

    def set_academic_update_orchestrator(
        self,
        service: AcademicUpdateOrchestrator | None,
    ) -> None:
        self._set_override("academic_update_orchestrator", service)

    def get_study_plan_materialization_service(self) -> StudyPlanMaterializationService:
        return self._get_or_build(
            "study_plan_materialization_service",
            build_study_plan_materialization_service,
        )

    def set_study_plan_materialization_service(
        self,
        service: StudyPlanMaterializationService | None,
    ) -> None:
        self._set_override("study_plan_materialization_service", service)

    def get_reminders_service(self) -> StudyPlanRemindersService:
        return self._get_or_build("reminders_service", self._build_reminders_service)

    def set_reminders_service(self, service: StudyPlanRemindersService | None) -> None:
        self._set_override("reminders_service", service)

    def get_tracking_service(self) -> StudySessionTrackingService:
        return self._get_or_build("tracking_service", self._build_tracking_service)

    def set_tracking_service(self, service: StudySessionTrackingService | None) -> None:
        self._set_override("tracking_service", service)

    def get_study_recommendation_service(self) -> StudyRecommendationService:
        return self._get_or_build(
            "study_recommendation_service",
            build_study_recommendation_service,
        )

    def set_study_recommendation_service(
        self,
        service: StudyRecommendationService | None,
    ) -> None:
        self._instances.pop("study_plan_enrichment_service", None)
        self._set_override("study_recommendation_service", service)

    def get_study_plan_enrichment_service(self) -> StudyPlanEnrichmentService:
        return self._get_or_build(
            "study_plan_enrichment_service",
            self._build_study_plan_enrichment_service,
        )

    def set_study_plan_enrichment_service(
        self,
        service: StudyPlanEnrichmentService | None,
    ) -> None:
        self._set_override("study_plan_enrichment_service", service)

    def get_microsoft_graph_state_repository(self) -> MicrosoftGraphStateRepository:
        return self._get_or_build(
            "microsoft_graph_state_repository",
            lambda: build_microsoft_graph_state_repository(database_url_from_env()),
        )

    def set_microsoft_graph_state_repository(
        self,
        repository: MicrosoftGraphStateRepository | None,
    ) -> None:
        self._set_override("microsoft_graph_state_repository", repository)

    def get_microsoft_oauth_client(self) -> MicrosoftOAuthClient:
        return self._get_or_build("microsoft_oauth_client", self._build_microsoft_oauth_client)

    def set_microsoft_oauth_client(self, client: MicrosoftOAuthClient | None) -> None:
        self._set_override("microsoft_oauth_client", client)

    def get_microsoft_oauth_flow_service(self) -> MicrosoftOAuthFlowService:
        return self._get_or_build(
            "microsoft_oauth_flow_service",
            self._build_microsoft_oauth_flow_service,
        )

    def set_microsoft_oauth_flow_service(
        self,
        service: MicrosoftOAuthFlowService | None,
    ) -> None:
        self._set_override("microsoft_oauth_flow_service", service)

    def get_outlook_calendar_sync_service(self) -> OutlookCalendarSyncService:
        return self._get_or_build(
            "outlook_calendar_sync_service",
            self._build_outlook_calendar_sync_service,
        )

    def set_outlook_calendar_sync_service(
        self,
        service: OutlookCalendarSyncService | None,
    ) -> None:
        self._set_override("outlook_calendar_sync_service", service)

    def get_outlook_fixed_schedule_sync_service(self) -> OutlookFixedScheduleSyncService:
        return self._get_or_build(
            "outlook_fixed_schedule_sync_service",
            self._build_outlook_fixed_schedule_sync_service,
        )

    def set_outlook_fixed_schedule_sync_service(
        self,
        service: OutlookFixedScheduleSyncService | None,
    ) -> None:
        self._set_override("outlook_fixed_schedule_sync_service", service)

    def get_outlook_fixed_schedule_repair_service(self) -> OutlookFixedScheduleRepairService:
        return self._get_or_build(
            "outlook_fixed_schedule_repair_service",
            self._build_outlook_fixed_schedule_repair_service,
        )

    def set_outlook_fixed_schedule_repair_service(
        self,
        service: OutlookFixedScheduleRepairService | None,
    ) -> None:
        self._set_override("outlook_fixed_schedule_repair_service", service)

    def get_microsoft_todo_sync_service(self) -> MicrosoftTodoSyncService:
        return self._get_or_build(
            "microsoft_todo_sync_service",
            self._build_microsoft_todo_sync_service,
        )

    def set_microsoft_todo_sync_service(
        self,
        service: MicrosoftTodoSyncService | None,
    ) -> None:
        self._set_override("microsoft_todo_sync_service", service)

    def get_outlook_one_time_event_service(self) -> OutlookOneTimeEventService:
        return self._get_or_build(
            "outlook_one_time_event_service",
            self._build_outlook_one_time_event_service,
        )

    def set_outlook_one_time_event_service(
        self,
        service: OutlookOneTimeEventService | None,
    ) -> None:
        self._set_override("outlook_one_time_event_service", service)

    def _build_study_plan_enrichment_service(self) -> StudyPlanEnrichmentService:
        return build_study_plan_enrichment_service(
            recommendation_service=self.get_study_recommendation_service()
        )

    def _build_academic_update_orchestrator(self) -> AcademicUpdateOrchestrator:
        return build_academic_update_orchestrator(
            persistence_service=self.get_academic_activity_persistence_service()
        )

    def _build_reminders_service(self) -> StudyPlanRemindersService:
        materialization_service = self.get_study_plan_materialization_service()
        return build_study_plan_reminders_service(
            instances_repository=getattr(materialization_service, "repository", None)
        )

    def _build_tracking_service(self) -> StudySessionTrackingService:
        materialization_service = self.get_study_plan_materialization_service()
        return build_study_session_tracking_service(
            instances_repository=getattr(materialization_service, "repository", None)
        )

    def _build_microsoft_oauth_client(self) -> MicrosoftOAuthClient:
        state_repository = self.get_microsoft_graph_state_repository()
        return build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )

    def _build_microsoft_oauth_flow_service(self) -> MicrosoftOAuthFlowService:
        return build_microsoft_oauth_flow_service(
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _build_outlook_calendar_sync_service(self) -> OutlookCalendarSyncService:
        return build_outlook_calendar_sync_service(
            instances_repository=None,
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _build_outlook_fixed_schedule_sync_service(self) -> OutlookFixedScheduleSyncService:
        schedule_service = self.get_schedule_service()
        return build_outlook_fixed_schedule_sync_service(
            schedule_repository=getattr(schedule_service, "repository", None),
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _build_outlook_fixed_schedule_repair_service(self) -> OutlookFixedScheduleRepairService:
        schedule_service = self.get_schedule_service()
        return build_outlook_fixed_schedule_repair_service(
            schedule_repository=getattr(schedule_service, "repository", None),
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _build_microsoft_todo_sync_service(self) -> MicrosoftTodoSyncService:
        return build_microsoft_todo_sync_service(
            instances_repository=None,
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _build_outlook_one_time_event_service(self) -> OutlookOneTimeEventService:
        return build_outlook_one_time_event_service(
            state_repository=self.get_microsoft_graph_state_repository(),
            auth_client=self.get_microsoft_oauth_client(),
        )

    def _get_or_build(self, key: str, builder: Callable[[], T]) -> T:
        if key in self._overrides:
            return self._overrides[key]
        if key not in self._instances:
            self._instances[key] = builder()
        return self._instances[key]

    def _set_override(self, key: str, value: Any | None) -> None:
        self._instances.pop(key, None)
        if value is None:
            self._overrides.pop(key, None)
            return
        self._overrides[key] = value


_APP_CONTAINER: AppContainer | None = None


def get_app_container() -> AppContainer:
    """Retorna el container singleton usado por el runtime actual."""

    global _APP_CONTAINER
    if _APP_CONTAINER is None:
        _APP_CONTAINER = AppContainer()
    return _APP_CONTAINER


def set_app_container(container: AppContainer | None) -> None:
    """Permite reemplazar el container global durante pruebas."""

    global _APP_CONTAINER
    _APP_CONTAINER = container


def reset_app_container() -> AppContainer:
    """Reinicia el container global y retorna una nueva instancia."""

    container = AppContainer()
    set_app_container(container)
    return container
