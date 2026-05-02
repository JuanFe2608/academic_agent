"""Schemas reutilizables del dominio de onboarding."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel, Occupation


class ConsentState(BaseSchemaModel):
    """Seguimiento del consentimiento del usuario."""

    accepted: bool = False
    timestamp: Optional[str] = None
    policy_url: Optional[str] = None
    policy_version: Optional[str] = None
    channel: Optional[str] = None


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
    average_grade: Optional[int] = None
    occupation: Optional[Occupation] = None
    persisted_student_id: Optional[int] = None


class MicrosoftOAuthOnboardingState(BaseSchemaModel):
    """Estado transitorio del paso OAuth Microsoft durante onboarding."""

    status: Literal["idle", "pending", "authorized", "failed"] = "idle"
    state_token: Optional[str] = None
    authorization_url: Optional[str] = None
    expires_at: Optional[str] = None
    attempts: int = 0
    last_error: Optional[str] = None


class OnboardingState(BaseSchemaModel):
    """Metadatos operativos del flujo de onboarding."""

    current_field: Optional[str] = None
    pending_student_code_scope_confirmation: bool = False
    pending_low_grade_confirmation: bool = False
    pending_low_grade_value: Optional[int] = None
    slot_errors: dict[str, str] = Field(default_factory=dict)
    microsoft_oauth: MicrosoftOAuthOnboardingState = Field(
        default_factory=MicrosoftOAuthOnboardingState
    )
    persistence_error: Optional[str] = None
    profile_stage: Literal["collecting", "confirming", "persisting"] = "collecting"


__all__ = [
    "ConsentState",
    "MicrosoftOAuthOnboardingState",
    "OnboardingState",
    "StudentProfile",
]
