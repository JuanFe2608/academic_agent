"""Pruebas del servicio de personalizacion academica."""

from __future__ import annotations

from agents.support.personalization.config import PersonalizationConfig
from agents.support.personalization.repository import (
    InMemoryPersonalizationRepository,
    PersonalizationRepositoryError,
)
from agents.support.personalization.service import PersonalizationService


def _completed_study_profile() -> dict[str, object]:
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )
    result = service.evaluate_answers(
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
    return result.model_dump(mode="json")


def test_personalization_service_persists_completed_profile() -> None:
    repository = InMemoryPersonalizationRepository()
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=repository,
    )
    study_profile = _completed_study_profile()

    persist_result = service.persist_study_profile(
        student_id=21,
        schedule_profile_id=5,
        study_profile=study_profile,
    )

    assert persist_result.persisted is True
    assert persist_result.personalization_profile_id == 1
    assert persist_result.version_number == 1
    assert repository._profiles[21]["scores"][0]["raw_score"] == 600
    assert repository._profiles[21]["scores"][0]["max_score"] == 600
    assert repository._profiles[21]["scores"][0]["normalized_score"] == 1.0


def test_personalization_service_persists_tiebreaker_answers_in_same_profile() -> None:
    repository = InMemoryPersonalizationRepository()
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=repository,
    )
    study_profile = service.refine_with_tiebreaker(
        answers={
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
        },
        tiebreaker_answers={"TB01": 1, "TB02": 4, "TB03": 4},
    ).model_dump(mode="json")

    persist_result = service.persist_study_profile(
        student_id=21,
        schedule_profile_id=5,
        study_profile=study_profile,
    )

    assert persist_result.persisted is True
    saved_answers = repository._profiles[21]["answers"]
    assert len(saved_answers) == 13
    assert any(
        answer["answer_stage"] == "tiebreaker" and answer["question_id"] == "TB01"
        for answer in saved_answers
    )
    assert repository._profiles[21]["result_payload"]["tiebreaker"]["assessment"][
        "activation_reasons"
    ] == ["low_gap_between_top_scores"]


def test_personalization_service_rejects_incomplete_profile() -> None:
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )

    persist_result = service.persist_study_profile(
        student_id=21,
        schedule_profile_id=5,
        study_profile={"status": "collecting", "answers": {"Q01": 1}},
    )

    assert persist_result.persisted is False
    assert persist_result.error_code == "incomplete_study_profile"


def test_personalization_service_requires_student_id() -> None:
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=InMemoryPersonalizationRepository(),
    )

    persist_result = service.persist_study_profile(
        student_id=None,
        schedule_profile_id=5,
        study_profile=_completed_study_profile(),
    )

    assert persist_result.persisted is False
    assert persist_result.error_code == "missing_student_id"


class _PermissionDeniedRepository:
    def replace_student_personalization(self, **_kwargs):
        raise PersonalizationRepositoryError(
            "permission denied for table study_personalization_profiles"
        )


def test_personalization_service_maps_permission_denied_to_actionable_error() -> None:
    service = PersonalizationService(
        config=PersonalizationConfig(enabled=True),
        repository=_PermissionDeniedRepository(),
    )

    persist_result = service.persist_study_profile(
        student_id=21,
        schedule_profile_id=5,
        study_profile=_completed_study_profile(),
    )

    assert persist_result.persisted is False
    assert persist_result.error_code == "personalization_permission_denied"
    assert "migrations/0005_grant_personalization_permissions.sql" in str(
        persist_result.detail
    )
