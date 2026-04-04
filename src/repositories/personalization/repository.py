"""Repositorios para persistencia del perfil de personalizacion academica."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class PersonalizationRepositoryError(Exception):
    """Error base del repositorio de personalizacion."""


@dataclass(frozen=True)
class PersistedPersonalizationProfile:
    """Resultado minimo de persistencia del perfil de personalizacion."""

    personalization_profile_id: int
    version_number: int


class PersonalizationRepository(Protocol):
    """Contrato para guardar resultados finales del cuestionario."""

    def replace_student_personalization(
        self,
        student_id: int,
        schedule_profile_id: int | None,
        questionnaire_version: str,
        scoring_version: str,
        status: str,
        top_techniques: list[str],
        weakness_tags: list[str],
        result_payload: dict[str, object],
        answers: list[Any],
        scores: list[Any],
    ) -> PersistedPersonalizationProfile: ...


class InMemoryPersonalizationRepository:
    """Repositorio en memoria para pruebas del dominio."""

    def __init__(self) -> None:
        self._profiles: dict[int, dict[str, Any]] = {}
        self._history: dict[int, list[dict[str, Any]]] = {}
        self._next_profile_id = 1

    def replace_student_personalization(
        self,
        student_id: int,
        schedule_profile_id: int | None,
        questionnaire_version: str,
        scoring_version: str,
        status: str,
        top_techniques: list[str],
        weakness_tags: list[str],
        result_payload: dict[str, object],
        answers: list[Any],
        scores: list[Any],
    ) -> PersistedPersonalizationProfile:
        current_version = len(self._history.get(student_id, []))
        profile_id = self._next_profile_id
        self._next_profile_id += 1
        payload = {
            "id": profile_id,
            "student_id": student_id,
            "schedule_profile_id": schedule_profile_id,
            "version_number": current_version + 1,
            "questionnaire_version": questionnaire_version,
            "scoring_version": scoring_version,
            "status": status,
            "top_techniques": list(top_techniques),
            "weakness_tags": list(weakness_tags),
            "result_payload": dict(result_payload),
            "answers": [answer.model_dump() for answer in answers],
            "scores": [score.model_dump() for score in scores],
            "is_current": True,
        }
        previous = self._profiles.get(student_id)
        if previous is not None:
            previous["is_current"] = False
            previous["status"] = "superseded"
        self._profiles[student_id] = payload
        self._history.setdefault(student_id, []).append(payload)
        return PersistedPersonalizationProfile(
            personalization_profile_id=profile_id,
            version_number=current_version + 1,
        )


class PostgresPersonalizationRepository:
    """Repositorio PostgreSQL del perfil de personalizacion."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def replace_student_personalization(
        self,
        student_id: int,
        schedule_profile_id: int | None,
        questionnaire_version: str,
        scoring_version: str,
        status: str,
        top_techniques: list[str],
        weakness_tags: list[str],
        result_payload: dict[str, object],
        answers: list[Any],
        scores: list[Any],
    ) -> PersistedPersonalizationProfile:
        with self._connect() as conn:
            current_version_row = conn.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) AS current_version
                FROM study_personalization_profiles
                WHERE student_id = %s
                """,
                (student_id,),
            ).fetchone()
            current_version = _row_value(current_version_row, "current_version", 0)

            conn.execute(
                """
                UPDATE study_personalization_profiles
                SET is_current = FALSE,
                    status = 'superseded',
                    updated_at = NOW()
                WHERE student_id = %s
                  AND is_current = TRUE
                """,
                (student_id,),
            )

            profile_row = conn.execute(
                """
                INSERT INTO study_personalization_profiles (
                    student_id,
                    schedule_profile_id,
                    version_number,
                    questionnaire_version,
                    scoring_version,
                    status,
                    top_techniques,
                    weakness_tags,
                    result_payload,
                    is_current
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, TRUE
                )
                RETURNING id, version_number
                """,
                (
                    student_id,
                    schedule_profile_id,
                    int(current_version) + 1,
                    questionnaire_version,
                    scoring_version,
                    status,
                    json.dumps(top_techniques),
                    json.dumps(weakness_tags),
                    json.dumps(result_payload),
                ),
            ).fetchone()
            profile_id = _row_value(profile_row, "id")
            version_number = _row_value(profile_row, "version_number", int(current_version) + 1)

            for answer in answers:
                conn.execute(
                    """
                    INSERT INTO study_personalization_answers (
                        personalization_profile_id,
                        question_id,
                        option_id,
                        answer_value
                    ) VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (
                        profile_id,
                        answer.question_id,
                        answer.option_id,
                        json.dumps(answer.answer_value),
                    ),
                )

            for score in scores:
                conn.execute(
                    """
                    INSERT INTO study_personalization_scores (
                        personalization_profile_id,
                        technique_id,
                        technique_name,
                        score,
                        max_score,
                        normalized_score,
                        rank,
                        rationale_tags
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        profile_id,
                        score.technique_id,
                        score.technique_name,
                        score.raw_score,
                        score.max_score,
                        score.normalized_score,
                        score.rank,
                        json.dumps(score.rationale_tags),
                    ),
                )

            conn.commit()
        return PersistedPersonalizationProfile(
            personalization_profile_id=profile_id,
            version_number=version_number,
        )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - depende del driver real
            raise PersonalizationRepositoryError(str(exc)) from exc


def build_personalization_repository(
    database_url: str,
) -> PersonalizationRepository:
    """Construye el repositorio PostgreSQL o falla de forma explicita."""

    return PostgresPersonalizationRepository(require_database_url(database_url))


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if key == "id":
        return row[0]
    if key == "version_number":
        return row[1] if len(row) > 1 else default
    if key == "current_version":
        return row[0]
    return default
