"""Servicios del dominio de onboarding."""

from .config import OnboardingConfig, VerificationMode, load_onboarding_config
from .email_sender import DisabledEmailSender, EmailSender, InMemoryEmailSender
from .service import (
    OnboardingService,
    OnboardingRepositoryError,
    PersistStudentResult,
    SendVerificationCodeResult,
    VerifyEmailCodeResult,
    build_onboarding_service,
)

__all__ = [
    "DisabledEmailSender",
    "EmailSender",
    "InMemoryEmailSender",
    "OnboardingConfig",
    "OnboardingRepositoryError",
    "OnboardingService",
    "PersistStudentResult",
    "SendVerificationCodeResult",
    "VerificationMode",
    "VerifyEmailCodeResult",
    "build_onboarding_service",
    "load_onboarding_config",
]
