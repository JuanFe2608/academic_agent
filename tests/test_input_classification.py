"""Pruebas del clasificador deterministico de input."""

from __future__ import annotations

from services.conversation.input_classifier import classify_input


def test_classifies_text_with_academic_activity_intent() -> None:
    result = classify_input("Tengo parcial de calculo el viernes")

    assert result.input_type == "text"
    assert result.utility == "useful"
    assert result.is_useful is True
    assert result.possible_intent == "manage_academic_activity"
    assert "activity_management" in result.signals


def test_classifies_study_todo_sync_intent() -> None:
    result = classify_input("Sincroniza mis pendientes de estudio con Microsoft To Do")

    assert result.possible_intent == "sync_study_todo"
    assert "todo_sync" in result.signals


def test_classifies_applied_study_method_before_activity_registration() -> None:
    result = classify_input("Como preparo una exposicion de Bases de datos?")

    assert result.possible_intent == "study_method_recommendation"
    assert "study_method_recommendation" in result.signals


def test_classifies_guided_academic_support_and_socratic_mode() -> None:
    guided = classify_input("Ayudame con este taller pero no me lo resuelvas")
    socratic = classify_input("Modo socratico para taller de Calculo sobre derivadas")

    assert guided.possible_intent == "request_guided_academic_help"
    assert "guided_academic_support" in guided.signals
    assert socratic.possible_intent == "enter_socratic_mode"
    assert "guided_academic_support" in socratic.signals


def test_classifies_emoji_only_as_noise() -> None:
    result = classify_input("👍👍")

    assert result.input_type == "emoji_only"
    assert result.utility == "noise"
    assert result.is_useful is False
    assert result.possible_intent == "smalltalk_contextual"


def test_classifies_sticker_only_as_noise() -> None:
    result = classify_input(media_types=["sticker"])

    assert result.input_type == "sticker_only"
    assert result.utility == "noise"
    assert result.is_useful is False


def test_classifies_image_only_as_media_input() -> None:
    result = classify_input(media_types=["image"])

    assert result.input_type == "image_only"
    assert result.utility == "media"
    assert result.is_useful is True
    assert result.possible_intent == "media_schedule_or_activity_input"


def test_classifies_confirmation_and_critical_command() -> None:
    confirmation = classify_input("si")
    command = classify_input("borra ese evento")
    cancel = classify_input("cancelar")

    assert confirmation.utility == "confirmation"
    assert confirmation.possible_intent == "confirmation"
    assert command.utility == "command"
    assert "critical_command" in command.signals
    assert cancel.utility == "command"


def test_confirmation_requires_standalone_short_answer() -> None:
    no_academic_need = classify_input("No entiendo calculo")
    yes_academic_need = classify_input("si puedo estudiar despues")
    punctuated_confirmation = classify_input("si!")

    assert no_academic_need.utility == "useful"
    assert no_academic_need.possible_intent != "confirmation"
    assert "confirmation" not in no_academic_need.signals
    assert yes_academic_need.utility == "useful"
    assert yes_academic_need.possible_intent == "study_method_recommendation"
    assert "confirmation" not in yes_academic_need.signals
    assert punctuated_confirmation.utility == "confirmation"
