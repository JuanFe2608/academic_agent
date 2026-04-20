"""Servicio de replanificacion controlada del plan de estudio."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from repositories.planning.replan_repository import (
    InMemoryStudyReplanRepository,
    StudyReplanRepository,
    StudyReplanRepositoryError,
    build_study_replan_repository,
)
from schemas.planning import StudyPlanState
from schemas.scheduling import Event
from services.scheduling.constants import DAY_LABELS as WEEKLY_DAY_LABELS
from services.scheduling.models import ensure_weekly_block
from services.scheduling.validation import DAY_ORDER, normalize_time, sort_events, validate_event

from .state_helpers import ensure_constraints, ensure_study_plan_state, study_plan_state_to_update
from .study_plan_sync_service import sync_subjects_and_study_plan

_TRACKING_REPLAN_TRIGGERS = {"missed_study_session", "skipped_study_session"}


@dataclass(frozen=True)
class StudyReplanProposalResult:
    """Resultado de generar una propuesta de replanificacion."""

    proposed: bool
    prompt_text: str = ""
    summary_text: str = ""
    reason_text: str = ""
    request_payload: dict[str, object] = field(default_factory=dict)
    proposal_payload: dict[str, object] = field(default_factory=dict)
    impact_payload: dict[str, object] = field(default_factory=dict)
    no_changes: bool = False
    error_code: str | None = None
    detail: str | None = None


class StudyReplanningService:
    """Construye propuestas antes de persistir cualquier replanificacion."""

    def __init__(self, repository: StudyReplanRepository | None = None) -> None:
        self.repository = repository

    def propose_replan(
        self,
        *,
        student_id: int | None,
        current_study_plan: StudyPlanState | dict | None,
        schedule_blocks: list,
        subjects: list,
        academic_activities: list | None,
        study_profile: object,
        constraints: object,
        timezone: str,
        replan_state: dict[str, object] | None,
        explicit_request_text: str | None = None,
        as_of: datetime | None = None,
    ) -> StudyReplanProposalResult:
        current_plan = ensure_study_plan_state(current_study_plan)
        replan = dict(replan_state or {})
        change_request = dict(replan.get("change_request") or {})
        trigger = _effective_trigger(replan, explicit_request_text)
        reason_text = _reason_text(trigger, change_request, explicit_request_text)
        if not current_plan.plan_events and not subjects:
            return StudyReplanProposalResult(
                proposed=False,
                no_changes=True,
                reason_text=reason_text,
                prompt_text=(
                    "Todavia no tengo un plan semanal base para replanificar. "
                    "Primero necesito que completes prioridades y plan de estudio."
                ),
                error_code="missing_current_study_plan",
            )

        try:
            sync_result = sync_subjects_and_study_plan(
                schedule_blocks=schedule_blocks,
                subjects=subjects,
                academic_activities=academic_activities,
                study_profile=study_profile,
                constraints=constraints,
                timezone=timezone,
            )
        except Exception as exc:
            return StudyReplanProposalResult(
                proposed=False,
                reason_text=reason_text,
                prompt_text=(
                    "No pude calcular una propuesta de replanificacion sin tocar tu plan actual."
                ),
                error_code="replan_planner_error",
                detail=str(exc),
            )

        candidate_plan = _plan_with_replan_metadata(
            sync_result.study_plan,
            trigger=trigger,
            reason_text=reason_text,
            current_plan=current_plan,
            as_of=as_of or _now(timezone),
        )
        candidate_plan = _apply_trigger_specific_adjustment(
            candidate_plan,
            current_plan=current_plan,
            schedule_blocks=schedule_blocks,
            constraints=constraints,
            timezone=timezone,
            trigger=trigger,
            change_request=change_request,
            as_of=as_of or _now(timezone),
        )
        impact_payload = _build_impact_payload(
            current_plan.plan_events,
            candidate_plan.plan_events,
            reason_text=reason_text,
        )
        if not _has_material_impact(impact_payload):
            return StudyReplanProposalResult(
                proposed=False,
                no_changes=True,
                reason_text=reason_text,
                prompt_text=(
                    "Revise tu plan y no encontre cambios necesarios por ahora. "
                    "Mantengo la version actual."
                ),
                impact_payload=impact_payload,
            )

        request_payload = {
            "trigger": trigger,
            "trigger_type": _repository_trigger_type(trigger),
            "reason_text": reason_text,
            "change_request": change_request,
            "explicit_request_text": explicit_request_text,
            "current_study_plan_profile_id": current_plan.persisted_profile_id,
            "generated_at": _iso_now(timezone),
        }
        study_plan_update = study_plan_state_to_update(candidate_plan)
        study_plan_update["plan_events"] = [_dump_model(event) for event in candidate_plan.plan_events]
        proposal_payload = {
            "study_plan": study_plan_update,
            "subjects": [_dump_model(item) for item in sync_result.subjects],
            "summary_text": _summary_text(impact_payload),
            "impact": impact_payload,
            "current_study_plan_profile_id": current_plan.persisted_profile_id,
            "replan_request_id": None,
            "replan_proposal_id": None,
            "proposal_number": None,
            "repository_error": None,
        }
        self._persist_request_and_proposal(
            student_id=student_id,
            request_payload=request_payload,
            proposal_payload=proposal_payload,
            impact_payload=impact_payload,
            summary_text=str(proposal_payload["summary_text"]),
        )
        prompt_text = _proposal_prompt(
            reason_text=reason_text,
            summary_text=str(proposal_payload["summary_text"]),
            impact_payload=impact_payload,
        )
        return StudyReplanProposalResult(
            proposed=True,
            prompt_text=prompt_text,
            summary_text=str(proposal_payload["summary_text"]),
            reason_text=reason_text,
            request_payload=request_payload,
            proposal_payload=proposal_payload,
            impact_payload=impact_payload,
        )

    def reject_replan(self, request_payload: dict[str, object] | None) -> None:
        request_id = _int_or_none((request_payload or {}).get("replan_request_id"))
        if not request_id or self.repository is None:
            return
        try:
            self.repository.mark_request_rejected(replan_request_id=request_id)
        except (StudyReplanRepositoryError, RepositoryConfigurationError):
            return

    def mark_applied(
        self,
        *,
        proposal_payload: dict[str, object] | None,
        resulting_study_plan_profile_id: int | None,
    ) -> None:
        proposal = dict(proposal_payload or {})
        request_id = _int_or_none(proposal.get("replan_request_id"))
        proposal_number = _int_or_none(proposal.get("proposal_number"))
        supersedes_id = _int_or_none(proposal.get("current_study_plan_profile_id"))
        resulting_id = _int_or_none(resulting_study_plan_profile_id)
        if (
            self.repository is None
            or not request_id
            or not proposal_number
            or not supersedes_id
            or not resulting_id
        ):
            return
        try:
            self.repository.mark_proposal_applied(
                replan_request_id=request_id,
                proposal_number=proposal_number,
                resulting_study_plan_profile_id=resulting_id,
                supersedes_study_plan_profile_id=supersedes_id,
            )
        except (StudyReplanRepositoryError, RepositoryConfigurationError):
            return

    def _persist_request_and_proposal(
        self,
        *,
        student_id: int | None,
        request_payload: dict[str, object],
        proposal_payload: dict[str, object],
        impact_payload: dict[str, object],
        summary_text: str,
    ) -> None:
        if self.repository is None or not student_id:
            return
        current_plan_id = _int_or_none(request_payload.get("current_study_plan_profile_id"))
        if not current_plan_id:
            return
        source_instance_id = _int_or_none(
            dict(request_payload.get("change_request") or {}).get("study_plan_event_instance_id")
        )
        trigger_type = str(request_payload.get("trigger_type") or "manual_review")
        if trigger_type == "missed_session" and not source_instance_id:
            return
        try:
            request = self.repository.create_request(
                student_id=int(student_id),
                current_study_plan_profile_id=current_plan_id,
                source_study_plan_event_instance_id=source_instance_id,
                trigger_type=trigger_type,
                reason_text=str(request_payload.get("reason_text") or "")[:500] or None,
                request_payload=_json_safe(request_payload),
            )
            request_payload["replan_request_id"] = request.request_id
            proposal_payload["replan_request_id"] = request.request_id
            proposal = self.repository.create_proposal(
                replan_request_id=request.request_id,
                summary_text=summary_text[:1000],
                proposal_payload=_json_safe(proposal_payload),
                impact_payload=_json_safe(impact_payload),
            )
            proposal_payload["replan_proposal_id"] = proposal.proposal_id
            proposal_payload["proposal_number"] = proposal.proposal_number
        except (StudyReplanRepositoryError, RepositoryConfigurationError) as exc:
            request_payload["repository_error"] = str(exc)
            proposal_payload["repository_error"] = str(exc)


def build_study_replanning_service() -> StudyReplanningService:
    """Construye el servicio de replanificacion segun el entorno."""

    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_STUDY_REPLAN_REPO", "").strip() == "1":
        return StudyReplanningService(repository=InMemoryStudyReplanRepository())
    return StudyReplanningService(
        repository=build_study_replan_repository(database_url_from_env())
    )


def is_replan_request_message(text: str | None) -> bool:
    """Detecta solicitudes explicitas de replanificacion."""

    normalized = _normalize_text(text)
    if not normalized:
        return False
    return bool(
        re.search(r"\b(replanifica|replanificar|replanificacion)\b", normalized)
        or re.search(r"\b(reagenda|reprograma|reorganiza|ajusta)\b", normalized)
        and re.search(r"\b(plan|semana|estudio|sesiones|cronograma)\b", normalized)
    )


def _effective_trigger(replan: dict[str, object], explicit_request_text: str | None) -> str:
    trigger = str(replan.get("trigger") or "").strip()
    if trigger:
        return trigger
    change_request = dict(replan.get("change_request") or {})
    trigger = str(change_request.get("trigger") or "").strip()
    if trigger:
        return trigger
    if is_replan_request_message(explicit_request_text):
        return "user_request"
    return "manual_review"


def _repository_trigger_type(trigger: str) -> str:
    if trigger in _TRACKING_REPLAN_TRIGGERS:
        return "missed_session"
    if trigger in {"fixed_schedule_change", "schedule_change", "availability_change"}:
        return "schedule_change"
    if trigger in {"academic_activity", "academic_deadline", "overload"}:
        return "overload"
    if trigger == "user_request":
        return "user_request"
    return "manual_review"


def _reason_text(
    trigger: str,
    change_request: dict[str, object],
    explicit_request_text: str | None,
) -> str:
    title = str(change_request.get("title") or change_request.get("activity_title") or "").strip()
    subject = str(change_request.get("subject_name") or "").strip()
    if trigger == "missed_study_session":
        return f"Sesion perdida: {title or 'sesion de estudio'}"
    if trigger == "skipped_study_session":
        return f"Sesion omitida: {title or 'sesion de estudio'}"
    if trigger in {"academic_activity", "academic_deadline"}:
        label = " ".join(part for part in (title, subject) if part).strip()
        return f"Cambio academico registrado: {label or 'actividad nueva'}"
    if trigger in {"fixed_schedule_change", "schedule_change"}:
        return "Cambio confirmado en el horario fijo"
    if trigger == "user_request":
        return str(explicit_request_text or "Solicitud directa del estudiante")[:180]
    return "Revision manual del plan de estudio"


def _plan_with_replan_metadata(
    plan: StudyPlanState,
    *,
    trigger: str,
    reason_text: str,
    current_plan: StudyPlanState,
    as_of: datetime,
) -> StudyPlanState:
    rules = dict(plan.rules or {})
    replan_payload = dict(rules.get("replan") or {})
    replan_payload.update(
        {
            "trigger": trigger,
            "reason": reason_text,
            "generated_at": as_of.isoformat(),
            "supersedes_study_plan_profile_id": current_plan.persisted_profile_id,
            "previous_version_number": current_plan.version_number,
        }
    )
    rules["replan"] = replan_payload
    rules["external_sync_status"] = "not_requested"
    rules["external_sync_requires_confirmation"] = True
    rules["external_sync_targets"] = ["outlook_calendar", "microsoft_todo"]
    return plan.model_copy(update={"rules": rules})


def _apply_trigger_specific_adjustment(
    candidate_plan: StudyPlanState,
    *,
    current_plan: StudyPlanState,
    schedule_blocks: list,
    constraints: object,
    timezone: str,
    trigger: str,
    change_request: dict[str, object],
    as_of: datetime,
) -> StudyPlanState:
    if trigger not in _TRACKING_REPLAN_TRIGGERS:
        return candidate_plan
    target = _find_tracking_target(candidate_plan.plan_events, current_plan.plan_events, change_request)
    if target is None:
        return candidate_plan
    duration = max(15, _event_duration_minutes(target))
    occupied = _occupied_intervals(
        schedule_blocks=schedule_blocks,
        plan_events=[event for event in candidate_plan.plan_events if _event_key(event) != _event_key(target)],
    )
    slot = _find_next_slot(
        occupied=occupied,
        constraints=constraints,
        duration_minutes=duration,
        timezone=timezone,
        change_request=change_request,
        fallback_day=target.dia,
        as_of=as_of,
    )
    if slot is None:
        return candidate_plan
    day, start, end = slot
    moved = target.model_copy(
        update={
            "dia": day,
            "inicio": start,
            "fin": end,
            "origen": "replan",
        }
    )
    updated_events = [
        moved if _event_key(event) == _event_key(target) else event
        for event in candidate_plan.plan_events
    ]
    return candidate_plan.model_copy(update={"plan_events": sort_events(updated_events)})


def _find_tracking_target(
    candidate_events: list[Event],
    current_events: list[Event],
    change_request: dict[str, object],
) -> Event | None:
    source_event_id = str(change_request.get("source_event_id") or "").strip()
    if source_event_id:
        for event in candidate_events:
            if str(event.id) == source_event_id:
                return event
    title = _normalize_text(str(change_request.get("title") or ""))
    if not title:
        payload = dict(change_request.get("instance_payload") or {})
        raw_event = payload.get("event")
        if isinstance(raw_event, dict):
            title = _normalize_text(str(raw_event.get("titulo") or ""))
    if title:
        for event in candidate_events:
            if _same_title(event.titulo, title):
                return event
    if source_event_id:
        for event in current_events:
            if str(event.id) == source_event_id:
                title = _normalize_text(event.titulo)
                break
        else:
            title = ""
        if title:
            for event in candidate_events:
                if _same_title(event.titulo, title):
                    return event
    return candidate_events[0] if candidate_events else None


def _build_impact_payload(
    current_events: list[Event],
    candidate_events: list[Event],
    *,
    reason_text: str,
) -> dict[str, object]:
    current_by_key = _events_by_semantic_key(current_events)
    candidate_by_key = _events_by_semantic_key(candidate_events)
    moved: list[dict[str, object]] = []
    new: list[dict[str, object]] = []
    canceled: list[dict[str, object]] = []

    for key, current in current_by_key.items():
        candidate = candidate_by_key.get(key)
        if candidate is None:
            canceled.append(_event_payload(current))
            continue
        if _slot_tuple(current) != _slot_tuple(candidate):
            moved.append(
                {
                    "title": candidate.titulo,
                    "from": _slot_label(current),
                    "to": _slot_label(candidate),
                    "reason": reason_text,
                }
            )

    for key, candidate in candidate_by_key.items():
        if key not in current_by_key:
            new.append(_event_payload(candidate))

    return {
        "reason": reason_text,
        "moved_sessions": moved,
        "new_sessions": new,
        "canceled_sessions": canceled,
        "current_event_count": len(current_events),
        "candidate_event_count": len(candidate_events),
    }


def _has_material_impact(impact_payload: dict[str, object]) -> bool:
    return bool(
        impact_payload.get("moved_sessions")
        or impact_payload.get("new_sessions")
        or impact_payload.get("canceled_sessions")
    )


def _summary_text(impact_payload: dict[str, object]) -> str:
    parts: list[str] = []
    moved = list(impact_payload.get("moved_sessions") or [])
    new = list(impact_payload.get("new_sessions") or [])
    canceled = list(impact_payload.get("canceled_sessions") or [])
    if moved:
        parts.append(f"{len(moved)} sesion(es) movida(s)")
    if new:
        parts.append(f"{len(new)} sesion(es) nueva(s)")
    if canceled:
        parts.append(f"{len(canceled)} sesion(es) cancelada(s)")
    return ", ".join(parts) if parts else "Sin cambios de sesiones"


def _proposal_prompt(
    *,
    reason_text: str,
    summary_text: str,
    impact_payload: dict[str, object],
) -> str:
    lines = [
        "Tengo una propuesta de replanificacion antes de aplicar cambios.",
        f"Razon: {reason_text}.",
        f"Impacto: {summary_text}.",
    ]
    detail_lines = _impact_detail_lines(impact_payload)
    if detail_lines:
        lines.append("")
        lines.extend(detail_lines)
    lines.extend(
        [
            "",
            "No sincronizare Outlook ni Microsoft To Do en esta fase.",
            "Confirmas que aplique esta nueva version del plan? Responde si o no.",
        ]
    )
    return "\n".join(lines)


def _impact_detail_lines(impact_payload: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for item in list(impact_payload.get("moved_sessions") or [])[:4]:
        lines.append(f"- Mover {item.get('title')}: {item.get('from')} -> {item.get('to')}")
    for item in list(impact_payload.get("new_sessions") or [])[:4]:
        lines.append(f"- Nueva: {item.get('title')} en {item.get('slot')}")
    for item in list(impact_payload.get("canceled_sessions") or [])[:4]:
        lines.append(f"- Cancelar: {item.get('title')} en {item.get('slot')}")
    return lines


def _events_by_semantic_key(events: list[Event]) -> dict[str, Event]:
    counters: dict[str, int] = {}
    result: dict[str, Event] = {}
    for event in sort_events(list(events)):
        title = _normalize_text(event.titulo)
        counters[title] = counters.get(title, 0) + 1
        result[f"{title}#{counters[title]}"] = event
    return result


def _event_payload(event: Event) -> dict[str, object]:
    return {
        "id": event.id,
        "title": event.titulo,
        "slot": _slot_label(event),
        "day": event.dia,
        "start": event.inicio,
        "end": event.fin,
    }


def _slot_tuple(event: Event) -> tuple[str, str, str]:
    return event.dia, event.inicio, event.fin


def _slot_label(event: Event) -> str:
    return f"{event.dia} {event.inicio}-{event.fin}"


def _same_title(left: str, normalized_right: str) -> bool:
    left_normalized = _normalize_text(left)
    right = _normalize_text(normalized_right)
    if not left_normalized or not right:
        return False
    return left_normalized == right or left_normalized in right or right in left_normalized


def _event_key(event: Event) -> tuple[str, str]:
    return _normalize_text(event.titulo), str(event.id)


def _event_duration_minutes(event: Event) -> int:
    return _to_minutes(event.fin) - _to_minutes(event.inicio)


def _occupied_intervals(*, schedule_blocks: list, plan_events: list[Event]) -> dict[str, list[tuple[int, int]]]:
    occupied: dict[str, list[tuple[int, int]]] = {day: [] for day in DAY_ORDER}
    for raw_block in schedule_blocks or []:
        try:
            block = ensure_weekly_block(raw_block)
        except Exception:
            continue
        if not block.is_active:
            continue
        day_label = WEEKLY_DAY_LABELS.get(block.day_of_week, block.day_of_week)
        occupied.setdefault(day_label, [])
        occupied[day_label].append((_to_minutes(block.start_time), _to_minutes(block.end_time)))
    for event in plan_events:
        try:
            validate_event(event)
        except ValueError:
            continue
        occupied[event.dia].append((_to_minutes(event.inicio), _to_minutes(event.fin)))
    return {day: _merge_intervals(intervals) for day, intervals in occupied.items()}


def _find_next_slot(
    *,
    occupied: dict[str, list[tuple[int, int]]],
    constraints: object,
    duration_minutes: int,
    timezone: str,
    change_request: dict[str, object],
    fallback_day: str,
    as_of: datetime,
) -> tuple[str, str, str] | None:
    normalized_constraints = ensure_constraints(constraints)
    awake_windows = _awake_windows(
        sleep_start=normalized_constraints.sleep_start,
        sleep_end=normalized_constraints.sleep_end,
    )
    start_day_index = _start_day_index(change_request, fallback_day, timezone, as_of)
    for offset in range(1, len(DAY_ORDER) + 1):
        day = DAY_ORDER[(start_day_index + offset) % len(DAY_ORDER)]
        free_windows = list(awake_windows)
        for busy in occupied.get(day, []):
            free_windows = _subtract_interval_list(free_windows, busy)
        for start, end in free_windows:
            cursor = _round_up_to_step(start, 15)
            while cursor + duration_minutes <= end:
                return day, _minutes_to_hhmm(cursor), _minutes_to_hhmm(cursor + duration_minutes)
                cursor += 15
    return None


def _start_day_index(
    change_request: dict[str, object],
    fallback_day: str,
    timezone: str,
    as_of: datetime,
) -> int:
    planned_date = _parse_date(change_request.get("planned_date"))
    if planned_date is not None:
        return planned_date.weekday()
    try:
        return DAY_ORDER.index(fallback_day)
    except ValueError:
        try:
            return as_of.astimezone(ZoneInfo(timezone)).weekday()
        except Exception:
            return as_of.weekday()


def _awake_windows(*, sleep_start: str, sleep_end: str) -> list[tuple[int, int]]:
    start = _to_minutes(sleep_start)
    end = _to_minutes(sleep_end)
    if start == end:
        return [(0, 24 * 60)]
    if start < end:
        return _merge_intervals([(0, start), (end, 24 * 60)])
    return [(end, start)]


def _subtract_interval_list(
    windows: list[tuple[int, int]],
    blocked: tuple[int, int],
) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    blocked_start, blocked_end = blocked
    for start, end in windows:
        if blocked_end <= start or blocked_start >= end:
            result.append((start, end))
            continue
        if blocked_start > start:
            result.append((start, blocked_start))
        if blocked_end < end:
            result.append((blocked_end, end))
    return result


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    clean = sorted((start, end) for start, end in intervals if end > start)
    if not clean:
        return []
    merged = [clean[0]]
    for start, end in clean[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _to_minutes(value: str) -> int:
    normalized = normalize_time(value)
    hours, minutes = normalized.split(":", maxsplit=1)
    return int(hours) * 60 + int(minutes)


def _minutes_to_hhmm(value: int) -> str:
    bounded = max(0, min(24 * 60, value))
    return f"{bounded // 60:02d}:{bounded % 60:02d}"


def _round_up_to_step(value: int, step: int) -> int:
    remainder = value % step
    return value if remainder == 0 else value + (step - remainder)


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _dump_model(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def _json_safe(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return {}


def _json_safe_value(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_text(value: str | None) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota")))
    except Exception:
        return datetime.now(ZoneInfo("UTC"))


def _iso_now(timezone: str) -> str:
    return _now(timezone).isoformat()


__all__ = [
    "StudyReplanProposalResult",
    "StudyReplanningService",
    "build_study_replanning_service",
    "is_replan_request_message",
]
