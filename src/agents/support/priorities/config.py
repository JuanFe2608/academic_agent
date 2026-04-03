"""Configuración del módulo de prioridades académicas."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PrioritiesConfig:
    """Parámetros configurables del subflujo de prioridades."""

    enabled: bool = False
    prompt_version: str = "v1"


def load_priorities_config() -> PrioritiesConfig:
    """Carga configuración desde variables de entorno."""

    return PrioritiesConfig(
        enabled=_env_bool("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", False),
        prompt_version=os.getenv("ACADEMIC_AGENT_PRIORITIES_PROMPT_VERSION", "v1").strip()
        or "v1",
    )


def is_priorities_enabled() -> bool:
    """Indica si el módulo debe integrarse al grafo activo."""

    return load_priorities_config().enabled


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on"}
