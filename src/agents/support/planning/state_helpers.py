"""Helpers tipados para el subestado `study_plan` y sus dependencias.

Estos helpers siguen el mismo patron usado en scheduling: permiten trabajar
con modelos Pydantic dentro de los servicios, pero devuelven payloads simples
compatibles con el contrato actual del grafo.
"""

from __future__ import annotations

from agents.support.state import Constraints, StudyPlanState, StudyProfile


def ensure_constraints(raw_state: Constraints | dict | None) -> Constraints:
    """Coacciona las restricciones del agente a su modelo canónico."""

    if isinstance(raw_state, Constraints):
        return raw_state.model_copy(deep=True)
    return Constraints(**dict(raw_state or {}))


def ensure_study_profile(raw_state: StudyProfile | dict | None) -> StudyProfile:
    """Coacciona el perfil de estudio a un modelo estable para planificación."""

    if isinstance(raw_state, StudyProfile):
        return raw_state.model_copy(deep=True)
    return StudyProfile(**dict(raw_state or {}))


def ensure_study_plan_state(
    raw_state: StudyPlanState | dict | None,
) -> StudyPlanState:
    """Coacciona el subestado `study_plan` a su modelo canónico."""

    if isinstance(raw_state, StudyPlanState):
        return raw_state.model_copy(deep=True)
    return StudyPlanState(**dict(raw_state or {}))


def study_plan_state_to_update(plan_state: StudyPlanState | dict | None) -> dict[str, object]:
    """Serializa `StudyPlanState` preservando eventos como modelos."""

    normalized = ensure_study_plan_state(plan_state)
    return {
        "plan_events": list(normalized.plan_events),
        "rules": dict(normalized.rules),
        "persisted_profile_id": normalized.persisted_profile_id,
        "version_number": normalized.version_number,
        "persistence_error": normalized.persistence_error,
        "materialized_instance_count": normalized.materialized_instance_count,
        "superseded_instance_count": normalized.superseded_instance_count,
        "materialized_horizon_days": normalized.materialized_horizon_days,
        "materialized_through_date": normalized.materialized_through_date,
        "materialization_error": normalized.materialization_error,
    }


def update_study_plan_state(
    raw_state: StudyPlanState | dict | None,
    **changes: object,
) -> dict[str, object]:
    """Aplica cambios al subestado `study_plan` sin romper su contrato actual."""

    normalized = ensure_study_plan_state(raw_state)
    updated = normalized.model_copy(update=changes)
    return study_plan_state_to_update(updated)
