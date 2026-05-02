"""Nodo para sincronizar el horario fijo confirmado hacia Outlook."""

from __future__ import annotations

from datetime import date

from agents.support.dependencies import get_outlook_fixed_schedule_sync_service
from agents.support.nodes.collect_study_profile.prompt import build_question_prompt
from agents.support.nodes.utils import append_message
from agents.support.state import AgentState
from services.personalization import (
    get_question_by_index,
    get_question_count,
    is_personalization_enabled,
    load_personalization_config,
)
from services.personalization.runtime import coerce_int_answer_map
from services.scheduling import format_schedule_end_date


def sync_fixed_schedule(state: AgentState) -> dict:
    """Sincroniza a Outlook sin bloquear la continuidad del flujo principal."""

    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    calendar_state = dict(state.get("calendar", {}))

    result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=schedule_state.get("persisted_profile_id"),
        calendar_state=calendar_state,
        calendar_id=calendar_state.get("calendar_id"),
    )

    if result.synced:
        return _maybe_start_radar(
            state,
            {
                "calendar": {
                    **calendar_state,
                    "provider": "outlook",
                    "authorized": True,
                    "synced_event_map": dict(result.synced_event_map),
                },
                "phase": "study_profile",
                "awaiting_user_input": False,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    (
                        "✅ También guardé tu horario fijo en Outlook "
                        f"hasta el {format_schedule_end_date(_parse_schedule_end_date(schedule_state))}."
                    ),
                ),
            },
        )

    message = (
        "Tu horario quedó guardado en el sistema, pero no pude sincronizarlo con Outlook.\n"
        f"Detalle técnico: {result.detail or result.error_code or 'desconocido'}"
    )
    return _maybe_start_radar(
        state,
        {
            "calendar": {
                **calendar_state,
                "provider": calendar_state.get("provider") or "outlook",
                "synced_event_map": dict(result.synced_event_map),
            },
            "phase": "study_profile",
            "awaiting_user_input": False,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                message,
            ),
        },
    )


def _parse_schedule_end_date(schedule_state: dict) -> date | None:
    raw_value = str(schedule_state.get("schedule_end_date") or "").strip()
    if not raw_value:
        return None
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None


def _maybe_start_radar(state: AgentState, update: dict) -> dict:
    """Arranca el Radar en el mismo cierre del horario para evitar estados mudos."""

    if not is_personalization_enabled():
        return update

    study_profile = dict(state.get("study_profile", {}))
    if not _should_start_initial_radar_prompt(study_profile):
        return update

    config = load_personalization_config()
    answers = coerce_int_answer_map(study_profile.get("answers", {}))
    study_profile["status"] = "collecting"
    study_profile["questionnaire_version"] = config.questionnaire_version
    study_profile["scoring_version"] = config.scoring_version
    study_profile["current_question_index"] = 0
    study_profile["answers"] = answers

    question = get_question_by_index(0)
    radar_prompt = build_question_prompt(
        question,
        question_number=1,
        total_questions=get_question_count(),
        include_intro=True,
        answered_count=0,
    )

    update["study_profile"] = study_profile
    update["awaiting_user_input"] = True
    update["messages"] = list(update.get("messages") or []) + append_message(
        state.get("messages", []),
        "assistant",
        radar_prompt,
    )
    return update


def _should_start_initial_radar_prompt(study_profile: dict) -> bool:
    if study_profile.get("persisted_profile_id"):
        return False
    answers = coerce_int_answer_map(study_profile.get("answers", {}))
    if answers:
        return False
    current_index = int(study_profile.get("current_question_index") or 0)
    status = str(study_profile.get("status") or "collecting").strip()
    return current_index == 0 and status in {"", "idle", "collecting"}
