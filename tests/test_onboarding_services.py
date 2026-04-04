"""Pruebas de validacion y servicios del onboarding."""

from __future__ import annotations

from agents.support.onboarding.validators import (
    validate_average_grade,
    validate_institutional_email,
)
from repositories.onboarding.repository import InMemoryOnboardingRepository
from services.onboarding import InMemoryEmailSender, OnboardingConfig, OnboardingService


def test_validate_institutional_email_normalizes_to_lowercase() -> None:
    config = OnboardingConfig()

    result = validate_institutional_email("Estudiante@UCATOLICA.EDU.CO", config)

    assert result.is_valid is True
    assert result.value == "estudiante@ucatolica.edu.co"


def test_validate_institutional_email_accepts_outlook_when_allowed() -> None:
    config = OnboardingConfig(
        allowed_email_domains=("ucatolica.edu.co", "outlook.com")
    )

    result = validate_institutional_email("Prueba@Outlook.com", config)

    assert result.is_valid is True
    assert result.value == "prueba@outlook.com"


def test_validate_average_grade_rejects_comma_separator() -> None:
    config = OnboardingConfig()

    result = validate_average_grade("76,5", config)

    assert result.is_valid is False


def test_onboarding_service_sends_and_verifies_code() -> None:
    config = OnboardingConfig(verification_secret="test-secret")
    repository = InMemoryOnboardingRepository()
    sender = InMemoryEmailSender()
    service = OnboardingService(config=config, repository=repository, email_sender=sender)

    send_result = service.send_email_verification("ana@ucatolica.edu.co")
    sent_email, sent_code, _ = sender.sent_messages[-1]
    verify_result = service.verify_email_code(sent_email, sent_code)

    assert send_result.sent is True
    assert verify_result.verified is True
    assert repository.get_verification_challenge(sent_email) is None


def test_onboarding_service_limits_invalid_attempts() -> None:
    config = OnboardingConfig(verification_secret="test-secret", max_verification_attempts=2)
    repository = InMemoryOnboardingRepository()
    sender = InMemoryEmailSender()
    service = OnboardingService(config=config, repository=repository, email_sender=sender)

    service.send_email_verification("ana@ucatolica.edu.co")
    first = service.verify_email_code("ana@ucatolica.edu.co", "000000")
    second = service.verify_email_code("ana@ucatolica.edu.co", "111111")

    assert first.verified is False
    assert first.error_code == "invalid_code"
    assert second.verified is False
    assert second.error_code == "max_attempts_exceeded"


def test_onboarding_service_rejects_duplicate_student_code_on_persist() -> None:
    config = OnboardingConfig()
    repository = InMemoryOnboardingRepository()
    sender = InMemoryEmailSender()
    service = OnboardingService(config=config, repository=repository, email_sender=sender)

    first_profile = {
        "full_name": "Ana Maria Perez",
        "student_code": "67000912",
        "age": 20,
        "institutional_email": "ana1@ucatolica.edu.co",
        "email_verified": True,
        "academic_program": "Ingenieria de Sistemas y Computacion",
        "supported_program": True,
        "semester": 6,
        "average_grade": 85.0,
    }
    second_profile = {
        "full_name": "Ana Maria Gomez",
        "student_code": "67000912",
        "age": 21,
        "institutional_email": "ana2@ucatolica.edu.co",
        "email_verified": True,
        "academic_program": "Ingenieria de Sistemas y Computacion",
        "supported_program": True,
        "semester": 7,
        "average_grade": 82.0,
    }

    first_result = service.persist_student(first_profile)
    second_result = service.persist_student(second_profile)

    assert first_result.persisted is True
    assert second_result.persisted is False
    assert second_result.error_code == "duplicate_student_code"


def test_onboarding_service_can_skip_verification_in_disabled_mode() -> None:
    config = OnboardingConfig(verification_mode="disabled")
    repository = InMemoryOnboardingRepository()
    service = OnboardingService(config=config, repository=repository)

    result = service.send_email_verification("ana@ucatolica.edu.co")

    assert result.sent is True
    assert result.error_code == "verification_disabled"
    assert repository.get_verification_challenge("ana@ucatolica.edu.co") is None


def test_onboarding_service_can_use_fixed_verification_code() -> None:
    config = OnboardingConfig(
        verification_mode="fixed",
        fixed_verification_code="654321",
        verification_secret="test-secret",
    )
    repository = InMemoryOnboardingRepository()
    service = OnboardingService(config=config, repository=repository)

    send_result = service.send_email_verification("ana@ucatolica.edu.co")
    verify_result = service.verify_email_code("ana@ucatolica.edu.co", "654321")

    assert send_result.sent is True
    assert send_result.error_code == "fixed_code"
    assert send_result.debug_code == "654321"
    assert verify_result.verified is True
