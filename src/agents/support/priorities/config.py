"""Configuración del módulo de prioridades académicas."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PrioritiesConfig:
    """Parámetros configurables del subflujo de prioridades."""

    enabled: bool = False
    post_radar_flow_enabled: bool = False
    prompt_version: str = "v2"


def load_priorities_config() -> PrioritiesConfig:
    """Carga configuración desde variables de entorno."""

    return PrioritiesConfig(
        enabled=_env_bool("ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE", False),
        post_radar_flow_enabled=_env_bool(
            "ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW",
            False,
        ),
        prompt_version=os.getenv("ACADEMIC_AGENT_PRIORITIES_PROMPT_VERSION", "v2").strip()
        or "v2",
    )


def is_priorities_enabled() -> bool:
    """Indica si el módulo debe integrarse al grafo activo."""

    return load_priorities_config().enabled


def is_post_radar_flow_enabled() -> bool:
    """Indica si el Radar debe encadenar automáticamente prioridades semanales."""

    return load_priorities_config().post_radar_flow_enabled


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on"}
