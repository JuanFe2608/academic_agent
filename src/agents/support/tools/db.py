"""Factories de persistencia y servicios compartidos."""

from __future__ import annotations

from agents.support.onboarding.service import OnboardingService, build_onboarding_service
from agents.support.personalization.service import (
    PersonalizationService,
    build_personalization_service,
)
from agents.support.scheduling.service import ScheduleService, build_schedule_service

_ONBOARDING_SERVICE: OnboardingService | None = None
_PERSONALIZATION_SERVICE: PersonalizationService | None = None
_SCHEDULE_SERVICE: ScheduleService | None = None


def get_onboarding_service() -> OnboardingService:
    """Retorna una instancia reusable del servicio de onboarding."""

    global _ONBOARDING_SERVICE
    if _ONBOARDING_SERVICE is None:
        _ONBOARDING_SERVICE = build_onboarding_service()
    return _ONBOARDING_SERVICE


def set_onboarding_service(service: OnboardingService | None) -> None:
    """Permite inyectar un servicio durante pruebas."""

    global _ONBOARDING_SERVICE
    _ONBOARDING_SERVICE = service


def get_personalization_service() -> PersonalizationService:
    """Retorna una instancia reusable del servicio de personalizacion."""

    global _PERSONALIZATION_SERVICE
    if _PERSONALIZATION_SERVICE is None:
        _PERSONALIZATION_SERVICE = build_personalization_service()
    return _PERSONALIZATION_SERVICE


def set_personalization_service(service: PersonalizationService | None) -> None:
    """Permite inyectar un servicio de personalizacion durante pruebas."""

    global _PERSONALIZATION_SERVICE
    _PERSONALIZATION_SERVICE = service


def get_schedule_service() -> ScheduleService:
    """Retorna una instancia reusable del servicio de horarios."""

    global _SCHEDULE_SERVICE
    if _SCHEDULE_SERVICE is None:
        _SCHEDULE_SERVICE = build_schedule_service()
    return _SCHEDULE_SERVICE


def set_schedule_service(service: ScheduleService | None) -> None:
    """Permite inyectar un servicio de horarios durante pruebas."""

    global _SCHEDULE_SERVICE
    _SCHEDULE_SERVICE = service
