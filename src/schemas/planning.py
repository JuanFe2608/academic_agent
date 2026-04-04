"""Schemas reutilizables de prioridades y planificacion."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel, Prioridad
from .scheduling import Event


class SubjectItem(BaseSchemaModel):
    """Metadatos de materias para priorización y planificación."""

    nombre: str
    prioridad: Prioridad
    dificultad: int
    urgencia: Optional[Prioridad] = None
    carga_semanal_min: Optional[int] = None
    origen: Optional[str] = None


class PrioritiesState(BaseSchemaModel):
    """Estado operativo de captura de prioridades académicas."""

    status: Literal["idle", "collecting", "completed", "skipped"] = "idle"
    prompt_version: str = "v1"
    source: Optional[str] = None
    last_error: Optional[str] = None
    persisted_profile_id: Optional[int] = None
    version_number: Optional[int] = None
    persistence_error: Optional[str] = None


class StudyPlanState(BaseSchemaModel):
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


class ReplanState(BaseSchemaModel):
    """Estado de replanificacion automatica y propuestas."""

    trigger: Optional[str] = None
    change_request: Optional[dict[str, object]] = None
    proposals: list[list[Event]] = Field(default_factory=list)
    selected_index: Optional[int] = None
    pending_prompt: Optional[str] = None
    return_to_menu: Optional[bool] = None


class Constraints(BaseSchemaModel):
    """Restricciones duras para agenda y plan de estudio."""

    sleep_start: str = "23:00"
    sleep_end: str = "06:00"
    study_session_min: int = 25
    study_session_max: int = 90
    max_study_per_day_min: int = 180


__all__ = [
    "Constraints",
    "PrioritiesState",
    "ReplanState",
    "StudyPlanState",
    "SubjectItem",
]
