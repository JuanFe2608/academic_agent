"""Servicio de aplicación para registrar tracking real de sesiones."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from repositories.planning.instances_repository import StudyPlanInstancesRepository
from repositories.planning.tracking_repository import (
    InMemoryStudySessionTrackingRepository,
    RecordedStudySessionMutation,
    StudyPlanInstanceSnapshot,
    StudySessionMutation,
    StudySessionTrackingRepository,
    StudySessionTrackingRepositoryError,
    build_study_session_tracking_repository,
)
from .tracking_state_helpers import (
    ensure_feedback_content,
    normalize_actor_type,
    normalize_completion_pct,
    normalize_notes,
    normalize_optional_score,
    normalize_payload,
    normalize_timestamp,
)


@dataclass(frozen=True)
class TrackStudySessionResult:
    """Resultado público de un evento de tracking."""

    tracked: bool
    instance_id: int | None = None
    previous_status: str | None = None
    resulting_status: str | None = None
    checkin_id: int | None = None
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MarkMissedStudySessionsResult:
    """Resultado agregado del proceso de marcar sesiones perdidas."""

    processed: bool
    marked_count: int = 0
    instance_ids: list[int] = field(default_factory=list)
    error_code: str | None = None
    detail: str | None = None


class StudySessionTrackingService:
    """Orquesta cambios sobre instancias y la bitácora de checkins."""

    def __init__(self, repository: StudySessionTrackingRepository) -> None:
        self.repository = repository

    def start_session(
        self,
        *,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
        actor_type: object = "student",
        reported_at: object = None,
        actual_start_at: object = None,
        notes: object = None,
        checkin_payload: object = None,
    ) -> TrackStudySessionResult:
        instance, error = self._get_instance(student_id, study_plan_event_instance_id)
        if error is not None:
            return error
        if instance.status == "in_progress":
            return _invalid_transition(
                instance,
                error_code="already_in_progress",
                detail="La sesión ya estaba marcada como in_progress.",
            )
        if instance.status != "scheduled":
            return _invalid_transition(
                instance,
                error_code="invalid_status_transition",
                detail=f"No puedes iniciar una sesión con status={instance.status!r}.",
            )

        try:
            actor = normalize_actor_type(actor_type)
            now_value = _now_for_instance(instance)
            reported = normalize_timestamp(reported_at, default=now_value)
            actual_start = normalize_timestamp(actual_start_at, default=reported)
            mutation = StudySessionMutation(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
                checkin_type="start",
                actor_type=actor,
                reported_at=reported,
                actual_start_at=actual_start,
                actual_end_at=None,
                completion_pct=None,
                comprehension_score=None,
                energy_score=None,
                notes=normalize_notes(notes),
                checkin_payload=normalize_payload(checkin_payload),
                next_status="in_progress",
                instance_completion_pct=None,
                instance_completed_at=None,
            )
        except ValueError as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=instance.id,
                previous_status=instance.status,
                resulting_status=instance.status,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        return self._apply_mutation(mutation, instance)

    def complete_session(
        self,
        *,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
        actor_type: object = "student",
        reported_at: object = None,
        actual_start_at: object = None,
        actual_end_at: object = None,
        completion_pct: object = 100,
        comprehension_score: object = None,
        energy_score: object = None,
        notes: object = None,
        checkin_payload: object = None,
    ) -> TrackStudySessionResult:
        instance, error = self._get_instance(student_id, study_plan_event_instance_id)
        if error is not None:
            return error
        if instance.status == "completed":
            return _invalid_transition(
                instance,
                error_code="already_completed",
                detail="La sesión ya estaba completada.",
            )
        if instance.status not in {"scheduled", "in_progress"}:
            return _invalid_transition(
                instance,
                error_code="invalid_status_transition",
                detail=f"No puedes completar una sesión con status={instance.status!r}.",
            )

        try:
            actor = normalize_actor_type(actor_type)
            now_value = _now_for_instance(instance)
            reported = normalize_timestamp(reported_at, default=now_value)
            actual_end = normalize_timestamp(actual_end_at, default=reported)
            actual_start = normalize_timestamp(actual_start_at, default=instance.starts_at)
            if actual_end is not None and actual_start is not None and actual_end < actual_start:
                raise ValueError("actual_end_at no puede ser menor que actual_start_at")
            normalized_completion_pct = normalize_completion_pct(completion_pct, default=100)
            mutation = StudySessionMutation(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
                checkin_type="complete",
                actor_type=actor,
                reported_at=reported,
                actual_start_at=actual_start,
                actual_end_at=actual_end,
                completion_pct=normalized_completion_pct,
                comprehension_score=normalize_optional_score(
                    "comprehension_score",
                    comprehension_score,
                ),
                energy_score=normalize_optional_score("energy_score", energy_score),
                notes=normalize_notes(notes),
                checkin_payload=normalize_payload(checkin_payload),
                next_status="completed",
                instance_completion_pct=normalized_completion_pct,
                instance_completed_at=actual_end,
            )
        except ValueError as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=instance.id,
                previous_status=instance.status,
                resulting_status=instance.status,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        return self._apply_mutation(mutation, instance)

    def skip_session(
        self,
        *,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
        actor_type: object = "student",
        reported_at: object = None,
        actual_start_at: object = None,
        actual_end_at: object = None,
        notes: object = None,
        checkin_payload: object = None,
    ) -> TrackStudySessionResult:
        instance, error = self._get_instance(student_id, study_plan_event_instance_id)
        if error is not None:
            return error
        if instance.status == "skipped":
            return _invalid_transition(
                instance,
                error_code="already_skipped",
                detail="La sesión ya estaba marcada como skipped.",
            )
        if instance.status not in {"scheduled", "in_progress"}:
            return _invalid_transition(
                instance,
                error_code="invalid_status_transition",
                detail=f"No puedes omitir una sesión con status={instance.status!r}.",
            )

        try:
            actor = normalize_actor_type(actor_type)
            now_value = _now_for_instance(instance)
            reported = normalize_timestamp(reported_at, default=now_value)
            actual_start = normalize_timestamp(actual_start_at, default=None)
            actual_end = normalize_timestamp(actual_end_at, default=None)
            if actual_end is not None and actual_start is None:
                actual_start = instance.starts_at
            if actual_end is not None and actual_start is not None and actual_end < actual_start:
                raise ValueError("actual_end_at no puede ser menor que actual_start_at")
            mutation = StudySessionMutation(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
                checkin_type="skip",
                actor_type=actor,
                reported_at=reported,
                actual_start_at=actual_start,
                actual_end_at=actual_end,
                completion_pct=0,
                comprehension_score=None,
                energy_score=None,
                notes=normalize_notes(notes),
                checkin_payload=normalize_payload(checkin_payload),
                next_status="skipped",
                instance_completion_pct=0,
                instance_completed_at=None,
            )
        except ValueError as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=instance.id,
                previous_status=instance.status,
                resulting_status=instance.status,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        return self._apply_mutation(mutation, instance)

    def mark_session_missed(
        self,
        *,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
        actor_type: object = "system",
        reported_at: object = None,
        notes: object = None,
        checkin_payload: object = None,
    ) -> TrackStudySessionResult:
        instance, error = self._get_instance(student_id, study_plan_event_instance_id)
        if error is not None:
            return error
        if instance.status == "missed":
            return _invalid_transition(
                instance,
                error_code="already_missed",
                detail="La sesión ya estaba marcada como missed.",
            )
        if instance.status not in {"scheduled", "in_progress"}:
            return _invalid_transition(
                instance,
                error_code="invalid_status_transition",
                detail=f"No puedes marcar como perdida una sesión con status={instance.status!r}.",
            )

        try:
            actor = normalize_actor_type(actor_type, default="system")
            now_value = _now_for_instance(instance)
            reported = normalize_timestamp(reported_at, default=now_value)
            payload = normalize_payload(checkin_payload)
            payload.setdefault("previous_status", instance.status)
            mutation = StudySessionMutation(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
                checkin_type="missed_confirmation",
                actor_type=actor,
                reported_at=reported,
                actual_start_at=None,
                actual_end_at=None,
                completion_pct=0,
                comprehension_score=None,
                energy_score=None,
                notes=normalize_notes(notes),
                checkin_payload=payload,
                next_status="missed",
                instance_completion_pct=0,
                instance_completed_at=None,
            )
        except ValueError as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=instance.id,
                previous_status=instance.status,
                resulting_status=instance.status,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        return self._apply_mutation(mutation, instance)

    def record_feedback(
        self,
        *,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
        actor_type: object = "student",
        reported_at: object = None,
        completion_pct: object = None,
        comprehension_score: object = None,
        energy_score: object = None,
        notes: object = None,
        checkin_payload: object = None,
    ) -> TrackStudySessionResult:
        instance, error = self._get_instance(student_id, study_plan_event_instance_id)
        if error is not None:
            return error

        try:
            actor = normalize_actor_type(actor_type)
            now_value = _now_for_instance(instance)
            reported = normalize_timestamp(reported_at, default=now_value)
            payload = normalize_payload(checkin_payload)
            normalized_notes = normalize_notes(notes)
            normalized_completion_pct = normalize_completion_pct(completion_pct, default=None)
            normalized_comprehension = normalize_optional_score(
                "comprehension_score",
                comprehension_score,
            )
            normalized_energy = normalize_optional_score("energy_score", energy_score)
            ensure_feedback_content(
                notes=normalized_notes,
                completion_pct=normalized_completion_pct,
                comprehension_score=normalized_comprehension,
                energy_score=normalized_energy,
                payload=payload,
            )
            mutation = StudySessionMutation(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
                checkin_type="feedback",
                actor_type=actor,
                reported_at=reported,
                actual_start_at=None,
                actual_end_at=None,
                completion_pct=normalized_completion_pct,
                comprehension_score=normalized_comprehension,
                energy_score=normalized_energy,
                notes=normalized_notes,
                checkin_payload=payload,
            )
        except ValueError as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=instance.id,
                previous_status=instance.status,
                resulting_status=instance.status,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        return self._apply_mutation(mutation, instance)

    def mark_due_sessions_missed(
        self,
        *,
        student_id: int | None = None,
        as_of: object = None,
        grace_minutes: int = 30,
        limit: int = 100,
        actor_type: object = "system",
    ) -> MarkMissedStudySessionsResult:
        try:
            actor = normalize_actor_type(actor_type, default="system")
            effective_as_of = normalize_timestamp(
                as_of,
                default=datetime.now(ZoneInfo("UTC")),
            )
            recorded = self.repository.mark_due_sessions_missed(
                student_id=student_id,
                as_of=effective_as_of,
                grace_minutes=max(0, int(grace_minutes)),
                limit=max(1, int(limit)),
                actor_type=actor,
            )
        except ValueError as exc:
            return MarkMissedStudySessionsResult(
                processed=False,
                error_code="invalid_tracking_payload",
                detail=str(exc),
            )
        except (StudySessionTrackingRepositoryError, RepositoryConfigurationError) as exc:
            return MarkMissedStudySessionsResult(
                processed=False,
                error_code="study_session_tracking_error",
                detail=str(exc),
            )

        return MarkMissedStudySessionsResult(
            processed=True,
            marked_count=len(recorded),
            instance_ids=[item.instance.id for item in recorded],
        )

    def _get_instance(
        self,
        student_id: int | None,
        study_plan_event_instance_id: int | None,
    ) -> tuple[StudyPlanInstanceSnapshot | None, TrackStudySessionResult | None]:
        if not student_id:
            return None, TrackStudySessionResult(
                tracked=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para tracking.",
            )
        if not study_plan_event_instance_id:
            return None, TrackStudySessionResult(
                tracked=False,
                error_code="missing_study_plan_event_instance_id",
                detail="No encontré la instancia del plan para tracking.",
            )
        try:
            instance = self.repository.get_instance(
                student_id=int(student_id),
                study_plan_event_instance_id=int(study_plan_event_instance_id),
            )
        except (StudySessionTrackingRepositoryError, RepositoryConfigurationError) as exc:
            return None, TrackStudySessionResult(
                tracked=False,
                instance_id=int(study_plan_event_instance_id),
                error_code="study_session_tracking_error",
                detail=str(exc),
            )
        if instance is None:
            return None, TrackStudySessionResult(
                tracked=False,
                instance_id=int(study_plan_event_instance_id),
                error_code="study_plan_event_instance_not_found",
                detail="No encontré la instancia solicitada.",
            )
        return instance, None

    def _apply_mutation(
        self,
        mutation: StudySessionMutation,
        previous_instance: StudyPlanInstanceSnapshot,
    ) -> TrackStudySessionResult:
        try:
            recorded = self.repository.apply_session_mutation(mutation=mutation)
        except (StudySessionTrackingRepositoryError, RepositoryConfigurationError) as exc:
            return TrackStudySessionResult(
                tracked=False,
                instance_id=previous_instance.id,
                previous_status=previous_instance.status,
                resulting_status=previous_instance.status,
                error_code="study_session_tracking_error",
                detail=str(exc),
            )
        return _success_result(recorded)


def build_study_session_tracking_service(
    *,
    instances_repository: StudyPlanInstancesRepository | Any | None = None,
) -> StudySessionTrackingService:
    """Construye el servicio de tracking según el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_SESSION_TRACKING_REPO", "").strip() == "1":
        repository = InMemoryStudySessionTrackingRepository(
            instances_repository=instances_repository
        )
    else:
        repository = build_study_session_tracking_repository(database_url_from_env())
    return StudySessionTrackingService(repository=repository)


def _success_result(recorded: RecordedStudySessionMutation) -> TrackStudySessionResult:
    return TrackStudySessionResult(
        tracked=True,
        instance_id=recorded.instance.id,
        previous_status=recorded.previous_status,
        resulting_status=recorded.instance.status,
        checkin_id=recorded.checkin_id,
    )


def _invalid_transition(
    instance: StudyPlanInstanceSnapshot,
    *,
    error_code: str,
    detail: str,
) -> TrackStudySessionResult:
    return TrackStudySessionResult(
        tracked=False,
        instance_id=instance.id,
        previous_status=instance.status,
        resulting_status=instance.status,
        error_code=error_code,
        detail=detail,
    )


def _now_for_instance(instance: StudyPlanInstanceSnapshot) -> datetime:
    try:
        return datetime.now(ZoneInfo(instance.timezone))
    except Exception:
        return datetime.now(ZoneInfo("UTC"))
