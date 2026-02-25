"""Definiciones de estado y utilidades de normalizacion ligeras.

Este modulo centraliza el estado basado en TypedDict y provee utilidades
minimas para normalizar/validar campos de eventos. Evita la logica de
parseo/render que vive en los modulos de tools.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Literal, NotRequired, Optional, TypedDict

Phase = Literal[
    "consent",
    "profile",
    "schedules",
    "extras",
    "draft",
    "validate",
    "sync",
    "priorities",
    "study_plan",
    "running",
    "replan",
    "end",
]

EventType = Literal["confirmado", "tentativo"]
EventCategory = Literal["academico", "laboral", "extracurricular", "estudio"]
CalendarProvider = Literal["outlook", "google"]
Ocupacion = Literal["solo_estudio", "solo_trabajo", "ambos", "ninguna"]
Prioridad = Literal["alta", "media", "baja"]


class Event(TypedDict):
    """Estructura canonica del evento de agenda."""

    id: str
    dia: str
    inicio: str
    fin: str
    titulo: str
    tipo: EventType
    categoria: EventCategory
    origen: str
    prioridad: NotRequired[Prioridad]
    dificultad: NotRequired[int]
    timezone: str


class ConsentState(TypedDict):
    """Seguimiento del consentimiento del usuario."""

    accepted: bool
    timestamp: Optional[str]


class StudentProfile(TypedDict):
    """Atributos del perfil del estudiante recolectados al inicio."""

    nombre: Optional[str]
    edad: Optional[int]
    correo: Optional[str]
    codigo: Optional[str]
    programa: Optional[str]
    semestre: Optional[int]
    promedio: Optional[float]
    ocupacion: Optional[Ocupacion]


class RawInputs(TypedDict):
    """Entradas crudas de horarios (imagenes/texto) antes de normalizar."""

    horario_academico_img: Optional[str]
    horario_laboral_text: Optional[str]
    horario_laboral_img: Optional[str]
    extras: list[str]


class ExtracurricularItem(TypedDict):
    """Definicion de actividad extracurricular y eventos tentativos."""

    nombre: str
    es_variable: bool
    detalle: str
    tentativo: list[Event]


class SchedulePreview(TypedDict):
    """Vista previa de datos de horario parseados."""

    text: Optional[str]
    image_path: Optional[str]


class CalendarState(TypedDict):
    """Metadatos de integracion de calendario."""

    provider: Optional[CalendarProvider]
    authorized: bool
    calendar_id: Optional[str]
    synced_event_map: dict[str, str]


class SubjectItem(TypedDict):
    """Metadatos de materias para priorizacion."""

    nombre: str
    prioridad: Prioridad
    dificultad: int


class StudyProfile(TypedDict):
    """Cuestionario de metodo de estudio y metodo seleccionado."""

    answers: dict[str, object]
    method: Optional[str]
    how_to: Optional[str]


class StudyPlanState(TypedDict):
    """Plan de estudio generado y reglas de planificacion."""

    plan_events: list[Event]
    rules: dict[str, object]


class ReplanState(TypedDict):
    """Estado de replanificacion automatica y propuestas."""

    trigger: Optional[str]
    change_request: Optional[dict[str, object]]
    proposals: list[list[Event]]
    selected_index: Optional[int]


class RemindersState(TypedDict):
    """Configuracion de recordatorios y politicas."""

    enabled: bool
    policy: dict[str, object]


class Constraints(TypedDict):
    """Restricciones duras para agenda y plan de estudio."""

    sleep_start: str
    sleep_end: str
    study_session_min: int
    study_session_max: int
    max_study_per_day_min: int


class AgentState(TypedDict):
    """Estado de nivel superior guardado en el grafo."""

    messages: list
    phase: Phase
    errors: list[str]
    timezone: str
    consent: ConsentState
    student_profile: StudentProfile
    raw_inputs: RawInputs
    extracurricular: list[ExtracurricularItem]
    events: list[Event]
    events_validated: bool
    schedule_preview: SchedulePreview
    calendar: CalendarState
    subjects: list[SubjectItem]
    study_profile: StudyProfile
    study_plan: StudyPlanState
    replan: ReplanState
    reminders: RemindersState
    constraints: Constraints


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
    "d": "Domingo",
    "do": "Domingo",
    "dom": "Domingo",
    "domingo": "Domingo",
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


def validate_event(event: Event) -> None:
    """Valida un Event por campos requeridos y formatos.

    Verifica campos obligatorios, dia/hora normalizados, inicio antes de fin
    y categorias validas. Lanza ValueError si falla.
    """

    if not isinstance(event, dict):
        raise ValueError("event must be a dict")

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
        if key not in event or event[key] in (None, ""):
            raise ValueError(f"missing required field: {key}")

    normalized_day = normalize_day(event["dia"])
    if normalized_day != event["dia"]:
        raise ValueError("dia must be normalized to Lunes..Domingo")

    start = normalize_time(event["inicio"])
    end = normalize_time(event["fin"])
    if start != event["inicio"] or end != event["fin"]:
        raise ValueError("inicio/fin must be in HH:MM format")

    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])
    if start_minutes >= end_minutes:
        raise ValueError("inicio must be before fin")

    if event["tipo"] not in EVENT_TYPES:
        raise ValueError("invalid event tipo")
    if event["categoria"] not in EVENT_CATEGORIES:
        raise ValueError("invalid event categoria")

    if "prioridad" in event and event["prioridad"] not in PRIORIDADES:
        raise ValueError("invalid prioridad")
    if "dificultad" in event:
        dificultad = event["dificultad"]
        if not isinstance(dificultad, int) or not (1 <= dificultad <= 5):
            raise ValueError("dificultad must be int between 1 and 5")


def sort_events(events: list[Event]) -> list[Event]:
    """Retorna eventos ordenados por dia y hora de inicio."""

    order = {day: idx for idx, day in enumerate(DAY_ORDER)}

    def sort_key(item: Event) -> tuple[int, int]:
        raw_day = item.get("dia", "")
        try:
            normalized_day = normalize_day(raw_day)
        except ValueError:
            normalized_day = raw_day
        day_index = order.get(normalized_day, len(DAY_ORDER))
        time = normalize_time(item.get("inicio", "00:00"))
        minutes = int(time[:2]) * 60 + int(time[3:])
        return day_index, minutes

    return sorted(events, key=sort_key)


def make_initial_state() -> AgentState:
    """Construye el AgentState inicial con valores coherentes."""

    return {
        "messages": [],
        "phase": "consent",
        "errors": [],
        "timezone": "America/Bogota",
        "consent": {"accepted": False, "timestamp": None},
        "student_profile": {
            "nombre": None,
            "edad": None,
            "correo": None,
            "codigo": None,
            "programa": None,
            "semestre": None,
            "promedio": None,
            "ocupacion": None,
        },
        "raw_inputs": {
            "horario_academico_img": None,
            "horario_laboral_text": None,
            "horario_laboral_img": None,
            "extras": [],
        },
        "extracurricular": [],
        "events": [],
        "events_validated": False,
        "schedule_preview": {"text": None, "image_path": None},
        "calendar": {
            "provider": None,
            "authorized": False,
            "calendar_id": None,
            "synced_event_map": {},
        },
        "subjects": [],
        "study_profile": {"answers": {}, "method": None, "how_to": None},
        "study_plan": {"plan_events": [], "rules": {}},
        "replan": {
            "trigger": None,
            "change_request": None,
            "proposals": [],
            "selected_index": None,
        },
        "reminders": {"enabled": False, "policy": {}},
        "constraints": {
            "sleep_start": "23:00",
            "sleep_end": "06:00",
            "study_session_min": 25,
            "study_session_max": 90,
            "max_study_per_day_min": 180,
        },
    }
