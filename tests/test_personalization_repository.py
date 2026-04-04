"""Pruebas de repositorios del modulo de personalizacion."""

from __future__ import annotations

from contextlib import contextmanager

from repositories.personalization.repository import (
    InMemoryPersonalizationRepository,
    PostgresPersonalizationRepository,
)
from services.personalization.models import PersonalizationAnswer, TechniqueScore


def _answer(question_id: str, technique_id: str, value: int) -> PersonalizationAnswer:
    return PersonalizationAnswer(
        question_id=question_id,
        question_text=f"Pregunta {question_id}",
        technique_id=technique_id,
        value=value,
        label="Frecuentemente",
    )


def _tiebreaker_answer(
    question_id: str,
    technique_id: str,
    value: int,
    option_id: str,
) -> PersonalizationAnswer:
    return PersonalizationAnswer(
        question_id=question_id,
        question_text=f"Pregunta {question_id}",
        technique_id=technique_id,
        value=value,
        label=f"Opcion {option_id}",
        answer_stage="tiebreaker",
        option_id=option_id,
    )


def _score(
    technique_id: str,
    name: str,
    raw_score: int,
    rank: int,
    *,
    max_score: int = 3,
    normalized_score: float = 1.0,
) -> TechniqueScore:
    return TechniqueScore(
        technique_id=technique_id,
        technique_name=name,
        priority_order=rank,
        raw_score=raw_score,
        max_score=max_score,
        normalized_score=normalized_score,
        percentage_score=round(normalized_score * 100, 2),
        rank=rank,
        rationale_tags=[technique_id],
    )


def test_in_memory_personalization_repository_versions_profiles() -> None:
    repository = InMemoryPersonalizationRepository()
    first = repository.replace_student_personalization(
        student_id=7,
        schedule_profile_id=11,
        questionnaire_version="v1",
        scoring_version="v1",
        status="completed",
        top_techniques=["pomodoro", "feynman", "active_recall"],
        weakness_tags=["procrastination"],
        result_payload={"status": "completed"},
        answers=[_answer("Q01", "pomodoro", 2)],
        scores=[_score("pomodoro", "Pomodoro", 2, 1)],
    )
    second = repository.replace_student_personalization(
        student_id=7,
        schedule_profile_id=12,
        questionnaire_version="v1",
        scoring_version="v1",
        status="completed",
        top_techniques=["feynman", "pomodoro", "active_recall"],
        weakness_tags=["explanation_gap"],
        result_payload={"status": "completed"},
        answers=[_answer("Q03", "feynman", 3)],
        scores=[_score("feynman", "Feynman", 3, 1)],
    )

    assert first.personalization_profile_id == 1
    assert first.version_number == 1
    assert second.personalization_profile_id == 2
    assert second.version_number == 2
    assert repository._profiles[7]["status"] == "completed"
    assert repository._history[7][0]["status"] == "superseded"
    assert repository._history[7][1]["is_current"] is True


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.commit_called = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if "SELECT COALESCE(MAX(version_number)" in query:
            return _FakeResult({"current_version": 0})
        if "RETURNING id, version_number" in query:
            return _FakeResult({"id": 11, "version_number": 1})
        return _FakeResult(None)

    def commit(self) -> None:
        self.commit_called = True


@contextmanager
def _fake_connect(connection: _FakeConnection):
    yield connection


def test_postgres_personalization_repository_persists_profile_answers_and_scores(monkeypatch) -> None:
    connection = _FakeConnection()
    repository = PostgresPersonalizationRepository("postgresql://ignored")
    monkeypatch.setattr(repository, "_connect", lambda: _fake_connect(connection))

    persisted = repository.replace_student_personalization(
        student_id=5,
        schedule_profile_id=9,
        questionnaire_version="v1",
        scoring_version="v1",
        status="completed",
        top_techniques=["pomodoro", "feynman", "active_recall"],
        weakness_tags=["procrastination"],
        result_payload={"status": "completed"},
        answers=[
            _answer("Q01", "pomodoro", 3),
            _answer("Q02", "pomodoro", 2),
        ],
        scores=[
            _score("pomodoro", "Pomodoro", 5, 1, max_score=6, normalized_score=0.8333),
            _score("feynman", "Feynman", 3, 2, max_score=3, normalized_score=1.0),
        ],
    )

    assert persisted.personalization_profile_id == 11
    assert persisted.version_number == 1
    assert connection.commit_called is True
    assert any(
        "INSERT INTO study_personalization_profiles" in query
        for query, _ in connection.executed
    )
    assert sum(
        1
        for query, _ in connection.executed
        if "INSERT INTO study_personalization_answers" in query
    ) == 2
    assert sum(
        1
        for query, _ in connection.executed
        if "INSERT INTO study_personalization_scores" in query
    ) == 2
    score_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_personalization_scores" in query
    ]
    answer_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_personalization_answers" in query
    ]
    assert score_params == [
        (11, "pomodoro", "Pomodoro", 5, 6, 0.8333, 1, '["pomodoro"]'),
        (11, "feynman", "Feynman", 3, 3, 1.0, 2, '["feynman"]'),
    ]
    assert answer_params == [
        (11, "Q01", None, '{"value": 3, "label": "Frecuentemente", "answer_stage": "radar"}'),
        (11, "Q02", None, '{"value": 2, "label": "Frecuentemente", "answer_stage": "radar"}'),
    ]


def test_postgres_personalization_repository_preserves_tiebreaker_option_id() -> None:
    connection = _FakeConnection()
    repository = PostgresPersonalizationRepository("postgresql://ignored")
    repository._connect = lambda: _fake_connect(connection)

    repository.replace_student_personalization(
        student_id=5,
        schedule_profile_id=9,
        questionnaire_version="v3",
        scoring_version="v3",
        status="completed",
        top_techniques=["pomodoro", "feynman", "active_recall"],
        weakness_tags=["procrastination"],
        result_payload={"status": "completed"},
        answers=[
            _answer("Q01", "pomodoro", 3),
            _tiebreaker_answer("TB01", "pomodoro", 4, "4"),
        ],
        scores=[_score("pomodoro", "Pomodoro", 5, 1, max_score=6, normalized_score=0.8333)],
    )

    answer_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_personalization_answers" in query
    ]
    score_params = [
        params
        for query, params in connection.executed
        if "INSERT INTO study_personalization_scores" in query
    ]

    assert score_params == [
        (11, "pomodoro", "Pomodoro", 5, 6, 0.8333, 1, '["pomodoro"]'),
    ]
    assert answer_params == [
        (11, "Q01", None, '{"value": 3, "label": "Frecuentemente", "answer_stage": "radar"}'),
        (
            11,
            "TB01",
            "4",
            '{"value": 4, "label": "Opcion 4", "answer_stage": "tiebreaker", "option_id": "4"}',
        ),
    ]
