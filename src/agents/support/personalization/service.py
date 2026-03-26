"""Servicio de scoring y persistencia del modulo de personalizacion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agents.support.onboarding.repository import RepositoryConfigurationError
from agents.support.personalization.config import (
    PersonalizationConfig,
    load_personalization_config,
)
from agents.support.personalization.models import (
    PersonalizationAnswer,
    PersonalizationResult,
    TechniqueScore,
)
from agents.support.personalization.parser import likert_label
from agents.support.personalization.questionnaire import get_questions
from agents.support.personalization.repository import (
    InMemoryPersonalizationRepository,
    PersistedPersonalizationProfile,
    PersonalizationRepository,
    PersonalizationRepositoryError,
    build_personalization_repository,
)
from agents.support.personalization.scoring import evaluate_questionnaire
from agents.support.tools.db_config import database_url_from_env


@dataclass(frozen=True)
class PersistStudyProfileResult:
    """Resultado de persistir la caracterizacion del estudiante."""

    persisted: bool
    personalization_profile_id: int | None = None
    version_number: int | None = None
    error_code: str | None = None
    detail: str | None = None


class PersonalizationService:
    """Orquesta evaluacion y persistencia del cuestionario."""

    def __init__(
        self,
        config: PersonalizationConfig,
        repository: PersonalizationRepository,
    ) -> None:
        self.config = config
        self.repository = repository

    def evaluate_answers(self, answers: dict[str, int]) -> PersonalizationResult:
        """Evalua el cuestionario y retorna el resultado estructurado."""

        return evaluate_questionnaire(
            answers,
            high_score_threshold=self.config.high_score_threshold,
        )

    def persist_study_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        study_profile: Any,
    ) -> PersistStudyProfileResult:
        """Persiste el resultado final del cuestionario."""

        if not student_id:
            return PersistStudyProfileResult(
                persisted=False,
                error_code="missing_student_id",
                detail="No encontre el estudiante persistido para asociar la caracterizacion.",
            )

        try:
            result = _coerce_personalization_result(study_profile)
        except ValueError as exc:
            return PersistStudyProfileResult(
                persisted=False,
                error_code="incomplete_study_profile",
                detail=str(exc),
            )

        answers = _build_answer_records(result)
        scores = [_coerce_score(score) for score in result.scores]

        try:
            record = self.repository.replace_student_personalization(
                student_id=student_id,
                schedule_profile_id=schedule_profile_id,
                questionnaire_version=result.questionnaire_version,
                scoring_version=result.scoring_version,
                status=result.status,
                top_techniques=list(result.top_techniques),
                weakness_tags=list(result.weakness_tags),
                result_payload=result.model_dump(mode="json"),
                answers=answers,
                scores=scores,
            )
        except (PersonalizationRepositoryError, RepositoryConfigurationError) as exc:
            error_code, detail = _describe_persistence_exception(exc)
            return PersistStudyProfileResult(
                persisted=False,
                error_code=error_code,
                detail=detail,
            )

        return PersistStudyProfileResult(
            persisted=True,
            personalization_profile_id=record.personalization_profile_id,
            version_number=record.version_number,
        )


def build_personalization_service() -> PersonalizationService:
    """Construye el servicio de personalizacion segun el entorno."""

    config = load_personalization_config()
    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_PERSONALIZATION_REPO", "").strip() == "1":
        repository = InMemoryPersonalizationRepository()
    else:
        repository = build_personalization_repository(database_url_from_env())
    return PersonalizationService(config=config, repository=repository)


def _coerce_personalization_result(study_profile: Any) -> PersonalizationResult:
    data = _study_profile_dict(study_profile)
    if str(data.get("status") or "") != "completed":
        raise ValueError("El cuestionario de personalizacion aun no esta completo.")

    payload = {
        "questionnaire_version": data.get("questionnaire_version"),
        "scoring_version": data.get("scoring_version"),
        "status": data.get("status"),
        "answers": dict(data.get("answers") or {}),
        "weakness_tags": list(data.get("weakness_tags") or []),
        "scores": list(data.get("scores") or []),
        "top_techniques": list(data.get("top_techniques") or []),
        "confidence": data.get("confidence"),
        "observations": list(data.get("observations") or []),
        "method": data.get("method"),
        "how_to": data.get("how_to"),
    }
    return PersonalizationResult(**payload)


def _build_answer_records(result: PersonalizationResult) -> list[PersonalizationAnswer]:
    records: list[PersonalizationAnswer] = []
    for question in get_questions():
        value = result.answers.get(question.question_id)
        if value is None:
            raise ValueError(f"Falta la respuesta de {question.question_id}.")
        records.append(
            PersonalizationAnswer(
                question_id=question.question_id,
                question_text=question.prompt,
                technique_id=question.technique_id,
                value=int(value),
                label=likert_label(int(value)),
            )
        )
    return records


def _coerce_score(score: TechniqueScore | dict[str, object]) -> TechniqueScore:
    if isinstance(score, TechniqueScore):
        return score
    return TechniqueScore(**score)


def _study_profile_dict(study_profile: Any) -> dict[str, Any]:
    if isinstance(study_profile, dict):
        return study_profile
    if hasattr(study_profile, "model_dump"):
        return dict(study_profile.model_dump())
    if hasattr(study_profile, "dict"):
        return dict(study_profile.dict())
    return dict(study_profile or {})


def _describe_persistence_exception(
    exc: Exception,
) -> tuple[str, str]:
    detail = str(exc).strip() or "desconocido"
    normalized = detail.lower()
    if "permission denied for table study_personalization_" in normalized:
        return (
            "personalization_permission_denied",
            "El usuario de la app no tiene permisos sobre las tablas de personalizacion. "
            "Aplica la migracion `migrations/0005_grant_personalization_permissions.sql` "
            "con un rol administrador y reinicia el servicio. "
            f"PostgreSQL reporto: {detail}",
        )
    if "permission denied for sequence study_personalization_" in normalized:
        return (
            "personalization_permission_denied",
            "El usuario de la app no tiene permisos sobre las secuencias de personalizacion. "
            "Aplica la migracion `migrations/0005_grant_personalization_permissions.sql` "
            "con un rol administrador y reinicia el servicio. "
            f"PostgreSQL reporto: {detail}",
        )
    return "personalization_persistence_error", detail
