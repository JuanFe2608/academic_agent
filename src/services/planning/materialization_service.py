"""Servicio para materializar ocurrencias reales del plan semanal."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from schemas.scheduling import Event
from services.scheduling.validation import (
    DAY_ORDER,
    normalize_day,
    normalize_time,
    validate_event,
)

from repositories.planning.instances_repository import (
    InMemoryStudyPlanInstancesRepository,
    MaterializedStudyPlanInstance,
    StudyPlanInstancesRepository,
    StudyPlanInstancesRepositoryError,
    build_study_plan_instances_repository,
)
from .state_helpers import ensure_study_plan_state

DEFAULT_MATERIALIZATION_HORIZON_DAYS = 14


@dataclass(frozen=True)
class MaterializeStudyPlanInstancesResult:
    """Resultado público de materializar instancias del plan."""

    materialized: bool
    materialized_instance_count: int = 0
    superseded_instance_count: int = 0
    horizon_days: int = DEFAULT_MATERIALIZATION_HORIZON_DAYS
    materialized_through_date: str | None = None
    error_code: str | None = None
    detail: str | None = None


class StudyPlanMaterializationService:
    """Orquesta la materialización idempotente del plan semanal."""

    def __init__(
        self,
        repository: StudyPlanInstancesRepository,
        *,
        horizon_days: int = DEFAULT_MATERIALIZATION_HORIZON_DAYS,
    ) -> None:
        self.repository = repository
        self.horizon_days = max(1, int(horizon_days))

    def materialize_plan_instances(
        self,
        *,
        student_id: int | None,
        study_plan_profile_id: int | None,
        study_plan: object,
        timezone: str,
    ) -> MaterializeStudyPlanInstancesResult:
        if not student_id:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para materializar instancias.",
                horizon_days=self.horizon_days,
            )
        if not study_plan_profile_id:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="missing_study_plan_profile_id",
                detail="No encontré el plan persistido para materializar instancias.",
                horizon_days=self.horizon_days,
            )

        normalized_plan = ensure_study_plan_state(study_plan)
        try:
            for event in normalized_plan.plan_events:
                validate_event(event if isinstance(event, Event) else event)
        except ValueError as exc:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="invalid_study_plan",
                detail=str(exc),
                horizon_days=self.horizon_days,
            )

        try:
            zone = ZoneInfo(str(timezone or "America/Bogota"))
        except Exception as exc:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="invalid_timezone",
                detail=str(exc),
                horizon_days=self.horizon_days,
            )

        local_now = datetime.now(zone)
        horizon_start = local_now.date()
        horizon_end = horizon_start + timedelta(days=self.horizon_days - 1)

        if not normalized_plan.plan_events:
            return MaterializeStudyPlanInstancesResult(
                materialized=True,
                materialized_instance_count=0,
                superseded_instance_count=0,
                horizon_days=self.horizon_days,
                materialized_through_date=horizon_end.isoformat(),
            )

        event_keys = [
            (position, str(event.id))
            for position, event in enumerate(normalized_plan.plan_events, start=1)
        ]

        try:
            persisted_event_map = self.repository.get_persisted_plan_event_map(
                study_plan_profile_id=study_plan_profile_id,
                plan_event_keys=event_keys,
            )
        except (StudyPlanInstancesRepositoryError, RepositoryConfigurationError) as exc:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="study_plan_instances_repository_error",
                detail=str(exc),
                horizon_days=self.horizon_days,
                materialized_through_date=horizon_end.isoformat(),
            )

        missing_keys = [key for key in event_keys if key not in persisted_event_map]
        if missing_keys:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="missing_persisted_plan_events",
                detail=(
                    "No pude resolver los eventos persistidos del plan para estas claves: "
                    f"{missing_keys!r}"
                ),
                horizon_days=self.horizon_days,
                materialized_through_date=horizon_end.isoformat(),
            )

        instances: list[MaterializedStudyPlanInstance] = []
        for position, event in enumerate(normalized_plan.plan_events, start=1):
            persisted_event = persisted_event_map[(position, str(event.id))]
            planned_dates = _matching_dates_for_event(
                day_label=str(event.dia),
                horizon_start=horizon_start,
                horizon_end=horizon_end,
            )
            try:
                event_zone = ZoneInfo(str(event.timezone or timezone))
            except Exception as exc:
                return MaterializeStudyPlanInstancesResult(
                    materialized=False,
                    error_code="invalid_event_timezone",
                    detail=str(exc),
                    horizon_days=self.horizon_days,
                    materialized_through_date=horizon_end.isoformat(),
                )
            for planned_date in planned_dates:
                starts_at = _combine_date_and_time(
                    planned_date,
                    str(event.inicio),
                    event_zone,
                )
                ends_at = _combine_date_and_time(
                    planned_date,
                    str(event.fin),
                    event_zone,
                )
                if ends_at <= local_now:
                    continue

                instances.append(
                    MaterializedStudyPlanInstance(
                        study_plan_event_id=persisted_event.event_id,
                        source_instance_key=_source_instance_key(
                            study_plan_profile_id=study_plan_profile_id,
                            position=position,
                            source_event_id=str(event.id),
                            planned_date=planned_date,
                        ),
                        planned_date=planned_date,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        timezone=str(event_zone),
                        instance_payload={
                            "study_plan_profile_id": study_plan_profile_id,
                            "study_plan_event_id": persisted_event.event_id,
                            "position": position,
                            "planned_date": planned_date.isoformat(),
                            "source_event_id": str(event.id),
                            "event": event.model_dump(mode="python"),
                        },
                    )
                )

        try:
            sync_result = self.repository.sync_materialized_instances(
                student_id=student_id,
                study_plan_profile_id=study_plan_profile_id,
                active_from=local_now,
                instances=instances,
            )
        except (StudyPlanInstancesRepositoryError, RepositoryConfigurationError) as exc:
            return MaterializeStudyPlanInstancesResult(
                materialized=False,
                error_code="study_plan_instances_sync_error",
                detail=str(exc),
                horizon_days=self.horizon_days,
                materialized_through_date=horizon_end.isoformat(),
            )

        return MaterializeStudyPlanInstancesResult(
            materialized=True,
            materialized_instance_count=sync_result.materialized_instance_count,
            superseded_instance_count=sync_result.superseded_instance_count,
            horizon_days=self.horizon_days,
            materialized_through_date=horizon_end.isoformat(),
        )


    def find_instance_for_session_and_date(
        self,
        *,
        student_id: int,
        study_plan_profile_id: int,
        source_event_id: str,
        target_date: date,
    ) -> dict[str, Any] | None:
        """Busca la instancia materializada para un evento en una fecha ±1 día."""
        try:
            results = self.repository.find_instances_by_event_and_date_range(
                student_id=student_id,
                study_plan_profile_id=study_plan_profile_id,
                source_event_id=source_event_id,
                planned_date_from=target_date - timedelta(days=1),
                planned_date_to=target_date + timedelta(days=1),
            )
            return results[0] if results else None
        except (StudyPlanInstancesRepositoryError, RepositoryConfigurationError):
            return None

    def update_instance_schedule_manually(
        self,
        *,
        source_instance_key: str,
        student_id: int,
        new_starts_at: datetime,
        new_ends_at: datetime,
    ) -> bool:
        """Actualiza horario de una instancia y la marca como movida manualmente."""
        try:
            return self.repository.update_instance_schedule(
                source_instance_key=source_instance_key,
                student_id=student_id,
                new_starts_at=new_starts_at,
                new_ends_at=new_ends_at,
            )
        except (StudyPlanInstancesRepositoryError, RepositoryConfigurationError):
            return False

    def cancel_instance(
        self,
        *,
        source_instance_key: str,
        student_id: int,
    ) -> bool:
        """Marca una instancia como eliminada (aceptar borrado del estudiante en Outlook)."""
        try:
            return self.repository.cancel_instance(
                source_instance_key=source_instance_key,
                student_id=student_id,
            )
        except (StudyPlanInstancesRepositoryError, RepositoryConfigurationError):
            return False


def build_study_plan_materialization_service() -> StudyPlanMaterializationService:
    """Construye el servicio de materialización según el entorno."""

    horizon_days = _horizon_days_from_env()
    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_PLAN_INSTANCES_REPO", "").strip() == "1":
        repository = InMemoryStudyPlanInstancesRepository()
    else:
        repository = build_study_plan_instances_repository(database_url_from_env())
    return StudyPlanMaterializationService(
        repository=repository,
        horizon_days=horizon_days,
    )


def _horizon_days_from_env() -> int:
    raw_value = os.getenv("ACADEMIC_AGENT_STUDY_PLAN_MATERIALIZATION_DAYS", "").strip()
    if not raw_value:
        return DEFAULT_MATERIALIZATION_HORIZON_DAYS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_MATERIALIZATION_HORIZON_DAYS


def _matching_dates_for_event(
    *,
    day_label: str,
    horizon_start: date,
    horizon_end: date,
) -> list[date]:
    normalized_label = normalize_day(day_label)
    target_weekday = DAY_ORDER.index(normalized_label)
    current = horizon_start
    matches: list[date] = []
    while current <= horizon_end:
        if current.weekday() == target_weekday:
            matches.append(current)
        current += timedelta(days=1)
    return matches


def _combine_date_and_time(planned_date: date, hhmm: str, zone: ZoneInfo) -> datetime:
    normalized = normalize_time(hhmm)
    hours, minutes = normalized.split(":", maxsplit=1)
    parsed = time(hour=int(hours), minute=int(minutes))
    return datetime.combine(planned_date, parsed, tzinfo=zone)


def _source_instance_key(
    *,
    study_plan_profile_id: int,
    position: int,
    source_event_id: str,
    planned_date: date,
) -> str:
    return (
        f"study-plan:{study_plan_profile_id}:position:{position}:"
        f"event:{source_event_id}:date:{planned_date.isoformat()}"
    )
