"""Servicios del dominio de planificación académica."""

from .academic_activity_persistence_service import (
    AcademicActivityPersistenceService,
    ListAcademicActivitiesResult,
    PersistAcademicActivityResult,
    build_academic_activity_persistence_service,
)
from .academic_activity_service import (
    AcademicActivityApplyResult,
    AcademicActivityParseResult,
    active_academic_activities,
    apply_confirmed_academic_activity_operation,
    coerce_academic_activities,
    format_activity_brief,
    parse_academic_activity_request,
    priority_update_text_for_activity,
    render_activity_list,
)
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
from .operational_policy import (
    StudyPlanOperationalPolicy,
    load_study_plan_operational_policy,
)
from .persistence_service import (
    PersistStudyPlanningSnapshotResult,
    StudyPlanningPersistenceService,
    build_study_planning_persistence_service,
)
from .replanning_service import (
    StudyReplanProposalResult,
    StudyReplanningService,
    build_study_replanning_service,
    is_replan_request_message,
)
from .session_tracking_flow_service import (
    StudySessionTrackingFlowResult,
    StudySessionTrackingIntent,
    apply_study_session_tracking_text,
    is_study_session_tracking_message,
    parse_study_session_tracking_intent,
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
    "AcademicActivityApplyResult",
    "AcademicActivityParseResult",
    "AcademicActivityPersistenceService",
    "DailyCompletionParseResult",
    "DailyFocusResult",
    "ListAcademicActivitiesResult",
    "MaterializeStudyPlanInstancesResult",
    "MarkMissedStudySessionsResult",
    "PersistAcademicActivityResult",
    "PersistStudyPlanningSnapshotResult",
    "StudyPlanMaterializationService",
    "StudyPlanOperationalPolicy",
    "StudyReplanProposalResult",
    "StudyReplanningService",
    "StudyPlanSyncResult",
    "StudyPlanningPersistenceService",
    "StudySessionTrackingFlowResult",
    "StudySessionTrackingIntent",
    "StudySessionTrackingService",
    "TrackStudySessionResult",
    "active_academic_activities",
    "apply_confirmed_academic_activity_operation",
    "build_academic_activity_persistence_service",
    "build_daily_focus",
    "build_initial_study_plan",
    "load_study_plan_operational_policy",
    "build_study_plan_materialization_service",
    "build_study_planning_persistence_service",
    "build_study_replanning_service",
    "build_study_session_tracking_service",
    "coerce_academic_activities",
    "ensure_constraints",
    "ensure_study_plan_state",
    "ensure_study_profile",
    "format_activity_brief",
    "is_study_session_tracking_message",
    "is_replan_request_message",
    "parse_academic_activity_request",
    "parse_study_session_tracking_intent",
    "study_plan_state_to_update",
    "sync_subjects_and_study_plan",
    "apply_study_session_tracking_text",
    "parse_daily_completion_response",
    "priority_update_text_for_activity",
    "render_activity_list",
    "update_study_plan_state",
]
