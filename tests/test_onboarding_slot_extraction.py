"""Pruebas del extractor incremental de slots de onboarding."""

from __future__ import annotations

from services.onboarding import OnboardingConfig, extract_onboarding_slots


def test_extract_onboarding_slots_from_natural_profile_sentence() -> None:
    config = OnboardingConfig()

    result = extract_onboarding_slots(
        "Soy Andres Gomez, tengo 20 y voy en octavo.",
        config=config,
    )

    assert result.raw_slots == {
        "full_name": "Andres Gomez",
        "age": "20",
        "semester": "8",
    }


def test_extract_onboarding_slots_from_labeled_profile_data() -> None:
    config = OnboardingConfig()

    result = extract_onboarding_slots(
        (
            "Me llamo Ana Maria Perez. Código 67000912. "
            "Correo ANA@UCATOLICA.EDU.CO. Promedio 85.5"
        ),
        config=config,
    )

    assert result.raw_slots["full_name"] == "Ana Maria Perez"
    assert result.raw_slots["student_code"] == "67000912"
    assert result.raw_slots["institutional_email"] == "ANA@UCATOLICA.EDU.CO"
    assert result.raw_slots["average_grade"] == "85.5"


def test_extract_onboarding_slots_respects_candidate_fields() -> None:
    config = OnboardingConfig()

    result = extract_onboarding_slots(
        "Soy Andres Gomez, tengo 20 y voy en octavo.",
        config=config,
        candidate_fields=["age"],
    )

    assert result.raw_slots == {"age": "20"}
