"""Pruebas del motor de scoring y ranking de personalizacion."""

from __future__ import annotations

from agents.support.personalization.scoring import evaluate_questionnaire, rank_techniques


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

    assert pomodoro.raw_score == 5
    assert pomodoro.max_score == 6
    assert pomodoro.normalized_score == 0.8333
    assert pomodoro.percentage_score == 83.33
    assert pomodoro.rank == 1


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


def test_evaluate_questionnaire_sets_low_confidence_on_tie() -> None:
    answers = _empty_answers()
    answers["Q03"] = 3
    answers["Q04"] = 3

    result = evaluate_questionnaire(answers)

    assert result.confidence == "baja"


def test_evaluate_questionnaire_builds_observations_and_weakness_tags() -> None:
    answers = _empty_answers()
    answers["Q01"] = 3
    answers["Q02"] = 3
    answers["Q08"] = 3

    result = evaluate_questionnaire(answers)

    assert result.top_techniques[0] == "pomodoro"
    assert "Dificultades de concentracion o procrastinacion." in result.observations
    assert "rapid_forgetting" in result.weakness_tags

