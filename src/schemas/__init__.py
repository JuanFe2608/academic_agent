"""DTOs, modelos Pydantic y contratos reutilizables del sistema."""

from .common import BaseSchemaModel, Occupation, Ocupacion, Prioridad
from .channels import AggregatedInput, BufferedMessage
from .conversation import (
    ConversationInputType,
    ConversationRouteAction,
    ConversationRouteDecision,
    InputClassification,
    InputUtility,
    InteractionState,
    ScopeAction,
    ScopeCategory,
    ScopeDecision,
)
from .microsoft_graph import CalendarProvider, CalendarState
from .onboarding import (
    ConsentState,
    EmailVerificationState,
    MicrosoftOAuthOnboardingState,
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
    "AggregatedInput",
    "BufferedMessage",
    "CalendarProvider",
    "CalendarState",
    "ConsentState",
    "Constraints",
    "ConversationInputType",
    "ConversationRouteAction",
    "ConversationRouteDecision",
    "EmailVerificationState",
    "Event",
    "EventCategory",
    "EventType",
    "ExtracurricularItem",
    "InteractionState",
    "InputClassification",
    "InputUtility",
    "MicrosoftOAuthOnboardingState",
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
    "ScopeAction",
    "ScopeCategory",
    "ScopeDecision",
    "StudentProfile",
    "StudyPlanState",
    "StudyRecommendationQuery",
    "StudyRecommendationResult",
    "StudyProfile",
    "SubjectItem",
]
