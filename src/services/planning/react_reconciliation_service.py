"""Reconciliacion deterministica tras tools del agente ReAct.

El agente conserva autonomia conversacional, pero las invariantes de negocio
se aplican aqui: solo fuentes academicas generan materias y sesiones de estudio.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from schemas.planning import StudyPlanState
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block

from .academic_activity_service import coerce_academic_activities
from .state_helpers import ensure_study_plan_state, study_plan_state_to_update
from .study_plan_sync_service import sync_subjects_and_study_plan

_RECONCILED_FIELDS: frozenset[str] = frozenset({
    "schedule",
    "subjects",
    "academic_activities",
    "study_plan",
    "constraints",
})


def reconcile_react_tool_updates(state: Any, tool_updates: dict[str, Any]) -> dict[str, Any]:
    """Ajusta updates de tools ReAct para mantener plan y materias coherentes.

    La reconciliacion se ejecuta despues del ciclo ReAct, cuando todas las tools
    ya devolvieron sus cambios. Esto evita que una tool posterior use el estado
    viejo capturado al inicio del turno.
    """

    if not tool_updates or not _needs_reconciliation(tool_updates):
        return tool_updates

    effective = _effective_payload(state, tool_updates)
    schedule_blocks = _coerce_schedule_blocks(effective.get("schedule"))
    activities = coerce_academic_activities(effective.get("academic_activities", []))
    source_keys = _academic_source_keys(schedule_blocks, activities)

    reconciled = dict(tool_updates)
    if not source_keys:
        reconciled["subjects"] = []
        if _has_any_study_plan(effective.get("study_plan")):
            reconciled["study_plan"] = _empty_study_plan_update(
                reason="no_academic_subject_sources",
            )
        return reconciled

    filtered_subjects = [
        subject
        for subject in effective.get("subjects", []) or []
        if _normalize_key(_get_attr(subject, "nombre")) in source_keys
    ]
    sync_result = sync_subjects_and_study_plan(
        schedule_blocks=schedule_blocks,
        subjects=filtered_subjects,
        academic_activities=activities,
        study_profile=effective.get("study_profile", {}),
        constraints=effective.get("constraints", {}),
        timezone=str(effective.get("timezone") or "America/Bogota"),
    )
    plan = _with_reconciliation_metadata(
        sync_result.study_plan,
        source=sync_result.source,
        trigger_fields=sorted(key for key in tool_updates if key in _RECONCILED_FIELDS),
    )
    reconciled["subjects"] = list(sync_result.subjects)
    reconciled["study_plan"] = study_plan_state_to_update(plan)
    return reconciled


def _needs_reconciliation(tool_updates: dict[str, Any]) -> bool:
    return bool(_RECONCILED_FIELDS.intersection(tool_updates))


def _effective_payload(state: Any, updates: dict[str, Any]) -> dict[str, Any]:
    if isinstance(state, dict):
        payload = dict(state)
    elif hasattr(state, "model_dump"):
        payload = dict(state.model_dump(mode="python"))
    else:
        payload = dict(getattr(state, "__dict__", {}))
    payload.update(updates)
    return payload


def _coerce_schedule_blocks(raw_schedule: Any) -> list[WeeklyScheduleBlock]:
    if hasattr(raw_schedule, "blocks"):
        raw_blocks = getattr(raw_schedule, "blocks", [])
    elif isinstance(raw_schedule, dict):
        raw_blocks = raw_schedule.get("blocks", [])
    else:
        raw_blocks = []

    blocks: list[WeeklyScheduleBlock] = []
    for raw_block in list(raw_blocks or []):
        try:
            blocks.append(ensure_weekly_block(raw_block))
        except Exception:
            continue
    return blocks


def _academic_source_keys(
    blocks: list[WeeklyScheduleBlock],
    activities: list,
) -> set[str]:
    keys = {
        _normalize_key(block.title)
        for block in blocks
        if block.is_active and block.block_type == "academic" and block.title.strip()
    }
    keys.update(
        _normalize_key(activity.subject_name)
        for activity in activities
        if activity.status == "pending" and str(activity.subject_name or "").strip()
    )
    return {key for key in keys if key}


def _has_any_study_plan(raw_plan: Any) -> bool:
    plan = ensure_study_plan_state(raw_plan)
    return bool(plan.plan_events or plan.rules)


def _empty_study_plan_update(*, reason: str) -> dict[str, object]:
    return study_plan_state_to_update(
        StudyPlanState(
            plan_events=[],
            rules={
                "planner_version": "study_planner_v1",
                "status": "skipped",
                "reason": reason,
                "react_reconciliation": {
                    "status": "cleared",
                    "reason": reason,
                },
            },
        )
    )


def _with_reconciliation_metadata(
    plan: StudyPlanState,
    *,
    source: str,
    trigger_fields: list[str],
) -> StudyPlanState:
    rules = dict(plan.rules or {})
    rules["react_reconciliation"] = {
        "status": "applied",
        "subjects_source": source,
        "trigger_fields": trigger_fields,
    }
    return plan.model_copy(update={"rules": rules})


def _get_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())


__all__ = ["reconcile_react_tool_updates"]
