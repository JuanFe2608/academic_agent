"""Schemas reutilizables del dominio de scheduling."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel, Prioridad

EventType = Literal["confirmado", "tentativo"]
EventCategory = Literal["academico", "laboral", "extracurricular", "estudio"]
ScheduleContextType = Literal["academic", "work"]


class Event(BaseSchemaModel):
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


class RawInputs(BaseSchemaModel):
    """Entradas crudas de horarios antes de normalizar."""

    horario_academico_img: Optional[str] = None
    horario_academico_text: Optional[str] = None
    horario_laboral_tipo: Optional[str] = None
    horario_laboral_text: Optional[str] = None
    horario_laboral_img: Optional[str] = None
    extras: list[str] = Field(default_factory=list)


class ExtracurricularItem(BaseSchemaModel):
    """Definicion de actividad extracurricular y eventos tentativos."""

    nombre: str
    es_variable: bool
    detalle: str
    dias: list[str] = Field(default_factory=list)
    frecuencia: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    tentativo: list[Event] = Field(default_factory=list)


class PendingExtracurricularItem(BaseSchemaModel):
    """Contexto pendiente para completar una actividad extracurricular."""

    nombre: str = ""
    dias: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    es_variable: Optional[bool] = None
    raw_text: str = ""


class PendingScheduleItem(BaseSchemaModel):
    """Contexto pendiente para completar un bloque academico o laboral."""

    schedule_type: ScheduleContextType
    title: str = ""
    days: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    raw_text: str = ""


class SchedulePreview(BaseSchemaModel):
    """Vista previa de datos de horario parseados."""

    text: Optional[str] = None
    image_path: Optional[str] = None


__all__ = [
    "Event",
    "EventCategory",
    "EventType",
    "ExtracurricularItem",
    "PendingExtracurricularItem",
    "PendingScheduleItem",
    "RawInputs",
    "ScheduleContextType",
    "SchedulePreview",
]
