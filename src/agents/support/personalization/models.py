"""Modelos canonicos del modulo de personalizacion academica."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LikertValue = Literal[0, 1, 2, 3]
ConfidenceLevel = Literal["alta", "media", "baja"]


class QuestionDefinition(BaseModel):
    """Define una pregunta cerrada del cuestionario."""

    question_id: str
    prompt: str
    technique_id: str


class TechniqueDefinition(BaseModel):
    """Define una tecnica de estudio disponible para ranking."""

    technique_id: str
    display_name: str
    priority_order: int
    rationale_tags: list[str] = Field(default_factory=list)
    observation: str


class ParsedLikertAnswer(BaseModel):
    """Resultado determinista del parser de respuestas Likert."""

    value: LikertValue | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.value is not None


class PersonalizationAnswer(BaseModel):
    """Representa una respuesta persistible por pregunta."""

    question_id: str
    question_text: str
    technique_id: str
    value: LikertValue
    label: str

    @property
    def answer_value(self) -> dict[str, object]:
        return {
            "value": int(self.value),
            "label": self.label,
        }


class TechniqueScore(BaseModel):
    """Score final de una tecnica de estudio."""

    technique_id: str
    technique_name: str
    priority_order: int
    raw_score: int
    max_score: int
    normalized_score: float
    percentage_score: float
    rank: int = 0
    rationale_tags: list[str] = Field(default_factory=list)


class PersonalizationResult(BaseModel):
    """Resultado estructurado final del cuestionario."""

    questionnaire_version: str
    scoring_version: str
    status: Literal["completed"] = "completed"
    answers: dict[str, int] = Field(default_factory=dict)
    weakness_tags: list[str] = Field(default_factory=list)
    scores: list[TechniqueScore] = Field(default_factory=list)
    top_techniques: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = "baja"
    observations: list[str] = Field(default_factory=list)
    method: str | None = None
    how_to: str | None = None

