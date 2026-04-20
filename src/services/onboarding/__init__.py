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
from .slot_extraction import (
    ONBOARDING_SLOT_FIELDS,
    OnboardingSlotExtraction,
    extract_onboarding_slots,
)

__all__ = [
    "DisabledEmailSender",
    "EmailSender",
    "InMemoryEmailSender",
    "ONBOARDING_SLOT_FIELDS",
    "OnboardingConfig",
    "OnboardingRepositoryError",
    "OnboardingService",
    "OnboardingSlotExtraction",
    "PersistStudentResult",
    "SendVerificationCodeResult",
    "VerificationMode",
    "VerifyEmailCodeResult",
    "build_onboarding_service",
    "extract_onboarding_slots",
    "load_onboarding_config",
]
