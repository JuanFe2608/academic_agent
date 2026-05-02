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
    allowed_email_domains: tuple[str, ...] = ("ucatolica.edu.co",)
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
    institutional_email_domain = _env(
        "ACADEMIC_AGENT_INSTITUTIONAL_EMAIL_DOMAIN",
        "ucatolica.edu.co",
    ).lower()
    allowed_email_domains = _resolve_allowed_email_domains(
        institutional_email_domain=institutional_email_domain,
        verification_mode=verification_mode,
    )

    return OnboardingConfig(
        institutional_email_domain=institutional_email_domain,
        allowed_email_domains=allowed_email_domains,
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


def _resolve_allowed_email_domains(
    *,
    institutional_email_domain: str,
    verification_mode: VerificationMode,
) -> tuple[str, ...]:
    raw_domains = os.getenv("ACADEMIC_AGENT_ALLOWED_EMAIL_DOMAINS", "").strip()
    if raw_domains:
        candidates = [item.strip().lower() for item in raw_domains.split(",")]
    elif _env_bool("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", False):
        candidates = ["outlook.com", "hotmail.com", "live.com", "msn.com"]
    elif verification_mode in {"disabled", "fixed"}:
        candidates = [institutional_email_domain, "outlook.com"]
    else:
        candidates = [institutional_email_domain]

    normalized: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized or [institutional_email_domain])


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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on", "required", "obligatorio"}
