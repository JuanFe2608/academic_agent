"""Contrato minimo del estado conversacional del agente.

Este modulo mantiene el contrato plano que LangGraph usa hoy para evitar una
reescritura del grafo, pero además expone particiones tipadas por dominio para
reducir el acoplamiento alrededor de ``AgentState`` y dejar una base segura
para migraciones posteriores.

Los DTOs reutilizables viven en ``schemas/`` y las utilidades de dominio
en ``services/``.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from langchain_core.messages import BaseMessage
from pydantic import Field, field_validator

from agents.support.media import add_sanitized_messages, materialize_image_reference, sanitize_messages
from schemas.common import BaseSchemaModel as _BaseSchemaModel
from schemas.conversation import InteractionState as _InteractionState
from schemas.microsoft_graph import CalendarState as _CalendarState
from schemas.onboarding import (
    ConsentState as _ConsentState,
    OnboardingState as _OnboardingState,
    StudentProfile as _StudentProfile,
)
from schemas.personalization import StudyProfile as _StudyProfile
from schemas.planning import (
    AcademicActivity as _AcademicActivity,
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
    "microsoft_oauth",
    "schedules",
    "extras",
    "draft",
    "validate",
    "schedule_edit",
    "schedule_persist",
    "schedule_sync",
    "schedule_renewal",
    "schedule_repair",
    "fixed_schedule_management",
    "study_profile",
    "priorities",
    "running",
    "end",
]

_ExtrasCollectStage = Literal["awaiting_type", "awaiting_details", "awaiting_more", "done"]
_UserStatus = Literal["start", "valid", "out_of_scope"]


class _ConversationState(_BaseSchemaModel):
    """Vista tipada del estado conversacional y de runtime."""

    messages: Annotated[list[BaseMessage], add_sanitized_messages] = Field(default_factory=list)
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

    @field_validator("messages", mode="before")
    @classmethod
    def _sanitize_conversation_messages(cls, value: object) -> object:
        return sanitize_messages(value)

    @field_validator("last_user_images", mode="before")
    @classmethod
    def _sanitize_conversation_image_refs(cls, value: object) -> object:
        return _sanitize_image_ref_list(value)


class _OnboardingDomainState(_BaseSchemaModel):
    """Vista tipada del dominio de onboarding."""

    consent: _ConsentState = Field(default_factory=_ConsentState)
    student_profile: _StudentProfile = Field(default_factory=_StudentProfile)
    onboarding: _OnboardingState = Field(default_factory=_OnboardingState)


class _SchedulingDomainState(_BaseSchemaModel):
    """Vista tipada del dominio de captura y revisión de horarios."""

    raw_inputs: _RawInputs = Field(default_factory=_RawInputs)
    extras_collect_stage: _ExtrasCollectStage | None = None
    extras_pending_is_variable: bool | None = None
    extras_pending_items: list[_PendingExtracurricularItem] = Field(default_factory=list)
    academic_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    work_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    extracurricular: list[_ExtracurricularItem] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)
    schedule_preview: _SchedulePreview = Field(default_factory=_SchedulePreview)
    schedule: _ScheduleFlowState = Field(default_factory=_ScheduleFlowState)


class _PlanningDomainState(_BaseSchemaModel):
    """Vista tipada de personalización, planificación y recordatorios."""

    subjects: list[_SubjectItem] = Field(default_factory=list)
    academic_activities: list[_AcademicActivity] = Field(default_factory=list)
    study_profile: _StudyProfile = Field(default_factory=_StudyProfile)
    priorities: _PrioritiesState = Field(default_factory=_PrioritiesState)
    study_plan: _StudyPlanState = Field(default_factory=_StudyPlanState)
    replan: _ReplanState = Field(default_factory=_ReplanState)
    reminders: _RemindersState = Field(default_factory=_RemindersState)
    constraints: _Constraints = Field(default_factory=_Constraints)


class _IntegrationState(_BaseSchemaModel):
    """Vista tipada de adaptadores externos acoplados al grafo."""

    calendar: _CalendarState = Field(default_factory=_CalendarState)


class _PartitionedAgentState(_BaseSchemaModel):
    """Composición tipada del estado por dominio.

    Esta vista no reemplaza todavía el contrato plano del grafo. Su objetivo es
    declarar ownership y servir como punto de apoyo para migraciones
    incrementales de lectores y escritores.
    """

    conversation: _ConversationState = Field(default_factory=_ConversationState)
    interaction: _InteractionState = Field(default_factory=_InteractionState)
    onboarding: _OnboardingDomainState = Field(default_factory=_OnboardingDomainState)
    scheduling: _SchedulingDomainState = Field(default_factory=_SchedulingDomainState)
    planning: _PlanningDomainState = Field(default_factory=_PlanningDomainState)
    integrations: _IntegrationState = Field(default_factory=_IntegrationState)


class AgentState(_BaseSchemaModel):
    """Estado de nivel superior guardado en el grafo."""

    _FIELD_GROUPS: ClassVar[dict[str, tuple[str, ...]]] = {
        "conversation": (
            "messages",
            "phase",
            "errors",
            "timezone",
            "user_status",
            "welcome_sent",
            "last_user_text",
            "last_user_images",
            "profile_edit_target",
            "user_message_count",
            "awaiting_user_input",
        ),
        "interaction": ("interaction",),
        "onboarding": (
            "consent",
            "student_profile",
            "onboarding",
        ),
        "scheduling": (
            "raw_inputs",
            "extras_collect_stage",
            "extras_pending_is_variable",
            "extras_pending_items",
            "academic_pending_items",
            "work_pending_items",
            "extracurricular",
            "events",
            "schedule_preview",
            "schedule",
        ),
        "planning": (
            "subjects",
            "academic_activities",
            "study_profile",
            "priorities",
            "study_plan",
            "replan",
            "reminders",
            "constraints",
        ),
        "integrations": ("calendar",),
    }
    _DERIVATION_CANDIDATES: ClassVar[dict[str, str]] = {
        "events": "Copia de trabajo para replanning; schedule.blocks es la fuente de verdad. Migración pendiente Fase 1.",
    }

    messages: Annotated[list[BaseMessage], add_sanitized_messages] = Field(default_factory=list)
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
    interaction: _InteractionState = Field(default_factory=_InteractionState)
    consent: _ConsentState = Field(default_factory=_ConsentState)
    student_profile: _StudentProfile = Field(default_factory=_StudentProfile)
    onboarding: _OnboardingState = Field(default_factory=_OnboardingState)
    raw_inputs: _RawInputs = Field(default_factory=_RawInputs)
    extras_collect_stage: _ExtrasCollectStage | None = None
    extras_pending_is_variable: bool | None = None
    extras_pending_items: list[_PendingExtracurricularItem] = Field(default_factory=list)
    academic_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    work_pending_items: list[_PendingScheduleItem] = Field(default_factory=list)
    extracurricular: list[_ExtracurricularItem] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)
    schedule_preview: _SchedulePreview = Field(default_factory=_SchedulePreview)
    schedule: _ScheduleFlowState = Field(default_factory=_ScheduleFlowState)
    calendar: _CalendarState = Field(default_factory=_CalendarState)
    subjects: list[_SubjectItem] = Field(default_factory=list)
    academic_activities: list[_AcademicActivity] = Field(default_factory=list)
    study_profile: _StudyProfile = Field(default_factory=_StudyProfile)
    priorities: _PrioritiesState = Field(default_factory=_PrioritiesState)
    study_plan: _StudyPlanState = Field(default_factory=_StudyPlanState)
    replan: _ReplanState = Field(default_factory=_ReplanState)
    reminders: _RemindersState = Field(default_factory=_RemindersState)
    constraints: _Constraints = Field(default_factory=_Constraints)

    @field_validator("messages", mode="before")
    @classmethod
    def _sanitize_messages(cls, value: object) -> object:
        return sanitize_messages(value)

    @field_validator("last_user_images", mode="before")
    @classmethod
    def _sanitize_image_refs(cls, value: object) -> object:
        return _sanitize_image_ref_list(value)

    @classmethod
    def field_groups(cls) -> dict[str, tuple[str, ...]]:
        """Retorna la partición oficial de campos del estado por dominio."""

        return {name: tuple(fields) for name, fields in cls._FIELD_GROUPS.items()}

    @classmethod
    def field_group_for(cls, field_name: str) -> str | None:
        """Indica a qué subestado pertenece un campo top-level."""

        for group_name, field_names in cls._FIELD_GROUPS.items():
            if field_name in field_names:
                return group_name
        return None

    @classmethod
    def derivation_candidates(cls) -> dict[str, str]:
        """Lista campos legacy que deberían migrar a derivación controlada."""

        return dict(cls._DERIVATION_CANDIDATES)

    @property
    def conversation_state(self) -> _ConversationState:
        """Subestado tipado del runtime conversacional."""

        return _ConversationState(**self._group_payload("conversation"))

    @property
    def interaction_state(self) -> _InteractionState:
        """Subestado tipado de interaccion operativa."""

        return _InteractionState.model_validate(self.interaction)

    @property
    def onboarding_state(self) -> _OnboardingDomainState:
        """Subestado tipado del dominio de onboarding."""

        return _OnboardingDomainState(**self._group_payload("onboarding"))

    @property
    def scheduling_state(self) -> _SchedulingDomainState:
        """Subestado tipado del dominio de scheduling."""

        return _SchedulingDomainState(**self._group_payload("scheduling"))

    @property
    def planning_state(self) -> _PlanningDomainState:
        """Subestado tipado del dominio de planificación."""

        return _PlanningDomainState(**self._group_payload("planning"))

    @property
    def integration_state(self) -> _IntegrationState:
        """Subestado tipado de integraciones externas."""

        return _IntegrationState(**self._group_payload("integrations"))

    @property
    def partitions(self) -> _PartitionedAgentState:
        """Composición tipada del estado actual.

        Se usa como vista de lectura y como apoyo para construir resets o
        adapters transitorios sin expandir más el uso del contrato plano.
        """

        return _PartitionedAgentState(
            conversation=self.conversation_state,
            interaction=self.interaction_state,
            onboarding=self.onboarding_state,
            scheduling=self.scheduling_state,
            planning=self.planning_state,
            integrations=self.integration_state,
        )

    def legacy_group_payload(self, group_name: str) -> dict[str, object]:
        """Serializa un grupo de campos al formato plano actual del grafo."""

        return self._group_payload(group_name)

    def restart_payload_for_new_attempt(
        self,
        *,
        messages: list[BaseMessage],
        user_message_count: int,
        last_user_text: str | None,
    ) -> dict[str, object]:
        """Construye un reset seguro preservando el contrato plano vigente.

        El reset reusa un ``AgentState`` fresco para evitar divergencias entre
        defaults del estado y reseteos manuales dispersos por el código.
        """

        fresh = make_initial_state(timezone=self.timezone)
        payload = {
            **fresh.legacy_group_payload("conversation"),
            **fresh.legacy_group_payload("interaction"),
            **fresh.legacy_group_payload("onboarding"),
            **fresh.legacy_group_payload("scheduling"),
            **fresh.legacy_group_payload("planning"),
            **fresh.legacy_group_payload("integrations"),
        }
        payload.update(
            {
                "phase": "consent",
                "user_status": "start",
                "welcome_sent": True,
                "awaiting_user_input": True,
                "user_message_count": user_message_count,
                "last_user_text": last_user_text,
                "messages": messages,
            }
        )
        return payload

    def _group_payload(self, group_name: str) -> dict[str, object]:
        data = self.model_dump(mode="python")
        return {
            field_name: data[field_name]
            for field_name in self._FIELD_GROUPS[group_name]
        }


def make_initial_state(*, timezone: str = "America/Bogota") -> AgentState:
    """Construye el AgentState inicial con valores coherentes."""

    return AgentState(timezone=timezone)


def _sanitize_image_ref_list(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, str):
        return [materialize_image_reference(value)]
    if isinstance(value, (list, tuple)):
        return [materialize_image_reference(str(item)) for item in value if str(item or "").strip()]
    return value


__all__ = [
    "AgentState",
    "Phase",
    "make_initial_state",
]
