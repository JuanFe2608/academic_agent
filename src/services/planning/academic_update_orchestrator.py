"""Orquestador de actualizaciones académicas puntuales."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.planning.academic_activity_persistence_service import (
    AcademicActivityPersistenceService,
)
from services.planning.academic_activity_service import coerce_academic_activities
from services.priorities import (
    apply_academic_event_update,
    current_week_bounds,
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)


@dataclass
class PriorityComputeResult:
    detected: bool
    subjects: list = field(default_factory=list)
    priorities: dict | None = None
    replan: dict | None = None
    requires_clarification: bool = False
    message: str | None = None


def reference_date(timezone: str) -> date:
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).date()
    except Exception:
        return datetime.now().date()


def reference_datetime(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota")))
    except Exception:
        return datetime.now()


def _primary_technique_id(study_profile: dict) -> str | None:
    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _replace_activity(activities: list, replacement) -> list:
    updated = []
    found = False
    for activity in coerce_academic_activities(activities):
        if activity.activity_id == replacement.activity_id:
            updated.append(replacement)
            found = True
        else:
            updated.append(activity)
    if not found:
        updated.append(replacement)
    return updated


class AcademicUpdateOrchestrator:
    """Encapsula la lógica de negocio del nodo handle_academic_update."""

    def __init__(self, persistence_service: AcademicActivityPersistenceService) -> None:
        self._persistence = persistence_service

    def load_activities(self, student_id: int | None, local_activities: list) -> list:
        """Carga actividades del cache de estado; si está vacío consulta persistencia."""
        local = coerce_academic_activities(local_activities)
        if local:
            return local
        if not student_id:
            return local
        try:
            result = self._persistence.list_activities(
                student_id=student_id,
                include_deleted=True,
            )
        except Exception:
            return local
        if result.loaded:
            return result.activities
        return local

    def persist_activity(self, student_id: int | None, activity, *, operation: str):
        """Persiste la actividad; retorna la actividad con metadata de persistencia."""
        if activity is None:
            return None
        if not student_id:
            return activity
        try:
            if operation == "delete":
                result = self._persistence.delete_activity(
                    student_id=student_id,
                    activity_id=activity.activity_id,
                )
                if not result.persisted:
                    result = self._persistence.upsert_activity(
                        student_id=student_id, activity=activity
                    )
            else:
                result = self._persistence.upsert_activity(
                    student_id=student_id, activity=activity
                )
        except Exception as exc:
            return activity.model_copy(update={"persistence_error": str(exc)})
        if result.persisted and result.activity is not None:
            return result.activity
        return activity.model_copy(
            update={"persistence_error": result.error_code or result.detail}
        )

    def replace_activity(self, activities: list, replacement) -> list:
        return _replace_activity(activities, replacement)

    def compute_priority_update(
        self,
        text: str,
        *,
        subjects: list,
        schedule_blocks: list,
        academic_activities: list,
        study_profile: dict,
        ref_date: date,
        timezone: str,
        priorities_state: dict,
    ) -> PriorityComputeResult:
        """Aplica una actualización de prioridades a partir de texto libre."""
        week_start, week_end = current_week_bounds(ref_date)
        priorities = resolve_prioritized_subjects(
            schedule_blocks=list(schedule_blocks),
            subjects=list(subjects),
            academic_activities=list(academic_activities),
            primary_technique_id=_primary_technique_id(study_profile),
            reference_date=ref_date,
        )
        current_subjects = subject_items_to_update(priorities.subject_items)
        result = apply_academic_event_update(
            subjects=current_subjects,
            text=text,
            reference_date=ref_date,
            timezone=timezone,
        )
        if not result.detected:
            return PriorityComputeResult(detected=False, subjects=current_subjects)

        updated_subjects = subject_items_to_update(result.subjects or current_subjects)
        replan = _build_replan(priorities_state.get("replan", {}), result)
        return PriorityComputeResult(
            detected=True,
            subjects=updated_subjects,
            priorities=update_priorities_state(
                priorities_state,
                status="completed" if result.event_type == "academic_deadline" else "collecting",
                prompt_version="v2",
                source="event_update",
                last_error=None,
                capture_stage=None,
                week_start=week_start,
                week_end=week_end,
                draft={"event_update": result.payload},
            ),
            replan=replan if result.replan_required else None,
            requires_clarification=bool(result.requires_clarification),
            message=result.message,
        )

    def compute_priority_update_from_activity(
        self,
        activity,
        *,
        subjects: list,
        schedule_blocks: list,
        academic_activities: list,
        study_profile: dict,
        ref_date: date,
        timezone: str,
        priorities_state: dict,
    ) -> PriorityComputeResult:
        """Recalcula prioridades tras crear/actualizar una actividad académica."""
        from services.planning.academic_activity_service import (
            priority_update_text_for_activity,
        )

        update_text = priority_update_text_for_activity(activity)
        if not update_text:
            return PriorityComputeResult(detected=False)

        return self.compute_priority_update(
            update_text,
            subjects=subjects,
            schedule_blocks=schedule_blocks,
            academic_activities=[*list(academic_activities), activity],
            study_profile=study_profile,
            ref_date=ref_date,
            timezone=timezone,
            priorities_state=priorities_state,
        )


def build_academic_update_orchestrator(
    persistence_service: AcademicActivityPersistenceService,
) -> AcademicUpdateOrchestrator:
    return AcademicUpdateOrchestrator(persistence_service=persistence_service)


def _build_replan(current_replan: dict, result) -> dict:
    replan = dict(current_replan)
    replan["trigger"] = str(result.payload.get("trigger") or result.event_type or "user_request")
    replan["change_request"] = dict(result.payload)
    replan["pending_prompt"] = result.message if result.requires_clarification else None
    return replan
