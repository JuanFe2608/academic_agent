"""Clasificador deterministico de inputs agregados."""

from __future__ import annotations

import re
import unicodedata

from schemas.conversation import InputClassification
from services.planning.replanning_service import is_replan_request_message
from services.planning.session_tracking_flow_service import is_study_session_tracking_message
from services.study_recommendations import is_applied_study_method_message
from services.sync.study_calendar_sync_intent import is_study_calendar_sync_message
from services.sync.study_todo_sync_intent import is_study_todo_sync_message

from .guided_academic_support import (
    is_guided_academic_support_message,
    is_socratic_mode_message,
)
from .text_normalization import contains_any, normalize_text

_CONFIRMATION_TERMS = {
    "si",
    "sí",
    "ok",
    "vale",
    "listo",
    "confirmo",
    "confirmar",
    "de acuerdo",
    "correcto",
    "no",
    "cancelar",
}
_CRITICAL_COMMAND_TERMS = {
    "borra",
    "borrar",
    "elimina",
    "eliminar",
    "cancela",
    "cancelar",
    "reagenda",
    "reprograma",
    "mueve",
    "cambia",
}
_GREETING_TERMS = {"hola", "buenas", "gracias", "hey", "ola"}
_PROFILE_TERMS = {"nombre", "codigo", "correo", "semestre", "promedio", "edad"}
_SCHEDULE_TERMS = {
    "horario",
    "clase",
    "clases",
    "franja",
    "disponibilidad",
    "cruce",
    "trabajo",
}
_ACTIVITY_TERMS = {
    "parcial",
    "quiz",
    "tarea",
    "taller",
    "entrega",
    "exposicion",
    "ejercicio",
    "proyecto",
    "laboratorio",
    "estudio pendiente",
    "sesion de estudio",
}
_PRIORITY_TERMS = {"prioridad", "priorizar", "urgente", "importante", "primero"}
_STUDY_METHOD_TERMS = {
    "pomodoro",
    "feynman",
    "tecnica",
    "tecnicas",
    "metodo",
    "metodos",
    "estudiar",
    "repasar",
    "memorizar",
}
_WEEKLY_PLAN_TERMS = {"semana", "cronograma", "plan", "bloques", "organizar"}
_REPLAN_TERMS = {"replanifica", "replanificar", "replanificacion", "reagenda", "reprograma"}
_CALENDAR_TERMS = {"calendario", "outlook", "evento", "recordatorio", "agenda"}
_VIEW_TASKS_TERMS = {
    "mis tareas",
    "ver tareas",
    "que tengo pendiente",
    "actividades pendientes",
    "mis pendientes",
    "cuales son mis tareas",
    "que me falta",
    "tareas pendientes",
    "pendientes de hoy",
    "listar tareas",
}
_VIEW_AGENDA_TERMS = {
    "ver mi agenda",
    "mi agenda",
    "agenda de hoy",
    "que tengo hoy",
    "que hay hoy",
    "ver agenda",
    "agenda semanal",
    "ver mi semana",
    "que tengo esta semana",
    "que hay esta semana",
    "lo que tengo hoy",
    "lo que tengo esta semana",
}
_RISK_TERMS = {
    "crisis",
    "salud mental",
    "psicologo",
    "psicologa",
    "bienestar",
    "no quiero vivir",
    "me quiero morir",
    "hacerme dano",
    "suicid",
}


def classify_input(
    text: str | None = None,
    *,
    media_types: list[str] | tuple[str, ...] | set[str] | None = None,
) -> InputClassification:
    """Clasifica tipo, utilidad e intent probable de un input agregado."""

    normalized_text = normalize_text(text)
    normalized_media = _normalize_media_types(media_types)
    input_type = _classify_input_type(normalized_text, normalized_media, text)
    signals: list[str] = []
    possible_intent = _detect_possible_intent(normalized_text, signals)

    if input_type in {"sticker_only", "emoji_only"}:
        return InputClassification(
            input_type=input_type,
            utility="noise",
            is_useful=False,
            possible_intent=possible_intent or "smalltalk_contextual",
            confidence=0.78,
            normalized_text=normalized_text,
            signals=signals or [input_type],
            media_types=normalized_media,
        )

    if input_type in {"image_only", "mixed", "audio", "document"} and not normalized_text:
        return InputClassification(
            input_type=input_type,
            utility="media",
            is_useful=True,
            possible_intent=possible_intent or _media_intent(input_type),
            confidence=0.72,
            normalized_text=normalized_text,
            signals=signals or [input_type],
            media_types=normalized_media,
        )

    if contains_any(normalized_text, _CRITICAL_COMMAND_TERMS):
        signals.append("critical_command")
        return InputClassification(
            input_type=input_type,
            utility="command",
            is_useful=True,
            possible_intent=possible_intent or "critical_command",
            confidence=0.84,
            normalized_text=normalized_text,
            signals=signals,
            media_types=normalized_media,
        )

    if _is_confirmation_text(normalized_text):
        signals.append("confirmation")
        return InputClassification(
            input_type=input_type,
            utility="confirmation",
            is_useful=True,
            possible_intent=possible_intent or "confirmation",
            confidence=0.86,
            normalized_text=normalized_text,
            signals=signals,
            media_types=normalized_media,
        )

    if contains_any(normalized_text, _GREETING_TERMS) and len(normalized_text.split()) <= 3:
        signals.append("smalltalk")
        return InputClassification(
            input_type=input_type,
            utility="noise",
            is_useful=False,
            possible_intent=possible_intent or "smalltalk_contextual",
            confidence=0.7,
            normalized_text=normalized_text,
            signals=signals,
            media_types=normalized_media,
        )

    if possible_intent == "wellbeing_or_crisis_signal":
        return InputClassification(
            input_type=input_type,
            utility="sensitive",
            is_useful=True,
            possible_intent=possible_intent,
            confidence=0.9,
            normalized_text=normalized_text,
            signals=signals,
            media_types=normalized_media,
        )

    return InputClassification(
        input_type=input_type,
        utility="useful" if normalized_text or normalized_media else "noise",
        is_useful=bool(normalized_text or normalized_media),
        possible_intent=possible_intent,
        confidence=0.76 if possible_intent else 0.45,
        normalized_text=normalized_text,
        signals=signals,
        media_types=normalized_media,
    )


def _normalize_media_types(media_types: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    values: list[str] = []
    for media_type in media_types or []:
        normalized = normalize_text(str(media_type)).replace(" ", "_")
        if normalized:
            values.append(normalized)
    return list(dict.fromkeys(values))


def _classify_input_type(normalized_text: str, media_types: list[str], raw_text: str | None) -> str:
    if _is_emoji_only(str(raw_text or "")):
        return "emoji_only"
    has_text = bool(normalized_text)
    if media_types and has_text:
        return "mixed"
    if media_types:
        if "sticker" in media_types:
            return "sticker_only"
        if "image" in media_types:
            return "image_only"
        if "audio" in media_types:
            return "audio"
        if "document" in media_types:
            return "document"
        return "mixed"
    return "text"


def _detect_possible_intent(normalized_text: str, signals: list[str]) -> str | None:
    if not normalized_text:
        return None
    if is_socratic_mode_message(normalized_text):
        signals.append("guided_academic_support")
        return "enter_socratic_mode"
    if is_guided_academic_support_message(normalized_text):
        signals.append("guided_academic_support")
        return "request_guided_academic_help"
    if is_applied_study_method_message(normalized_text):
        signals.append("study_method_recommendation")
        return "study_method_recommendation"
    if is_study_session_tracking_message(normalized_text):
        signals.append("session_tracking")
        return "track_study_session"
    if is_replan_request_message(normalized_text) or contains_any(normalized_text, _REPLAN_TERMS):
        signals.append("replanning")
        return "request_replan"
    if is_study_calendar_sync_message(normalized_text):
        signals.append("calendar_sync")
        return "sync_study_calendar"
    if is_study_todo_sync_message(normalized_text):
        signals.append("todo_sync")
        return "sync_study_todo"
    if contains_any(normalized_text, _VIEW_TASKS_TERMS):
        signals.append("activity_management")
        return "view_tasks"
    if contains_any(normalized_text, _VIEW_AGENDA_TERMS):
        signals.append("schedule_management")
        return "view_weekly_agenda"
    if _is_concept_question(normalized_text):
        signals.append("guided_academic_support")
        return "answer_academic_concept_question"
    checks = [
        ("wellbeing_or_crisis_signal", _RISK_TERMS, "risk_or_wellbeing"),
        ("update_student_profile", _PROFILE_TERMS, "student_profile"),
        ("manage_fixed_schedule", _SCHEDULE_TERMS, "schedule_management"),
        ("manage_academic_activity", _ACTIVITY_TERMS, "activity_management"),
        ("prioritize_academic_work", _PRIORITY_TERMS, "prioritization"),
        ("study_method_recommendation", _STUDY_METHOD_TERMS, "study_method_recommendation"),
        ("weekly_planning", _WEEKLY_PLAN_TERMS, "weekly_planning"),
        ("calendar_action", _CALENDAR_TERMS, "calendar_action"),
    ]
    for intent, terms, signal in checks:
        if contains_any(normalized_text, terms):
            signals.append(signal)
            return intent
    return None


def _media_intent(input_type: str) -> str:
    if input_type == "image_only":
        return "media_schedule_or_activity_input"
    if input_type == "document":
        return "document_input"
    if input_type == "audio":
        return "audio_input"
    return "media_input"


def _is_concept_question(normalized_text: str) -> bool:
    """Detecta preguntas del tipo '¿qué es X?' sobre conceptos o temas académicos."""
    starters = (
        "que es ",
        "que son ",
        "para que sirve ",
        "para que se usa ",
        "como funciona ",
        "como se usa ",
        "cuando se usa ",
        "en que consiste ",
        "explicame ",
        "que significa ",
        "cual es la diferencia entre ",
        "que diferencia hay entre ",
        "que diferencia hay ",
    )
    return any(normalized_text.startswith(s) for s in starters)


def _is_confirmation_text(normalized_text: str) -> bool:
    candidate = re.sub(r"^[^\w]+|[^\w]+$", "", normalized_text).strip()
    if not candidate:
        return False
    return candidate in {normalize_text(term) for term in _CONFIRMATION_TERMS}


def _is_emoji_only(raw_text: str) -> bool:
    compact = "".join(ch for ch in raw_text.strip() if not ch.isspace())
    if not compact:
        return False
    has_symbol = False
    for char in compact:
        if char in {"\ufe0f", "\u200d"}:
            continue
        if char.isalnum():
            return False
        category = unicodedata.category(char)
        if category in {"So", "Sk"}:
            has_symbol = True
            continue
        return False
    return has_symbol


__all__ = ["classify_input"]
