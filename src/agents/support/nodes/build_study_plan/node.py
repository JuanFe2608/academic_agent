"""Nodo fino para sincronizar el plan semanal de estudio."""

from __future__ import annotations

from copy import deepcopy

from agents.support.dependencies import get_study_recommendation_service
from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.nodes.utils import append_message
from agents.support.planning.formatter import build_study_plan_summary
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.planning import (
    active_academic_activities,
    ensure_study_plan_state,
    study_plan_state_to_update,
    sync_subjects_and_study_plan,
)
from services.priorities import subject_items_to_update
from services.study_recommendations import (
    AppliedStudyMethodRequest,
    AppliedStudyMethodService,
)


def build_study_plan(state: AgentState) -> dict:
    """Sincroniza materias y plan semanal sin cargar lógica en el nodo."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    messages = state.get("messages", [])
    try:
        result = sync_subjects_and_study_plan(
            schedule_blocks=list(schedule_state.blocks),
            subjects=list(state.get("subjects", [])),
            academic_activities=list(state.get("academic_activities", [])),
            study_profile=state.get("study_profile", {}),
            constraints=state.get("constraints", {}),
            timezone=state.get("timezone", "America/Bogota"),
        )
    except Exception:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "No pude recalcular tu plan semanal en este momento, pero dejé tu base anterior intacta.",
            ),
        }

    study_plan = _enrich_study_plan_with_rag_session_guidance(
        study_plan=result.study_plan,
        subjects=result.subjects,
        study_profile=dict(state.get("study_profile", {})),
    )
    study_plan = _enrich_study_plan_with_applied_methods(
        study_plan=study_plan,
        subjects=result.subjects,
        academic_activities=list(state.get("academic_activities", [])),
        study_profile=dict(state.get("study_profile", {})),
    )
    study_plan = _mark_external_sync_as_pending_confirmation(study_plan)
    update = {
        "subjects": subject_items_to_update(result.subjects),
        "study_plan": study_plan_state_to_update(study_plan),
        "phase": "end",
        "awaiting_user_input": False,
    }
    persisted_update = persist_planning_snapshot_for_update(state, update)
    persisted_update["messages"] = append_message(
        messages,
        "assistant",
        build_study_plan_summary(
            subject_items_to_update(persisted_update.get("subjects", result.subjects)),
            ensure_study_plan_state(persisted_update.get("study_plan", study_plan)),
            reminders=persisted_update.get("reminders", state.get("reminders", {})),
        ),
    )
    return persisted_update


def _mark_external_sync_as_pending_confirmation(study_plan):
    """Marca que el plan aun no debe salir a Outlook o Microsoft To Do."""

    rules = deepcopy(dict(study_plan.rules or {}))
    rules.setdefault("external_sync_status", "not_requested")
    rules.setdefault("external_sync_requires_confirmation", True)
    rules.setdefault("external_sync_targets", ["outlook_calendar", "microsoft_todo"])
    return study_plan.model_copy(update={"rules": rules})


def _enrich_study_plan_with_rag_session_guidance(
    *,
    study_plan,
    subjects,
    study_profile: dict,
):
    """Agrega guia pedagogica sin alterar eventos ni restricciones del planner."""

    rules = deepcopy(dict(study_plan.rules or {}))
    primary_technique = str(rules.get("primary_technique_id") or "").strip()
    if not primary_technique:
        return study_plan
    primary_subject = subjects[0] if subjects else None
    subject_name = getattr(primary_subject, "nombre", None)
    try:
        service = get_study_recommendation_service()
        if not service.status.ready:
            return study_plan
        result = service.recommend_for_session(
            technique_id=primary_technique,
            subject_name=subject_name,
            available_minutes=_int_or_none(rules.get("session_minutes")),
            student_signals=list(study_profile.get("weakness_tags") or []),
            top_techniques=list(study_profile.get("top_techniques") or []),
            max_chunks=3,
        )
    except Exception:
        return study_plan

    if (
        not result.source_chunks
        or not result.answer.strip()
        or not _result_supports_primary_technique(result.source_chunks, primary_technique)
    ):
        return study_plan

    rules["rag_session_guidance"] = {
        "answer": _clean_text(result.answer),
        "cautions": [_compact_text(caution, max_chars=240) for caution in result.cautions[:2]],
        "source_chunks": list(result.source_chunks),
        "relations_used": list(result.relations_used),
        "confidence": result.confidence,
        "primary_technique_id": primary_technique,
        "subject_name": subject_name,
    }
    return study_plan.model_copy(update={"rules": rules})


def _enrich_study_plan_with_applied_methods(
    *,
    study_plan,
    subjects,
    academic_activities: list,
    study_profile: dict,
):
    """Guarda instrucciones aplicadas por actividad sin alterar el planner."""

    activities = active_academic_activities(academic_activities)
    if not activities:
        return study_plan
    try:
        recommendation_service = get_study_recommendation_service()
        if not getattr(recommendation_service.status, "ready", False):
            return study_plan
    except Exception:
        return study_plan

    service = AppliedStudyMethodService(recommendation_service)
    rules = deepcopy(dict(study_plan.rules or {}))
    subject_lookup = {str(subject.nombre or "").lower(): subject for subject in subjects}
    event_ids_by_subject = _event_ids_by_subject(study_plan.plan_events)
    payloads: list[dict[str, object]] = []

    for activity in activities[:3]:
        subject = subject_lookup.get(str(activity.subject_name or "").lower())
        result = service.apply_to_activity(
            AppliedStudyMethodRequest(
                subject_name=activity.subject_name,
                activity_type=activity.activity_type,
                activity_title=activity.activity_title,
                available_minutes=(
                    activity.estimated_effort_minutes
                    or _int_or_none(rules.get("session_minutes"))
                ),
                urgency=activity.priority_level or getattr(subject, "urgencia", None),
                difficulty=activity.difficulty_level or getattr(subject, "dificultad", None),
                student_signals=list(study_profile.get("weakness_tags") or []),
                top_techniques=list(study_profile.get("top_techniques") or []),
            )
        )
        if not result.applied:
            continue
        payload = result.to_rule_payload()
        payload["activity_id"] = activity.activity_id
        payload["due_date"] = activity.due_date
        payload["session_event_ids"] = event_ids_by_subject.get(
            str(activity.subject_name or "").lower(),
            [],
        )
        payloads.append(payload)

    if not payloads:
        return study_plan
    rules["applied_method_guidance"] = {
        "status": "generated",
        "source": "phase_18_activity_method_application",
        "activity_count": len(payloads),
        "items": payloads,
    }
    return study_plan.model_copy(update={"rules": rules})


def _event_ids_by_subject(events) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for event in events:
        title = str(getattr(event, "titulo", "") or "")
        subject = title.split("·", maxsplit=1)[-1].strip() if "·" in title else title
        key = subject.lower()
        if not key:
            continue
        mapping.setdefault(key, []).append(str(getattr(event, "id", "")))
    return mapping


def _result_supports_primary_technique(
    source_chunks: list[str],
    primary_technique: str,
) -> bool:
    """Evita mostrar guia de una tecnica distinta a la tecnica base del plan."""

    prefix = f"technique.{primary_technique}::"
    return any(str(chunk_id).startswith(prefix) for chunk_id in source_chunks)


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _compact_text(text: str, *, max_chars: int = 520) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    cutoff = cleaned.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return cleaned[:cutoff].rstrip(" .,;:") + "..."


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
