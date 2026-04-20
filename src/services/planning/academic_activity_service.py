"""Dominio deterministico para actividades academicas puntuales."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from schemas.common import Prioridad
from schemas.planning import AcademicActivity, AcademicActivityType, SubjectItem

_ACTIVITY_TYPE_KEYWORDS: dict[AcademicActivityType, set[str]] = {
    "parcial": {"parcial", "examen", "evaluacion", "final"},
    "quiz": {"quiz", "quices", "control", "prueba corta"},
    "tarea": {"tarea", "deber"},
    "taller": {"taller"},
    "entrega": {"entrega", "trabajo"},
    "exposicion": {"exposicion", "presentacion"},
    "proyecto": {"proyecto"},
    "estudio_pendiente": {
        "estudio pendiente",
        "sesion de estudio",
        "pendiente estudiar",
        "tengo que estudiar",
    },
}
_TYPE_LABELS: dict[str, str] = {
    "parcial": "parcial",
    "quiz": "quiz",
    "tarea": "tarea",
    "taller": "taller",
    "entrega": "entrega",
    "exposicion": "exposicion",
    "proyecto": "proyecto",
    "estudio_pendiente": "estudio pendiente",
}
_LIST_TERMS = {
    "listar",
    "lista",
    "mostrar",
    "muestra",
    "ver",
    "pendientes",
    "actividades",
}
_DELETE_TERMS = {"borra", "borrar", "elimina", "eliminar", "quita", "quitar"}
_UPDATE_TERMS = {
    "cambia",
    "cambiar",
    "editar",
    "edita",
    "modifica",
    "modificar",
    "mueve",
    "mover",
    "reprograma",
    "reprogramar",
    "aplaza",
    "aplazar",
    "adelanta",
    "adelantar",
}
_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
_DATE_STOP_TOKENS = {
    "hoy",
    "manana",
    "pasado",
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
}
_SUBJECT_STOP_TOKENS = {
    *list(_WEEKDAYS),
    "hoy",
    "manana",
    "pasado",
    "el",
    "la",
    "las",
    "los",
    "para",
    "antes",
    "vence",
    "a",
    "con",
    "prioridad",
    "urgente",
    "dificultad",
    "dificil",
    "facil",
    "hora",
    "horas",
    "min",
    "minutos",
}
_MISSING_LABELS = {
    "activity_type": "tipo de actividad",
    "subject_name": "materia",
    "due_date": "fecha",
    "activity_reference": "actividad exacta",
    "change_detail": "dato a cambiar",
}


@dataclass(frozen=True)
class AcademicActivityParseResult:
    """Resultado de interpretar una solicitud sobre actividades puntuales."""

    detected: bool
    action: str = "unknown"
    slots: dict[str, object] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    pending_payload: dict[str, object] = field(default_factory=dict)
    confirmation_payload: dict[str, object] = field(default_factory=dict)
    activities: list[AcademicActivity] = field(default_factory=list)
    message: str = ""
    requires_confirmation: bool = False
    requires_clarification: bool = False


@dataclass(frozen=True)
class AcademicActivityApplyResult:
    """Resultado de aplicar una operacion ya confirmada."""

    applied: bool
    action: str
    activities: list[AcademicActivity]
    activity: AcademicActivity | None = None
    message: str = ""
    replan_required: bool = False
    payload: dict[str, object] = field(default_factory=dict)


def parse_academic_activity_request(
    text: str | None,
    *,
    existing_activities: list[AcademicActivity | dict] | None,
    subjects: list[SubjectItem | dict] | None,
    reference_date: date,
    timezone: str,
    pending_payload: dict[str, object] | None = None,
) -> AcademicActivityParseResult:
    """Extrae intencion y slots de una solicitud conversacional."""

    normalized_text = _normalize(text)
    pending = _valid_pending_payload(pending_payload)
    subject_names = _subject_names(subjects)
    activities = coerce_academic_activities(existing_activities)
    if not normalized_text and not pending:
        return AcademicActivityParseResult(detected=False, activities=activities)

    action = _detect_action(normalized_text)
    if pending and action == "unknown":
        action = str(pending.get("operation") or "create")

    slots = _extract_slots(
        text,
        subject_names=subject_names,
        reference_date=reference_date,
        timezone=timezone,
    )
    if pending and action in {"create", "update"}:
        slots = _merge_slots(dict(pending.get("slots") or {}), slots)

    if action == "list":
        active = active_academic_activities(activities)
        return AcademicActivityParseResult(
            detected=True,
            action="list",
            activities=active,
            message=render_activity_list(active),
        )

    if action == "delete":
        matches = match_academic_activities(activities, slots=slots, text=text)
        if len(matches) != 1:
            return _clarify_activity_reference("delete", matches, activities, slots)
        activity = matches[0]
        payload = {
            "domain": "activity_management",
            "operation": "delete",
            "activity_id": activity.activity_id,
            "activity": activity.model_dump(mode="python"),
        }
        return AcademicActivityParseResult(
            detected=True,
            action="delete",
            slots=slots,
            confirmation_payload=payload,
            message=f"Voy a eliminar {format_activity_brief(activity)}. Confirma con si o no.",
            requires_confirmation=True,
        )

    if action == "update":
        matches = match_academic_activities(activities, slots=slots, text=text)
        if len(matches) != 1:
            return _clarify_activity_reference("update", matches, activities, slots)
        changes = _editable_changes(slots)
        if not changes:
            return AcademicActivityParseResult(
                detected=True,
                action="update",
                slots=slots,
                missing_fields=["change_detail"],
                pending_payload={
                    "domain": "activity_management",
                    "operation": "update",
                    "activity_id": matches[0].activity_id,
                    "slots": slots,
                },
                message="Que quieres cambiar de esa actividad? Puedes responder: viernes, 2 horas, prioridad alta o dificultad 4.",
                requires_clarification=True,
            )
        preview = _preview_activity_update(matches[0], changes, timezone=timezone)
        payload = {
            "domain": "activity_management",
            "operation": "update",
            "activity_id": matches[0].activity_id,
            "changes": changes,
            "activity": preview.model_dump(mode="python"),
        }
        return AcademicActivityParseResult(
            detected=True,
            action="update",
            slots=slots,
            confirmation_payload=payload,
            message=(
                f"Voy a dejar {format_activity_brief(matches[0])} como "
                f"{format_activity_brief(preview)}. Confirma con si o no."
            ),
            requires_confirmation=True,
        )

    if action in {"create", "unknown"} and (pending or _looks_like_activity_request(normalized_text)):
        missing = _missing_create_fields(slots)
        if missing:
            payload = {
                "domain": "activity_management",
                "operation": "create",
                "slots": slots,
                "raw_text": str(text or pending.get("raw_text") if pending else text or ""),
            }
            return AcademicActivityParseResult(
                detected=True,
                action="create",
                slots=slots,
                missing_fields=missing,
                pending_payload=payload,
                message=_missing_prompt(missing, slots),
                requires_clarification=True,
            )
        activity = build_activity_from_slots(slots, source_text=str(text or ""), timezone=timezone)
        payload = {
            "domain": "activity_management",
            "operation": "create",
            "activity": activity.model_dump(mode="python"),
            "slots": slots,
        }
        return AcademicActivityParseResult(
            detected=True,
            action="create",
            slots=slots,
            confirmation_payload=payload,
            message=f"Voy a registrar {format_activity_brief(activity)}. Confirma con si o no.",
            requires_confirmation=True,
        )

    return AcademicActivityParseResult(detected=False, activities=activities)


def apply_confirmed_academic_activity_operation(
    activities: list[AcademicActivity | dict] | None,
    payload: dict[str, object],
    *,
    timezone: str,
    reference_date: date,
) -> AcademicActivityApplyResult:
    """Aplica una operacion confirmada sobre la lista canonica."""

    normalized = coerce_academic_activities(activities)
    operation = str(payload.get("operation") or "")
    now = _now_iso(timezone)

    if operation == "create":
        raw_activity = dict(payload.get("activity") or {})
        activity = ensure_academic_activity(raw_activity).model_copy(
            update={
                "created_at": raw_activity.get("created_at") or now,
                "updated_at": now,
                "status": raw_activity.get("status") or "pending",
            }
        )
        updated = [item for item in normalized if item.activity_id != activity.activity_id]
        updated.append(activity)
        updated = sort_academic_activities(updated)
        return AcademicActivityApplyResult(
            applied=True,
            action="create",
            activities=updated,
            activity=activity,
            message=f"Listo. Registre {format_activity_brief(activity)}.",
            replan_required=_activity_requires_replan(activity, reference_date=reference_date),
            payload=_operation_payload(operation, activity),
        )

    if operation == "update":
        activity_id = str(payload.get("activity_id") or "")
        changes = dict(payload.get("changes") or {})
        updated: list[AcademicActivity] = []
        changed_activity: AcademicActivity | None = None
        for activity in normalized:
            if activity.activity_id != activity_id:
                updated.append(activity)
                continue
            changed_activity = _preview_activity_update(
                activity,
                changes,
                timezone=timezone,
            ).model_copy(update={"updated_at": now})
            updated.append(changed_activity)
        if changed_activity is None:
            return AcademicActivityApplyResult(
                applied=False,
                action="update",
                activities=normalized,
                message="No encontre esa actividad para actualizarla.",
            )
        updated = sort_academic_activities(updated)
        return AcademicActivityApplyResult(
            applied=True,
            action="update",
            activities=updated,
            activity=changed_activity,
            message=f"Listo. Actualice {format_activity_brief(changed_activity)}.",
            replan_required=True,
            payload=_operation_payload(operation, changed_activity),
        )

    if operation == "delete":
        activity_id = str(payload.get("activity_id") or "")
        updated = []
        deleted_activity: AcademicActivity | None = None
        for activity in normalized:
            if activity.activity_id != activity_id:
                updated.append(activity)
                continue
            deleted_activity = activity.model_copy(
                update={"status": "deleted", "updated_at": now}
            )
            updated.append(deleted_activity)
        if deleted_activity is None:
            return AcademicActivityApplyResult(
                applied=False,
                action="delete",
                activities=normalized,
                message="No encontre esa actividad para eliminarla.",
            )
        return AcademicActivityApplyResult(
            applied=True,
            action="delete",
            activities=sort_academic_activities(updated),
            activity=deleted_activity,
            message=f"Listo. Elimine {format_activity_brief(deleted_activity)}.",
            replan_required=True,
            payload=_operation_payload(operation, deleted_activity),
        )

    return AcademicActivityApplyResult(
        applied=False,
        action=operation or "unknown",
        activities=normalized,
        message="No encontre una operacion de actividad academica para aplicar.",
    )


def build_activity_from_slots(
    slots: dict[str, object],
    *,
    source_text: str,
    timezone: str,
) -> AcademicActivity:
    """Construye una actividad validada a partir de slots completos."""

    now = _now_iso(timezone)
    activity_type = str(slots.get("activity_type") or "tarea")
    subject_name = str(slots.get("subject_name") or "").strip()
    title = str(slots.get("activity_title") or "").strip()
    if not title:
        title = _default_title(activity_type, subject_name)
    return AcademicActivity(
        activity_type=activity_type,  # type: ignore[arg-type]
        subject_name=subject_name,
        activity_title=title,
        due_date=_optional_str(slots.get("due_date")),
        due_time=_optional_str(slots.get("due_time")),
        estimated_effort_minutes=_optional_int(slots.get("estimated_effort_minutes")),
        priority_level=_optional_priority(slots.get("priority_level")),
        difficulty_level=_optional_int(slots.get("difficulty_level")),
        status="pending",
        source_text=source_text or None,
        created_at=now,
        updated_at=now,
    )


def ensure_academic_activity(raw_item: AcademicActivity | dict) -> AcademicActivity:
    if isinstance(raw_item, AcademicActivity):
        return raw_item.model_copy(deep=True)
    return AcademicActivity(**dict(raw_item))


def coerce_academic_activities(
    raw_items: list[AcademicActivity | dict] | None,
) -> list[AcademicActivity]:
    return [ensure_academic_activity(item) for item in list(raw_items or [])]


def active_academic_activities(
    activities: list[AcademicActivity | dict] | None,
) -> list[AcademicActivity]:
    return [
        activity
        for activity in sort_academic_activities(coerce_academic_activities(activities))
        if activity.status != "deleted"
    ]


def sort_academic_activities(activities: list[AcademicActivity]) -> list[AcademicActivity]:
    return sorted(
        activities,
        key=lambda activity: (
            activity.status == "deleted",
            activity.due_date or "9999-12-31",
            activity.due_time or "23:59",
            _normalize(activity.subject_name),
            _normalize(activity.activity_title),
        ),
    )


def match_academic_activities(
    activities: list[AcademicActivity | dict] | None,
    *,
    slots: dict[str, object] | None = None,
    text: str | None = None,
) -> list[AcademicActivity]:
    """Busca una actividad activa por tipo, materia o titulo."""

    candidates = active_academic_activities(activities)
    normalized_text = _normalize(text)
    data = dict(slots or {})
    subject = _normalize(_optional_str(data.get("subject_name")))
    activity_type = _normalize(_optional_str(data.get("activity_type")))
    title = _normalize(_optional_str(data.get("activity_title")))
    default_title = _normalize(_default_title(activity_type, subject)) if activity_type and subject else ""

    if subject:
        candidates = [
            activity
            for activity in candidates
            if subject in _normalize(activity.subject_name)
            or _normalize(activity.subject_name) in subject
        ]
    if activity_type:
        candidates = [
            activity
            for activity in candidates
            if _normalize(activity.activity_type) == activity_type
        ]
    if title and title != default_title:
        candidates = [
            activity
            for activity in candidates
            if title in _normalize(activity.activity_title)
            or title in _normalize(activity.subject_name)
        ]
    if normalized_text and not (subject or activity_type or title):
        textual_matches = [
            activity
            for activity in candidates
            if _normalize(activity.subject_name) in normalized_text
            or _normalize(activity.activity_type) in normalized_text
            or _normalize(activity.activity_title) in normalized_text
        ]
        if textual_matches:
            candidates = textual_matches
    return candidates


def render_activity_list(activities: list[AcademicActivity | dict] | None) -> str:
    """Renderiza una lista breve de actividades pendientes."""

    active = active_academic_activities(activities)
    if not active:
        return "No tengo actividades academicas pendientes registradas."
    lines = ["Actividades pendientes:"]
    for index, activity in enumerate(active, start=1):
        lines.append(f"{index}. {format_activity_brief(activity)}")
    return "\n".join(lines)


def format_activity_brief(activity: AcademicActivity | dict) -> str:
    item = ensure_academic_activity(activity)
    label = _TYPE_LABELS.get(item.activity_type, str(item.activity_type).replace("_", " "))
    due = item.due_date or "sin fecha"
    if item.due_time:
        due = f"{due} {item.due_time}"
    effort = (
        f", esfuerzo {item.estimated_effort_minutes} min"
        if item.estimated_effort_minutes
        else ""
    )
    priority = f", prioridad {item.priority_level}" if item.priority_level else ""
    return f"{label} de {item.subject_name} para {due}{effort}{priority}"


def priority_update_text_for_activity(activity: AcademicActivity) -> str | None:
    """Construye un texto compatible con el calculo de prioridad semanal."""

    if not activity.due_date or activity.activity_type == "estudio_pendiente":
        return None
    try:
        parsed_date = date.fromisoformat(activity.due_date)
    except ValueError:
        return None
    compatible_type = activity.activity_type
    if compatible_type in {"tarea", "proyecto"}:
        compatible_type = "entrega"  # El scoring semanal agrupa tareas/proyectos como entregas.
    if compatible_type == "taller":
        compatible_type = "actividad"
    return (
        f"{compatible_type} de {activity.subject_name} "
        f"{parsed_date.day:02d}/{parsed_date.month:02d}/{parsed_date.year}"
    )


def _detect_action(normalized_text: str) -> str:
    if not normalized_text:
        return "unknown"
    if _contains_any(normalized_text, _DELETE_TERMS):
        return "delete"
    if _contains_any(normalized_text, _UPDATE_TERMS):
        return "update"
    if _contains_any(normalized_text, _LIST_TERMS) and (
        "actividad" in normalized_text
        or "pendiente" in normalized_text
        or _detect_activity_type(normalized_text)
    ):
        return "list"
    if _looks_like_activity_request(normalized_text):
        return "create"
    return "unknown"


def _looks_like_activity_request(normalized_text: str) -> bool:
    return bool(_detect_activity_type(normalized_text))


def _extract_slots(
    text: str | None,
    *,
    subject_names: list[str],
    reference_date: date,
    timezone: str,
) -> dict[str, object]:
    normalized_text = _normalize(text)
    slots: dict[str, object] = {}
    activity_type = _detect_activity_type(normalized_text)
    if activity_type:
        slots["activity_type"] = activity_type

    due_date = _resolve_due_date(normalized_text, reference_date=reference_date)
    if due_date:
        slots["due_date"] = due_date
    due_time = _resolve_due_time(normalized_text)
    if due_time:
        slots["due_time"] = due_time

    effort = _resolve_effort_minutes(normalized_text)
    if effort:
        slots["estimated_effort_minutes"] = effort
    priority = _resolve_priority(normalized_text)
    if priority:
        slots["priority_level"] = priority
    difficulty = _resolve_difficulty(normalized_text)
    if difficulty:
        slots["difficulty_level"] = difficulty

    subject_name = _extract_subject_name(
        text,
        normalized_text,
        subject_names=subject_names,
        activity_type=activity_type,
    )
    if subject_name:
        slots["subject_name"] = subject_name

    if activity_type and subject_name:
        slots["activity_title"] = _extract_activity_title(
            normalized_text,
            activity_type=activity_type,
            subject_name=subject_name,
        )
    return slots


def _detect_activity_type(normalized_text: str) -> AcademicActivityType | None:
    for activity_type, keywords in _ACTIVITY_TYPE_KEYWORDS.items():
        if _contains_any(normalized_text, keywords):
            return activity_type
    return None


def _extract_subject_name(
    raw_text: str | None,
    normalized_text: str,
    *,
    subject_names: list[str],
    activity_type: AcademicActivityType | None,
) -> str | None:
    del activity_type
    known_matches = [
        subject
        for subject in subject_names
        if _normalize(subject) and _contains_phrase(normalized_text, _normalize(subject))
    ]
    if len(known_matches) == 1:
        return known_matches[0]

    tokens = normalized_text.split()
    for index, token in enumerate(tokens):
        if token not in {"de", "para", "sobre", "en"}:
            continue
        if index + 1 >= len(tokens) or tokens[index + 1] in _DATE_STOP_TOKENS:
            continue
        collected: list[str] = []
        for candidate in tokens[index + 1 :]:
            if candidate in _SUBJECT_STOP_TOKENS:
                break
            if re.fullmatch(r"\d{1,2}(?::\d{2})?", candidate):
                break
            if "/" in candidate:
                break
            collected.append(candidate)
        candidate_name = _clean_subject_candidate(" ".join(collected))
        if candidate_name:
            return _title_case(candidate_name)

    if _looks_like_subject_only(normalized_text):
        candidate = _clean_subject_candidate(normalized_text)
        if candidate:
            return _title_case(candidate)

    del raw_text
    return None


def _extract_activity_title(
    normalized_text: str,
    *,
    activity_type: str,
    subject_name: str,
) -> str:
    del normalized_text
    return _default_title(activity_type, subject_name)


def _resolve_due_date(normalized_text: str, *, reference_date: date) -> str | None:
    if "pasado manana" in normalized_text:
        return (reference_date + timedelta(days=2)).isoformat()
    if "manana" in normalized_text:
        return (reference_date + timedelta(days=1)).isoformat()
    if "hoy" in normalized_text:
        return reference_date.isoformat()
    for token, weekday in _WEEKDAYS.items():
        if not _contains_phrase(normalized_text, token):
            continue
        days_ahead = weekday - reference_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return (reference_date + timedelta(days=days_ahead)).isoformat()
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", normalized_text)
    if iso_match:
        try:
            return date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            ).isoformat()
        except ValueError:
            return None
    date_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normalized_text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        raw_year = date_match.group(3)
        year = reference_date.year if raw_year is None else int(raw_year)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _resolve_due_time(normalized_text: str) -> str | None:
    match = re.search(
        r"\b(?:a las|para las|antes de las|vence a las)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
        normalized_text,
    )
    if match is None:
        match = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?\b", normalized_text)
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").replace(".", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _resolve_effort_minutes(normalized_text: str) -> int | None:
    hour_match = re.search(r"\b(\d{1,2})\s*(?:h|hora|horas)\b", normalized_text)
    if hour_match:
        return int(hour_match.group(1)) * 60
    minute_match = re.search(r"\b(\d{1,3})\s*(?:min|minuto|minutos)\b", normalized_text)
    if minute_match:
        return int(minute_match.group(1))
    return None


def _resolve_priority(normalized_text: str) -> Prioridad | None:
    if _contains_phrase(normalized_text, "urgente") or _contains_phrase(normalized_text, "alta"):
        return "alta"
    if _contains_phrase(normalized_text, "media"):
        return "media"
    if _contains_phrase(normalized_text, "baja"):
        return "baja"
    return None


def _resolve_difficulty(normalized_text: str) -> int | None:
    match = re.search(r"\b(?:dificultad|dificil|nivel)\s*(\d)\b", normalized_text)
    if match is None:
        match = re.search(r"\b(\d)\s*/\s*5\b", normalized_text)
    if match is None:
        return None
    value = int(match.group(1))
    if 1 <= value <= 5:
        return value
    return None


def _missing_create_fields(slots: dict[str, object]) -> list[str]:
    missing = []
    for field_name in ("activity_type", "subject_name", "due_date"):
        if not _optional_str(slots.get(field_name)):
            missing.append(field_name)
    return missing


def _missing_prompt(missing: list[str], slots: dict[str, object]) -> str:
    first = missing[0]
    activity_type = str(slots.get("activity_type") or "actividad")
    if first == "activity_type":
        return "Que tipo de actividad es? Puede ser parcial, quiz, tarea, taller, entrega, exposicion o proyecto."
    if first == "subject_name":
        return f"Necesito la materia para registrar el {activity_type}. Responde solo con la materia, por ejemplo: Calculo."
    if first == "due_date":
        subject = str(slots.get("subject_name") or "esa materia")
        return f"Necesito la fecha para registrar {activity_type} de {subject}. Responde por ejemplo: viernes o 24/04."
    labels = ", ".join(_MISSING_LABELS.get(item, item) for item in missing)
    return f"Necesito este dato para continuar: {labels}."


def _clarify_activity_reference(
    action: str,
    matches: list[AcademicActivity],
    activities: list[AcademicActivity],
    slots: dict[str, object],
) -> AcademicActivityParseResult:
    if not active_academic_activities(activities):
        return AcademicActivityParseResult(
            detected=True,
            action=action,
            message="No tengo actividades pendientes registradas para esa solicitud.",
        )
    if not matches:
        return AcademicActivityParseResult(
            detected=True,
            action=action,
            slots=slots,
            missing_fields=["activity_reference"],
            pending_payload={
                "domain": "activity_management",
                "operation": action,
                "slots": slots,
            },
            message=(
                "No encontre una actividad pendiente con esa referencia. "
                "Puedes decirme la materia y el tipo, por ejemplo: parcial de Calculo."
            ),
            requires_clarification=True,
        )
    return AcademicActivityParseResult(
        detected=True,
        action=action,
        slots=slots,
        missing_fields=["activity_reference"],
        pending_payload={
            "domain": "activity_management",
            "operation": action,
            "slots": slots,
        },
        message=(
            "Encontre varias actividades posibles:\n"
            f"{render_activity_list(matches)}\n"
            "Dime la materia y el tipo exactos para continuar."
        ),
        requires_clarification=True,
    )


def _preview_activity_update(
    activity: AcademicActivity,
    changes: dict[str, object],
    *,
    timezone: str,
) -> AcademicActivity:
    del timezone
    payload = {key: value for key, value in changes.items() if value is not None}
    if "activity_type" in payload or "subject_name" in payload:
        activity_type = str(payload.get("activity_type") or activity.activity_type)
        subject_name = str(payload.get("subject_name") or activity.subject_name)
        payload.setdefault("activity_title", _default_title(activity_type, subject_name))
    return activity.model_copy(update=payload)


def _editable_changes(slots: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in slots.items()
        if key
        in {
            "activity_type",
            "subject_name",
            "activity_title",
            "due_date",
            "due_time",
            "estimated_effort_minutes",
            "priority_level",
            "difficulty_level",
        }
        and value is not None
    }


def _operation_payload(operation: str, activity: AcademicActivity) -> dict[str, object]:
    return {
        "domain": "activity_management",
        "operation": operation,
        "activity": activity.model_dump(mode="python"),
        "trigger": "academic_activity",
    }


def _activity_requires_replan(activity: AcademicActivity, *, reference_date: date) -> bool:
    if activity.priority_level == "alta":
        return True
    if not activity.due_date:
        return False
    try:
        days_left = (date.fromisoformat(activity.due_date) - reference_date).days
    except ValueError:
        return False
    return days_left <= 3


def _valid_pending_payload(payload: dict[str, object] | None) -> dict[str, object]:
    data = dict(payload or {})
    if data.get("domain") != "activity_management":
        return {}
    if data.get("operation") not in {"create", "update", "delete"}:
        return {}
    return data


def _merge_slots(base: dict[str, object], extra: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in extra.items():
        if value is not None and str(value).strip():
            merged[key] = value
    return merged


def _subject_names(subjects: list[SubjectItem | dict] | None) -> list[str]:
    names: list[str] = []
    for item in subjects or []:
        value = item.nombre if isinstance(item, SubjectItem) else dict(item).get("nombre")
        if str(value or "").strip():
            names.append(str(value).strip())
    return names


def _clean_subject_candidate(value: str) -> str:
    tokens = [
        token
        for token in _normalize(value).split()
        if token
        and token not in _SUBJECT_STOP_TOKENS
        and not _contains_any(token, set().union(*_ACTIVITY_TYPE_KEYWORDS.values()))
    ]
    return " ".join(tokens).strip()


def _looks_like_subject_only(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    if _detect_activity_type(normalized_text):
        return False
    if _resolve_due_date(normalized_text, reference_date=date.today()):
        return False
    if _resolve_due_time(normalized_text):
        return False
    if _contains_any(normalized_text, _DELETE_TERMS | _UPDATE_TERMS | _LIST_TERMS):
        return False
    words = normalized_text.split()
    return 1 <= len(words) <= 5


def _default_title(activity_type: str, subject_name: str) -> str:
    label = _TYPE_LABELS.get(activity_type, activity_type.replace("_", " "))
    return f"{label.capitalize()} de {subject_name}".strip()


def _title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in _normalize(value).split())


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_priority(value: object) -> Prioridad | None:
    normalized = _normalize(value)
    if normalized in {"alta", "media", "baja"}:
        return normalized  # type: ignore[return-value]
    return None


def _contains_any(text: str, phrases: set[str]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize(phrase)
    if not text or not normalized_phrase:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", text))


def _normalize(value: object) -> str:
    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())


def _now_iso(timezone: str) -> str:
    try:
        zone = ZoneInfo(str(timezone or "America/Bogota"))
    except Exception:
        zone = ZoneInfo("America/Bogota")
    return datetime.now(zone).isoformat()


__all__ = [
    "AcademicActivityApplyResult",
    "AcademicActivityParseResult",
    "active_academic_activities",
    "apply_confirmed_academic_activity_operation",
    "build_activity_from_slots",
    "coerce_academic_activities",
    "ensure_academic_activity",
    "format_activity_brief",
    "match_academic_activities",
    "parse_academic_activity_request",
    "priority_update_text_for_activity",
    "render_activity_list",
    "sort_academic_activities",
]
