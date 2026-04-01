"""Render del subflujo de desempate del perfil."""

from __future__ import annotations

from typing import Any

from agents.support.personalization.formatter import (
    build_tiebreaker_prompt as _build_tiebreaker_prompt,
)


def build_tiebreaker_prompt(
    question: Any,
    *,
    question_number: int,
    total_questions: int,
    include_intro: bool = False,
    invalid_answer: bool = False,
    answered_count: int = 0,
) -> str:
    """Delegacion ligera hacia el render determinista del dominio."""

    return _build_tiebreaker_prompt(
        question,
        question_number=question_number,
        total_questions=total_questions,
        include_intro=include_intro,
        invalid_answer=invalid_answer,
        answered_count=answered_count,
    )
