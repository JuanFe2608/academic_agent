"""Enriquecimiento del plan de estudio con guia RAG y metodos aplicados."""

from __future__ import annotations

from copy import deepcopy

from services.planning.academic_activity_service import active_academic_activities
from services.study_recommendations import (
    AppliedStudyMethodRequest,
    AppliedStudyMethodService,
)


class StudyPlanEnrichmentService:
    def __init__(self, recommendation_service) -> None:
        self._recommendation_service = recommendation_service

    def enrich_with_rag_guidance(self, study_plan, subjects: list, study_profile: dict):
        """Agrega guia pedagogica RAG sin alterar eventos ni restricciones del planner."""

        rules = deepcopy(dict(study_plan.rules or {}))
        primary_technique = str(rules.get("primary_technique_id") or "").strip()
        if not primary_technique:
            return study_plan
        primary_subject = subjects[0] if subjects else None
        subject_name = getattr(primary_subject, "nombre", None)
        try:
            svc = self._recommendation_service
            if not svc.status.ready:
                return study_plan
            result = svc.recommend_for_session(
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
            "cautions": [_compact_text(c, max_chars=240) for c in result.cautions[:2]],
            "source_chunks": list(result.source_chunks),
            "relations_used": list(result.relations_used),
            "confidence": result.confidence,
            "primary_technique_id": primary_technique,
            "subject_name": subject_name,
        }
        return study_plan.model_copy(update={"rules": rules})

    def enrich_with_applied_methods(
        self,
        study_plan,
        subjects: list,
        academic_activities: list,
        study_profile: dict,
    ):
        """Guarda instrucciones aplicadas por actividad sin alterar el planner."""

        activities = active_academic_activities(academic_activities)
        if not activities:
            return study_plan
        try:
            if not getattr(self._recommendation_service.status, "ready", False):
                return study_plan
        except Exception:
            return study_plan

        applied_service = AppliedStudyMethodService(self._recommendation_service)
        rules = deepcopy(dict(study_plan.rules or {}))
        subject_lookup = {str(s.nombre or "").lower(): s for s in subjects}
        event_ids_by_subject = _event_ids_by_subject(study_plan.plan_events)
        payloads: list[dict] = []

        for activity in activities[:3]:
            subject = subject_lookup.get(str(activity.subject_name or "").lower())
            result = applied_service.apply_to_activity(
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
                str(activity.subject_name or "").lower(), []
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

    def fully_enrich(
        self,
        study_plan,
        subjects: list,
        academic_activities: list,
        study_profile: dict,
    ):
        """Aplica las tres etapas de enriquecimiento en orden: RAG, métodos aplicados, sync pendiente."""
        study_plan = self.enrich_with_rag_guidance(study_plan, subjects, study_profile)
        study_plan = self.enrich_with_applied_methods(
            study_plan, subjects, academic_activities, study_profile
        )
        return self.mark_external_sync_as_pending(study_plan)

    def mark_external_sync_as_pending(self, study_plan):
        """Marca que el plan aun no debe salir a Outlook o Microsoft To Do."""

        rules = deepcopy(dict(study_plan.rules or {}))
        rules.setdefault("external_sync_status", "not_requested")
        rules.setdefault("external_sync_requires_confirmation", True)
        rules.setdefault("external_sync_targets", ["outlook_calendar", "microsoft_todo"])
        return study_plan.model_copy(update={"rules": rules})


def build_study_plan_enrichment_service(recommendation_service) -> StudyPlanEnrichmentService:
    return StudyPlanEnrichmentService(recommendation_service)


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


def _result_supports_primary_technique(source_chunks: list[str], primary_technique: str) -> bool:
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
