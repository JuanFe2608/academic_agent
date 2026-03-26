"""Motor determinista de scoring y ranking de tecnicas de estudio."""

from __future__ import annotations

from collections.abc import Mapping

from agents.support.personalization.models import (
    ConfidenceLevel,
    PersonalizationResult,
    TechniqueScore,
)
from agents.support.personalization.questionnaire import (
    QUESTIONNAIRE_VERSION,
    SCORING_VERSION,
    get_question_count,
    get_questions,
    get_questions_for_technique,
    get_techniques,
)


def evaluate_questionnaire(
    answers: Mapping[str, int],
    *,
    high_score_threshold: float = 0.67,
) -> PersonalizationResult:
    """Calcula el ranking completo y el top 3 a partir del cuestionario."""

    normalized_answers = _validate_answers(answers)
    ranked_scores = rank_techniques(normalized_answers)
    top_techniques = [score.technique_id for score in ranked_scores[:3]]
    confidence = classify_confidence(ranked_scores)
    observations = build_observations(ranked_scores, threshold=high_score_threshold)
    weakness_tags = build_weakness_tags(ranked_scores, threshold=high_score_threshold)

    return PersonalizationResult(
        questionnaire_version=QUESTIONNAIRE_VERSION,
        scoring_version=SCORING_VERSION,
        status="completed",
        answers=normalized_answers,
        weakness_tags=weakness_tags,
        scores=ranked_scores,
        top_techniques=top_techniques,
        confidence=confidence,
        observations=observations,
        method=None,
        how_to=None,
    )


def rank_techniques(answers: Mapping[str, int]) -> list[TechniqueScore]:
    """Construye el ranking completo de tecnicas con desempate estable."""

    normalized_answers = _validate_answers(answers)
    scores: list[TechniqueScore] = []
    for technique in get_techniques():
        questions = get_questions_for_technique(technique.technique_id)
        raw_score = sum(normalized_answers[question.question_id] for question in questions)
        max_score = len(questions) * 3
        normalized_score = raw_score / max_score if max_score else 0.0
        scores.append(
            TechniqueScore(
                technique_id=technique.technique_id,
                technique_name=technique.display_name,
                priority_order=technique.priority_order,
                raw_score=raw_score,
                max_score=max_score,
                normalized_score=round(normalized_score, 4),
                percentage_score=round(normalized_score * 100, 2),
                rationale_tags=list(technique.rationale_tags),
            )
        )

    scores.sort(
        key=lambda item: (
            -item.normalized_score,
            item.priority_order,
            item.technique_id,
        )
    )
    return [
        score.model_copy(update={"rank": index})
        for index, score in enumerate(scores, start=1)
    ]


def classify_confidence(scores: list[TechniqueScore]) -> ConfidenceLevel:
    """Calcula la confianza segun la diferencia entre top 1 y top 2."""

    if len(scores) < 2:
        return "baja"

    difference = scores[0].normalized_score - scores[1].normalized_score
    if difference >= 0.20:
        return "alta"
    if difference >= 0.10:
        return "media"
    return "baja"


def build_observations(
    scores: list[TechniqueScore],
    *,
    threshold: float,
) -> list[str]:
    """Genera observaciones deterministas para tecnicas con puntaje alto."""

    observations: list[str] = []
    for score in scores:
        if score.normalized_score < threshold:
            continue
        observation = _observation_for_technique(score.technique_id)
        if observation and observation not in observations:
            observations.append(observation)
    return observations


def build_weakness_tags(
    scores: list[TechniqueScore],
    *,
    threshold: float,
) -> list[str]:
    """Construye tags de debilidad a partir de scores altos o del top 3."""

    selected_scores = [score for score in scores if score.normalized_score >= threshold]
    if not selected_scores:
        selected_scores = scores[:3]

    weakness_tags: list[str] = []
    for score in selected_scores:
        for tag in score.rationale_tags:
            if tag not in weakness_tags:
                weakness_tags.append(tag)
    return weakness_tags


def _validate_answers(answers: Mapping[str, int]) -> dict[str, int]:
    expected_ids = [question.question_id for question in get_questions()]
    missing = [question_id for question_id in expected_ids if question_id not in answers]
    if missing:
        raise ValueError(
            "Respuestas incompletas para personalizacion: " + ", ".join(missing)
        )

    normalized: dict[str, int] = {}
    for question in get_questions():
        raw_value = answers[question.question_id]
        if not isinstance(raw_value, int) or not (0 <= raw_value <= 3):
            raise ValueError(
                f"Respuesta invalida para {question.question_id}: {raw_value!r}"
            )
        normalized[question.question_id] = raw_value

    if len(normalized) != get_question_count():
        raise ValueError("La cantidad de respuestas no coincide con el cuestionario.")
    return normalized


def _observation_for_technique(technique_id: str) -> str | None:
    for technique in get_techniques():
        if technique.technique_id == technique_id:
            return technique.observation
    return None

