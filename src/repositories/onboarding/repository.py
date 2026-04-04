"""Repositorios para persistencia del onboarding."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url


class OnboardingRepositoryError(Exception):
    """Error base del repositorio de onboarding."""


class DuplicateInstitutionalEmailError(OnboardingRepositoryError):
    """El correo institucional ya existe."""


class DuplicateStudentCodeError(OnboardingRepositoryError):
    """El codigo estudiantil ya existe."""


@dataclass(frozen=True)
class VerificationChallengeRecord:
    """Representa el reto activo de verificacion de correo."""

    institutional_email: str
    code_hash: str
    expires_at: datetime
    attempts: int
    max_attempts: int
    resend_count: int


class OnboardingRepository(Protocol):
    """Contrato de persistencia del onboarding."""

    def student_exists_by_email(self, institutional_email: str) -> bool: ...

    def student_exists_by_code(self, student_code: str) -> bool: ...

    def upsert_verification_challenge(
        self,
        institutional_email: str,
        code_hash: str,
        expires_at: datetime,
        max_attempts: int,
    ) -> VerificationChallengeRecord: ...

    def get_verification_challenge(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None: ...

    def increment_verification_attempts(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None: ...

    def delete_verification_challenge(self, institutional_email: str) -> None: ...

    def create_student(self, profile: Any) -> int: ...


class InMemoryOnboardingRepository:
    """Repositorio en memoria para pruebas unitarias."""

    def __init__(self) -> None:
        self._students_by_email: dict[str, dict[str, Any]] = {}
        self._students_by_code: dict[str, dict[str, Any]] = {}
        self._verification_challenges: dict[str, VerificationChallengeRecord] = {}
        self._next_student_id = 1

    def student_exists_by_email(self, institutional_email: str) -> bool:
        return institutional_email in self._students_by_email

    def student_exists_by_code(self, student_code: str) -> bool:
        return student_code in self._students_by_code

    def upsert_verification_challenge(
        self,
        institutional_email: str,
        code_hash: str,
        expires_at: datetime,
        max_attempts: int,
    ) -> VerificationChallengeRecord:
        current = self._verification_challenges.get(institutional_email)
        resend_count = (current.resend_count if current else 0) + 1
        record = VerificationChallengeRecord(
            institutional_email=institutional_email,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            max_attempts=max_attempts,
            resend_count=resend_count,
        )
        self._verification_challenges[institutional_email] = record
        return record

    def get_verification_challenge(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None:
        return self._verification_challenges.get(institutional_email)

    def increment_verification_attempts(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None:
        record = self._verification_challenges.get(institutional_email)
        if record is None:
            return None
        updated = VerificationChallengeRecord(
            institutional_email=record.institutional_email,
            code_hash=record.code_hash,
            expires_at=record.expires_at,
            attempts=record.attempts + 1,
            max_attempts=record.max_attempts,
            resend_count=record.resend_count,
        )
        self._verification_challenges[institutional_email] = updated
        return updated

    def delete_verification_challenge(self, institutional_email: str) -> None:
        self._verification_challenges.pop(institutional_email, None)

    def create_student(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")
        if self.student_exists_by_email(institutional_email):
            raise DuplicateInstitutionalEmailError(institutional_email)
        if self.student_exists_by_code(student_code):
            raise DuplicateStudentCodeError(student_code)

        student_id = self._next_student_id
        self._next_student_id += 1

        payload = {
            "id": student_id,
            "full_name": _profile_value(profile, "full_name"),
            "student_code": student_code,
            "age": _profile_value(profile, "age"),
            "institutional_email": institutional_email,
            "email_verified": bool(_profile_value(profile, "email_verified", False)),
            "academic_program": _profile_value(profile, "academic_program"),
            "supported_program": _profile_value(profile, "supported_program"),
            "semester": _profile_value(profile, "semester"),
            "average_grade": _profile_value(profile, "average_grade"),
            "created_at": datetime.now(timezone.utc),
        }
        self._students_by_email[institutional_email] = payload
        self._students_by_code[student_code] = payload
        return student_id


class PostgresOnboardingRepository:
    """Repositorio PostgreSQL preparado para produccion."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def student_exists_by_email(self, institutional_email: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM students WHERE institutional_email = %s LIMIT 1",
                (institutional_email,),
            ).fetchone()
            return row is not None

    def student_exists_by_code(self, student_code: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM students WHERE student_code = %s LIMIT 1",
                (student_code,),
            ).fetchone()
            return row is not None

    def upsert_verification_challenge(
        self,
        institutional_email: str,
        code_hash: str,
        expires_at: datetime,
        max_attempts: int,
    ) -> VerificationChallengeRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO email_verification_challenges (
                    institutional_email,
                    code_hash,
                    expires_at,
                    attempts,
                    max_attempts,
                    resend_count,
                    last_sent_at
                ) VALUES (%s, %s, %s, 0, %s, 1, NOW())
                ON CONFLICT (institutional_email)
                DO UPDATE SET
                    code_hash = EXCLUDED.code_hash,
                    expires_at = EXCLUDED.expires_at,
                    attempts = 0,
                    max_attempts = EXCLUDED.max_attempts,
                    resend_count = email_verification_challenges.resend_count + 1,
                    last_sent_at = NOW(),
                    updated_at = NOW()
                RETURNING institutional_email, code_hash, expires_at, attempts, max_attempts, resend_count
                """,
                (institutional_email, code_hash, expires_at, max_attempts),
            ).fetchone()
            conn.commit()
        return _challenge_from_row(row)

    def get_verification_challenge(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT institutional_email, code_hash, expires_at, attempts, max_attempts, resend_count
                FROM email_verification_challenges
                WHERE institutional_email = %s
                """,
                (institutional_email,),
            ).fetchone()
            if row is None:
                return None
            return _challenge_from_row(row)

    def increment_verification_attempts(
        self,
        institutional_email: str,
    ) -> VerificationChallengeRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE email_verification_challenges
                SET attempts = attempts + 1,
                    updated_at = NOW()
                WHERE institutional_email = %s
                RETURNING institutional_email, code_hash, expires_at, attempts, max_attempts, resend_count
                """,
                (institutional_email,),
            ).fetchone()
            conn.commit()
            if row is None:
                return None
            return _challenge_from_row(row)

    def delete_verification_challenge(self, institutional_email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM email_verification_challenges WHERE institutional_email = %s",
                (institutional_email,),
            )
            conn.commit()

    def create_student(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")

        if self.student_exists_by_email(institutional_email):
            raise DuplicateInstitutionalEmailError(institutional_email)
        if self.student_exists_by_code(student_code):
            raise DuplicateStudentCodeError(student_code)

        academic_program = _profile_value(profile, "academic_program")
        supported_program = bool(_profile_value(profile, "supported_program", False))

        with self._connect() as conn:
            program_id = None
            if academic_program:
                row = conn.execute(
                    "SELECT id FROM academic_programs WHERE name = %s LIMIT 1",
                    (academic_program,),
                ).fetchone()
                if row is not None:
                    program_id = row[0] if not isinstance(row, dict) else row["id"]

            row = conn.execute(
                """
                INSERT INTO students (
                    full_name,
                    student_code,
                    age,
                    institutional_email,
                    email_verified,
                    email_verified_at,
                    program_id,
                    supported_program,
                    semester,
                    average_grade
                ) VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    _profile_value(profile, "full_name"),
                    student_code,
                    _profile_value(profile, "age"),
                    institutional_email,
                    bool(_profile_value(profile, "email_verified", False)),
                    program_id,
                    supported_program,
                    _profile_value(profile, "semester"),
                    _profile_value(profile, "average_grade"),
                ),
            ).fetchone()
            conn.commit()
        return row[0] if not isinstance(row, dict) else row["id"]

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - depende del driver real
            raise OnboardingRepositoryError(str(exc)) from exc


def build_postgres_repository(database_url: str | None) -> PostgresOnboardingRepository:
    """Construye el repositorio PostgreSQL o falla con mensaje claro."""

    return PostgresOnboardingRepository(require_database_url(database_url))


def _challenge_from_row(row: Any) -> VerificationChallengeRecord:
    return VerificationChallengeRecord(
        institutional_email=row["institutional_email"],
        code_hash=row["code_hash"],
        expires_at=row["expires_at"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        resend_count=row["resend_count"],
    )


def _profile_value(profile: Any, field: str, default: Any = None) -> Any:
    if isinstance(profile, dict):
        return profile.get(field, default)
    return getattr(profile, field, default)
