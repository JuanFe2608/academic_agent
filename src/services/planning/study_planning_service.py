"""Servicio determinista para construir un plan semanal inicial de estudio.

La meta de esta primera fase no es resolver todo el dominio de planificación,
ni introducir todavía prioridades conversacionales, CRUD académico o
replanificación. El objetivo es producir un plan semanal base a partir de:

- bloques fijos ya confirmados del horario,
- restricciones duras del estudiante,
- técnica(s) de estudio priorizadas por el Radar,
- materias explícitas del estado o, si no existen aún, materias derivadas del
  horario académico confirmado.

El resultado se serializa en `study_plan.plan_events` usando el mismo modelo de
`Event` que ya maneja el resto del sistema.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from services.personalization import get_technique
from services.priorities import PrioritizedSubject, resolve_prioritized_subjects
from services.priorities.state_helpers import ensure_subject_items
from services.scheduling.constants import DAY_LABELS, DAY_ORDER, SPANISH_TO_ENGLISH
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from schemas.planning import StudyPlanState
from schemas.scheduling import Event
from services.scheduling.validation import normalize_day as normalize_spanish_day
from services.scheduling.validation import new_event_id, sort_events, validate_event

from .state_helpers import ensure_constraints, ensure_study_profile

TECHNIQUE_SESSION_MINUTES = {
    "pomodoro": 25,
    "feynman": 50,
    "active_recall": 45,
    "cornell": 45,
    "mapas_conceptuales": 60,
    "mnemotecnia": 30,
    "repeticion_espaciada": 30,
    "interleaving": 40,
}

DEFAULT_SESSION_MINUTES = 45
SPACED_REPETITION_GAP_DAYS = 2
DEFAULT_GAP_DAYS = 1
@dataclass(frozen=True)
class SessionRequest:
    """Solicitud interna de una sesión de estudio concreta."""

    subject: PrioritizedSubject
    sequence_number: int


@dataclass(frozen=True)
class PlacementCandidate:
    """Posible ubicación válida para una sesión dentro de la semana."""

    day_of_week: str
    window_index: int
    start_minute: int
    duration_minutes: int
    score: tuple[int, int, int, int, int, int]


def build_initial_study_plan(
    *,
    schedule_blocks: list[WeeklyScheduleBlock | dict],
    subjects: list,
    study_profile: object,
    constraints: object,
    timezone: str,
    prioritized_subjects: list[PrioritizedSubject] | None = None,
    subject_source: str | None = None,
) -> StudyPlanState:
    """Construye un plan semanal inicial compatible con el estado actual.

    Parameters
    ----------
    schedule_blocks:
        Bloques fijos ya confirmados del horario semanal.
    subjects:
        Materias priorizadas explícitamente por el estado. Si no hay, se
        derivan del horario académico.
    study_profile:
        Resultado del Radar de estudio, del que se toma la técnica principal.
    constraints:
        Restricciones duras de sueño, duración de sesión y máximo diario.
    timezone:
        Zona horaria del estudiante para los eventos generados.
    """

    active_blocks = _active_blocks(schedule_blocks)
    normalized_constraints = ensure_constraints(constraints)
    normalized_profile = ensure_study_profile(study_profile)
    normalized_subjects = ensure_subject_items(subjects)

    if not active_blocks:
        return StudyPlanState(
            plan_events=[],
            rules={
                "planner_version": "study_planner_v1",
                "status": "skipped",
                "reason": "no_confirmed_schedule_blocks",
            },
        )

    top_techniques = _known_techniques(normalized_profile.top_techniques)
    primary_technique_id = top_techniques[0] if top_techniques else None
    primary_technique = _safe_get_technique(primary_technique_id)

    session_minutes = _resolve_session_minutes(
        primary_technique_id,
        normalized_constraints,
    )
    min_session_minutes = _resolve_min_session_minutes(
        normalized_constraints,
        session_minutes,
    )
    spacing_days = (
        SPACED_REPETITION_GAP_DAYS
        if primary_technique_id == "repeticion_espaciada"
        else DEFAULT_GAP_DAYS
    )
    interleave_subjects = "interleaving" in top_techniques[:2]

    if prioritized_subjects is None:
        priorities = resolve_prioritized_subjects(
            schedule_blocks=active_blocks,
            subjects=normalized_subjects,
            primary_technique_id=primary_technique_id,
        )
        planning_subjects = priorities.prioritized_subjects
        subject_source = priorities.source
    else:
        planning_subjects = list(prioritized_subjects)
        subject_source = subject_source or "state.subjects"
    requests = _build_session_requests(planning_subjects, interleave=interleave_subjects)

    available_windows = _build_available_windows(active_blocks, normalized_constraints)
    plan_events, unscheduled_requests = _allocate_sessions(
        requests=requests,
        available_windows=available_windows,
        session_minutes=session_minutes,
        min_session_minutes=min_session_minutes,
        max_study_per_day_min=normalized_constraints.max_study_per_day_min,
        spacing_days=spacing_days,
        timezone=timezone,
    )

    return StudyPlanState(
        plan_events=sort_events(plan_events),
        rules={
            "planner_version": "study_planner_v1",
            "status": "generated" if plan_events else "generated_empty",
            "primary_technique_id": primary_technique_id,
            "primary_technique_name": (
                primary_technique.display_name if primary_technique is not None else None
            ),
            "techniques_considered": list(top_techniques[:3]),
            "technique_support_hint": (
                primary_technique.support_hint if primary_technique is not None else None
            ),
            "session_minutes": session_minutes,
            "min_session_minutes": min_session_minutes,
            "spacing_days": spacing_days,
            "interleave_subjects": interleave_subjects,
            "max_study_per_day_min": normalized_constraints.max_study_per_day_min,
            "subjects_source": subject_source,
            "subjects_used": [
                {
                    "nombre": subject.nombre,
                    "prioridad": subject.prioridad,
                    "dificultad": subject.dificultad,
                    "urgencia": subject.urgencia,
                    "carga_semanal_min": subject.carga_semanal_min,
                    "weekly_sessions": subject.weekly_sessions,
                    "preferred_days": list(subject.preferred_days),
                    "planning_score": subject.planning_score,
                    "origen": subject.origen,
                }
                for subject in planning_subjects
            ],
            "unscheduled_requests": [
                {
                    "subject": request.subject.nombre,
                    "sequence_number": request.sequence_number,
                }
                for request in unscheduled_requests
            ],
        },
    )


def _active_blocks(schedule_blocks: list[WeeklyScheduleBlock | dict]) -> list[WeeklyScheduleBlock]:
    blocks: list[WeeklyScheduleBlock] = []
    for raw_block in schedule_blocks:
        block = ensure_weekly_block(raw_block)
        if block.is_active:
            blocks.append(block)
    return blocks


def _known_techniques(techniques: list[str]) -> list[str]:
    known: list[str] = []
    for technique_id in list(techniques or []):
        if _safe_get_technique(technique_id) is None:
            continue
        known.append(technique_id)
    return known


def _safe_get_technique(technique_id: str | None):
    if not technique_id:
        return None
    try:
        return get_technique(technique_id)
    except KeyError:
        return None


def _resolve_session_minutes(primary_technique_id: str | None, constraints) -> int:
    raw_recommended = TECHNIQUE_SESSION_MINUTES.get(
        primary_technique_id,
        DEFAULT_SESSION_MINUTES,
    )
    max_allowed = max(
        15,
        min(
            constraints.study_session_max,
            constraints.max_study_per_day_min,
        ),
    )
    min_allowed = min(max(15, constraints.study_session_min), max_allowed)
    return max(min_allowed, min(raw_recommended, max_allowed))


def _resolve_min_session_minutes(constraints, session_minutes: int) -> int:
    return min(max(15, constraints.study_session_min), session_minutes)


def _build_session_requests(
    subjects: list[PrioritizedSubject],
    *,
    interleave: bool,
) -> list[SessionRequest]:
    if not subjects:
        return []
    if not interleave:
        return [
            SessionRequest(subject=subject, sequence_number=index + 1)
            for subject in subjects
            for index in range(subject.weekly_sessions)
        ]

    remaining = {subject.nombre: subject.weekly_sessions for subject in subjects}
    by_name = {subject.nombre: subject for subject in subjects}
    counters = defaultdict(int)
    requests: list[SessionRequest] = []

    while any(count > 0 for count in remaining.values()):
        for subject in subjects:
            if remaining[subject.nombre] <= 0:
                continue
            counters[subject.nombre] += 1
            requests.append(
                SessionRequest(
                    subject=by_name[subject.nombre],
                    sequence_number=counters[subject.nombre],
                )
            )
            remaining[subject.nombre] -= 1
    return requests


def _build_available_windows(
    schedule_blocks: list[WeeklyScheduleBlock],
    constraints,
) -> dict[str, list[tuple[int, int]]]:
    busy_by_day: dict[str, list[tuple[int, int]]] = {day: [] for day in DAY_ORDER}
    for block in schedule_blocks:
        busy_by_day[block.day_of_week].append(
            (_to_minutes(block.start_time), _to_minutes(block.end_time))
        )
    for day, start_minute, end_minute in _unavailable_window_intervals(constraints):
        busy_by_day[day].append((start_minute, end_minute))

    awake_intervals = _awake_intervals(
        sleep_start=constraints.sleep_start,
        sleep_end=constraints.sleep_end,
    )

    pref_start = getattr(constraints, "preferred_study_start", None)
    pref_end = getattr(constraints, "preferred_study_end", None)
    if pref_start and pref_end:
        pref_start_min = _to_minutes(pref_start)
        pref_end_min = _to_minutes(pref_end)
        if pref_start_min < pref_end_min:
            preferred = _intersect_intervals(awake_intervals, [(pref_start_min, pref_end_min)])
            if preferred:
                awake_intervals = preferred

    available: dict[str, list[tuple[int, int]]] = {}
    for day in DAY_ORDER:
        merged_busy = _merge_intervals(busy_by_day[day])
        free_windows = list(awake_intervals)
        for interval in merged_busy:
            free_windows = _subtract_interval_list(free_windows, interval)
        available[day] = free_windows
    return available


def _unavailable_window_intervals(constraints) -> list[tuple[str, int, int]]:
    intervals: list[tuple[str, int, int]] = []
    windows = list(getattr(constraints, "unavailable_windows", []) or [])
    for window in windows:
        day = _normalize_constraint_day(_constraint_value(window, "day"))
        if day not in DAY_ORDER:
            continue
        try:
            start = _to_minutes(str(_constraint_value(window, "start_time") or ""))
            end = _to_minutes(str(_constraint_value(window, "end_time") or ""))
        except Exception:
            continue
        if start == end:
            continue
        if start < end:
            intervals.append((day, start, end))
            continue
        intervals.append((day, start, 24 * 60))
        next_day = DAY_ORDER[(DAY_ORDER.index(day) + 1) % len(DAY_ORDER)]
        intervals.append((next_day, 0, end))
    return intervals


def _constraint_value(window, key: str):
    if isinstance(window, dict):
        return window.get(key)
    return getattr(window, key, None)


def _normalize_constraint_day(value) -> str:
    raw = str(value or "").strip()
    if raw in DAY_ORDER:
        return raw
    try:
        spanish = normalize_spanish_day(raw)
    except ValueError:
        spanish = raw.title()
    return SPANISH_TO_ENGLISH.get(spanish, raw.lower())


def _awake_intervals(*, sleep_start: str, sleep_end: str) -> list[tuple[int, int]]:
    start = _to_minutes(sleep_start)
    end = _to_minutes(sleep_end)

    if start == end:
        return [(0, 24 * 60)]
    if start < end:
        return _merge_intervals([(0, start), (end, 24 * 60)])
    return [(end, start)]


def _intersect_intervals(
    a: list[tuple[int, int]],
    b: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for a_start, a_end in a:
        for b_start, b_end in b:
            lo = max(a_start, b_start)
            hi = min(a_end, b_end)
            if lo < hi:
                result.append((lo, hi))
    return result


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    clean = sorted(
        [(start, end) for start, end in intervals if end > start],
        key=lambda item: (item[0], item[1]),
    )
    if not clean:
        return []

    merged = [clean[0]]
    for start, end in clean[1:]:
        current_start, current_end = merged[-1]
        if start <= current_end:
            merged[-1] = (current_start, max(current_end, end))
            continue
        merged.append((start, end))
    return merged


def _subtract_interval_list(
    windows: list[tuple[int, int]],
    busy_interval: tuple[int, int],
) -> list[tuple[int, int]]:
    busy_start, busy_end = busy_interval
    remaining: list[tuple[int, int]] = []
    for window_start, window_end in windows:
        if busy_end <= window_start or busy_start >= window_end:
            remaining.append((window_start, window_end))
            continue
        if busy_start > window_start:
            remaining.append((window_start, busy_start))
        if busy_end < window_end:
            remaining.append((busy_end, window_end))
    return _merge_intervals(remaining)


def _allocate_sessions(
    *,
    requests: list[SessionRequest],
    available_windows: dict[str, list[tuple[int, int]]],
    session_minutes: int,
    min_session_minutes: int,
    max_study_per_day_min: int,
    spacing_days: int,
    timezone: str,
) -> tuple[list[Event], list[SessionRequest]]:
    events: list[Event] = []
    unscheduled_requests: list[SessionRequest] = []
    scheduled_minutes_by_day = {day: 0 for day in DAY_ORDER}
    subject_last_day_index: dict[str, int] = {}
    day_subjects: dict[str, set[str]] = {day: set() for day in DAY_ORDER}

    for request in requests:
        candidate = _find_best_candidate(
            request=request,
            available_windows=available_windows,
            scheduled_minutes_by_day=scheduled_minutes_by_day,
            max_study_per_day_min=max_study_per_day_min,
            spacing_days=spacing_days,
            subject_last_day_index=subject_last_day_index,
            day_subjects=day_subjects,
            target_duration=session_minutes,
            min_duration=session_minutes,
        )
        if candidate is None and min_session_minutes < session_minutes:
            candidate = _find_best_candidate(
                request=request,
                available_windows=available_windows,
                scheduled_minutes_by_day=scheduled_minutes_by_day,
                max_study_per_day_min=max_study_per_day_min,
                spacing_days=spacing_days,
                subject_last_day_index=subject_last_day_index,
                day_subjects=day_subjects,
                target_duration=session_minutes,
                min_duration=min_session_minutes,
            )

        if candidate is None:
            unscheduled_requests.append(request)
            continue

        end_minute = candidate.start_minute + candidate.duration_minutes
        available_windows[candidate.day_of_week] = _reserve_window(
            available_windows[candidate.day_of_week],
            candidate.window_index,
            candidate.start_minute,
            end_minute,
        )
        scheduled_minutes_by_day[candidate.day_of_week] += candidate.duration_minutes
        day_subjects[candidate.day_of_week].add(request.subject.nombre)
        subject_last_day_index[request.subject.nombre] = DAY_ORDER.index(candidate.day_of_week)

        event = Event(
            id=new_event_id(),
            dia=_event_day_label(candidate.day_of_week),
            inicio=_minutes_to_hhmm(candidate.start_minute),
            fin=_minutes_to_hhmm(end_minute),
            titulo=f"Estudio · {request.subject.nombre}",
            tipo="tentativo",
            categoria="estudio",
            origen="study_planner",
            prioridad=request.subject.prioridad,
            dificultad=request.subject.dificultad,
            timezone=timezone,
        )
        validate_event(event)
        events.append(event)

    return events, unscheduled_requests


def _find_best_candidate(
    *,
    request: SessionRequest,
    available_windows: dict[str, list[tuple[int, int]]],
    scheduled_minutes_by_day: dict[str, int],
    max_study_per_day_min: int,
    spacing_days: int,
    subject_last_day_index: dict[str, int],
    day_subjects: dict[str, set[str]],
    target_duration: int,
    min_duration: int,
) -> PlacementCandidate | None:
    best_candidate: PlacementCandidate | None = None

    for day_index, day_of_week in enumerate(DAY_ORDER):
        remaining_day_minutes = max_study_per_day_min - scheduled_minutes_by_day[day_of_week]
        if remaining_day_minutes < min_duration:
            continue
        if request.subject.nombre in day_subjects[day_of_week]:
            continue

        last_day_index = subject_last_day_index.get(request.subject.nombre)
        spacing_penalty = _spacing_penalty(day_index, last_day_index, spacing_days)
        preferred_penalty = _preferred_day_penalty(day_of_week, request.subject.preferred_days)

        for window_index, (window_start, window_end) in enumerate(available_windows[day_of_week]):
            allocatable = min(
                target_duration,
                remaining_day_minutes,
                window_end - window_start,
            )
            if allocatable < min_duration:
                continue

            candidate = PlacementCandidate(
                day_of_week=day_of_week,
                window_index=window_index,
                start_minute=window_start,
                duration_minutes=allocatable,
                score=(
                    spacing_penalty,
                    preferred_penalty,
                    scheduled_minutes_by_day[day_of_week],
                    day_index,
                    window_start,
                    -allocatable,
                ),
            )
            if best_candidate is None or candidate.score < best_candidate.score:
                best_candidate = candidate
    return best_candidate


def _spacing_penalty(
    current_day_index: int,
    last_day_index: int | None,
    spacing_days: int,
) -> int:
    if last_day_index is None:
        return 0
    gap = abs(current_day_index - last_day_index)
    if gap >= spacing_days:
        return 0
    return spacing_days - gap


def _preferred_day_penalty(day_of_week: str, preferred_days: tuple[str, ...]) -> int:
    if not preferred_days:
        return 0
    return 0 if day_of_week in preferred_days else 1


def _reserve_window(
    windows: list[tuple[int, int]],
    window_index: int,
    start_minute: int,
    end_minute: int,
) -> list[tuple[int, int]]:
    reserved: list[tuple[int, int]] = []
    for index, (window_start, window_end) in enumerate(windows):
        if index != window_index:
            reserved.append((window_start, window_end))
            continue
        if start_minute > window_start:
            reserved.append((window_start, start_minute))
        if end_minute < window_end:
            reserved.append((end_minute, window_end))
    return _merge_intervals(reserved)


def _event_day_label(day_of_week: str) -> str:
    label = DAY_LABELS[day_of_week]
    return label.replace("é", "e").replace("á", "a")
def _to_minutes(value: str) -> int:
    hours, minutes = value.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)


def _minutes_to_hhmm(value: int) -> str:
    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"
