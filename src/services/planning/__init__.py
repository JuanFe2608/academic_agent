"""Servicios del dominio de planificación académica."""

from .daily_accompaniment_service import (
    DailyCompletionParseResult,
    DailyFocusResult,
    build_daily_focus,
    parse_daily_completion_response,
)
from .materialization_service import (
    MaterializeStudyPlanInstancesResult,
    StudyPlanMaterializationService,
    build_study_plan_materialization_service,
)
from .persistence_service import (
    PersistStudyPlanningSnapshotResult,
    StudyPlanningPersistenceService,
    build_study_planning_persistence_service,
)
from .state_helpers import (
    ensure_constraints,
    ensure_study_plan_state,
    ensure_study_profile,
    study_plan_state_to_update,
    update_study_plan_state,
)
from .study_plan_sync_service import StudyPlanSyncResult, sync_subjects_and_study_plan
from .study_planning_service import build_initial_study_plan
from .tracking_service import (
    MarkMissedStudySessionsResult,
    StudySessionTrackingService,
    TrackStudySessionResult,
    build_study_session_tracking_service,
)

__all__ = [
    "DailyCompletionParseResult",
    "DailyFocusResult",
    "MaterializeStudyPlanInstancesResult",
    "MarkMissedStudySessionsResult",
    "PersistStudyPlanningSnapshotResult",
    "StudyPlanMaterializationService",
    "StudyPlanSyncResult",
    "StudyPlanningPersistenceService",
    "StudySessionTrackingService",
    "TrackStudySessionResult",
    "build_daily_focus",
    "build_initial_study_plan",
    "build_study_plan_materialization_service",
    "build_study_planning_persistence_service",
    "build_study_session_tracking_service",
    "ensure_constraints",
    "ensure_study_plan_state",
    "ensure_study_profile",
    "study_plan_state_to_update",
    "sync_subjects_and_study_plan",
    "parse_daily_completion_response",
    "update_study_plan_state",
]
