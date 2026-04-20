"""Servicio para resolver la priorización académica de materias.

Este módulo separa la construcción del catálogo de materias del servicio de
planificación semanal. Su responsabilidad es producir una vista consistente de
las materias con carga, dificultad y urgencia útiles para planificar, incluso
si el estado todavía viene parcialmente vacío.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from services.scheduling.constants import DAY_ORDER
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from schemas.common import Prioridad
from schemas.planning import AcademicActivity, SubjectItem

from .state_helpers import ensure_subject_items

PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baja": 1}
URGENCY_WEIGHT = {None: 0, "baja": 1, "media": 2, "alta": 3}
_ACTIVITY_DEFAULT_EFFORT_MINUTES = {
    "parcial": 150,
    "quiz": 75,
    "tarea": 90,
    "taller": 90,
    "entrega": 120,
    "exposicion": 120,
    "proyecto": 180,
    "estudio_pendiente": 60,
}


@dataclass(frozen=True)
class PrioritizedSubject:
    """Materia enriquecida con datos útiles para planificación semanal."""

    nombre: str
    prioridad: Prioridad
    dificultad: int
    urgencia: Prioridad | None
    carga_semanal_min: int | None
    preferred_days: tuple[str, ...]
    weekly_sessions: int
    planning_score: int
    origen: str


@dataclass(frozen=True)
class PrioritizationResult:
    """Resultado normalizado del módulo de prioridades."""

    subject_items: list[SubjectItem]
    prioritized_subjects: list[PrioritizedSubject]
    source: str


def resolve_prioritized_subjects(
    *,
    schedule_blocks: list[WeeklyScheduleBlock | dict],
    subjects: list[SubjectItem | dict] | None,
    academic_activities: list[AcademicActivity | dict] | None = None,
    primary_technique_id: str | None = None,
    reference_date: date | None = None,
) -> PrioritizationResult:
    """Resuelve materias normalizadas y su orden de planificación.

    Si `subjects` ya trae información explícita, la preserva y solo rellena los
    vacíos obvios con datos derivados del horario. Si no existe, crea una base
    mínima a partir de los bloques académicos confirmados.
    """

    active_blocks = _active_blocks(schedule_blocks)
    academic_stats = _academic_subject_stats(active_blocks)
    activity_stats = _academic_activity_stats(
        academic_activities,
        reference_date=reference_date or date.today(),
    )
    explicit_subjects = ensure_subject_items(subjects)

    if explicit_subjects:
        normalized_items, prioritized_subjects = _build_from_explicit_subjects(
            explicit_subjects,
            academic_stats=academic_stats,
            activity_stats=activity_stats,
            primary_technique_id=primary_technique_id,
        )
        return PrioritizationResult(
            subject_items=normalized_items,
            prioritized_subjects=prioritized_subjects,
            source="state.subjects",
        )

    if academic_stats or activity_stats:
        normalized_items, prioritized_subjects = _build_from_academic_schedule(
            academic_stats,
            activity_stats=activity_stats,
            primary_technique_id=primary_technique_id,
        )
        return PrioritizationResult(
            subject_items=normalized_items,
            prioritized_subjects=prioritized_subjects,
            source="derived_from_schedule" if academic_stats else "academic_activities",
        )

    fallback = SubjectItem(
        nombre="Estudio general",
        prioridad="media",
        dificultad=3,
        urgencia=None,
        carga_semanal_min=None,
        origen="fallback",
    )
    prioritized = _to_prioritized_subject(
        fallback,
        preferred_days=tuple(),
        primary_technique_id=primary_technique_id,
    )
    return PrioritizationResult(
        subject_items=[fallback],
        prioritized_subjects=[prioritized],
        source="fallback",
    )


def _build_from_explicit_subjects(
    subjects: list[SubjectItem],
    *,
    academic_stats: dict[str, dict[str, object]],
    activity_stats: dict[str, dict[str, object]],
    primary_technique_id: str | None,
) -> tuple[list[SubjectItem], list[PrioritizedSubject]]:
    normalized_items: list[SubjectItem] = []
    prioritized_subjects: list[PrioritizedSubject] = []
    seen_keys: set[str] = set()

    for subject in subjects:
        if not subject.nombre.strip():
            continue
        key = _normalize_title(subject.nombre)
        seen_keys.add(key)
        stats = academic_stats.get(key, {})
        activity = activity_stats.get(key, {})
        carga = _merge_activity_load(_resolve_subject_load(subject, stats), activity)
        normalized = _merge_subject_activity_signals(
            subject,
            activity,
            carga_semanal_min=carga,
            origen=subject.origen or "manual",
        )
        preferred_days = tuple(stats.get("days", ()))
        normalized_items.append(normalized)
        prioritized_subjects.append(
            _to_prioritized_subject(
                normalized,
                preferred_days=preferred_days,
                primary_technique_id=primary_technique_id,
            )
        )

    for key, activity in activity_stats.items():
        if key in seen_keys:
            continue
        subject = _subject_from_activity_stats(activity)
        normalized_items.append(subject)
        prioritized_subjects.append(
            _to_prioritized_subject(
                subject,
                preferred_days=tuple(),
                primary_technique_id=primary_technique_id,
            )
        )

    sorted_subjects = _sort_prioritized_subjects(prioritized_subjects)
    index_by_name = {subject.nombre: position for position, subject in enumerate(sorted_subjects)}
    normalized_items.sort(key=lambda item: index_by_name.get(item.nombre, len(index_by_name)))
    return normalized_items, sorted_subjects


def _build_from_academic_schedule(
    academic_stats: dict[str, dict[str, object]],
    *,
    activity_stats: dict[str, dict[str, object]],
    primary_technique_id: str | None,
) -> tuple[list[SubjectItem], list[PrioritizedSubject]]:
    subject_items: list[SubjectItem] = []
    prioritized_subjects: list[PrioritizedSubject] = []
    seen_keys: set[str] = set()

    for key, stats in academic_stats.items():
        seen_keys.add(key)
        activity = activity_stats.get(key, {})
        carga = _merge_activity_load(int(stats["minutes"]), activity)
        base_priority = _priority_from_class_minutes(carga or int(stats["minutes"]))
        subject = SubjectItem(
            nombre=str(stats["title"]),
            prioridad=base_priority,
            dificultad=3,
            urgencia=None,
            carga_semanal_min=carga,
            origen="derived_from_schedule",
        )
        subject = _merge_subject_activity_signals(
            subject,
            activity,
            carga_semanal_min=carga,
            origen="derived_from_schedule",
        )
        subject_items.append(subject)
        prioritized_subjects.append(
            _to_prioritized_subject(
                subject,
                preferred_days=tuple(stats["days"]),
                primary_technique_id=primary_technique_id,
            )
        )

    for key, activity in activity_stats.items():
        if key in seen_keys:
            continue
        subject = _subject_from_activity_stats(activity)
        subject_items.append(subject)
        prioritized_subjects.append(
            _to_prioritized_subject(
                subject,
                preferred_days=tuple(),
                primary_technique_id=primary_technique_id,
            )
        )

    sorted_subjects = _sort_prioritized_subjects(prioritized_subjects)
    index_by_name = {subject.nombre: position for position, subject in enumerate(sorted_subjects)}
    subject_items.sort(key=lambda item: index_by_name.get(item.nombre, len(index_by_name)))
    return subject_items, sorted_subjects


def _to_prioritized_subject(
    subject: SubjectItem,
    *,
    preferred_days: tuple[str, ...],
    primary_technique_id: str | None,
) -> PrioritizedSubject:
    carga = subject.carga_semanal_min
    weekly_sessions = _weekly_sessions_for_subject(
        prioridad=subject.prioridad,
        dificultad=int(subject.dificultad),
        urgencia=subject.urgencia,
        carga_semanal_min=carga,
        primary_technique_id=primary_technique_id,
    )
    planning_score = _planning_score(
        prioridad=subject.prioridad,
        dificultad=int(subject.dificultad),
        urgencia=subject.urgencia,
        carga_semanal_min=carga,
        computed_priority_score=subject.computed_priority_score,
    )
    return PrioritizedSubject(
        nombre=subject.nombre.strip(),
        prioridad=subject.prioridad,
        dificultad=max(1, min(int(subject.dificultad), 5)),
        urgencia=subject.urgencia,
        carga_semanal_min=carga,
        preferred_days=preferred_days,
        weekly_sessions=weekly_sessions,
        planning_score=planning_score,
        origen=str(subject.origen or "manual"),
    )


def _active_blocks(schedule_blocks: list[WeeklyScheduleBlock | dict]) -> list[WeeklyScheduleBlock]:
    blocks: list[WeeklyScheduleBlock] = []
    for raw_block in schedule_blocks:
        block = ensure_weekly_block(raw_block)
        if block.is_active:
            blocks.append(block)
    return blocks


def _academic_subject_stats(
    schedule_blocks: list[WeeklyScheduleBlock],
) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for block in schedule_blocks:
        if block.block_type != "academic":
            continue
        title = block.title.strip()
        if not title:
            continue
        key = _normalize_title(title)
        entry = stats.setdefault(
            key,
            {
                "title": title,
                "minutes": 0,
                "days": [],
            },
        )
        entry["minutes"] = int(entry["minutes"]) + _duration_minutes(
            block.start_time,
            block.end_time,
        )
        days = list(entry["days"])
        if block.day_of_week not in days:
            days.append(block.day_of_week)
        entry["days"] = tuple(sorted(days, key=lambda value: DAY_ORDER.index(value)))
    return dict(
        sorted(
            stats.items(),
            key=lambda item: (-int(item[1]["minutes"]), str(item[1]["title"]).lower()),
        )
    )


def _academic_activity_stats(
    activities: list[AcademicActivity | dict] | None,
    *,
    reference_date: date,
) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for raw_activity in list(activities or []):
        try:
            activity = (
                raw_activity
                if isinstance(raw_activity, AcademicActivity)
                else AcademicActivity(**dict(raw_activity))
            )
        except Exception:
            continue
        if activity.status != "pending" or not activity.subject_name.strip():
            continue

        key = _normalize_title(activity.subject_name)
        effort = _activity_effort_minutes(activity)
        due_priority = _priority_from_due_date(
            activity.due_date,
            reference_date=reference_date,
        )
        activity_priority = _stronger_priority(activity.priority_level, due_priority)
        difficulty = activity.difficulty_level or _default_activity_difficulty(activity)
        entry = stats.setdefault(
            key,
            {
                "title": activity.subject_name.strip(),
                "effort_minutes": 0,
                "priority": None,
                "urgency": None,
                "difficulty": 3,
                "urgency_type": None,
                "urgency_due_at": None,
            },
        )
        entry["effort_minutes"] = int(entry["effort_minutes"]) + effort
        entry["priority"] = _stronger_priority(
            entry.get("priority"),
            activity_priority,
        )
        entry["urgency"] = _stronger_priority(
            entry.get("urgency"),
            due_priority,
        )
        entry["difficulty"] = max(int(entry.get("difficulty") or 3), int(difficulty))
        if _is_nearer_due_date(activity.due_date, entry.get("urgency_due_at")):
            entry["urgency_due_at"] = activity.due_date
            entry["urgency_type"] = activity.activity_type

    return dict(
        sorted(
            stats.items(),
            key=lambda item: (
                str(item[1].get("urgency_due_at") or "9999-12-31"),
                -PRIORITY_WEIGHT.get(item[1].get("priority"), 0),
                str(item[1].get("title") or "").lower(),
            ),
        )
    )


def _merge_subject_activity_signals(
    subject: SubjectItem,
    activity: dict[str, object],
    *,
    carga_semanal_min: int | None,
    origen: str,
) -> SubjectItem:
    if not activity:
        return subject.model_copy(
            update={
                "dificultad": max(1, min(int(subject.dificultad), 5)),
                "carga_semanal_min": carga_semanal_min,
                "origen": origen,
            }
        )

    priority = _stronger_priority(subject.prioridad, activity.get("priority"))
    urgency = _stronger_priority(subject.urgencia, activity.get("urgency"))
    difficulty = max(
        max(1, min(int(subject.dificultad), 5)),
        max(1, min(int(activity.get("difficulty") or 3), 5)),
    )
    updates: dict[str, object] = {
        "prioridad": priority or subject.prioridad,
        "dificultad": difficulty,
        "urgencia": urgency,
        "carga_semanal_min": carga_semanal_min,
        "origen": origen,
    }
    due_at = activity.get("urgency_due_at")
    if due_at and _is_nearer_due_date(due_at, subject.urgency_due_at):
        updates["urgency_type"] = activity.get("urgency_type")
        updates["urgency_due_at"] = due_at
        updates["priority_source"] = subject.priority_source or "academic_activity_seed"
    return subject.model_copy(update=updates)


def _subject_from_activity_stats(activity: dict[str, object]) -> SubjectItem:
    carga = max(30, int(activity.get("effort_minutes") or 0))
    priority = activity.get("priority") or _priority_from_class_minutes(carga)
    return SubjectItem(
        nombre=str(activity.get("title") or "Actividad academica").strip(),
        prioridad=priority,  # type: ignore[arg-type]
        dificultad=max(1, min(int(activity.get("difficulty") or 3), 5)),
        urgencia=activity.get("urgency"),  # type: ignore[arg-type]
        carga_semanal_min=carga,
        origen="academic_activity",
        urgency_type=str(activity.get("urgency_type") or "") or None,
        urgency_due_at=str(activity.get("urgency_due_at") or "") or None,
        priority_source="academic_activity_seed",
    )


def _merge_activity_load(
    base_minutes: int | None,
    activity: dict[str, object],
) -> int | None:
    effort = int(activity.get("effort_minutes") or 0)
    if effort <= 0:
        return base_minutes
    if base_minutes is None:
        return max(30, effort)
    return max(30, int(base_minutes) + effort)


def _resolve_subject_load(subject: SubjectItem, stats: dict[str, object]) -> int | None:
    if subject.carga_semanal_min is not None:
        return max(30, int(subject.carga_semanal_min))
    if stats:
        return max(30, int(stats.get("minutes") or 0))
    fallback = 180 if subject.prioridad == "alta" else 120 if subject.prioridad == "media" else 90
    return fallback


def _planning_score(
    *,
    prioridad: Prioridad,
    dificultad: int,
    urgencia: Prioridad | None,
    carga_semanal_min: int | None,
    computed_priority_score: float | None = None,
) -> int:
    if computed_priority_score is not None:
        return int(round(max(0.0, min(float(computed_priority_score), 1.0)) * 1000))
    carga_score = min(int((carga_semanal_min or 0) / 30), 20)
    return (
        PRIORITY_WEIGHT[prioridad] * 100
        + URGENCY_WEIGHT[urgencia] * 80
        + max(1, min(int(dificultad), 5)) * 10
        + carga_score
    )


def _weekly_sessions_for_subject(
    *,
    prioridad: Prioridad,
    dificultad: int,
    urgencia: Prioridad | None,
    carga_semanal_min: int | None,
    primary_technique_id: str | None,
) -> int:
    sessions = 1
    carga = int(carga_semanal_min or 0)
    if carga >= 180:
        sessions += 1
    if carga >= 300:
        sessions += 1
    if prioridad == "alta":
        sessions += 1
    if int(dificultad) >= 4:
        sessions += 1
    if urgencia == "alta":
        sessions += 1
    elif urgencia == "media":
        sessions = max(sessions, 2)
    if primary_technique_id == "repeticion_espaciada":
        sessions = max(sessions, 2)
    return min(sessions, 4)


def _sort_prioritized_subjects(
    subjects: list[PrioritizedSubject],
) -> list[PrioritizedSubject]:
    return sorted(
        subjects,
        key=lambda subject: (
            -subject.planning_score,
            subject.nombre.lower(),
        ),
    )


def _priority_from_class_minutes(minutes: int) -> Prioridad:
    if minutes >= 180:
        return "alta"
    if minutes >= 90:
        return "media"
    return "baja"


def _activity_effort_minutes(activity: AcademicActivity) -> int:
    if activity.estimated_effort_minutes:
        return max(15, int(activity.estimated_effort_minutes))
    return _ACTIVITY_DEFAULT_EFFORT_MINUTES.get(activity.activity_type, 90)


def _default_activity_difficulty(activity: AcademicActivity) -> int:
    if activity.activity_type in {"parcial", "proyecto"}:
        return 4
    return 3


def _priority_from_due_date(
    due_date: str | None,
    *,
    reference_date: date,
) -> Prioridad | None:
    parsed = _parse_date(due_date)
    if parsed is None:
        return None
    days_left = (parsed - reference_date).days
    if days_left < 0:
        return None
    if days_left <= 3:
        return "alta"
    if days_left <= 7:
        return "media"
    return "baja"


def _stronger_priority(
    current: object,
    candidate: object,
) -> Prioridad | None:
    current_value = _priority_or_none(current)
    candidate_value = _priority_or_none(candidate)
    if current_value is None:
        return candidate_value
    if candidate_value is None:
        return current_value
    return (
        candidate_value
        if PRIORITY_WEIGHT[candidate_value] > PRIORITY_WEIGHT[current_value]
        else current_value
    )


def _priority_or_none(value: object) -> Prioridad | None:
    if value in {"alta", "media", "baja"}:
        return value  # type: ignore[return-value]
    return None


def _is_nearer_due_date(candidate: object, current: object) -> bool:
    candidate_date = _parse_date(candidate)
    if candidate_date is None:
        return False
    current_date = _parse_date(current)
    return current_date is None or candidate_date < current_date


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_title(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def _duration_minutes(start_time: str, end_time: str) -> int:
    return _to_minutes(end_time) - _to_minutes(start_time)


def _to_minutes(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)
