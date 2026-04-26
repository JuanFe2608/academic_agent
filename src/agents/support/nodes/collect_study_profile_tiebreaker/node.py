"""Nodo para recolectar los retos extra de desempate del perfil."""

from __future__ import annotations

from agents.support.dependencies import get_personalization_service
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from services.personalization import (
    get_tiebreaker_question_by_index,
    get_tiebreaker_question_count,
    parse_choice_answer,
)
from services.personalization.runtime import coerce_int_answer_map, current_timestamp

from .prompt import build_tiebreaker_prompt


def collect_study_profile_tiebreaker(state: AgentState) -> dict:
    """Pregunta 3 retos extra cuando el perfil principal tiene baja discriminacion."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    study_profile = dict(state.get("study_profile", {}))
    tiebreaker = dict(study_profile.get("tiebreaker", {}))
    total_questions = get_tiebreaker_question_count()
    answers = coerce_int_answer_map(tiebreaker.get("answers", {}))
    answer_timestamps = dict(tiebreaker.get("answer_timestamps") or {})
    current_index = int(tiebreaker.get("current_question_index") or 0)

    if current_index >= total_questions and len(answers) == total_questions:
        return _finalize_tiebreaker(
            state,
            study_profile,
            tiebreaker,
            answers,
            answer_timestamps,
        )

    if not has_new_input:
        question = get_tiebreaker_question_by_index(current_index)
        study_profile["status"] = "tiebreaker_collecting"
        tiebreaker["status"] = "collecting"
        tiebreaker["activated"] = True
        tiebreaker["started_at"] = tiebreaker.get("started_at") or current_timestamp(
            state.get("timezone")
        )
        tiebreaker["current_question_index"] = current_index
        tiebreaker["answers"] = answers
        tiebreaker["answer_timestamps"] = answer_timestamps
        study_profile["tiebreaker"] = tiebreaker
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_tiebreaker_prompt(
                    question,
                    question_number=current_index + 1,
                    total_questions=total_questions,
                    include_intro=current_index == 0 and not answers,
                    answered_count=len(answers),
                ),
            ),
        }

    question = get_tiebreaker_question_by_index(current_index)
    parsed_answer = parse_choice_answer(
        last_text or "",
        valid_values={option.option_id for option in question.options},
    )
    if not parsed_answer.is_valid:
        study_profile["status"] = "tiebreaker_collecting"
        tiebreaker["status"] = "collecting"
        tiebreaker["activated"] = True
        tiebreaker["started_at"] = tiebreaker.get("started_at") or current_timestamp(
            state.get("timezone")
        )
        tiebreaker["current_question_index"] = current_index
        tiebreaker["answers"] = answers
        tiebreaker["answer_timestamps"] = answer_timestamps
        study_profile["tiebreaker"] = tiebreaker
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_tiebreaker_prompt(
                    question,
                    question_number=current_index + 1,
                    total_questions=total_questions,
                    invalid_answer=True,
                    answered_count=len(answers),
                ),
            ),
        }

    answers[question.question_id] = int(parsed_answer.value)
    answer_timestamps[question.question_id] = current_timestamp(state.get("timezone"))
    study_profile["status"] = "tiebreaker_collecting"
    tiebreaker["status"] = "collecting"
    tiebreaker["activated"] = True
    tiebreaker["started_at"] = tiebreaker.get("started_at") or current_timestamp(
        state.get("timezone")
    )
    tiebreaker["answers"] = answers
    tiebreaker["answer_timestamps"] = answer_timestamps

    next_index = current_index + 1
    if next_index < total_questions:
        next_question = get_tiebreaker_question_by_index(next_index)
        tiebreaker["current_question_index"] = next_index
        study_profile["tiebreaker"] = tiebreaker
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_tiebreaker_prompt(
                    next_question,
                    question_number=next_index + 1,
                    total_questions=total_questions,
                    answered_count=len(answers),
                ),
            ),
        }

    return _finalize_tiebreaker(
        state,
        study_profile,
        tiebreaker,
        answers,
        answer_timestamps,
        current_count=current_count,
        last_text=last_text,
    )


def _finalize_tiebreaker(
    state: AgentState,
    study_profile: dict,
    tiebreaker: dict,
    answers: dict[str, int],
    answer_timestamps: dict[str, str],
    *,
    current_count: int | None = None,
    last_text: str | None = None,
) -> dict:
    messages = state.get("messages", [])
    completed_at = current_timestamp(state.get("timezone"))
    result = get_personalization_service().refine_with_tiebreaker(
        answers=coerce_int_answer_map(study_profile.get("answers", {})),
        tiebreaker_answers=answers,
    )
    study_profile.update(result.model_dump(mode="json"))
    merged_tiebreaker = dict(study_profile.get("tiebreaker", {}))
    merged_tiebreaker["status"] = "completed"
    merged_tiebreaker["activated"] = True
    merged_tiebreaker["answers"] = answers
    merged_tiebreaker["answer_timestamps"] = answer_timestamps
    merged_tiebreaker["current_question_index"] = get_tiebreaker_question_count()
    merged_tiebreaker["started_at"] = tiebreaker.get("started_at") or completed_at
    merged_tiebreaker["completed_at"] = completed_at
    merged_tiebreaker["answer_details"] = _hydrate_answer_details(
        merged_tiebreaker.get("answer_details", []),
        answer_timestamps,
    )
    study_profile["tiebreaker"] = merged_tiebreaker
    study_profile["status"] = "completed"
    study_profile["completed_at"] = completed_at
    update = {
        "study_profile": study_profile,
        "phase": "study_profile",
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            "Listo. Voy a consolidar el resultado afinado de tu Radar.",
        ),
    }
    if current_count is not None:
        update["user_message_count"] = current_count
    if last_text is not None:
        update["last_user_text"] = last_text
    return update


def _hydrate_answer_details(
    raw_details: list[dict] | list,
    answer_timestamps: dict[str, str],
) -> list[dict]:
    hydrated: list[dict] = []
    for item in raw_details or []:
        detail = dict(item) if isinstance(item, dict) else dict(item.model_dump())
        question_id = str(detail.get("question_id") or "").strip()
        if question_id and question_id in answer_timestamps:
            detail["answered_at"] = answer_timestamps[question_id]
        hydrated.append(detail)
    return hydrated
