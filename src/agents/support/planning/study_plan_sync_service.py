"""Servicio para sincronizar `subjects` y `study_plan` desde el estado del agente."""

from __future__ import annotations

from dataclasses import dataclass

from agents.support.priorities.subject_prioritization_service import resolve_prioritized_subjects
from agents.support.state import StudyPlanState, StudyProfile, SubjectItem

from .study_planning_service import build_initial_study_plan


@dataclass(frozen=True)
class StudyPlanSyncResult:
    """Resultado consolidado de materias y plan semanal."""

    subjects: list[SubjectItem]
    study_plan: StudyPlanState
    source: str


def sync_subjects_and_study_plan(
    *,
    schedule_blocks: list,
    subjects: list,
    study_profile: StudyProfile | dict,
    constraints: object,
    timezone: str,
) -> StudyPlanSyncResult:
    """Sincroniza catálogo de materias y plan semanal inicial."""

    primary_technique_id = _primary_technique_id(study_profile)
    priorities = resolve_prioritized_subjects(
        schedule_blocks=schedule_blocks,
        subjects=subjects,
        primary_technique_id=primary_technique_id,
    )
    study_plan = build_initial_study_plan(
        schedule_blocks=schedule_blocks,
        subjects=priorities.subject_items,
        study_profile=study_profile,
        constraints=constraints,
        timezone=timezone,
        prioritized_subjects=priorities.prioritized_subjects,
        subject_source=priorities.source,
    )
    return StudyPlanSyncResult(
        subjects=priorities.subject_items,
        study_plan=study_plan,
        source=priorities.source,
    )


def _primary_technique_id(study_profile: StudyProfile | dict) -> str | None:
    data = study_profile if isinstance(study_profile, dict) else study_profile.model_dump(mode="python")
    techniques = list(data.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None
