"""DTOs, modelos Pydantic y contratos reutilizables del sistema."""

from .common import BaseSchemaModel, Occupation, Ocupacion, Prioridad
from .microsoft_graph import CalendarProvider, CalendarState
from .onboarding import (
    ConsentState,
    EmailVerificationState,
    OnboardingState,
    StudentProfile,
)
from .personalization import StudyProfile
from .planning import Constraints, PrioritiesState, ReplanState, StudyPlanState, SubjectItem
from .rag import (
    NormalizedRagDocument,
    RagChunk,
    RagCorpusBuildResult,
    RagDocumentMetadata,
    RagRelation,
    RagValidationIssue,
    StudyRecommendationQuery,
    StudyRecommendationResult,
)
from .reminders import RemindersState
from .scheduling import (
    Event,
    EventCategory,
    EventType,
    ExtracurricularItem,
    PendingExtracurricularItem,
    PendingScheduleItem,
    RawInputs,
    ScheduleContextType,
    SchedulePreview,
)

__all__ = [
    "BaseSchemaModel",
    "CalendarProvider",
    "CalendarState",
    "ConsentState",
    "Constraints",
    "EmailVerificationState",
    "Event",
    "EventCategory",
    "EventType",
    "ExtracurricularItem",
    "Occupation",
    "Ocupacion",
    "OnboardingState",
    "PendingExtracurricularItem",
    "PendingScheduleItem",
    "Prioridad",
    "PrioritiesState",
    "NormalizedRagDocument",
    "RagChunk",
    "RagCorpusBuildResult",
    "RagDocumentMetadata",
    "RagRelation",
    "RagValidationIssue",
    "RawInputs",
    "RemindersState",
    "ReplanState",
    "ScheduleContextType",
    "SchedulePreview",
    "StudentProfile",
    "StudyPlanState",
    "StudyRecommendationQuery",
    "StudyRecommendationResult",
    "StudyProfile",
    "SubjectItem",
]
