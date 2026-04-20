"""Servicios de onboarding: verificacion de correo y persistencia."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from .config import OnboardingConfig, load_onboarding_config
from .email_sender import DisabledEmailSender, EmailSender
from repositories.onboarding.repository import (
    DuplicateInstitutionalEmailError,
    DuplicateStudentCodeError,
    InMemoryOnboardingRepository,
    OnboardingRepository,
    OnboardingRepositoryError,
    build_postgres_repository,
)


@dataclass(frozen=True)
class SendVerificationCodeResult:
    """Resultado de generar y enviar un codigo de verificacion."""

    sent: bool
    error_code: str | None = None
    expires_at: datetime | None = None
    attempts: int = 0
    resend_count: int = 0
    debug_code: str | None = None


@dataclass(frozen=True)
class VerifyEmailCodeResult:
    """Resultado de validar el codigo recibido."""

    verified: bool
    error_code: str | None = None
    expires_at: datetime | None = None
    attempts: int = 0
    max_attempts: int = 0


@dataclass(frozen=True)
class PersistStudentResult:
    """Resultado de guardar al estudiante."""

    persisted: bool
    student_id: int | None = None
    error_code: str | None = None
    detail: str | None = None


class OnboardingService:
    """Orquesta verificacion y persistencia del onboarding."""

    def __init__(
        self,
        config: OnboardingConfig,
        repository: OnboardingRepository,
        email_sender: EmailSender | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.email_sender = email_sender or DisabledEmailSender()

    def send_email_verification(self, institutional_email: str) -> SendVerificationCodeResult:
        """Genera un codigo, guarda su hash y lo envia al correo."""

        if self.config.verification_mode == "disabled":
            return SendVerificationCodeResult(
                sent=True,
                error_code="verification_disabled",
            )

        if self.repository.student_exists_by_email(institutional_email):
            return SendVerificationCodeResult(sent=False, error_code="duplicate_email")

        verification_code = self._resolve_verification_code()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.config.verification_ttl_minutes
        )
        code_hash = _hash_verification_code(
            institutional_email,
            verification_code,
            self.config.verification_secret,
        )
        record = self.repository.upsert_verification_challenge(
            institutional_email=institutional_email,
            code_hash=code_hash,
            expires_at=expires_at,
            max_attempts=self.config.max_verification_attempts,
        )

        if self.config.verification_mode == "fixed":
            return SendVerificationCodeResult(
                sent=True,
                error_code="fixed_code",
                expires_at=record.expires_at,
                attempts=record.attempts,
                resend_count=record.resend_count,
                debug_code=verification_code,
            )

        sent = self.email_sender.send_verification_code(
            institutional_email,
            verification_code,
            expires_at,
        )
        if not sent:
            self.repository.delete_verification_challenge(institutional_email)
            return SendVerificationCodeResult(
                sent=False,
                error_code="email_sender_unavailable",
            )

        return SendVerificationCodeResult(
            sent=True,
            expires_at=record.expires_at,
            attempts=record.attempts,
            resend_count=record.resend_count,
        )

    def verify_email_code(
        self,
        institutional_email: str,
        submitted_code: str,
    ) -> VerifyEmailCodeResult:
        """Valida codigo, expiracion e intentos maximos."""

        challenge = self.repository.get_verification_challenge(institutional_email)
        if challenge is None:
            return VerifyEmailCodeResult(
                verified=False,
                error_code="challenge_not_found",
            )

        now = datetime.now(timezone.utc)
        if challenge.attempts >= challenge.max_attempts:
            return VerifyEmailCodeResult(
                verified=False,
                error_code="max_attempts_exceeded",
                expires_at=challenge.expires_at,
                attempts=challenge.attempts,
                max_attempts=challenge.max_attempts,
            )

        if now >= _ensure_aware(challenge.expires_at):
            return VerifyEmailCodeResult(
                verified=False,
                error_code="expired",
                expires_at=challenge.expires_at,
                attempts=challenge.attempts,
                max_attempts=challenge.max_attempts,
            )

        expected_hash = _hash_verification_code(
            institutional_email,
            submitted_code,
            self.config.verification_secret,
        )
        if not hmac.compare_digest(expected_hash, challenge.code_hash):
            updated = self.repository.increment_verification_attempts(institutional_email)
            record = updated or challenge
            error_code = (
                "max_attempts_exceeded"
                if record.attempts >= record.max_attempts
                else "invalid_code"
            )
            return VerifyEmailCodeResult(
                verified=False,
                error_code=error_code,
                expires_at=record.expires_at,
                attempts=record.attempts,
                max_attempts=record.max_attempts,
            )

        self.repository.delete_verification_challenge(institutional_email)
        return VerifyEmailCodeResult(
            verified=True,
            expires_at=challenge.expires_at,
            attempts=challenge.attempts,
            max_attempts=challenge.max_attempts,
        )

    def persist_student(self, profile: Any) -> PersistStudentResult:
        """Guarda al estudiante solo cuando el correo ya esta verificado."""

        if not bool(_profile_value(profile, "email_verified", False)):
            return PersistStudentResult(
                persisted=False,
                error_code="email_not_verified",
                detail="El correo institucional aun no ha sido verificado.",
            )
        try:
            student_id = self.repository.create_student(profile)
        except DuplicateInstitutionalEmailError as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="duplicate_email",
                detail=str(exc),
            )
        except DuplicateStudentCodeError as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="duplicate_student_code",
                detail=str(exc),
            )
        except (OnboardingRepositoryError, RepositoryConfigurationError) as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="persistence_error",
                detail=str(exc),
            )

        return PersistStudentResult(persisted=True, student_id=student_id)

    def persist_verified_identity(self, profile: Any) -> PersistStudentResult:
        """Crea o actualiza la identidad minima antes del OAuth bloqueante."""

        if not bool(_profile_value(profile, "email_verified", False)):
            return PersistStudentResult(
                persisted=False,
                error_code="email_not_verified",
                detail="El correo institucional aun no ha sido verificado.",
            )
        required_fields = (
            "full_name",
            "student_code",
            "age",
            "institutional_email",
        )
        missing = [
            field
            for field in required_fields
            if _profile_value(profile, field) in (None, "")
        ]
        if missing:
            return PersistStudentResult(
                persisted=False,
                error_code="missing_identity_fields",
                detail=f"Faltan campos de identidad para OAuth: {', '.join(missing)}.",
            )
        try:
            student_id = self.repository.upsert_verified_student_identity(profile)
        except DuplicateInstitutionalEmailError as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="duplicate_email",
                detail=str(exc),
            )
        except DuplicateStudentCodeError as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="duplicate_student_code",
                detail=str(exc),
            )
        except (OnboardingRepositoryError, RepositoryConfigurationError) as exc:
            return PersistStudentResult(
                persisted=False,
                error_code="persistence_error",
                detail=str(exc),
            )

        return PersistStudentResult(persisted=True, student_id=student_id)

    def _resolve_verification_code(self) -> str:
        fixed_code = str(self.config.fixed_verification_code or "").strip()
        if self.config.verification_mode == "fixed" and fixed_code:
            return fixed_code
        return _generate_numeric_code(self.config.verification_code_length)


def build_onboarding_service() -> OnboardingService:
    """Construye el servicio por defecto segun la configuracion del entorno."""

    config = load_onboarding_config()
    repository = _build_repository()
    sender = DisabledEmailSender()
    return OnboardingService(config=config, repository=repository, email_sender=sender)


def _build_repository() -> OnboardingRepository:
    if os.getenv("ACADEMIC_AGENT_USE_IN_MEMORY_ONBOARDING_REPO", "").strip() == "1":
        return InMemoryOnboardingRepository()
    return build_postgres_repository(database_url_from_env())


def _generate_numeric_code(length: int) -> str:
    limit = 10**length
    return f"{secrets.randbelow(limit):0{length}d}"


def _hash_verification_code(
    institutional_email: str,
    verification_code: str,
    secret: str,
) -> str:
    payload = f"{institutional_email.lower()}:{verification_code}".encode("utf-8")
    key = secret.encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _profile_value(profile: Any, field: str, default: Any = None) -> Any:
    if isinstance(profile, dict):
        return profile.get(field, default)
    return getattr(profile, field, default)
