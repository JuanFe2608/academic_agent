"""Nodo para recolectar el cuestionario de caracterizacion academica."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.personalization import (
    get_question_by_index,
    get_question_count,
    get_questions,
    load_personalization_config,
    parse_likert_answer,
)
from agents.support.state import AgentState
from agents.support.tools.db import get_personalization_service

from .prompt import build_question_prompt


def collect_study_profile(state: AgentState) -> dict:
    """Pregunta una afirmacion a la vez y calcula el resultado al final."""

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
    answers = _coerce_answers(study_profile.get("answers", {}))
    current_index = int(study_profile.get("current_question_index") or 0)

    if current_index >= total_questions and len(answers) == total_questions:
        result = get_personalization_service().evaluate_answers(answers)
        study_profile.update(result.model_dump(mode="json"))
        study_profile["status"] = "completed"
        study_profile["current_question_index"] = total_questions
        study_profile["persistence_error"] = None
        return {
            "study_profile": study_profile,
            "phase": "study_profile_persist",
            "awaiting_user_input": False,
        }

    if not has_new_input:
        question = get_question_by_index(current_index)
        study_profile["status"] = "collecting"
        study_profile["questionnaire_version"] = config.questionnaire_version
        study_profile["scoring_version"] = config.scoring_version
        study_profile["current_question_index"] = current_index
        study_profile["answers"] = answers
        return {
            "study_profile": study_profile,
            "phase": "study_profile",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_question_prompt(
                    current_index + 1,
                    total_questions,
                    question.prompt,
                    include_intro=current_index == 0 and not answers,
                ),
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
                    current_index + 1,
                    total_questions,
                    question.prompt,
                    invalid_answer=True,
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
                    next_index + 1,
                    total_questions,
                    next_question.prompt,
                ),
            ),
        }

    result = get_personalization_service().evaluate_answers(answers)
    study_profile.update(result.model_dump(mode="json"))
    study_profile["status"] = "completed"
    study_profile["current_question_index"] = len(get_questions())
    study_profile["persistence_error"] = None
    return {
        "study_profile": study_profile,
        "phase": "study_profile_persist",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            "Perfecto. Voy a consolidar tu caracterizacion academica.",
        ),
    }


def _study_profile_dict(state: AgentState) -> dict:
    study_profile_state = state.get("study_profile", {})
    return dict(study_profile_state)


def _coerce_answers(raw_answers: object) -> dict[str, int]:
    answers: dict[str, int] = {}
    if not isinstance(raw_answers, dict):
        return answers
    for question_id, value in raw_answers.items():
        try:
            answers[str(question_id)] = int(value)
        except (TypeError, ValueError):
            continue
    return answers

