"""Configuracion del modulo de personalizacion academica."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .questionnaire import (
    QUESTIONNAIRE_VERSION,
    SCORING_VERSION,
)


@dataclass(frozen=True)
class PersonalizationConfig:
    """Parametros configurables del modulo de personalizacion."""

    enabled: bool = False
    questionnaire_version: str = QUESTIONNAIRE_VERSION
    scoring_version: str = SCORING_VERSION
    high_score_threshold: float = 0.67


def load_personalization_config() -> PersonalizationConfig:
    """Carga configuracion desde variables de entorno."""

    return PersonalizationConfig(
        enabled=_env_bool("ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE", False),
        questionnaire_version=QUESTIONNAIRE_VERSION,
        scoring_version=SCORING_VERSION,
        high_score_threshold=_env_float(
            "ACADEMIC_AGENT_PERSONALIZATION_HIGH_SCORE_THRESHOLD",
            0.67,
        ),
    )


def is_personalization_enabled() -> bool:
    """Indica si el modulo debe integrarse al grafo activo."""

    return load_personalization_config().enabled


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if 0 <= parsed <= 1 else default
