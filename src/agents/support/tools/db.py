"""Factories de persistencia y servicios de onboarding."""

from __future__ import annotations

from agents.support.onboarding.service import OnboardingService, build_onboarding_service

_ONBOARDING_SERVICE: OnboardingService | None = None


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
