"""Servicio de aplicación para captura conversacional de prioridades."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.priorities.config import load_priorities_config
from agents.support.priorities.formatter import (
    build_auto_priority_prompt,
    build_priorities_processing_message,
)
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.planning import coerce_academic_activities, parse_academic_activity_request
from services.priorities import (
    current_week_bounds,
    ensure_priorities_state,
    parse_priority_command,
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)
from schemas.planning import SubjectItem

_PRIORITY_LABELS = {"alta", "media", "baja"}


def handle_priorities_turn(state: AgentState) -> dict:
    """Coordina el subflujo semanal de prioridades con flujo abierto de un solo turno.

    El agente calcula automáticamente el orden de prioridades y le pide al estudiante
    únicamente si hay algo que no haya captado. No solicita rankings ni menús numéricos.
    """

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    config = load_priorities_config()
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    timezone = state.get("timezone", "America/Bogota")
    reference_date = _reference_date(timezone)
    week_start, week_end = current_week_bounds(reference_date)
    priorities_state = ensure_priorities_state(state.get("priorities", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        academic_activities=list(state.get("academic_activities", [])),
        primary_technique_id=_primary_technique_id(study_profile),
        reference_date=reference_date,
    )
    current_subjects = subject_items_to_update(priorities.subject_items)
    prompt_version = _prompt_version(config.prompt_version)

    # Primer turno o reactivación desde fase running: mostrar prioridades auto-calculadas
    if not has_new_input or _starts_from_direct_prioritization_request(
        state=state,
        priorities_state=priorities_state,
        has_new_input=has_new_input,
    ):
        return _ask_context(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=current_subjects,
            source=priorities.source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
        )

    # Segundo turno: el estudiante respondió a la pregunta abierta
    return _handle_context_input(
        state=state,
        messages=messages,
        last_text=last_text,
        current_count=current_count,
        subjects=current_subjects,
        source=priorities.source,
        prompt_version=prompt_version,
        week_start=week_start,
        week_end=week_end,
        timezone=timezone,
        reference_date=reference_date,
        schedule_blocks=list(schedule_state.blocks),
        study_profile=study_profile,
    )


def _ask_context(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
) -> dict:
    """Muestra el orden calculado y hace la única pregunta abierta."""

    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="collecting",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage="ask_context",
            week_start=week_start,
            week_end=week_end,
            draft={"subject_names": [s.nombre for s in subjects]},
        ),
        "phase": "priorities",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            build_auto_priority_prompt(subjects, week_start=week_start, week_end=week_end),
        ),
    }


def _handle_context_input(
    *,
    state: AgentState,
    messages: list,
    last_text: str | None,
    current_count: int,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
    timezone: str,
    reference_date,
    schedule_blocks: list,
    study_profile: dict,
) -> dict:
    """Procesa la respuesta abierta del estudiante y avanza al plan semanal."""

    if parse_priority_command(last_text) == "omitir":
        return _skip(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=subjects,
            source=source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
        )

    # Respuesta de descarte explícita → proceder de inmediato
    if _looks_like_dismissal(last_text):
        return _complete(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=subjects,
            source=source,
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
        )

    manual_subjects = _parse_manual_subject_rows(last_text)
    if manual_subjects:
        new_priorities = resolve_prioritized_subjects(
            schedule_blocks=schedule_blocks,
            subjects=manual_subjects,
            academic_activities=list(state.get("academic_activities", [])),
            primary_technique_id=_primary_technique_id(study_profile),
            reference_date=reference_date,
        )
        updated_subjects = subject_items_to_update(new_priorities.subject_items)
        return _complete(
            state=state,
            messages=messages,
            current_count=current_count,
            last_text=last_text,
            subjects=updated_subjects,
            source="manual_priority_input",
            prompt_version=prompt_version,
            week_start=week_start,
            week_end=week_end,
        )

    # Intentar extraer una nueva actividad académica del texto libre
    existing_activities = coerce_academic_activities(state.get("academic_activities", []))
    activity_result = parse_academic_activity_request(
        last_text,
        existing_activities=existing_activities,
        subjects=subjects,
        reference_date=reference_date,
        timezone=timezone,
    )

    # Actividad detectada sin ambigüedades ni confirmación pendiente → incorporar al estado
    if (
        activity_result.detected
        and not activity_result.requires_clarification
        and not activity_result.requires_confirmation
    ):
        updated_activities = list(activity_result.activities or existing_activities)
        new_priorities = resolve_prioritized_subjects(
            schedule_blocks=schedule_blocks,
            subjects=subjects,
            academic_activities=updated_activities,
            primary_technique_id=_primary_technique_id(study_profile),
            reference_date=reference_date,
        )
        updated_subjects = subject_items_to_update(new_priorities.subject_items)
        return {
            "academic_activities": updated_activities,
            **_complete(
                state=state,
                messages=messages,
                current_count=current_count,
                last_text=last_text,
                subjects=updated_subjects,
                source="weekly_flow_with_activity",
                prompt_version=prompt_version,
                week_start=week_start,
                week_end=week_end,
            ),
        }

    # Cualquier otro texto (mención ambigua, texto libre, pregunta) → proceder igual.
    # Actividades complejas se registran via handle_academic_update en fase running.
    return _complete(
        state=state,
        messages=messages,
        current_count=current_count,
        last_text=last_text,
        subjects=subjects,
        source=source,
        prompt_version=prompt_version,
        week_start=week_start,
        week_end=week_end,
    )


def _complete(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
) -> dict:
    """Cierra el subflujo de prioridades y avanza a la generación del plan."""

    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft={"subject_names": [s.nombre for s in subjects]},
        ),
        "phase": "running",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            build_priorities_processing_message(subjects),
        ),
    }


def _skip(
    *,
    state: AgentState,
    messages: list,
    current_count: int,
    last_text: str | None,
    subjects: list,
    source: str,
    prompt_version: str,
    week_start: str,
    week_end: str,
) -> dict:
    """Marca el snapshot como omitido sin recalcular prioridades nuevas."""

    return {
        "subjects": subjects,
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="skipped",
            prompt_version=prompt_version,
            source=source,
            last_error=None,
            capture_stage=None,
            week_start=week_start,
            week_end=week_end,
            draft={"subject_names": [s.nombre for s in subjects]},
        ),
        "phase": "running",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            "Listo, omití la actualización de prioridades por ahora.",
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _primary_technique_id(study_profile: dict) -> str | None:
    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _starts_from_direct_prioritization_request(
    *,
    state: AgentState,
    priorities_state,
    has_new_input: bool,
) -> bool:
    """Detecta reactivación desde fase running para no interpretar el texto como respuesta."""

    if not has_new_input:
        return False
    if str(state.get("phase") or "") == "priorities":
        return False
    if priorities_state.capture_stage is not None:
        return False
    return priorities_state.status in {"idle", "completed", "skipped"}


def _looks_like_dismissal(text: str | None) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    return normalized in {
        "no",
        "nada",
        "no hay nada",
        "no nada",
        "no hay nada mas",
        "no hay nada más",
        "está bien",
        "esta bien",
        "listo",
        "ok",
        "dale",
        "si",
        "sí",
        "después",
        "despues",
        "procede",
        "continua",
        "continúa",
        "todo bien",
        "todo está bien",
        "todo esta bien",
        "ya está",
        "ya esta",
        "correcto",
        "perfecto",
        "sin novedad",
        "ninguna",
        "ninguno",
    }


def _parse_manual_subject_rows(text: str | None) -> list[SubjectItem]:
    """Acepta filas tipo `Materia | alta | 5 | media | 4h` como corrección rápida."""

    rows = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not rows or not any("|" in row for row in rows):
        return []

    subjects: list[SubjectItem] = []
    for row in rows:
        parts = [part.strip() for part in row.split("|")]
        if len(parts) != 5:
            return []
        name, priority, difficulty, urgency, weekly_load = parts
        priority = priority.lower()
        urgency = urgency.lower()
        if not name or priority not in _PRIORITY_LABELS:
            return []
        if urgency in {"", "no", "ninguna", "ninguno", "sin urgencia"}:
            urgency_value = None
        elif urgency in _PRIORITY_LABELS:
            urgency_value = urgency
        else:
            return []
        try:
            difficulty_value = int(difficulty)
        except ValueError:
            return []
        if difficulty_value < 1 or difficulty_value > 5:
            return []
        load_value = _parse_weekly_load_minutes(weekly_load)
        if load_value is None:
            return []
        subjects.append(
            SubjectItem(
                nombre=name,
                prioridad=priority,  # type: ignore[arg-type]
                dificultad=difficulty_value,
                urgencia=urgency_value,  # type: ignore[arg-type]
                carga_semanal_min=load_value,
                origen="manual_priority_input",
                priority_source="manual_priority_input",
                is_priority_confirmed=True,
            )
        )
    return subjects


def _parse_weekly_load_minutes(value: str) -> int | None:
    normalized = " ".join(value.strip().lower().replace(",", ".").split())
    if not normalized:
        return None
    number_text = ""
    for character in normalized:
        if character.isdigit() or character == ".":
            number_text += character
        elif number_text:
            break
    if not number_text:
        return None
    try:
        amount = float(number_text)
    except ValueError:
        return None
    if amount <= 0:
        return None
    if "h" in normalized or "hora" in normalized:
        return max(1, int(round(amount * 60)))
    return max(1, int(round(amount)))


def _prompt_version(config_value: str) -> str:
    return config_value if config_value and config_value != "v1" else "v2"


def _reference_date(timezone: str):
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).date()
    except Exception:
        return datetime.now().date()
