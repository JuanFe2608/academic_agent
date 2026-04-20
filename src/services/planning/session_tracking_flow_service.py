"""Capa conversacional para tracking de sesiones de estudio."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from repositories.planning.tracking_repository import StudyPlanInstanceSnapshot

from .tracking_service import StudySessionTrackingService, TrackStudySessionResult

_START_TERMS = {
    "empece",
    "empeze",
    "empecé",
    "inicie",
    "inicié",
    "arranque",
    "arranqué",
    "voy a estudiar",
    "voy a iniciar",
}
_COMPLETE_TERMS = {
    "termine",
    "terminé",
    "complete",
    "completé",
    "finalice",
    "finalicé",
    "ya estudie",
    "ya estudié",
    "ya hice",
    "hice la sesion",
    "hice la sesión",
}
_MISSED_TERMS = {
    "no pude estudiar",
    "no pude hacer",
    "no alcance",
    "no alcancé",
    "no estudie",
    "no estudié",
    "se me paso",
    "se me pasó",
    "perdi la sesion",
    "perdí la sesión",
}
_SKIP_TERMS = {
    "omitir",
    "omite",
    "saltar",
    "saltarme",
    "me salto",
    "no voy a poder",
    "cancela la sesion",
    "cancela la sesión",
}
_FEEDBACK_TERMS = {
    "avance",
    "avance parcial",
    "parcial",
    "la mitad",
    "mitad",
    "me falto",
    "me faltó",
    "entendi",
    "entendí",
    "repasar",
}
_SESSION_TERMS = {
    "sesion",
    "sesión",
    "bloque",
    "estudio",
    "estudiar",
    "repaso",
}
_STOPWORDS = {
    "estudio",
    "estudiar",
    "sesion",
    "sesión",
    "bloque",
    "de",
    "la",
    "el",
    "del",
    "para",
    "hoy",
    "ayer",
    "manana",
    "mañana",
}
_DAY_INDEX = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}


@dataclass(frozen=True)
class StudySessionTrackingIntent:
    """Intención parseada desde lenguaje natural."""

    detected: bool
    action: str | None = None
    source_text: str = ""
    completion_pct: int | None = None
    target_date: date | None = None
    explicit_instance_id: int | None = None


@dataclass(frozen=True)
class StudySessionTrackingFlowResult:
    """Resultado de aplicar tracking desde conversación."""

    detected: bool
    applied: bool = False
    message: str = ""
    action: str | None = None
    instance_id: int | None = None
    resulting_status: str | None = None
    requires_clarification: bool = False
    missing_fields: list[str] = field(default_factory=list)
    pending_payload: dict[str, object] = field(default_factory=dict)
    replan_required: bool = False
    replan_payload: dict[str, object] = field(default_factory=dict)
    error_code: str | None = None


def is_study_session_tracking_message(text: str | None) -> bool:
    """Detecta si un texto parece seguimiento de sesión de estudio."""

    return parse_study_session_tracking_intent(text).detected


def normalize_text(value: str | None) -> str:
    """Normalización local para evitar acoplar planning al paquete conversation."""

    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", normalized).strip()


def contains_any(text: str, phrases: set[str]) -> bool:
    """Indica si alguna frase aparece como termino o frase normalizada."""

    if not text:
        return False
    for phrase in phrases:
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase and re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", text):
            return True
    return False


def parse_study_session_tracking_intent(
    text: str | None,
    *,
    pending_payload: dict[str, object] | None = None,
    as_of: datetime | None = None,
) -> StudySessionTrackingIntent:
    """Parsea acciones de inicio, cierre, omisión, pérdida o avance parcial."""

    normalized = normalize_text(text)
    pending = dict(pending_payload or {})
    pending_action = str(pending.get("tracking_action") or "").strip() or None
    if not normalized and not pending_action:
        return StudySessionTrackingIntent(detected=False)

    action = _detect_tracking_action(normalized) or pending_action
    if action is None:
        return StudySessionTrackingIntent(detected=False)

    has_session_context = contains_any(normalized, _SESSION_TERMS) or bool(pending_action)
    if not has_session_context and action in {"start", "feedback"}:
        return StudySessionTrackingIntent(detected=False)

    original_text = str(pending.get("original_text") or "").strip()
    source_text = " ".join(part for part in (original_text, str(text or "").strip()) if part)
    effective_as_of = as_of or datetime.now(ZoneInfo("UTC"))
    return StudySessionTrackingIntent(
        detected=True,
        action=action,
        source_text=source_text or str(text or ""),
        completion_pct=_extract_completion_pct(normalized),
        target_date=_extract_target_date(normalized, effective_as_of),
        explicit_instance_id=_extract_instance_id(normalized),
    )


def apply_study_session_tracking_text(
    text: str,
    *,
    student_id: int | None,
    tracking_service: StudySessionTrackingService,
    timezone: str,
    interaction_payload: dict[str, object] | None = None,
    as_of: datetime | None = None,
) -> StudySessionTrackingFlowResult:
    """Resuelve la sesión referida por texto y aplica la transición de tracking."""

    effective_as_of = as_of or _now(timezone)
    pending_payload = (
        interaction_payload
        if str((interaction_payload or {}).get("domain") or "") == "session_tracking"
        else None
    )
    intent = parse_study_session_tracking_intent(
        text,
        pending_payload=pending_payload,
        as_of=effective_as_of,
    )
    if not intent.detected or intent.action is None:
        return StudySessionTrackingFlowResult(detected=False)

    if not student_id:
        return StudySessionTrackingFlowResult(
            detected=True,
            message=(
                "Todavia no puedo registrar esa sesion porque no encuentro tu perfil "
                "persistido. Termina el onboarding y vuelvo a intentarlo."
            ),
            action=intent.action,
            error_code="missing_student_id",
        )

    candidates = tracking_service.list_candidate_sessions(
        student_id=student_id,
        as_of=effective_as_of,
        days_before=14,
        days_after=14,
        limit=80,
    )
    resolved = _resolve_candidate(
        intent=intent,
        candidates=candidates,
        as_of=effective_as_of,
        last_instance_id=_last_instance_id(interaction_payload),
    )
    if resolved is None:
        return StudySessionTrackingFlowResult(
            detected=True,
            message=_clarification_message(intent),
            action=intent.action,
            requires_clarification=True,
            missing_fields=["study_session_reference"],
            pending_payload={
                "domain": "session_tracking",
                "tracking_action": intent.action,
                "original_text": intent.source_text,
            },
        )

    result = _apply_tracking_action(
        tracking_service=tracking_service,
        student_id=student_id,
        instance=resolved,
        intent=intent,
        as_of=effective_as_of,
    )
    if not result.tracked:
        return StudySessionTrackingFlowResult(
            detected=True,
            applied=False,
            message=_failure_message(result, resolved),
            action=intent.action,
            instance_id=resolved.id,
            resulting_status=result.resulting_status,
            error_code=result.error_code,
        )

    replan_required = intent.action in {"missed", "skip"}
    return StudySessionTrackingFlowResult(
        detected=True,
        applied=True,
        message=_success_message(intent.action, resolved, result),
        action=intent.action,
        instance_id=resolved.id,
        resulting_status=result.resulting_status,
        pending_payload={
            "domain": "session_tracking",
            "last_study_session_instance_id": resolved.id,
            "last_study_session_title": resolved.title,
            "last_study_session_status": result.resulting_status or resolved.status,
            "last_tracking_action": intent.action,
        },
        replan_required=replan_required,
        replan_payload=_replan_payload(intent, resolved, result) if replan_required else {},
    )


def _detect_tracking_action(normalized: str) -> str | None:
    if contains_any(normalized, _MISSED_TERMS):
        return "missed"
    if contains_any(normalized, _SKIP_TERMS):
        return "skip"
    if contains_any(normalized, _COMPLETE_TERMS):
        return "complete"
    if contains_any(normalized, _START_TERMS):
        return "start"
    if _extract_completion_pct(normalized) is not None or contains_any(normalized, _FEEDBACK_TERMS):
        return "feedback"
    return None


def _extract_completion_pct(normalized: str) -> int | None:
    match = re.search(r"(?<!\d)(100|[1-9]?\d)\s*%", normalized)
    if match:
        return max(0, min(100, int(match.group(1))))
    if "mitad" in normalized:
        return 50
    if "casi todo" in normalized:
        return 80
    return None


def _extract_instance_id(normalized: str) -> int | None:
    match = re.search(r"(?:sesion|instancia|bloque)\s*#?\s*(\d+)", normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_target_date(normalized: str, as_of: datetime) -> date | None:
    if "hoy" in normalized:
        return as_of.date()
    if "ayer" in normalized:
        return as_of.date() - timedelta(days=1)
    if "manana" in normalized or "mañana" in normalized:
        return as_of.date() + timedelta(days=1)
    for label, weekday in _DAY_INDEX.items():
        if contains_any(normalized, {label}):
            return _nearest_date_for_weekday(as_of.date(), weekday)
    return None


def _resolve_candidate(
    *,
    intent: StudySessionTrackingIntent,
    candidates: list[StudyPlanInstanceSnapshot],
    as_of: datetime,
    last_instance_id: int | None,
) -> StudyPlanInstanceSnapshot | None:
    if not candidates:
        return None
    if intent.explicit_instance_id is not None:
        for candidate in candidates:
            if candidate.id == intent.explicit_instance_id:
                return candidate

    scored = [
        (_candidate_score(candidate, intent, as_of, last_instance_id), candidate)
        for candidate in candidates
    ]
    scored = [(score, candidate) for score, candidate in scored if score > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], abs((item[1].starts_at - as_of).total_seconds()), item[1].id))
    return scored[0][1]


def _candidate_score(
    candidate: StudyPlanInstanceSnapshot,
    intent: StudySessionTrackingIntent,
    as_of: datetime,
    last_instance_id: int | None,
) -> int:
    score = _status_score(candidate.status, intent.action or "", candidate, as_of)
    if score <= 0:
        return 0

    normalized_text = normalize_text(intent.source_text)
    subject_mentioned = _mentions_subject(normalized_text, candidate)
    if _has_subject_reference(normalized_text):
        if not subject_mentioned:
            return 0
        score += 60

    if intent.target_date is not None:
        candidate_date = candidate.planned_date or candidate.starts_at.date()
        if candidate_date != intent.target_date:
            return 0
        score += 35

    if last_instance_id is not None and candidate.id == last_instance_id:
        score += 45

    hours = abs((candidate.starts_at - as_of).total_seconds()) / 3600
    score += max(0, 24 - int(hours))
    return score


def _status_score(
    status: str,
    action: str,
    candidate: StudyPlanInstanceSnapshot,
    as_of: datetime,
) -> int:
    if action == "start":
        return {"scheduled": 40, "in_progress": 20}.get(status, 0)
    if action == "complete":
        return {"in_progress": 55, "scheduled": 35, "completed": 5}.get(status, 0)
    if action == "skip":
        return {"scheduled": 45, "in_progress": 25}.get(status, 0)
    if action == "missed":
        if status not in {"scheduled", "in_progress"}:
            return 0
        return 50 if candidate.ends_at <= as_of else 25
    if action == "feedback":
        return {"in_progress": 45, "completed": 30, "scheduled": 25}.get(status, 0)
    return 0


def _mentions_subject(normalized_text: str, candidate: StudyPlanInstanceSnapshot) -> bool:
    candidate_text = normalize_text(
        " ".join(
            [
                candidate.title,
                str(candidate.payload.get("source_event_id") or ""),
                str(candidate.source_instance_key),
            ]
        )
    )
    for token in _significant_tokens(candidate_text):
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", normalized_text):
            return True
    return False


def _has_subject_reference(normalized_text: str) -> bool:
    tokens = _significant_tokens(normalized_text)
    return any(token not in _all_action_tokens() for token in tokens)


def _significant_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(text))
        if len(token) >= 4 and token not in {normalize_text(item) for item in _STOPWORDS}
    ]


def _all_action_tokens() -> set[str]:
    terms = _START_TERMS | _COMPLETE_TERMS | _MISSED_TERMS | _SKIP_TERMS | _FEEDBACK_TERMS | _SESSION_TERMS
    tokens: set[str] = set()
    for term in terms:
        tokens.update(_significant_tokens(term))
    return tokens


def _apply_tracking_action(
    *,
    tracking_service: StudySessionTrackingService,
    student_id: int,
    instance: StudyPlanInstanceSnapshot,
    intent: StudySessionTrackingIntent,
    as_of: datetime,
) -> TrackStudySessionResult:
    common = {
        "student_id": student_id,
        "study_plan_event_instance_id": instance.id,
        "actor_type": "student",
        "reported_at": as_of,
        "notes": intent.source_text,
        "checkin_payload": {
            "source": "conversation",
            "raw_text": intent.source_text,
            "tracking_action": intent.action,
        },
    }
    if intent.action == "start":
        return tracking_service.start_session(**common, actual_start_at=as_of)
    if intent.action == "complete":
        return tracking_service.complete_session(
            **common,
            actual_end_at=as_of,
            completion_pct=intent.completion_pct or 100,
        )
    if intent.action == "skip":
        return tracking_service.skip_session(**common)
    if intent.action == "missed":
        return tracking_service.mark_session_missed(**common)
    return tracking_service.record_partial_progress(
        **common,
        completion_pct=intent.completion_pct or 50,
    )


def _success_message(
    action: str | None,
    instance: StudyPlanInstanceSnapshot,
    result: TrackStudySessionResult,
) -> str:
    title = instance.title or "la sesion"
    if action == "start":
        return f"Listo, inicié el seguimiento de {title}."
    if action == "complete":
        return f"Listo, marqué como completada {title}."
    if action == "skip":
        return (
            f"Listo, marqué como omitida {title}. "
            "La dejaré como señal para replanificación."
        )
    if action == "missed":
        return (
            f"Entendido, marqué como perdida {title}. "
            "La dejaré como candidata para replanificación."
        )
    return (
        f"Registré tu avance en {title}. "
        f"Estado actual: {result.resulting_status or instance.status}."
    )


def _failure_message(
    result: TrackStudySessionResult,
    instance: StudyPlanInstanceSnapshot,
) -> str:
    if result.error_code in {"already_completed", "already_in_progress", "already_skipped", "already_missed"}:
        return f"Esa sesión ya estaba en estado {result.resulting_status or instance.status}."
    return (
        "No pude registrar ese seguimiento todavía. "
        f"Detalle: {result.error_code or result.detail or 'tracking_failed'}."
    )


def _clarification_message(intent: StudySessionTrackingIntent) -> str:
    action_label = {
        "start": "iniciar",
        "complete": "completar",
        "skip": "omitir",
        "missed": "marcar como perdida",
        "feedback": "registrar avance de",
    }.get(intent.action or "", "registrar")
    return (
        f"Necesito saber qué sesión quieres {action_label}. "
        "Puedes decirme la materia, el día o responder con algo como: "
        "`la de cálculo de hoy`."
    )


def _replan_payload(
    intent: StudySessionTrackingIntent,
    instance: StudyPlanInstanceSnapshot,
    result: TrackStudySessionResult,
) -> dict[str, object]:
    event_payload = dict(instance.payload.get("event") or {})
    return {
        "trigger": "missed_study_session" if intent.action == "missed" else "skipped_study_session",
        "study_plan_event_instance_id": instance.id,
        "study_plan_profile_id": instance.study_plan_profile_id,
        "title": instance.title,
        "planned_date": instance.planned_date.isoformat() if instance.planned_date else None,
        "starts_at": instance.starts_at.isoformat(),
        "ends_at": instance.ends_at.isoformat(),
        "source_event_id": str(event_payload.get("id") or instance.payload.get("source_event_id") or ""),
        "instance_payload": dict(instance.payload),
        "previous_status": result.previous_status,
        "resulting_status": result.resulting_status,
        "source_text": intent.source_text,
    }


def _last_instance_id(payload: dict[str, object] | None) -> int | None:
    raw_value = (payload or {}).get("last_study_session_instance_id")
    try:
        return int(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        return None


def _nearest_date_for_weekday(reference: date, weekday: int) -> date:
    delta = (weekday - reference.weekday()) % 7
    return reference + timedelta(days=delta)


def _now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota")))
    except Exception:
        return datetime.now(ZoneInfo("UTC"))


__all__ = [
    "StudySessionTrackingFlowResult",
    "StudySessionTrackingIntent",
    "apply_study_session_tracking_text",
    "is_study_session_tracking_message",
    "parse_study_session_tracking_intent",
]
