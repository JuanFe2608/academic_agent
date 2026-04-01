"""Pruebas del motor de scoring y ranking de personalizacion."""

from __future__ import annotations

import pytest

from agents.support.personalization.scoring import (
    assess_tiebreaker_need,
    evaluate_questionnaire,
    rank_techniques,
    refine_questionnaire_with_tiebreaker,
)


def _empty_answers() -> dict[str, int]:
    return {
        "Q01": 0,
        "Q02": 0,
        "Q03": 0,
        "Q04": 0,
        "Q05": 0,
        "Q06": 0,
        "Q07": 0,
        "Q08": 0,
        "Q09": 0,
        "Q10": 0,
    }


def test_rank_techniques_scores_pomodoro_with_two_questions() -> None:
    answers = _empty_answers()
    answers["Q01"] = 3
    answers["Q02"] = 2

    scores = rank_techniques(answers)
    pomodoro = next(score for score in scores if score.technique_id == "pomodoro")

    assert pomodoro.raw_score == 500
    assert pomodoro.max_score == 600
    assert pomodoro.normalized_score == 0.8333
    assert pomodoro.percentage_score == 83.33
    assert pomodoro.rank == 1


@pytest.mark.parametrize(
    ("overrides", "expected_top_three", "expected_top_score", "expected_signal"),
    [
        (
            {"Q01": 3, "Q02": 2},
            ["pomodoro", "feynman", "active_recall"],
            0.8333,
            "start_and_focus_friction",
        ),
        (
            {"Q03": 1, "Q04": 3, "Q05": 1},
            ["active_recall", "feynman", "cornell"],
            0.7037,
            "passive_review_dependence",
        ),
        (
            {"Q06": 3},
            ["mapas_conceptuales", "pomodoro", "feynman"],
            1.0,
            "concept_connection_gap",
        ),
        (
            {"Q09": 3, "Q10": 2},
            ["interleaving", "pomodoro", "feynman"],
            0.8333,
            "interleaving_friction",
        ),
        (
            {"Q08": 3},
            ["repeticion_espaciada", "pomodoro", "feynman"],
            1.0,
            "rapid_forgetting",
        ),
    ],
)
def test_golden_cases_produce_expected_top_technique_and_signal(
    overrides: dict[str, int],
    expected_top_three: list[str],
    expected_top_score: float,
    expected_signal: str,
) -> None:
    answers = _empty_answers()
    answers.update(overrides)

    result = evaluate_questionnaire(answers)

    assert result.top_techniques == expected_top_three
    assert result.scores[0].technique_id == expected_top_three[0]
    assert result.scores[0].normalized_score == expected_top_score
    assert result.signals[0].signal_id == expected_signal
    assert result.confidence == "alta"
    assert result.tiebreaker.assessment.needs_tiebreaker is False


def test_rank_techniques_uses_stable_tie_breaker_by_priority_order() -> None:
    answers = _empty_answers()
    answers["Q03"] = 3
    answers["Q04"] = 3

    scores = rank_techniques(answers)

    assert scores[0].technique_id == "feynman"
    assert scores[1].technique_id == "active_recall"
    assert scores[0].rank == 1
    assert scores[1].rank == 2


def test_evaluate_questionnaire_returns_top_three_and_full_ranking() -> None:
    answers = _empty_answers()
    for question_id in answers:
        answers[question_id] = 3

    result = evaluate_questionnaire(answers)

    assert len(result.scores) == 8
    assert result.top_techniques == [
        "pomodoro",
        "feynman",
        "active_recall",
    ]
    assert result.scores[0].rank == 1
    assert result.scores[-1].rank == 8


def test_evaluate_questionnaire_sets_high_confidence_when_weighted_gap_is_clear() -> None:
    answers = _empty_answers()
    answers["Q03"] = 3
    answers["Q04"] = 3

    result = evaluate_questionnaire(answers)

    assert result.confidence == "alta"


def test_evaluate_questionnaire_builds_observations_and_weakness_tags() -> None:
    answers = _empty_answers()
    answers["Q01"] = 3
    answers["Q02"] = 3
    answers["Q08"] = 3

    result = evaluate_questionnaire(answers)

    assert result.top_techniques[0] == "pomodoro"
    assert result.observations == [
        "Aparece dificultad para iniciar y sostener sesiones de estudio con foco.",
        "Si no vuelves sobre un tema en los días siguientes, tiendes a olvidarlo rápido.",
    ]
    assert "rapid_forgetting" in result.weakness_tags
    assert result.signals[0].signal_id == "start_and_focus_friction"


def test_evaluate_questionnaire_keeps_observations_supported_by_answers() -> None:
    answers = _empty_answers()
    answers.update({"Q03": 1, "Q04": 3, "Q05": 1})

    result = evaluate_questionnaire(answers)

    assert result.observations == [
        "Hay dependencia de relectura en lugar de recuperar la información activamente.",
    ]


def test_assess_tiebreaker_need_detects_uniform_answers() -> None:
    answers = _empty_answers()
    for question_id in answers:
        answers[question_id] = 1

    scores = rank_techniques(answers)
    assessment = assess_tiebreaker_need(answers, scores, "baja")

    assert assessment.uniform_response is True
    assert assessment.uniform_value == 1
    assert assessment.needs_tiebreaker is True
    assert assessment.activation_reasons == ["uniform_answers", "full_score_tie"]


def test_evaluate_questionnaire_handles_uniform_all_zero_responses() -> None:
    result = evaluate_questionnaire(_empty_answers())

    assert result.top_techniques == ["pomodoro", "feynman", "active_recall"]
    assert result.confidence == "baja"
    assert result.signals == []
    assert result.observations == []
    assert result.tiebreaker.assessment.model_dump() == {
        "uniform_response": True,
        "uniform_value": 0,
        "profile_confidence": "baja",
        "needs_tiebreaker": True,
        "activation_reasons": ["uniform_answers", "full_score_tie"],
        "score_tie": True,
        "top_gap": 0.0,
    }


def test_evaluate_questionnaire_handles_uniform_all_three_responses() -> None:
    answers = _empty_answers()
    for question_id in answers:
        answers[question_id] = 3

    result = evaluate_questionnaire(answers)

    assert result.top_techniques == ["pomodoro", "feynman", "active_recall"]
    assert result.confidence == "baja"
    assert [signal.signal_id for signal in result.signals] == [
        "start_and_focus_friction",
        "interleaving_friction",
        "explanation_gap",
        "passive_review_dependence",
        "notes_not_helping",
        "concept_connection_gap",
        "exact_memory_gap",
        "rapid_forgetting",
    ]
    assert result.tiebreaker.assessment.uniform_value == 3
    assert result.tiebreaker.assessment.needs_tiebreaker is True


def test_evaluate_questionnaire_detects_non_uniform_tie_between_techniques() -> None:
    answers = _empty_answers()
    answers.update({"Q03": 3, "Q05": 3})

    result = evaluate_questionnaire(answers)

    assert result.top_techniques == ["feynman", "cornell", "active_recall"]
    assert result.confidence == "baja"
    assert result.tiebreaker.assessment.activation_reasons == [
        "low_gap_between_top_scores"
    ]
    assert result.tiebreaker.assessment.score_tie is False
    assert result.tiebreaker.assessment.top_gap == 0.0


def test_evaluate_questionnaire_mixed_realistic_case_matches_expected_scoreboard() -> None:
    answers = _empty_answers()
    answers.update(
        {
            "Q01": 2,
            "Q02": 1,
            "Q03": 2,
            "Q04": 3,
            "Q05": 1,
            "Q06": 2,
            "Q07": 0,
            "Q08": 2,
            "Q09": 1,
            "Q10": 3,
        }
    )

    result = evaluate_questionnaire(answers)

    assert result.top_techniques == ["active_recall", "feynman", "mapas_conceptuales"]
    assert result.confidence == "media"
    assert [
        (
            score.technique_id,
            score.raw_score,
            score.max_score,
            score.normalized_score,
            score.rank,
        )
        for score in result.scores
    ] == [
        ("active_recall", 420, 540, 0.7778, 1),
        ("feynman", 200, 300, 0.6667, 2),
        ("mapas_conceptuales", 200, 300, 0.6667, 3),
        ("repeticion_espaciada", 200, 300, 0.6667, 4),
        ("interleaving", 400, 600, 0.6667, 5),
        ("pomodoro", 300, 600, 0.5, 6),
        ("cornell", 100, 300, 0.3333, 7),
        ("mnemotecnia", 0, 300, 0.0, 8),
    ]
    assert [signal.signal_id for signal in result.signals] == [
        "passive_review_dependence",
        "interleaving_friction",
        "explanation_gap",
        "concept_connection_gap",
        "rapid_forgetting",
    ]


def test_refine_questionnaire_with_tiebreaker_applies_boosts_and_updates_confidence() -> None:
    answers = _empty_answers()
    answers.update(
        {
            "Q01": 3,
            "Q02": 3,
            "Q03": 2,
            "Q04": 2,
            "Q05": 1,
            "Q06": 1,
            "Q07": 0,
            "Q08": 3,
            "Q09": 1,
            "Q10": 1,
        }
    )

    result = refine_questionnaire_with_tiebreaker(
        answers,
        {"TB01": 1, "TB02": 4, "TB03": 4},
    )

    assert result.tiebreaker.activated is True
    assert result.tiebreaker.boosts_by_technique["pomodoro"] == 200
    assert result.tiebreaker.confidence_before == "baja"
    assert result.tiebreaker.confidence_after == "alta"
    assert result.top_techniques == [
        "pomodoro",
        "feynman",
        "repeticion_espaciada",
    ]


def test_refine_questionnaire_with_tiebreaker_caps_uniform_zero_profile_confidence() -> None:
    result = refine_questionnaire_with_tiebreaker(
        _empty_answers(),
        {"TB01": 1, "TB02": 1, "TB03": 1},
    )

    assert result.top_techniques == [
        "mapas_conceptuales",
        "interleaving",
        "pomodoro",
    ]
    assert result.confidence == "media"
    assert result.tiebreaker.confidence_before == "baja"
    assert result.tiebreaker.confidence_after == "media"
    assert result.observations == [
        "El radar principal no marcó una dificultad fuerte; el desempate se usó para priorizar qué técnica conviene fortalecer primero."
    ]


def test_refine_questionnaire_with_tiebreaker_never_escalates_uniform_high_profile_to_alta() -> None:
    answers = _empty_answers()
    for question_id in answers:
        answers[question_id] = 3

    result = refine_questionnaire_with_tiebreaker(
        answers,
        {"TB01": 1, "TB02": 1, "TB03": 3},
    )

    assert result.top_techniques == [
        "mapas_conceptuales",
        "pomodoro",
        "active_recall",
    ]
    assert result.confidence == "media"
    assert result.tiebreaker.confidence_after == "media"
