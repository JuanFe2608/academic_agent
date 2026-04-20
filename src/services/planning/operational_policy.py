"""Politica operacional para materializacion y recordatorios del plan."""

from __future__ import annotations

import os
from dataclasses import dataclass

SUPPORTED_REMINDER_CHANNELS = {"in_app", "email", "whatsapp"}
DEFAULT_REMINDER_CHANNELS = ("in_app",)


@dataclass(frozen=True)
class StudyPlanOperationalPolicy:
    """Decision explicita de activacion operacional para fase 12."""

    materialization_enabled: bool = False
    reminders_enabled: bool = False
    reminder_channels: tuple[str, ...] = DEFAULT_REMINDER_CHANNELS


def load_study_plan_operational_policy() -> StudyPlanOperationalPolicy:
    """Carga la politica desde entorno con defaults seguros para el MVP."""

    materialization_enabled = _env_bool(
        "ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION",
        False,
    )
    reminders_enabled = _env_bool(
        "ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS",
        materialization_enabled,
    )
    return StudyPlanOperationalPolicy(
        materialization_enabled=materialization_enabled,
        reminders_enabled=bool(materialization_enabled and reminders_enabled),
        reminder_channels=_reminder_channels_from_env(),
    )


def _reminder_channels_from_env() -> tuple[str, ...]:
    raw_value = os.getenv("ACADEMIC_AGENT_REMINDER_CHANNELS", "").strip()
    if not raw_value:
        return DEFAULT_REMINDER_CHANNELS
    channels = tuple(
        channel
        for channel in dict.fromkeys(part.strip() for part in raw_value.split(","))
        if channel in SUPPORTED_REMINDER_CHANNELS
    )
    return channels or DEFAULT_REMINDER_CHANNELS


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "si", "on"}


__all__ = [
    "DEFAULT_REMINDER_CHANNELS",
    "SUPPORTED_REMINDER_CHANNELS",
    "StudyPlanOperationalPolicy",
    "load_study_plan_operational_policy",
]
