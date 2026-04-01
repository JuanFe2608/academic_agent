"""Motor determinista de scoring, confianza y desempate del perfil."""

from __future__ import annotations

from collections.abc import Mapping

from agents.support.personalization.models import (
    ConfidenceLevel,
    DetectedSignal,
    PersonalizationResult,
    SignalRuleDefinition,
    TechniqueScore,
    TiebreakerAnswer,
    TiebreakerAssessment,
    TiebreakerResult,
)
from agents.support.personalization.questionnaire import (
    QUESTIONNAIRE_VERSION,
    SCORING_VERSION,
    get_question_count,
    get_questions,
    get_signal_rules,
    get_technique,
    get_techniques,
    get_tiebreaker_max_boost_for_technique,
    get_tiebreaker_question_count,
    get_tiebreaker_questions,
)

_SCORE_TIE_EPSILON = 0.0001


def evaluate_questionnaire(
    answers: Mapping[str, int],
    *,
    high_score_threshold: float = 0.67,
) -> PersonalizationResult:
    """Evalua el Radar principal y decide si necesita desempate."""

    normalized_answers = _validate_answers(answers)
    ranked_scores = rank_techniques(normalized_answers)
    confidence = classify_confidence(ranked_scores)
    assessment = assess_tiebreaker_need(
        normalized_answers,
        ranked_scores,
        confidence,
    )
    signals = build_signals(normalized_answers)
    tiebreaker = TiebreakerResult(
        status="needed" if assessment.needs_tiebreaker else "not_needed",
        activated=False,
        assessment=assessment,
        ranking_before=[score.technique_id for score in ranked_scores],
        ranking_after=[score.technique_id for score in ranked_scores],
        confidence_before=confidence,
        confidence_after=confidence if not assessment.needs_tiebreaker else None,
    )
    observations = build_observations(
        ranked_scores,
        signals,
        threshold=high_score_threshold,
        tiebreaker=tiebreaker,
    )
    weakness_tags = build_weakness_tags(
        ranked_scores,
        signals,
        threshold=high_score_threshold,
    )

    return PersonalizationResult(
        questionnaire_version=QUESTIONNAIRE_VERSION,
        scoring_version=SCORING_VERSION,
        status="completed",
        answers=normalized_answers,
        weakness_tags=weakness_tags,
        scores=ranked_scores,
        top_techniques=[score.technique_id for score in ranked_scores[:3]],
        confidence=confidence,
        signals=signals,
        observations=observations,
        tiebreaker=tiebreaker,
        method=None,
        how_to=None,
    )


def refine_questionnaire_with_tiebreaker(
    answers: Mapping[str, int],
    tiebreaker_answers: Mapping[str, int],
    *,
    high_score_threshold: float = 0.67,
) -> PersonalizationResult:
    """Aplica el desempate y recalcula el ranking final refinado."""

    main_result = evaluate_questionnaire(
        answers,
        high_score_threshold=high_score_threshold,
    )
    normalized_tiebreaker_answers = _validate_tiebreaker_answers(tiebreaker_answers)
    boosts_by_technique, answer_details = evaluate_tiebreaker_answers(
        normalized_tiebreaker_answers
    )
    refined_scores = rank_techniques(
        main_result.answers,
        boosts_by_technique=boosts_by_technique,
        include_tiebreaker_ceiling=True,
    )
    refined_confidence = _cap_confidence_for_uniform_profile(
        classify_confidence(refined_scores),
        main_result.tiebreaker.assessment,
    )
    tiebreaker = TiebreakerResult(
        status="completed",
        activated=True,
        assessment=main_result.tiebreaker.assessment,
        answers=normalized_tiebreaker_answers,
        answer_details=answer_details,
        boosts_by_technique=boosts_by_technique,
        ranking_before=list(main_result.tiebreaker.ranking_before),
        ranking_after=[score.technique_id for score in refined_scores],
        confidence_before=main_result.confidence,
        confidence_after=refined_confidence,
    )
    observations = build_observations(
        refined_scores,
        list(main_result.signals),
        threshold=high_score_threshold,
        tiebreaker=tiebreaker,
    )
    weakness_tags = build_weakness_tags(
        refined_scores,
        list(main_result.signals),
        threshold=high_score_threshold,
    )

    return PersonalizationResult(
        questionnaire_version=main_result.questionnaire_version,
        scoring_version=main_result.scoring_version,
        status="completed",
        answers=dict(main_result.answers),
        weakness_tags=weakness_tags,
        scores=refined_scores,
        top_techniques=[score.technique_id for score in refined_scores[:3]],
        confidence=refined_confidence,
        signals=list(main_result.signals),
        observations=observations,
        tiebreaker=tiebreaker,
        method=main_result.method,
        how_to=main_result.how_to,
    )


def rank_techniques(
    answers: Mapping[str, int],
    *,
    boosts_by_technique: Mapping[str, int] | None = None,
    include_tiebreaker_ceiling: bool = False,
) -> list[TechniqueScore]:
    """Construye el ranking de tecnicas usando score normalizado y boosts opcionales."""

    normalized_answers = _validate_answers(answers)
    base_raw_scores = {technique.technique_id: 0 for technique in get_techniques()}
    base_max_scores = {technique.technique_id: 0 for technique in get_techniques()}

    for question in get_questions():
        answer_value = normalized_answers[question.question_id]
        for weight in question.technique_weights:
            base_raw_scores[weight.technique_id] += answer_value * int(weight.weight)
            base_max_scores[weight.technique_id] += 3 * int(weight.weight)

    resolved_boosts = {
        technique.technique_id: int((boosts_by_technique or {}).get(technique.technique_id, 0))
        for technique in get_techniques()
    }

    scores: list[TechniqueScore] = []
    for technique in get_techniques():
        technique_id = technique.technique_id
        base_raw_score = int(base_raw_scores[technique_id])
        base_max_score = int(base_max_scores[technique_id])
        boost_score = int(resolved_boosts[technique_id])
        tiebreaker_max_score = (
            get_tiebreaker_max_boost_for_technique(technique_id)
            if include_tiebreaker_ceiling
            else 0
        )
        raw_score = base_raw_score + boost_score
        max_score = base_max_score + tiebreaker_max_score
        base_normalized_score = base_raw_score / base_max_score if base_max_score else 0.0
        normalized_score = raw_score / max_score if max_score else 0.0

        scores.append(
            TechniqueScore(
                technique_id=technique_id,
                technique_name=technique.display_name,
                priority_order=technique.priority_order,
                raw_score=raw_score,
                max_score=max_score,
                normalized_score=round(normalized_score, 4),
                percentage_score=round(normalized_score * 100, 2),
                rank=0,
                base_raw_score=base_raw_score,
                base_max_score=base_max_score,
                base_normalized_score=round(base_normalized_score, 4),
                boost_score=boost_score,
                rationale_tags=list(technique.rationale_tags),
            )
        )

    scores.sort(
        key=lambda item: (
            -item.normalized_score,
            -item.boost_score,
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


def assess_tiebreaker_need(
    answers: Mapping[str, int],
    scores: list[TechniqueScore],
    confidence: ConfidenceLevel,
) -> TiebreakerAssessment:
    """Detecta baja discriminacion del perfil y decide si activar desempate."""

    normalized_answers = _validate_answers(answers)
    unique_values = {value for value in normalized_answers.values()}
    uniform_response = len(unique_values) == 1
    uniform_value = next(iter(unique_values)) if uniform_response else None
    score_tie = _is_full_score_tie(scores)
    top_gap = _top_gap(scores)

    activation_reasons: list[str] = []
    if uniform_response:
        activation_reasons.append("uniform_answers")
    if score_tie:
        activation_reasons.append("full_score_tie")
    elif confidence == "baja" and top_gap <= 0.10:
        activation_reasons.append("low_gap_between_top_scores")

    return TiebreakerAssessment(
        uniform_response=uniform_response,
        uniform_value=uniform_value,
        profile_confidence=confidence,
        needs_tiebreaker=bool(activation_reasons),
        activation_reasons=activation_reasons,
        score_tie=score_tie,
        top_gap=round(top_gap, 4),
    )


def evaluate_tiebreaker_answers(
    tiebreaker_answers: Mapping[str, int],
) -> tuple[dict[str, int], list[TiebreakerAnswer]]:
    """Convierte respuestas de desempate en boosts por tecnica."""

    normalized_answers = _validate_tiebreaker_answers(tiebreaker_answers)
    boosts_by_technique = {technique.technique_id: 0 for technique in get_techniques()}
    answer_details: list[TiebreakerAnswer] = []

    for question in get_tiebreaker_questions():
        selected_value = normalized_answers[question.question_id]
        option = next(
            option for option in question.options if int(option.option_id) == int(selected_value)
        )
        for boost in option.technique_boosts:
            boosts_by_technique[boost.technique_id] += int(boost.boost)
        answer_details.append(
            TiebreakerAnswer(
                question_id=question.question_id,
                question_title=question.challenge_title,
                prompt=question.prompt,
                selected_option_id=int(option.option_id),
                selected_option_label=option.label,
                favored_techniques=[boost.technique_id for boost in option.technique_boosts],
                applied_boosts=list(option.technique_boosts),
            )
        )

    compact_boosts = {
        technique_id: score
        for technique_id, score in boosts_by_technique.items()
        if int(score) > 0
    }
    return compact_boosts, answer_details


def build_signals(answers: Mapping[str, int]) -> list[DetectedSignal]:
    """Detecta señales relevantes a partir de reglas declarativas."""

    normalized_answers = _validate_answers(answers)
    detected: list[DetectedSignal] = []
    for rule in get_signal_rules():
        signal = _match_rule(rule, normalized_answers)
        if signal is not None:
            detected.append(signal)

    detected.sort(
        key=lambda item: (
            -sum(item.supporting_answers.values()),
            item.priority_order,
            item.signal_id,
        )
    )
    return detected


def build_observations(
    scores: list[TechniqueScore],
    signals: list[DetectedSignal],
    *,
    threshold: float,
    tiebreaker: TiebreakerResult | None = None,
) -> list[str]:
    """Genera observaciones deterministas desde señales, desempate y score alto."""

    observations: list[str] = []
    contextual_observation = _tiebreaker_context_observation(tiebreaker)
    if contextual_observation:
        observations.append(contextual_observation)

    covered_tags = {
        tag
        for signal in signals
        for tag in signal.weakness_tags
    }
    for signal in signals:
        if signal.message not in observations:
            observations.append(signal.message)
        if len(observations) >= 4:
            return observations

    for score in scores:
        if score.normalized_score < threshold:
            continue
        if _is_redundant_technique_observation(score, covered_tags):
            continue
        observation = _observation_for_technique(score.technique_id)
        if observation and observation not in observations:
            observations.append(observation)
        if len(observations) >= 4:
            break
    return observations


def build_weakness_tags(
    scores: list[TechniqueScore],
    signals: list[DetectedSignal],
    *,
    threshold: float,
) -> list[str]:
    """Construye tags de dificultad desde reglas y ranking."""

    weakness_tags: list[str] = []
    for signal in signals:
        for tag in signal.weakness_tags:
            if tag not in weakness_tags:
                weakness_tags.append(tag)

    selected_scores = [score for score in scores if score.normalized_score >= threshold]
    if not selected_scores:
        selected_scores = scores[:3]

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


def _validate_tiebreaker_answers(answers: Mapping[str, int]) -> dict[str, int]:
    expected_ids = [question.question_id for question in get_tiebreaker_questions()]
    missing = [question_id for question_id in expected_ids if question_id not in answers]
    if missing:
        raise ValueError(
            "Respuestas incompletas para el desempate: " + ", ".join(missing)
        )

    normalized: dict[str, int] = {}
    for question in get_tiebreaker_questions():
        raw_value = answers[question.question_id]
        valid_values = {int(option.option_id) for option in question.options}
        if not isinstance(raw_value, int) or int(raw_value) not in valid_values:
            raise ValueError(
                f"Respuesta invalida para {question.question_id}: {raw_value!r}"
            )
        normalized[question.question_id] = int(raw_value)

    if len(normalized) != get_tiebreaker_question_count():
        raise ValueError("La cantidad de respuestas no coincide con el desempate.")
    return normalized


def _match_rule(
    rule: SignalRuleDefinition,
    answers: Mapping[str, int],
) -> DetectedSignal | None:
    supporting_answers = {
        question_id: int(answers[question_id])
        for question_id in rule.question_ids
        if int(answers[question_id]) >= int(rule.threshold)
    }
    if len(supporting_answers) < int(rule.min_matches):
        return None

    average_score = sum(supporting_answers.values()) / max(len(supporting_answers), 1)
    strength = "alta" if average_score >= 2.5 else "media"
    return DetectedSignal(
        signal_id=rule.signal_id,
        label=rule.label,
        message=rule.message,
        strength=strength,
        supporting_question_ids=list(supporting_answers),
        supporting_answers=supporting_answers,
        related_techniques=list(rule.related_techniques),
        weakness_tags=list(rule.weakness_tags),
        priority_order=rule.priority_order,
    )


def _is_full_score_tie(scores: list[TechniqueScore]) -> bool:
    if not scores:
        return True
    reference = scores[0].normalized_score
    return all(abs(score.normalized_score - reference) <= _SCORE_TIE_EPSILON for score in scores)


def _top_gap(scores: list[TechniqueScore]) -> float:
    if len(scores) < 2:
        return 0.0
    return float(scores[0].normalized_score - scores[1].normalized_score)


def _cap_confidence_for_uniform_profile(
    confidence: ConfidenceLevel,
    assessment: TiebreakerAssessment,
) -> ConfidenceLevel:
    if not assessment.uniform_response:
        return confidence
    if confidence == "alta":
        return "media"
    return confidence


def _tiebreaker_context_observation(tiebreaker: TiebreakerResult | None) -> str | None:
    if tiebreaker is None or not tiebreaker.activated:
        return None

    assessment = tiebreaker.assessment
    if not assessment.uniform_response:
        return "El desempate ayudó a romper una diferencia muy corta entre técnicas y afinar la prioridad inicial."

    if assessment.uniform_value == 0:
        return (
            "El radar principal no marcó una dificultad fuerte; el desempate se usó para priorizar "
            "qué técnica conviene fortalecer primero."
        )
    if assessment.uniform_value == 1:
        return (
            "El radar principal mostró una dificultad leve distribuida; el desempate se usó para "
            "decidir por dónde empezar."
        )
    if assessment.uniform_value == 2:
        return (
            "El radar principal mostró una dificultad moderada general; el desempate ayudó a "
            "definir la técnica prioritaria inicial."
        )
    if assessment.uniform_value == 3:
        return (
            "El radar principal mostró dificultad alta en casi todo el perfil; el desempate se usó "
            "para definir la prioridad de acompañamiento."
        )
    return None


def _observation_for_technique(technique_id: str) -> str | None:
    try:
        return get_technique(technique_id).observation
    except KeyError:
        return None


def _is_redundant_technique_observation(
    score: TechniqueScore,
    covered_tags: set[str],
) -> bool:
    if not covered_tags:
        return False
    return any(tag in covered_tags for tag in score.rationale_tags)
