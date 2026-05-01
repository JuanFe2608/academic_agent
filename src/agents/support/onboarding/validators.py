"""Validadores y normalizadores deterministas del onboarding."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from agents.support.onboarding.messages import PROFILE_FIELD_ORDER
from services.onboarding import OnboardingConfig

_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)
_DECIMAL_PATTERN = re.compile(r"^\d+(?:\.\d{1,2})?$")

_YES_TOKENS = {"si", "sip", "s", "claro", "ok", "vale", "yes", "1"}
_NO_TOKENS = {"no", "nop", "n", "negativo", "2"}
_NAME_LOWER_PARTICLES = {"de", "del", "la", "las", "los", "y"}


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de una validacion de campo."""

    value: Any = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None


def validate_full_name(raw: str, config: OnboardingConfig) -> ValidationResult:
    """Valida y normaliza nombre completo."""

    normalized = collapse_spaces(raw)
    if not normalized or len(normalized) < 2:
        return ValidationResult(error="invalid_full_name")
    if len(normalized) > config.full_name_max_length:
        return ValidationResult(error="invalid_full_name")
    if any(char.isdigit() for char in normalized):
        return ValidationResult(error="invalid_full_name")
    if any(not (char.isalpha() or char.isspace()) for char in normalized):
        return ValidationResult(error="invalid_full_name")

    parts = normalized.split(" ")
    if len(parts) < 2:
        return ValidationResult(error="invalid_full_name")

    cleaned = " ".join(_normalize_name_part(part) for part in parts if part)
    return ValidationResult(value=cleaned)


def validate_student_code(code: str) -> bool:
    """Determina si el codigo pertenece al alcance del proyecto."""

    normalized = str(code or "").strip()
    return (
        normalized.isdigit()
        and len(normalized) == 8
        and normalized.startswith("67")
    )


def validate_student_code_field(raw: str, config: OnboardingConfig) -> ValidationResult:
    """Valida el codigo estudiantil para el onboarding."""

    normalized = str(raw or "").strip()
    if not normalized.isdigit():
        return ValidationResult(error="invalid_student_code")
    if len(normalized) != config.student_code_length:
        return ValidationResult(error="invalid_student_code")
    if not validate_student_code(normalized):
        return ValidationResult(error="unsupported_student_code")
    return ValidationResult(value=normalized)


def validate_age(raw: str, _config: OnboardingConfig) -> ValidationResult:
    """Valida edad entera en rango razonable."""

    normalized = str(raw or "").strip()
    if not re.fullmatch(r"\d{1,2}", normalized):
        return ValidationResult(error="invalid_age")
    age = int(normalized)
    if not 15 <= age <= 60:
        return ValidationResult(error="invalid_age")
    return ValidationResult(value=age)


_MICROSOFT_PERSONAL_DOMAIN_ROOTS = frozenset({"outlook", "hotmail", "live", "msn"})


def validate_institutional_email(
    raw: str,
    config: OnboardingConfig,
) -> ValidationResult:
    """Valida correo permitido para OAuth Microsoft."""

    normalized = str(raw or "").strip().lower()
    if not normalized or " " in normalized:
        return ValidationResult(error="invalid_institutional_email")
    if not _EMAIL_PATTERN.fullmatch(normalized):
        return ValidationResult(error="invalid_institutional_email")
    domain = normalized.rsplit("@", 1)[-1]
    allowed_domains = {
        str(item or "").strip().lower()
        for item in getattr(config, "allowed_email_domains", ())
        if str(item or "").strip()
    }
    if domain in allowed_domains:
        return ValidationResult(value=normalized)

    domain_root = domain.split(".")[0]
    if domain_root not in _MICROSOFT_PERSONAL_DOMAIN_ROOTS:
        return ValidationResult(error="non_microsoft_personal_email")
    return ValidationResult(value=normalized)


def validate_supported_program(raw: str, _config: OnboardingConfig) -> ValidationResult:
    """Interpreta la confirmacion del programa soportado."""

    parsed = parse_yes_no(raw)
    if parsed is None:
        return ValidationResult(error="invalid_supported_program")
    return ValidationResult(value=parsed)


def validate_semester(raw: str, _config: OnboardingConfig) -> ValidationResult:
    """Valida semestre entero entre 1 y 15."""

    normalized = str(raw or "").strip()
    if not re.fullmatch(r"\d{1,2}", normalized):
        return ValidationResult(error="invalid_semester")
    semester = int(normalized)
    if not 1 <= semester <= 15:
        return ValidationResult(error="invalid_semester")
    return ValidationResult(value=semester)


def validate_average_grade(raw: str, _config: OnboardingConfig) -> ValidationResult:
    """Valida promedio academico entero entre 0 y 100."""

    normalized = str(raw or "").strip()
    if not re.fullmatch(r"\d{1,3}", normalized):
        return ValidationResult(error="invalid_average_grade")
    grade = int(normalized)
    if not 0 <= grade <= 100:
        return ValidationResult(error="invalid_average_grade")
    return ValidationResult(value=grade)


def validate_profile_field(
    field: str,
    raw: str,
    config: OnboardingConfig,
) -> ValidationResult:
    """Despacha la validacion segun el campo esperado."""

    validators = {
        "full_name": validate_full_name,
        "student_code": validate_student_code_field,
        "age": validate_age,
        "institutional_email": validate_institutional_email,
        "supported_program": validate_supported_program,
        "semester": validate_semester,
        "average_grade": validate_average_grade,
    }
    validator = validators.get(field)
    if validator is None:
        return ValidationResult(error="unsupported_field")
    return validator(raw, config)


def get_missing_profile_fields(profile: Any) -> list[str]:
    """Retorna campos faltantes del perfil en el orden del onboarding."""

    missing: list[str] = []
    for field in PROFILE_FIELD_ORDER:
        value = profile_value(profile, field)
        if value in (None, ""):
            missing.append(field)
    return missing


def get_first_name(profile: Any) -> str | None:
    """Extrae el primer nombre del perfil."""

    full_name = str(profile_value(profile, "full_name", "") or "").strip()
    if not full_name:
        return None
    return full_name.split(" ", 1)[0]


def collapse_spaces(raw: str) -> str:
    """Recorta y colapsa espacios internos."""

    return " ".join(str(raw or "").strip().split())


def parse_yes_no(raw: str) -> bool | None:
    """Parser determinista para respuestas si/no."""

    normalized = normalize_text(raw)
    if not normalized:
        return None
    if normalized in _YES_TOKENS:
        return True
    if normalized in _NO_TOKENS:
        return False
    return None


def normalize_text(raw: str) -> str:
    """Normaliza texto para comparaciones simples."""

    value = str(raw or "").strip().lower()
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def profile_value(profile: Any, field: str, default: Any = None) -> Any:
    """Lee un valor desde dicts o modelos."""

    if isinstance(profile, dict):
        return profile.get(field, default)
    return getattr(profile, field, default)


def _normalize_name_part(part: str) -> str:
    if not part:
        return part
    lower_part = part.lower()
    if lower_part in _NAME_LOWER_PARTICLES:
        return lower_part
    return lower_part[0].upper() + lower_part[1:]
