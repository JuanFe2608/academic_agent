"""Schemas reutilizables del dominio de onboarding."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel, Occupation


class ConsentState(BaseSchemaModel):
    """Seguimiento del consentimiento del usuario."""

    accepted: bool = False
    timestamp: Optional[str] = None


class StudentProfile(BaseSchemaModel):
    """Atributos del perfil del estudiante recolectados al inicio."""

    full_name: Optional[str] = None
    student_code: Optional[str] = None
    age: Optional[int] = None
    institutional_email: Optional[str] = None
    email_verified: bool = False
    academic_program: Optional[str] = None
    supported_program: Optional[bool] = None
    semester: Optional[int] = None
    average_grade: Optional[float] = None
    occupation: Optional[Occupation] = None
    persisted_student_id: Optional[int] = None


class EmailVerificationState(BaseSchemaModel):
    """Estado transitorio de verificacion del correo institucional."""

    status: Literal["idle", "sent", "verified"] = "idle"
    attempts: int = 0
    resend_count: int = 0
    expires_at: Optional[str] = None
    last_error: Optional[str] = None


class OnboardingState(BaseSchemaModel):
    """Metadatos operativos del flujo de onboarding."""

    current_field: Optional[str] = None
    pending_student_code_scope_confirmation: bool = False
    email_verification: EmailVerificationState = Field(
        default_factory=EmailVerificationState
    )
    persistence_error: Optional[str] = None


__all__ = [
    "ConsentState",
    "EmailVerificationState",
    "OnboardingState",
    "StudentProfile",
]
