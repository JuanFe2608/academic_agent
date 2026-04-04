"""Contrato minimo del estado conversacional del agente.

Este modulo solo expone el estado del grafo y sus fases.
Los DTOs reutilizables viven en `schemas/` y las utilidades de dominio
en `services/`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field

from schemas.common import BaseSchemaModel as _BaseSchemaModel
from schemas.microsoft_graph import CalendarState as _CalendarState
from schemas.onboarding import (
    ConsentState as _ConsentState,
    OnboardingState as _OnboardingState,
    StudentProfile as _StudentProfile,
)
from schemas.personalization import StudyProfile as _StudyProfile
from schemas.planning import (
    Constraints as _Constraints,
    PrioritiesState as _PrioritiesState,
    ReplanState as _ReplanState,
    StudyPlanState as _StudyPlanState,
    SubjectItem as _SubjectItem,
)
from schemas.reminders import RemindersState as _RemindersState
from schemas.scheduling import (
    Event as _Event,
    ExtracurricularItem as _ExtracurricularItem,
    PendingExtracurricularItem as _PendingExtracurricularItem,
    PendingScheduleItem as _PendingScheduleItem,
    RawInputs as _RawInputs,
    SchedulePreview as _SchedulePreview,
)
from services.scheduling.models import ScheduleFlowState as _ScheduleFlowState

Phase = Literal[
    "consent",
    "profile",
    "email_verification_send",
    "email_verification",
    "profile_confirm",
    "profile_persist",
    "schedules",
    "extras",
    "draft",
    "validate",
    "schedule_edit",
    "schedule_persist",
    "sync",
    "study_profile",
    "study_profile_tiebreaker",
    "study_profile_persist",
    "priorities",
    "study_plan",
    "running",
    "replan",
    "end",
]

_ExtrasCollectStage = Literal["awaiting_type", "awaiting_details", "awaiting_more", "done"]
_UserStatus = Literal["start", "valid", "out_of_scope"]


class AgentState(_BaseSchemaModel):
    """Estado de nivel superior guardado en el grafo."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    phase: Phase = "consent"
    errors: list[str] = Field(default_factory=list)
    timezone: str = "America/Bogota"
    user_status: _UserStatus = "start"
    welcome_sent: bool = False
    last_user_text: str | None = None
    last_user_images: list[str] = Field(default_factory=list)
    profile_edit_target: str | None = None
    user_message_count: int = 0
    awaiting_user_input: bool = False
    consent: _ConsentState = Field(default_factory=_ConsentState)
    student_profile: _StudentProfile = Field(default_factory=_StudentProfile)
    onboarding: _OnboardingState = Field(default_factory=_OnboardingState)
    raw_inputs: _RawInputs = Field(default_factory=_RawInputs)
    extras_has_any: bool | None = None
    extras_collect_stage: _ExtrasCollectStage | None = None
    extras_pending_is_variable: bool | None = None
    extras_pending_items: list[_PendingExtracurricularItem] = Field(default_factory=list)
    academic_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    work_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    extracurricular: list[_ExtracurricularItem] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)
    events_validated: bool = False
    schedule_preview: _SchedulePreview = Field(default_factory=_SchedulePreview)
    schedule: _ScheduleFlowState = Field(default_factory=_ScheduleFlowState)
    calendar: _CalendarState = Field(default_factory=_CalendarState)
    subjects: list[_SubjectItem] = Field(default_factory=list)
    study_profile: _StudyProfile = Field(default_factory=_StudyProfile)
    priorities: _PrioritiesState = Field(default_factory=_PrioritiesState)
    study_plan: _StudyPlanState = Field(default_factory=_StudyPlanState)
    replan: _ReplanState = Field(default_factory=_ReplanState)
    reminders: _RemindersState = Field(default_factory=_RemindersState)
    constraints: _Constraints = Field(default_factory=_Constraints)


def make_initial_state() -> AgentState:
    """Construye el AgentState inicial con valores coherentes."""

    return AgentState()


__all__ = [
    "AgentState",
    "Phase",
    "make_initial_state",
]
