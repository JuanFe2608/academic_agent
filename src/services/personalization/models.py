"""Modelos canonicos del modulo de personalizacion academica."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LikertValue = Literal[0, 1, 2, 3]
ConfidenceLevel = Literal["alta", "media", "baja"]
TechniqueWeightRole = Literal["primary", "secondary"]
SignalStrength = Literal["media", "alta"]
AnswerStage = Literal["radar", "tiebreaker"]
TiebreakerStatus = Literal["not_needed", "needed", "collecting", "completed"]
TiebreakerActivationReason = Literal[
    "uniform_answers",
    "full_score_tie",
    "low_gap_between_top_scores",
]


class TechniqueWeight(BaseModel):
    """Peso de contribucion de una pregunta sobre una tecnica."""

    technique_id: str
    weight: int = Field(default=1, ge=1)
    role: TechniqueWeightRole = "primary"


class TechniqueBoost(BaseModel):
    """Boost de desempate aplicado a una tecnica."""

    technique_id: str
    boost: int = Field(default=1, ge=1)


class QuestionDefinition(BaseModel):
    """Define una pregunta cerrada del cuestionario."""

    question_id: str
    challenge_title: str
    challenge_emoji: str
    prompt: str
    technique_id: str
    technique_weights: list[TechniqueWeight] = Field(default_factory=list)
    measurement_tags: list[str] = Field(default_factory=list)


class TechniqueDefinition(BaseModel):
    """Define una tecnica de estudio disponible para ranking."""

    technique_id: str
    display_name: str
    priority_order: int
    rationale_tags: list[str] = Field(default_factory=list)
    observation: str
    support_hint: str


class SignalRuleDefinition(BaseModel):
    """Regla declarativa para detectar una senal relevante del estudiante."""

    signal_id: str
    label: str
    message: str
    question_ids: list[str] = Field(default_factory=list)
    threshold: LikertValue = 2
    min_matches: int = 1
    priority_order: int = 0
    related_techniques: list[str] = Field(default_factory=list)
    weakness_tags: list[str] = Field(default_factory=list)


class ChoiceOptionDefinition(BaseModel):
    """Opcion cerrada de una pregunta de desempate."""

    option_id: int = Field(ge=1)
    label: str
    technique_boosts: list[TechniqueBoost] = Field(default_factory=list)


class TiebreakerQuestionDefinition(BaseModel):
    """Define un reto extra para afinar el perfil."""

    question_id: str
    challenge_title: str
    challenge_emoji: str
    prompt: str
    options: list[ChoiceOptionDefinition] = Field(default_factory=list)


class ParsedLikertAnswer(BaseModel):
    """Resultado determinista del parser de respuestas Likert."""

    value: LikertValue | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.value is not None


class ParsedChoiceAnswer(BaseModel):
    """Resultado del parser de respuestas de opcion unica."""

    value: int | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.value is not None


class TiebreakerAssessment(BaseModel):
    """Diagnostico de baja discriminacion previo al desempate."""

    uniform_response: bool = False
    uniform_value: LikertValue | None = None
    profile_confidence: ConfidenceLevel = "baja"
    needs_tiebreaker: bool = False
    activation_reasons: list[TiebreakerActivationReason] = Field(default_factory=list)
    score_tie: bool = False
    top_gap: float = 0.0


class PersonalizationAnswer(BaseModel):
    """Representa una respuesta persistible por pregunta."""

    question_id: str
    question_text: str
    technique_id: str
    value: int
    label: str
    answer_stage: AnswerStage = "radar"
    option_id: str | None = None
    favored_techniques: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def answer_value(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "value": int(self.value),
            "label": self.label,
            "answer_stage": self.answer_stage,
        }
        if self.option_id:
            payload["option_id"] = self.option_id
        if self.favored_techniques:
            payload["favored_techniques"] = list(self.favored_techniques)
        if self.metadata:
            payload.update(self.metadata)
        return payload


class TiebreakerAnswer(BaseModel):
    """Respuesta estructurada del bloque de desempate."""

    question_id: str
    question_title: str
    prompt: str
    selected_option_id: int
    selected_option_label: str
    favored_techniques: list[str] = Field(default_factory=list)
    applied_boosts: list[TechniqueBoost] = Field(default_factory=list)
    answered_at: str | None = None


class TiebreakerResult(BaseModel):
    """Resultado estructurado del desempate."""

    status: TiebreakerStatus = "not_needed"
    activated: bool = False
    assessment: TiebreakerAssessment = Field(default_factory=TiebreakerAssessment)
    answers: dict[str, int] = Field(default_factory=dict)
    answer_details: list[TiebreakerAnswer] = Field(default_factory=list)
    boosts_by_technique: dict[str, int] = Field(default_factory=dict)
    ranking_before: list[str] = Field(default_factory=list)
    ranking_after: list[str] = Field(default_factory=list)
    confidence_before: ConfidenceLevel | None = None
    confidence_after: ConfidenceLevel | None = None
    started_at: str | None = None
    completed_at: str | None = None


class DetectedSignal(BaseModel):
    """Senal diagnostica detectada a partir de reglas deterministas."""

    signal_id: str
    label: str
    message: str
    strength: SignalStrength = "media"
    supporting_question_ids: list[str] = Field(default_factory=list)
    supporting_answers: dict[str, int] = Field(default_factory=dict)
    related_techniques: list[str] = Field(default_factory=list)
    weakness_tags: list[str] = Field(default_factory=list)
    priority_order: int = 0


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
    base_raw_score: int | None = None
    base_max_score: int | None = None
    base_normalized_score: float | None = None
    boost_score: int = 0
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
    signals: list[DetectedSignal] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    tiebreaker: TiebreakerResult = Field(default_factory=TiebreakerResult)
    completed_at: str | None = None
    method: str | None = None
    how_to: str | None = None
