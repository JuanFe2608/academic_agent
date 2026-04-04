"""Servicio de scoring y persistencia del modulo de personalizacion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from .config import (
    PersonalizationConfig,
    load_personalization_config,
)
from .models import (
    PersonalizationAnswer,
    PersonalizationResult,
    TechniqueScore,
)
from .parser import likert_label
from .questionnaire import (
    get_questions,
    get_tiebreaker_question_by_id,
    get_tiebreaker_questions,
)
from repositories.personalization.repository import (
    InMemoryPersonalizationRepository,
    PersonalizationRepository,
    PersonalizationRepositoryError,
    build_personalization_repository,
)
from .scoring import (
    evaluate_questionnaire,
    refine_questionnaire_with_tiebreaker,
)


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
        """Evalua el Radar principal y detecta si requiere desempate."""

        return evaluate_questionnaire(
            answers,
            high_score_threshold=self.config.high_score_threshold,
        )

    def refine_with_tiebreaker(
        self,
        *,
        answers: dict[str, int],
        tiebreaker_answers: dict[str, int],
    ) -> PersonalizationResult:
        """Aplica el desempate y retorna el ranking refinado final."""

        return refine_questionnaire_with_tiebreaker(
            answers,
            tiebreaker_answers,
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
        "signals": list(data.get("signals") or []),
        "observations": list(data.get("observations") or []),
        "tiebreaker": dict(data.get("tiebreaker") or {}),
        "completed_at": data.get("completed_at"),
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
    records.extend(_build_tiebreaker_answer_records(result))
    return records


def _build_tiebreaker_answer_records(
    result: PersonalizationResult,
) -> list[PersonalizationAnswer]:
    if not result.tiebreaker.answers:
        return []

    details_by_id = {
        detail.question_id: detail for detail in result.tiebreaker.answer_details
    }
    records: list[PersonalizationAnswer] = []
    for question in get_tiebreaker_questions():
        value = result.tiebreaker.answers.get(question.question_id)
        if value is None:
            continue

        detail = details_by_id.get(question.question_id)
        if detail is None:
            # Fallback defensivo si el payload llega incompleto.
            detail = _fallback_tiebreaker_detail(question.question_id, int(value))

        favored_techniques = list(detail.favored_techniques)
        primary_technique = favored_techniques[0] if favored_techniques else "tiebreaker"
        records.append(
            PersonalizationAnswer(
                question_id=question.question_id,
                question_text=detail.prompt,
                technique_id=primary_technique,
                value=int(detail.selected_option_id),
                label=detail.selected_option_label,
                answer_stage="tiebreaker",
                option_id=str(detail.selected_option_id),
                favored_techniques=favored_techniques,
                metadata={
                    "question_title": detail.question_title,
                    "boosts": {
                        boost.technique_id: int(boost.boost)
                        for boost in detail.applied_boosts
                    },
                    "answered_at": detail.answered_at,
                },
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


def _fallback_tiebreaker_detail(question_id: str, selected_option_id: int):
    question = get_tiebreaker_question_by_id(question_id)
    option = next(
        option
        for option in question.options
        if int(option.option_id) == int(selected_option_id)
    )
    from .models import TiebreakerAnswer

    return TiebreakerAnswer(
        question_id=question.question_id,
        question_title=question.challenge_title,
        prompt=question.prompt,
        selected_option_id=int(option.option_id),
        selected_option_label=option.label,
        favored_techniques=[boost.technique_id for boost in option.technique_boosts],
        applied_boosts=list(option.technique_boosts),
    )


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
