"""Formateadores deterministas del Radar de estudio."""

from __future__ import annotations

from typing import Any

from services.personalization.questionnaire import (
    get_intro_prompt,
    get_invalid_answer_prompt,
    get_microfeedback,
    get_question_options_prompt,
    get_technique,
    get_tiebreaker_intro_prompt,
    get_tiebreaker_invalid_answer_prompt,
    get_tiebreaker_microfeedback,
)

_FILLED_STEP = "🟩"
_EMPTY_STEP = "⬜"


def build_question_prompt(
    question: Any,
    *,
    question_number: int,
    total_questions: int,
    include_intro: bool = False,
    invalid_answer: bool = False,
    answered_count: int = 0,
) -> str:
    """Construye un reto del Radar de estudio en formato WhatsApp."""

    lines: list[str] = []
    if include_intro:
        lines.append(get_intro_prompt())
        lines.append("")

    if invalid_answer:
        lines.append(get_invalid_answer_prompt())
        lines.append("")
    else:
        microfeedback = get_microfeedback(answered_count)
        if microfeedback:
            lines.append(microfeedback)
            lines.append("")

    challenge_title = str(_value(question, "challenge_title", "Radar de estudio")).strip()
    challenge_emoji = str(_value(question, "challenge_emoji", "🧭")).strip()
    question_prompt = str(_value(question, "prompt", "")).strip()

    lines.append(f"Reto {question_number}/{total_questions} · {challenge_title} {challenge_emoji}")
    lines.append(f"Progreso {question_number}/{total_questions}: {build_progress_bar(question_number, total_questions)}")
    lines.append("")
    lines.append(question_prompt)
    lines.append("")
    lines.append(get_question_options_prompt())
    return "\n".join(lines).strip()


def build_tiebreaker_prompt(
    question: Any,
    *,
    question_number: int,
    total_questions: int,
    include_intro: bool = False,
    invalid_answer: bool = False,
    answered_count: int = 0,
) -> str:
    """Construye un reto extra del desempate en formato WhatsApp."""

    lines: list[str] = []
    if include_intro:
        lines.append(get_tiebreaker_intro_prompt())
        lines.append("")

    if invalid_answer:
        lines.append(get_tiebreaker_invalid_answer_prompt())
        lines.append("")
    else:
        microfeedback = get_tiebreaker_microfeedback(answered_count)
        if microfeedback:
            lines.append(microfeedback)
            lines.append("")

    challenge_title = str(_value(question, "challenge_title", "Afinando tu radar")).strip()
    challenge_emoji = str(_value(question, "challenge_emoji", "🎯")).strip()
    question_prompt = str(_value(question, "prompt", "")).strip()
    option_lines = _choice_option_lines(question)

    lines.append(f"{challenge_title} {challenge_emoji}")
    lines.append(f"Progreso {question_number}/{total_questions}: {build_progress_bar(question_number, total_questions)}")
    lines.append("")
    lines.append(question_prompt)
    lines.append("")
    lines.extend(option_lines)
    lines.append("")
    lines.append("Responde con un número del 1 al 4.")
    return "\n".join(lines).strip()


def build_personalization_summary(result: Any) -> str:
    """Construye el cierre final del Radar de estudio."""

    scores = list(_value(result, "scores", []))
    observations = list(_value(result, "observations", []))
    tiebreaker = _value(result, "tiebreaker", {}) or {}
    if len(scores) < 3:
        return "Ya terminé tu Radar de estudio, pero no pude construir el ranking completo."

    top_labels = [_score_label(scores[index]) for index in range(3)]
    tiebreaker_activated = bool(_value(tiebreaker, "activated", False))
    selected_observations = [str(item).strip() for item in observations if str(item).strip()][:3]
    lines = [
        "Listo, ya afiné mejor tu perfil de estudio 🎯"
        if tiebreaker_activated
        else "Radar de estudio completado 🧭",
        (
            "Con tus respuestas extra ya pude afinar mejor la prioridad de técnicas para ti."
            if tiebreaker_activated
            else "Ya identifiqué las técnicas que mejor pueden ayudarte en esta etapa."
        ),
    ]

    if selected_observations:
        lines.extend(
            [
                "",
                "Lo que detecté en tu forma de estudiar:",
            ]
        )
        lines.extend(f"- {observation}" for observation in selected_observations)
    else:
        lines.extend(
            [
                "",
                "No se activaron alertas fuertes en el radar, pero sí quedó claro qué técnicas pueden reforzar mejor tu método.",
            ]
        )

    lines.extend(
        [
            "",
            "Tus 3 técnicas más prometedoras ahora mismo:",
            f"1. {top_labels[0]}",
            f"2. {top_labels[1]}",
            f"3. {top_labels[2]}",
            "",
            (
                "Esto sugiere que te conviene empezar por "
                f"{_join_hints([_support_hint(score) for score in scores[:3]])}."
            ),
            "",
            "Con esto ya puedo pasar al siguiente paso: recomendarte técnicas y construir tu método de estudio personalizado.",
        ]
    )
    return "\n".join(lines)


def build_progress_bar(current_step: int, total_steps: int) -> str:
    """Renderiza una barra de progreso limpia para WhatsApp."""

    bounded_total = max(int(total_steps), 1)
    bounded_current = min(max(int(current_step), 0), bounded_total)
    return (_FILLED_STEP * bounded_current) + (_EMPTY_STEP * (bounded_total - bounded_current))


def _score_label(score: Any) -> str:
    technique_id = str(_value(score, "technique_id", "")).strip()
    if not technique_id:
        return "Sin técnica"
    try:
        return get_technique(technique_id).display_name
    except KeyError:
        return technique_id


def _support_hint(score: Any) -> str:
    technique_id = str(_value(score, "technique_id", "")).strip()
    if not technique_id:
        return "un refuerzo más claro del estudio"
    try:
        return get_technique(technique_id).support_hint
    except KeyError:
        return technique_id


def _choice_option_lines(question: Any) -> list[str]:
    options = list(_value(question, "options", []))
    lines: list[str] = []
    for option in options:
        option_id = _value(option, "option_id", "")
        label = str(_value(option, "label", "")).strip()
        lines.append(f"{option_id}. {label}")
    return lines


def _join_hints(hints: list[str]) -> str:
    filtered = [hint for hint in hints if hint]
    if not filtered:
        return "reforzar tu forma de estudiar"
    if len(filtered) == 1:
        return filtered[0]
    if len(filtered) == 2:
        return f"{filtered[0]} y {filtered[1]}"
    return f"{filtered[0]}, {filtered[1]} y {filtered[2]}"


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
