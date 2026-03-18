"""Configuracion del onboarding academico."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

VerificationMode = Literal["strict", "fixed", "disabled"]


@dataclass(frozen=True)
class OnboardingConfig:
    """Parametros deterministas del flujo de onboarding."""

    institutional_email_domain: str = "ucatolica.edu.co"
    supported_program_name: str = "Ingenieria de Sistemas y Computacion"
    student_code_length: int = 8
    full_name_max_length: int = 100
    verification_code_length: int = 6
    verification_ttl_minutes: int = 10
    max_verification_attempts: int = 5
    verification_secret: str = "development-only-secret"
    verification_mode: VerificationMode = "strict"
    fixed_verification_code: str = "123456"


def load_onboarding_config() -> OnboardingConfig:
    """Carga configuracion desde variables de entorno con defaults seguros."""

    verification_mode = _env(
        "ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE",
        "strict",
    ).lower()
    if verification_mode not in {"strict", "fixed", "disabled"}:
        verification_mode = "strict"

    return OnboardingConfig(
        institutional_email_domain=_env(
            "ACADEMIC_AGENT_INSTITUTIONAL_EMAIL_DOMAIN",
            "ucatolica.edu.co",
        ).lower(),
        supported_program_name=_env(
            "ACADEMIC_AGENT_SUPPORTED_PROGRAM_NAME",
            "Ingenieria de Sistemas y Computacion",
        ),
        student_code_length=_env_int("ACADEMIC_AGENT_STUDENT_CODE_LENGTH", 8),
        full_name_max_length=_env_int("ACADEMIC_AGENT_FULL_NAME_MAX_LENGTH", 100),
        verification_code_length=_env_int(
            "ACADEMIC_AGENT_VERIFICATION_CODE_LENGTH",
            6,
        ),
        verification_ttl_minutes=_env_int(
            "ACADEMIC_AGENT_VERIFICATION_TTL_MINUTES",
            10,
        ),
        max_verification_attempts=_env_int(
            "ACADEMIC_AGENT_MAX_VERIFICATION_ATTEMPTS",
            5,
        ),
        verification_secret=_env(
            "ACADEMIC_AGENT_VERIFICATION_SECRET",
            "development-only-secret",
        ),
        verification_mode=verification_mode,
        fixed_verification_code=_env(
            "ACADEMIC_AGENT_FIXED_VERIFICATION_CODE",
            "123456",
        ),
    )


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
