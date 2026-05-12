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

    def upsert_verified_student_identity(self, profile: Any) -> int: ...

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

    def upsert_verified_student_identity(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")
        persisted_student_id = _profile_value(profile, "persisted_student_id")
        existing_by_email = self._students_by_email.get(institutional_email)
        existing_by_code = self._students_by_code.get(student_code)

        if persisted_student_id is not None:
            expected_id = int(persisted_student_id)
            if existing_by_email and int(existing_by_email["id"]) != expected_id:
                raise DuplicateInstitutionalEmailError(institutional_email)
            if existing_by_code and int(existing_by_code["id"]) != expected_id:
                raise DuplicateStudentCodeError(student_code)
            existing = existing_by_email or existing_by_code
            if existing is None:
                existing = _student_payload(profile, student_id=expected_id)
            else:
                existing.update(_student_payload(profile, student_id=expected_id))
            self._replace_student_indexes(existing, institutional_email, student_code)
            self._students_by_email[institutional_email] = existing
            self._students_by_code[student_code] = existing
            return expected_id

        existing = existing_by_email or existing_by_code
        if existing_by_email and existing_by_code and existing_by_email["id"] != existing_by_code["id"]:
            raise DuplicateStudentCodeError(student_code)
        if existing_by_email and existing_by_code is None:
            raise DuplicateInstitutionalEmailError(institutional_email)
        if existing_by_code and existing_by_email is None:
            raise DuplicateStudentCodeError(student_code)
        if existing is not None:
            existing.update(_student_payload(profile, student_id=int(existing["id"])))
            self._replace_student_indexes(existing, institutional_email, student_code)
            self._students_by_email[institutional_email] = existing
            self._students_by_code[student_code] = existing
            return int(existing["id"])

        student_id = self._next_student_id
        self._next_student_id += 1
        payload = _student_payload(profile, student_id=student_id)
        self._students_by_email[institutional_email] = payload
        self._students_by_code[student_code] = payload
        return student_id

    def create_student(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")
        persisted_student_id = _profile_value(profile, "persisted_student_id")
        existing_by_email = self._students_by_email.get(institutional_email)
        existing_by_code = self._students_by_code.get(student_code)

        if persisted_student_id is not None:
            expected_id = int(persisted_student_id)
            if existing_by_email and int(existing_by_email["id"]) != expected_id:
                raise DuplicateInstitutionalEmailError(institutional_email)
            if existing_by_code and int(existing_by_code["id"]) != expected_id:
                raise DuplicateStudentCodeError(student_code)
            existing = existing_by_email or existing_by_code
            if existing is None:
                existing = _student_payload(profile, student_id=expected_id)
            else:
                existing.update(_student_payload(profile, student_id=expected_id))
            self._replace_student_indexes(existing, institutional_email, student_code)
            self._students_by_email[institutional_email] = existing
            self._students_by_code[student_code] = existing
            return expected_id

        # Si el mismo email y código ya apuntan al mismo estudiante (p.ej. insertado
        # parcialmente por el flujo OAuth), completar el perfil en lugar de rechazar.
        if (
            existing_by_email
            and existing_by_code
            and int(existing_by_email["id"]) == int(existing_by_code["id"])
        ):
            existing = existing_by_email
            existing.update(_student_payload(profile, student_id=int(existing["id"])))
            self._replace_student_indexes(existing, institutional_email, student_code)
            self._students_by_email[institutional_email] = existing
            self._students_by_code[student_code] = existing
            return int(existing["id"])

        if self.student_exists_by_email(institutional_email):
            raise DuplicateInstitutionalEmailError(institutional_email)
        if self.student_exists_by_code(student_code):
            raise DuplicateStudentCodeError(student_code)

        student_id = self._next_student_id
        self._next_student_id += 1

        payload = _student_payload(profile, student_id=student_id)
        self._students_by_email[institutional_email] = payload
        self._students_by_code[student_code] = payload
        return student_id

    def _replace_student_indexes(
        self,
        student: dict[str, object],
        institutional_email: str,
        student_code: str,
    ) -> None:
        student_id = int(student["id"])
        for email, indexed in list(self._students_by_email.items()):
            if email != institutional_email and int(indexed["id"]) == student_id:
                self._students_by_email.pop(email, None)
        for code, indexed in list(self._students_by_code.items()):
            if code != student_code and int(indexed["id"]) == student_id:
                self._students_by_code.pop(code, None)


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

    def upsert_verified_student_identity(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")
        existing_id = _profile_value(profile, "persisted_student_id")
        academic_program = _profile_value(profile, "academic_program")
        supported_program = bool(_profile_value(profile, "supported_program", False))
        email_verified = bool(_profile_value(profile, "email_verified", False))

        with self._connect() as conn:
            program_id = self._program_id(conn, academic_program)
            if existing_id is not None:
                self._ensure_unique_identity(
                    conn,
                    student_id=int(existing_id),
                    institutional_email=institutional_email,
                    student_code=student_code,
                )
                row = conn.execute(
                    """
                    UPDATE students
                    SET full_name = %s,
                        student_code = %s,
                        age = %s,
                        institutional_email = %s,
                        email_verified = students.email_verified OR %s,
                        email_verified_at = CASE
                            WHEN students.email_verified OR %s
                            THEN COALESCE(students.email_verified_at, NOW())
                            ELSE NULL
                        END,
                        program_id = %s,
                        supported_program = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        _profile_value(profile, "full_name"),
                        student_code,
                        _profile_value(profile, "age"),
                        institutional_email,
                        email_verified,
                        email_verified,
                        program_id,
                        supported_program,
                        int(existing_id),
                    ),
                ).fetchone()
                if row is None:
                    raise OnboardingRepositoryError(
                        f"No encontre estudiante id={existing_id} para actualizar identidad."
                    )
                conn.commit()
                return row[0] if not isinstance(row, dict) else row["id"]

            email_id = self._student_id_by_email(conn, institutional_email)
            code_id = self._student_id_by_code(conn, student_code)
            if email_id is not None and code_id is not None and int(email_id) != int(code_id):
                raise DuplicateStudentCodeError(student_code)
            if email_id is not None and code_id is None:
                raise DuplicateInstitutionalEmailError(institutional_email)
            if code_id is not None and email_id is None:
                raise DuplicateStudentCodeError(student_code)

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
                ) VALUES (
                    %s, %s, %s, %s,
                    %s,
                    CASE WHEN %s THEN NOW() ELSE NULL END,
                    %s, %s, NULL, NULL
                )
                ON CONFLICT (student_code) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    age = EXCLUDED.age,
                    institutional_email = EXCLUDED.institutional_email,
                    email_verified = students.email_verified OR EXCLUDED.email_verified,
                    email_verified_at = CASE
                        WHEN students.email_verified OR EXCLUDED.email_verified
                        THEN COALESCE(students.email_verified_at, NOW())
                        ELSE NULL
                    END,
                    program_id = EXCLUDED.program_id,
                    supported_program = EXCLUDED.supported_program,
                    updated_at = NOW()
                WHERE students.institutional_email = EXCLUDED.institutional_email
                RETURNING id
                """,
                (
                    _profile_value(profile, "full_name"),
                    student_code,
                    _profile_value(profile, "age"),
                    institutional_email,
                    email_verified,
                    email_verified,
                    program_id,
                    supported_program,
                ),
            ).fetchone()
            if row is None:
                raise DuplicateStudentCodeError(student_code)
            conn.commit()
        return row[0] if not isinstance(row, dict) else row["id"]

    def create_student(self, profile: Any) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")

        persisted_student_id = _profile_value(profile, "persisted_student_id")
        if persisted_student_id is not None:
            return self._complete_existing_student(
                profile,
                student_id=int(persisted_student_id),
            )

        # Si el mismo email y código ya apuntan al mismo estudiante (p.ej. insertado
        # parcialmente por el flujo OAuth), completar el perfil en lugar de rechazar.
        with self._connect() as conn:
            email_id = self._student_id_by_email(conn, institutional_email)
            code_id = self._student_id_by_code(conn, student_code)

        if email_id is not None and code_id is not None and int(email_id) == int(code_id):
            return self._complete_existing_student(profile, student_id=int(email_id))
        if email_id is not None:
            raise DuplicateInstitutionalEmailError(institutional_email)
        if code_id is not None:
            raise DuplicateStudentCodeError(student_code)

        academic_program = _profile_value(profile, "academic_program")
        supported_program = bool(_profile_value(profile, "supported_program", False))

        with self._connect() as conn:
            program_id = self._program_id(conn, academic_program)

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

    def _complete_existing_student(self, profile: Any, *, student_id: int) -> int:
        institutional_email = str(_profile_value(profile, "institutional_email") or "")
        student_code = str(_profile_value(profile, "student_code") or "")
        academic_program = _profile_value(profile, "academic_program")
        supported_program = bool(_profile_value(profile, "supported_program", False))

        with self._connect() as conn:
            self._ensure_unique_identity(
                conn,
                student_id=student_id,
                institutional_email=institutional_email,
                student_code=student_code,
            )
            program_id = self._program_id(conn, academic_program)
            row = conn.execute(
                """
                UPDATE students
                SET full_name = %s,
                    student_code = %s,
                    age = %s,
                    institutional_email = %s,
                    email_verified = %s,
                    email_verified_at = CASE
                        WHEN %s THEN COALESCE(email_verified_at, NOW())
                        ELSE NULL
                    END,
                    program_id = %s,
                    supported_program = %s,
                    semester = %s,
                    average_grade = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (
                    _profile_value(profile, "full_name"),
                    student_code,
                    _profile_value(profile, "age"),
                    institutional_email,
                    bool(_profile_value(profile, "email_verified", False)),
                    bool(_profile_value(profile, "email_verified", False)),
                    program_id,
                    supported_program,
                    _profile_value(profile, "semester"),
                    _profile_value(profile, "average_grade"),
                    student_id,
                ),
            ).fetchone()
            if row is None:
                raise OnboardingRepositoryError(
                    f"No encontre estudiante id={student_id} para completar perfil."
                )
            conn.commit()
        return row[0] if not isinstance(row, dict) else row["id"]

    def _program_id(self, conn: Any, academic_program: Any) -> int | None:
        if not academic_program:
            return None
        row = conn.execute(
            "SELECT id FROM academic_programs WHERE name = %s LIMIT 1",
            (academic_program,),
        ).fetchone()
        if row is None:
            return None
        return row[0] if not isinstance(row, dict) else row["id"]

    def _ensure_unique_identity(
        self,
        conn: Any,
        *,
        student_id: int,
        institutional_email: str,
        student_code: str,
    ) -> None:
        email_row = conn.execute(
            "SELECT id FROM students WHERE institutional_email = %s LIMIT 1",
            (institutional_email,),
        ).fetchone()
        email_id = None if email_row is None else (email_row[0] if not isinstance(email_row, dict) else email_row["id"])
        if email_id is not None and int(email_id) != int(student_id):
            raise DuplicateInstitutionalEmailError(institutional_email)

        code_row = conn.execute(
            "SELECT id FROM students WHERE student_code = %s LIMIT 1",
            (student_code,),
        ).fetchone()
        code_id = None if code_row is None else (code_row[0] if not isinstance(code_row, dict) else code_row["id"])
        if code_id is not None and int(code_id) != int(student_id):
            raise DuplicateStudentCodeError(student_code)

    def _student_id_by_email(self, conn: Any, institutional_email: str) -> int | None:
        row = conn.execute(
            "SELECT id FROM students WHERE institutional_email = %s LIMIT 1",
            (institutional_email,),
        ).fetchone()
        if row is None:
            return None
        return int(row[0] if not isinstance(row, dict) else row["id"])

    def _student_id_by_code(self, conn: Any, student_code: str) -> int | None:
        row = conn.execute(
            "SELECT id FROM students WHERE student_code = %s LIMIT 1",
            (student_code,),
        ).fetchone()
        if row is None:
            return None
        return int(row[0] if not isinstance(row, dict) else row["id"])

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except OnboardingRepositoryError:
            raise
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


def _student_payload(profile: Any, *, student_id: int) -> dict[str, Any]:
    institutional_email = str(_profile_value(profile, "institutional_email") or "")
    student_code = str(_profile_value(profile, "student_code") or "")
    return {
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
