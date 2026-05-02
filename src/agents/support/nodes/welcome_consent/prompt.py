"""Mensajes base para bienvenida y consentimiento."""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

WELCOME_MESSAGE = (
    "¡Hola! 👋✨\n"
    "Soy Lara, tu Asistente Académico Inteligente 🤖📚\n"
    "\n"
    "Estoy aquí para ayudarte a gestionar tu tiempo, planificar tus actividades "
    "académicas y recomendarte métodos de estudio personalizados según tu perfil "
    "y tus hábitos de estudio 🧠⏳\n"
    "\n"
    "Sé que la vida universitaria puede estar llena de entregas, parciales, "
    "proyectos y muchas responsabilidades,\n"
    "Pero no estás solo/a 💙\n"
    "\n"
    "Mi objetivo es apoyarte para que:\n"
    "✅ Organices mejor tu tiempo académico\n"
    "✅ Planifiques tus actividades de forma clara y realista\n"
    "✅ Identifiques métodos de estudio que se adapten a ti\n"
    "✅ Tengas una mejor visión de tus tareas, horarios y prioridades\n"
    "✅ Estudies con estrategias más alineadas con tu forma de aprender\n"
    "\n"
    "Juntos vamos a construir una planificación académica que se ajuste a ti 🎯"
)

HABEAS_DATA_PATH = "/legal/habeas-data"
HABEAS_DATA_POLICY_VERSION = "habeas-data-v1"


def habeas_data_policy_url() -> str:
    """Retorna la URL publica del documento de tratamiento de datos."""
    explicit_url = os.getenv("LARA_HABEAS_DATA_URL", "").strip()
    if explicit_url:
        return explicit_url

    public_base_url = os.getenv("ACADEMIC_AGENT_PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        return f"{public_base_url.rstrip('/')}{HABEAS_DATA_PATH}"

    redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "").strip()
    inferred_base_url = _origin_from_url(redirect_uri)
    if inferred_base_url:
        return f"{inferred_base_url}{HABEAS_DATA_PATH}"

    return f"http://localhost:8000{HABEAS_DATA_PATH}"


def consent_prompt() -> str:
    """Construye el mensaje corto de consentimiento para WhatsApp."""
    return (
        "❓ *¿Aceptas el tratamiento de tus datos personales para continuar en Lara AI?*\n"
        "\n"
        "Consulta la política completa aquí:\n"
        f"{habeas_data_policy_url()}\n"
        "\n"
        "Responde únicamente: *Sí* o *No*."
    )


def _origin_from_url(value: str) -> str | None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
