"""Pruebas del parser determinista del cuestionario de personalizacion."""

from __future__ import annotations

from services.personalization.parser import (
    likert_label,
    parse_choice_answer,
    parse_likert_answer,
)


def test_parse_likert_answer_accepts_plain_numeric_value() -> None:
    result = parse_likert_answer("2")

    assert result.is_valid is True
    assert result.value == 2


def test_parse_likert_answer_accepts_numeric_value_with_label() -> None:
    result = parse_likert_answer("3. Casi siempre")

    assert result.is_valid is True
    assert result.value == 3


def test_parse_likert_answer_accepts_textual_alias() -> None:
    result = parse_likert_answer("Me pasa seguido")

    assert result.is_valid is True
    assert result.value == 2


def test_parse_likert_answer_rejects_empty_value() -> None:
    result = parse_likert_answer("   ")

    assert result.is_valid is False
    assert result.error == "empty_answer"


def test_parse_likert_answer_rejects_non_numeric_value() -> None:
    result = parse_likert_answer("muchísimo")

    assert result.is_valid is False
    assert result.error == "invalid_answer"


def test_parse_likert_answer_rejects_out_of_range_value() -> None:
    result = parse_likert_answer("4")

    assert result.is_valid is False
    assert result.error == "invalid_answer"


def test_likert_label_returns_human_readable_label() -> None:
    assert likert_label(1) == "A veces"


def test_parse_choice_answer_accepts_plain_numeric_value() -> None:
    result = parse_choice_answer("4", valid_values={1, 2, 3, 4})

    assert result.is_valid is True
    assert result.value == 4


def test_parse_choice_answer_rejects_value_out_of_range() -> None:
    result = parse_choice_answer("5", valid_values={1, 2, 3, 4})

    assert result.is_valid is False
    assert result.error == "invalid_answer"
