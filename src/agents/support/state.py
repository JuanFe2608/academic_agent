"""Definiciones de estado y utilidades de normalizacion ligeras.

Este modulo centraliza el estado basado en Pydantic y provee utilidades
minimas para normalizar/validar campos de eventos. Evita la logica de
parseo/render que vive en los modulos de tools.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, Annotated, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from agents.support.scheduling.models import ScheduleFlowState

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

EventType = Literal["confirmado", "tentativo"]
EventCategory = Literal["academico", "laboral", "extracurricular", "estudio"]
CalendarProvider = Literal["outlook", "google"]
Occupation = Literal["solo_estudio", "ambos", "ninguna"]
Ocupacion = Occupation
Prioridad = Literal["alta", "media", "baja"]
ExtrasCollectStage = Literal["awaiting_type", "awaiting_details", "awaiting_more", "done"]
UserStatus = Literal["start", "valid", "out_of_scope"]
ScheduleContextType = Literal["academic", "work"]


class BaseStateModel(BaseModel):
    """Base de modelos con acceso tipo dict para compatibilidad."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class Event(BaseStateModel):
    """Estructura canonica del evento de agenda."""

    id: str
    dia: str
    inicio: str
    fin: str
    titulo: str
    tipo: EventType
    categoria: EventCategory
    origen: str
    prioridad: Optional[Prioridad] = None
    dificultad: Optional[int] = None
    timezone: str


class ConsentState(BaseStateModel):
    """Seguimiento del consentimiento del usuario."""

    accepted: bool = False
    timestamp: Optional[str] = None


class StudentProfile(BaseStateModel):
    """Atributos del perfil del estudiante recolectados al inicio."""

    full_name: Optional[str] = None
    student_code: Optional[str] = None
    age: Optional[int] = None
    institutional_email: Optional[str] = None
    email_verified: bool = False
    academic_program: Optional[str] = None
    supported_program: Optional[bool] = None
    semester: Optional[int] = None
    average_grade: Optional[float] = None
    occupation: Optional[Occupation] = None
    persisted_student_id: Optional[int] = None


class EmailVerificationState(BaseStateModel):
    """Estado transitorio de verificacion del correo institucional."""

    status: Literal["idle", "sent", "verified"] = "idle"
    attempts: int = 0
    resend_count: int = 0
    expires_at: Optional[str] = None
    last_error: Optional[str] = None


class OnboardingState(BaseStateModel):
    """Metadatos operativos del flujo de onboarding."""

    current_field: Optional[str] = None
    pending_student_code_scope_confirmation: bool = False
    email_verification: EmailVerificationState = Field(
        default_factory=EmailVerificationState
    )
    persistence_error: Optional[str] = None


class RawInputs(BaseStateModel):
    """Entradas crudas de horarios (imagenes/texto) antes de normalizar."""

    horario_academico_img: Optional[str] = None
    horario_academico_text: Optional[str] = None
    horario_laboral_tipo: Optional[str] = None
    horario_laboral_text: Optional[str] = None
    horario_laboral_img: Optional[str] = None
    extras: list[str] = Field(default_factory=list)


class ExtracurricularItem(BaseStateModel):
    """Definicion de actividad extracurricular y eventos tentativos."""

    nombre: str
    es_variable: bool
    detalle: str
    dias: list[str] = Field(default_factory=list)
    frecuencia: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    tentativo: list[Event] = Field(default_factory=list)


class PendingExtracurricularItem(BaseStateModel):
    """Contexto pendiente para completar una actividad extracurricular."""

    nombre: str = ""
    dias: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    es_variable: Optional[bool] = None
    raw_text: str = ""


class PendingScheduleItem(BaseStateModel):
    """Contexto pendiente para completar un bloque academico o laboral."""

    schedule_type: ScheduleContextType
    title: str = ""
    days: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    raw_text: str = ""


class SchedulePreview(BaseStateModel):
    """Vista previa de datos de horario parseados."""

    text: Optional[str] = None
    image_path: Optional[str] = None


class CalendarState(BaseStateModel):
    """Metadatos de integracion de calendario."""

    provider: Optional[CalendarProvider] = None
    authorized: bool = False
    calendar_id: Optional[str] = None
    synced_event_map: dict[str, str] = Field(default_factory=dict)


class SubjectItem(BaseStateModel):
    """Metadatos de materias para priorización y planificación."""

    nombre: str
    prioridad: Prioridad
    dificultad: int
    urgencia: Optional[Prioridad] = None
    carga_semanal_min: Optional[int] = None
    origen: Optional[str] = None


class StudyProfile(BaseStateModel):
    """Cuestionario de metodo de estudio y metodo seleccionado."""

    questionnaire_version: Optional[str] = None
    scoring_version: Optional[str] = None
    status: Literal["idle", "collecting", "tiebreaker_collecting", "completed"] = "idle"
    current_question_index: int = 0
    answers: dict[str, int] = Field(default_factory=dict)
    weakness_tags: list[str] = Field(default_factory=list)
    scores: list[dict[str, object]] = Field(default_factory=list)
    top_techniques: list[str] = Field(default_factory=list)
    confidence: Optional[Literal["alta", "media", "baja"]] = None
    signals: list[dict[str, object]] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    tiebreaker: dict[str, object] = Field(default_factory=dict)
    completed_at: Optional[str] = None
    persisted_profile_id: Optional[int] = None
    persistence_error: Optional[str] = None
    method: Optional[str] = None
    how_to: Optional[str] = None


class PrioritiesState(BaseStateModel):
    """Estado operativo de captura de prioridades académicas."""

    status: Literal["idle", "collecting", "completed", "skipped"] = "idle"
    prompt_version: str = "v1"
    source: Optional[str] = None
    last_error: Optional[str] = None
    persisted_profile_id: Optional[int] = None
    version_number: Optional[int] = None
    persistence_error: Optional[str] = None


class StudyPlanState(BaseStateModel):
    """Plan de estudio generado y reglas de planificacion."""

    plan_events: list[Event] = Field(default_factory=list)
    rules: dict[str, object] = Field(default_factory=dict)
    persisted_profile_id: Optional[int] = None
    version_number: Optional[int] = None
    persistence_error: Optional[str] = None
    materialized_instance_count: Optional[int] = None
    superseded_instance_count: Optional[int] = None
    materialized_horizon_days: Optional[int] = None
    materialized_through_date: Optional[str] = None
    materialization_error: Optional[str] = None


class ReplanState(BaseStateModel):
    """Estado de replanificacion automatica y propuestas."""

    trigger: Optional[str] = None
    change_request: Optional[dict[str, object]] = None
    proposals: list[list[Event]] = Field(default_factory=list)
    selected_index: Optional[int] = None
    pending_prompt: Optional[str] = None
    return_to_menu: Optional[bool] = None


class RemindersState(BaseStateModel):
    """Configuracion de recordatorios y politicas."""

    enabled: bool = True
    policy: dict[str, object] = Field(default_factory=dict)
    persisted_policy_ids: list[int] = Field(default_factory=list)
    last_dispatch_error: Optional[str] = None
    last_sync_at: Optional[str] = None


class Constraints(BaseStateModel):
    """Restricciones duras para agenda y plan de estudio."""

    sleep_start: str = "23:00"
    sleep_end: str = "06:00"
    study_session_min: int = 25
    study_session_max: int = 90
    max_study_per_day_min: int = 180


class AgentState(BaseStateModel):
    """Estado de nivel superior guardado en el grafo."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    phase: Phase = "consent"
    errors: list[str] = Field(default_factory=list)
    timezone: str = "America/Bogota"
    user_status: UserStatus = "start"
    welcome_sent: bool = False
    last_user_text: Optional[str] = None
    last_user_images: list[str] = Field(default_factory=list)
    profile_edit_target: Optional[str] = None
    user_message_count: int = 0
    awaiting_user_input: bool = False
    consent: ConsentState = Field(default_factory=ConsentState)
    student_profile: StudentProfile = Field(default_factory=StudentProfile)
    onboarding: OnboardingState = Field(default_factory=OnboardingState)
    raw_inputs: RawInputs = Field(default_factory=RawInputs)
    extras_has_any: Optional[bool] = None
    extras_collect_stage: Optional[ExtrasCollectStage] = None
    extras_pending_is_variable: Optional[bool] = None
    extras_pending_items: list[PendingExtracurricularItem] = Field(default_factory=list)
    academic_pending_items: list[PendingScheduleItem] = Field(default_factory=list)
    work_pending_items: list[PendingScheduleItem] = Field(default_factory=list)
    extracurricular: list[ExtracurricularItem] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    events_validated: bool = False
    schedule_preview: SchedulePreview = Field(default_factory=SchedulePreview)
    schedule: ScheduleFlowState = Field(default_factory=ScheduleFlowState)
    calendar: CalendarState = Field(default_factory=CalendarState)
    subjects: list[SubjectItem] = Field(default_factory=list)
    study_profile: StudyProfile = Field(default_factory=StudyProfile)
    priorities: PrioritiesState = Field(default_factory=PrioritiesState)
    study_plan: StudyPlanState = Field(default_factory=StudyPlanState)
    replan: ReplanState = Field(default_factory=ReplanState)
    reminders: RemindersState = Field(default_factory=RemindersState)
    constraints: Constraints = Field(default_factory=Constraints)


DAY_ORDER = [
    "Lunes",
    "Martes",
    "Miercoles",
    "Jueves",
    "Viernes",
    "Sabado",
    "Domingo",
]

DAY_ALIASES = {
    "l": "Lunes",
    "lu": "Lunes",
    "lun": "Lunes",
    "lunes": "Lunes",
    "ma": "Martes",
    "mar": "Martes",
    "martes": "Martes",
    "mi": "Miercoles",
    "mie": "Miercoles",
    "mier": "Miercoles",
    "miercoles": "Miercoles",
    "x": "Miercoles",
    "j": "Jueves",
    "ju": "Jueves",
    "jue": "Jueves",
    "jueves": "Jueves",
    "v": "Viernes",
    "vi": "Viernes",
    "vie": "Viernes",
    "viernes": "Viernes",
    "s": "Sabado",
    "sa": "Sabado",
    "sab": "Sabado",
    "sabado": "Sabado",
    "sabados": "Sabado",
    "d": "Domingo",
    "do": "Domingo",
    "dom": "Domingo",
    "domingo": "Domingo",
    "domingos": "Domingo",
}

EVENT_TYPES = {"confirmado", "tentativo"}
EVENT_CATEGORIES = {"academico", "laboral", "extracurricular", "estudio"}
PRIORIDADES = {"alta", "media", "baja"}


def new_event_id() -> str:
    """Retorna un identificador unico para un Event."""

    return str(uuid.uuid4())


def normalize_time(value: str) -> str:
    """Normaliza tiempo a formato HH:MM en 24h.

    Acepta formatos como "7am", "7:30 am" y "19:00".
    Lanza ValueError para entradas invalidas.
    """

    if value is None:
        raise ValueError("time value is required")
    raw = str(value).strip().lower()
    if not raw:
        raise ValueError("time value is required")

    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([ap]m)?$", raw)
    if not match:
        raise ValueError(f"invalid time format: {value!r}")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if minute < 0 or minute > 59:
        raise ValueError(f"invalid minutes: {value!r}")

    if meridiem:
        if hour < 1 or hour > 12:
            raise ValueError(f"invalid hour: {value!r}")
        if meridiem == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    else:
        if hour < 0 or hour > 23:
            raise ValueError(f"invalid hour: {value!r}")

    return f"{hour:02d}:{minute:02d}"


def normalize_day(value: str) -> str:
    """Normaliza el dia a nombres canonicos en espanol.

    Acepta variantes como "lun", "lunes", "L", etc.
    Lanza ValueError para entradas invalidas.
    """

    if value is None:
        raise ValueError("day value is required")
    raw = str(value).strip().lower()
    if not raw:
        raise ValueError("day value is required")

    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z]", "", folded)
    if not key:
        raise ValueError(f"invalid day: {value!r}")

    normalized = DAY_ALIASES.get(key)
    if not normalized:
        raise ValueError(f"invalid day: {value!r}")
    return normalized


def validate_event(event: Event | dict[str, Any]) -> None:
    """Valida un Event por campos requeridos y formatos.

    Verifica campos obligatorios, dia/hora normalizados, inicio antes de fin
    y categorias validas. Lanza ValueError si falla.
    """

    required = [
        "id",
        "dia",
        "inicio",
        "fin",
        "titulo",
        "tipo",
        "categoria",
        "origen",
        "timezone",
    ]
    for key in required:
        value = _event_value(event, key)
        if value in (None, ""):
            raise ValueError(f"missing required field: {key}")

    dia = _event_value(event, "dia")
    normalized_day = normalize_day(dia)
    if normalized_day != dia:
        raise ValueError("dia must be normalized to Lunes..Domingo")

    start = normalize_time(_event_value(event, "inicio"))
    end = normalize_time(_event_value(event, "fin"))
    if start != _event_value(event, "inicio") or end != _event_value(event, "fin"):
        raise ValueError("inicio/fin must be in HH:MM format")

    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])
    if start_minutes >= end_minutes:
        raise ValueError("inicio must be before fin")

    if _event_value(event, "tipo") not in EVENT_TYPES:
        raise ValueError("invalid event tipo")
    if _event_value(event, "categoria") not in EVENT_CATEGORIES:
        raise ValueError("invalid event categoria")

    prioridad = _event_value(event, "prioridad")
    if prioridad and prioridad not in PRIORIDADES:
        raise ValueError("invalid prioridad")
    dificultad = _event_value(event, "dificultad")
    if dificultad is not None:
        if not isinstance(dificultad, int) or not (1 <= dificultad <= 5):
            raise ValueError("dificultad must be int between 1 and 5")


def sort_events(events: list[Event]) -> list[Event]:
    """Retorna eventos ordenados por dia y hora de inicio."""

    order = {day: idx for idx, day in enumerate(DAY_ORDER)}

    def sort_key(item: Event) -> tuple[int, int]:
        raw_day = _event_value(item, "dia", "")
        try:
            normalized_day = normalize_day(raw_day)
        except ValueError:
            normalized_day = raw_day
        day_index = order.get(normalized_day, len(DAY_ORDER))
        time = normalize_time(_event_value(item, "inicio", "00:00"))
        minutes = int(time[:2]) * 60 + int(time[3:])
        return day_index, minutes

    return sorted(events, key=sort_key)


def make_initial_state() -> AgentState:
    """Construye el AgentState inicial con valores coherentes."""

    return AgentState()


def _event_value(event: Event | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)
