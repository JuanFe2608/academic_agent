"""Schemas reutilizables del dominio de personalizacion."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel


class StudyProfile(BaseSchemaModel):
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


__all__ = ["StudyProfile"]
