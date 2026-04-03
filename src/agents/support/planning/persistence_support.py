"""Helpers de integración para persistir snapshots académicos desde nodos."""

from __future__ import annotations

from agents.support.onboarding.repository import RepositoryConfigurationError
from agents.support.planning import update_study_plan_state
from agents.support.priorities.state_helpers import update_priorities_state
from agents.support.reminders_state_helpers import update_reminders_state
from agents.support.state import AgentState
from agents.support.tools.db import (
    get_reminders_service,
    get_study_plan_materialization_service,
    get_study_planning_persistence_service,
)



def persist_planning_snapshot_for_update(state: AgentState, update: dict) -> dict:
    """Persiste el snapshot académico derivado del estado y el update del nodo.

    Mantiene compatibilidad con el flujo actual: si la persistencia falla, no
    altera la UX visible ni el enrutamiento; solo deja trazabilidad en el estado.
    """

    profile = dict(state.get("student_profile", {}))
    student_id = profile.get("persisted_student_id")
    if not student_id:
        return update

    study_profile = dict(update.get("study_profile") or state.get("study_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    priorities_state = update.get("priorities", state.get("priorities", {}))
    subjects = update.get("subjects", state.get("subjects", []))
    study_plan = update.get("study_plan", state.get("study_plan", {}))

    try:
        service = get_study_planning_persistence_service()
    except RepositoryConfigurationError:
        return update

    result = service.persist_snapshot(
        student_id=student_id,
        schedule_profile_id=schedule_state.get("persisted_profile_id"),
        personalization_profile_id=study_profile.get("persisted_profile_id"),
        priorities_state=priorities_state,
        subjects=subjects,
        study_plan=study_plan,
        timezone=state.get("timezone", "America/Bogota"),
    )

    if result.persisted:
        merged = dict(update)
        merged["priorities"] = update_priorities_state(
            priorities_state,
            persisted_profile_id=result.priority_profile_id,
            version_number=result.priority_version_number,
            persistence_error=None,
        )
        merged["study_plan"] = update_study_plan_state(
            study_plan,
            persisted_profile_id=result.study_plan_profile_id,
            version_number=result.study_plan_version_number,
            persistence_error=None,
        )
        return _materialize_instances_for_update(
            state=state,
            update=merged,
            student_id=student_id,
            study_plan_profile_id=result.study_plan_profile_id,
        )

    error_code = result.error_code or "study_planning_persistence_error"
    merged = dict(update)
    merged["priorities"] = update_priorities_state(
        priorities_state,
        persistence_error=error_code,
    )
    merged["study_plan"] = update_study_plan_state(
        study_plan,
        persistence_error=error_code,
    )
    return merged


def _materialize_instances_for_update(
    *,
    state: AgentState,
    update: dict,
    student_id: int,
    study_plan_profile_id: int | None,
) -> dict:
    study_plan = update.get("study_plan", state.get("study_plan", {}))
    try:
        service = get_study_plan_materialization_service()
    except RepositoryConfigurationError:
        return update

    result = service.materialize_plan_instances(
        student_id=student_id,
        study_plan_profile_id=study_plan_profile_id,
        study_plan=study_plan,
        timezone=state.get("timezone", "America/Bogota"),
    )

    merged = dict(update)
    if result.materialized:
        merged["study_plan"] = update_study_plan_state(
            study_plan,
            materialized_instance_count=result.materialized_instance_count,
            superseded_instance_count=result.superseded_instance_count,
            materialized_horizon_days=result.horizon_days,
            materialized_through_date=result.materialized_through_date,
            materialization_error=None,
        )
        return _sync_reminders_for_update(
            state=state,
            update=merged,
            student_id=student_id,
            study_plan_profile_id=study_plan_profile_id,
        )

    merged["study_plan"] = update_study_plan_state(
        study_plan,
        materialization_error=result.error_code or "study_plan_materialization_error",
        materialized_horizon_days=result.horizon_days,
        materialized_through_date=result.materialized_through_date,
    )
    return merged


def _sync_reminders_for_update(
    *,
    state: AgentState,
    update: dict,
    student_id: int,
    study_plan_profile_id: int | None,
) -> dict:
    reminders_state = update.get("reminders", state.get("reminders", {}))
    try:
        service = get_reminders_service()
    except RepositoryConfigurationError:
        return update

    result = service.sync_reminders_for_study_plan(
        student_id=student_id,
        study_plan_profile_id=study_plan_profile_id,
        reminders_state=reminders_state,
        timezone=state.get("timezone", "America/Bogota"),
    )

    merged = dict(update)
    if result.synced:
        merged["reminders"] = update_reminders_state(
            reminders_state,
            persisted_policy_ids=result.persisted_policy_ids,
            last_dispatch_error=None,
            last_sync_at=result.synced_at,
        )
        return merged

    merged["reminders"] = update_reminders_state(
        reminders_state,
        last_dispatch_error=result.error_code or "study_plan_reminders_sync_error",
    )
    return merged
