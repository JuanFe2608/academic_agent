"""Nodo para recolectar el Radar principal de caracterizacion academica."""

from __future__ import annotations

from agents.support.dependencies import get_personalization_service
from agents.support.nodes.collect_study_profile_tiebreaker.node import (
    collect_study_profile_tiebreaker as _collect_tiebreaker,
)
from agents.support.nodes.persist_study_profile.node import (
    persist_study_profile as _persist_study_profile,
)
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from services.personalization import (
    get_question_by_index,
    get_question_count,
    load_personalization_config,
    parse_likert_answer,
)
from services.personalization.runtime import coerce_int_answer_map, current_timestamp

from .prompt import build_question_prompt


def collect_study_profile(state: AgentState) -> dict:
    """Despacha al paso correcto del Radar según study_profile.status."""

    study_profile = state.planning_state.study_profile
    status = study_profile.status or "collecting"
    if status == "tiebreaker_collecting":
        return _collect_tiebreaker(state)
    if status == "completed" and not study_profile.persisted_profile_id:
        return _persist_study_profile(state)
    return _do_collect_study_profile(state)


def _do_collect_study_profile(state: AgentState) -> dict:
    """Pregunta una afirmacion a la vez y deriva a desempate si hace falta."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    study_profile = _study_profile_dict(state)
    config = load_personalization_config()
    total_questions = get_question_count()
    answers = coerce_int_answer_map(study_profile.get("answers", {}))
    current_index = int(study_profile.get("current_question_index") or 0)

    if current_index >= total_questions and len(answers) == total_questions:
        result = get_personalization_service().evaluate_answers(answers)
        return _apply_main_result(
            state,
            study_profile,
            result.model_dump(mode="json"),
        )

    if not has_new_input:
        question = get_question_by_index(current_index)
        study_profile["status"] = "collecting"
        study_profile["questionnaire_version"] = config.questionnaire_version
        study_profile["scoring_version"] = config.scoring_version
        study_profile["current_question_index"] = current_index
        study_profile["answers"] = answers
        is_intro = current_index == 0 and not answers
        question_content = build_question_prompt(
            question,
            question_number=current_index + 1,
            total_questions=total_questions,
            include_intro=is_intro,
            answered_count=len(answers),
        )
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                question_content,
            ),
        }

    parsed_answer = parse_likert_answer(last_text or "")
    if not parsed_answer.is_valid:
        question = get_question_by_index(current_index)
        study_profile["status"] = "collecting"
        study_profile["questionnaire_version"] = config.questionnaire_version
        study_profile["scoring_version"] = config.scoring_version
        study_profile["current_question_index"] = current_index
        study_profile["answers"] = answers
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_question_prompt(
                    question,
                    question_number=current_index + 1,
                    total_questions=total_questions,
                    invalid_answer=True,
                    answered_count=len(answers),
                ),
            ),
        }

    question = get_question_by_index(current_index)
    answers[question.question_id] = int(parsed_answer.value)
    study_profile["status"] = "collecting"
    study_profile["questionnaire_version"] = config.questionnaire_version
    study_profile["scoring_version"] = config.scoring_version
    study_profile["answers"] = answers

    next_index = current_index + 1
    if next_index < total_questions:
        next_question = get_question_by_index(next_index)
        study_profile["current_question_index"] = next_index
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_question_prompt(
                    next_question,
                    question_number=next_index + 1,
                    total_questions=total_questions,
                    answered_count=len(answers),
                ),
            ),
        }

    result = get_personalization_service().evaluate_answers(answers)
    return _apply_main_result(
        state,
        study_profile,
        result.model_dump(mode="json"),
        current_count=current_count,
        last_text=last_text,
    )


def _apply_main_result(
    state: AgentState,
    study_profile: dict,
    result_payload: dict[str, object],
    *,
    current_count: int | None = None,
    last_text: str | None = None,
) -> dict:
    messages = state.get("messages", [])
    total_questions = get_question_count()
    study_profile.update(result_payload)
    study_profile["current_question_index"] = total_questions
    study_profile["persistence_error"] = None

    tiebreaker = dict(study_profile.get("tiebreaker", {}))
    assessment = dict(tiebreaker.get("assessment", {}))
    if bool(assessment.get("needs_tiebreaker")):
        tiebreaker["status"] = "needed"
        tiebreaker["activated"] = False
        tiebreaker["answers"] = coerce_int_answer_map(tiebreaker.get("answers", {}))
        tiebreaker["current_question_index"] = int(
            tiebreaker.get("current_question_index") or 0
        )
        tiebreaker["answer_timestamps"] = dict(tiebreaker.get("answer_timestamps") or {})
        study_profile["tiebreaker"] = tiebreaker
        study_profile["status"] = "tiebreaker_collecting"
        study_profile["completed_at"] = None
        update = {
            "study_profile": study_profile,
            "phase": "study_profile",
            "awaiting_user_input": False,
        }
    else:
        study_profile["status"] = "completed"
        study_profile["completed_at"] = current_timestamp(state.get("timezone"))
        update = {
            "study_profile": study_profile,
            "phase": "study_profile",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Voy a consolidar tu Radar de estudio.",
            ),
        }

    if current_count is not None:
        update["user_message_count"] = current_count
    if last_text is not None:
        update["last_user_text"] = last_text
    return update


def _study_profile_dict(state: AgentState) -> dict:
    study_profile_state = state.get("study_profile", {})
    return dict(study_profile_state)
