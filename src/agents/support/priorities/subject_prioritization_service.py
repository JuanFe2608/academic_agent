"""Servicio para resolver la priorización académica de materias.

Este módulo separa la construcción del catálogo de materias del servicio de
planificación semanal. Su responsabilidad es producir una vista consistente de
las materias con carga, dificultad y urgencia útiles para planificar, incluso
si el estado todavía viene parcialmente vacío.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.support.scheduling.constants import DAY_ORDER
from agents.support.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from agents.support.state import Prioridad, SubjectItem

from .state_helpers import ensure_subject_items

PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baja": 1}
URGENCY_WEIGHT = {None: 0, "baja": 1, "media": 2, "alta": 3}


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
    primary_technique_id: str | None = None,
) -> PrioritizationResult:
    """Resuelve materias normalizadas y su orden de planificación.

    Si `subjects` ya trae información explícita, la preserva y solo rellena los
    vacíos obvios con datos derivados del horario. Si no existe, crea una base
    mínima a partir de los bloques académicos confirmados.
    """

    active_blocks = _active_blocks(schedule_blocks)
    academic_stats = _academic_subject_stats(active_blocks)
    explicit_subjects = ensure_subject_items(subjects)

    if explicit_subjects:
        normalized_items, prioritized_subjects = _build_from_explicit_subjects(
            explicit_subjects,
            academic_stats=academic_stats,
            primary_technique_id=primary_technique_id,
        )
        return PrioritizationResult(
            subject_items=normalized_items,
            prioritized_subjects=prioritized_subjects,
            source="state.subjects",
        )

    if academic_stats:
        normalized_items, prioritized_subjects = _build_from_academic_schedule(
            academic_stats,
            primary_technique_id=primary_technique_id,
        )
        return PrioritizationResult(
            subject_items=normalized_items,
            prioritized_subjects=prioritized_subjects,
            source="derived_from_schedule",
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
    primary_technique_id: str | None,
) -> tuple[list[SubjectItem], list[PrioritizedSubject]]:
    normalized_items: list[SubjectItem] = []
    prioritized_subjects: list[PrioritizedSubject] = []

    for subject in subjects:
        if not subject.nombre.strip():
            continue
        stats = academic_stats.get(_normalize_title(subject.nombre), {})
        carga = _resolve_subject_load(subject, stats)
        normalized = subject.model_copy(
            update={
                "dificultad": max(1, min(int(subject.dificultad), 5)),
                "carga_semanal_min": carga,
                "origen": subject.origen or "manual",
            }
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

    sorted_subjects = _sort_prioritized_subjects(prioritized_subjects)
    index_by_name = {subject.nombre: position for position, subject in enumerate(sorted_subjects)}
    normalized_items.sort(key=lambda item: index_by_name.get(item.nombre, len(index_by_name)))
    return normalized_items, sorted_subjects


def _build_from_academic_schedule(
    academic_stats: dict[str, dict[str, object]],
    *,
    primary_technique_id: str | None,
) -> tuple[list[SubjectItem], list[PrioritizedSubject]]:
    subject_items: list[SubjectItem] = []
    prioritized_subjects: list[PrioritizedSubject] = []

    for stats in academic_stats.values():
        carga = int(stats["minutes"])
        subject = SubjectItem(
            nombre=str(stats["title"]),
            prioridad=_priority_from_class_minutes(carga),
            dificultad=3,
            urgencia=None,
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
) -> int:
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


def _normalize_title(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def _duration_minutes(start_time: str, end_time: str) -> int:
    return _to_minutes(end_time) - _to_minutes(start_time)


def _to_minutes(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)
