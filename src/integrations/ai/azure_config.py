"""Validacion defensiva de configuracion Azure OpenAI."""

from __future__ import annotations

from urllib.parse import urlsplit

_CHAT_DEPLOYMENT_DENYLIST = ("audio", "transcribe", "transcription", "tts", "whisper")
_TRANSCRIBE_DEPLOYMENT_HINTS = ("transcribe", "transcription", "whisper")


def validate_azure_resource_endpoint(value: str, *, env_name: str) -> str:
    """Retorna el endpoint base o lanza ValueError si parece una URL de API."""

    endpoint = str(value or "").strip().strip('"').strip("'").rstrip("/")
    if not endpoint:
        raise ValueError(f"Missing Azure OpenAI environment variable: {env_name}")

    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{env_name} debe ser una URL absoluta de Azure OpenAI")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{env_name} debe ser el endpoint base, sin query string")

    path = (parsed.path or "").strip("/")
    if path:
        raise ValueError(
            f"{env_name} debe ser el endpoint base del recurso, no una URL de deployment"
        )
    return endpoint


def validate_chat_deployment_name(value: str, *, env_name: str) -> str:
    """Evita usar deployments de audio como modelo conversacional."""

    deployment = str(value or "").strip().strip('"').strip("'")
    if not deployment:
        raise ValueError(f"Missing Azure OpenAI environment variable: {env_name}")
    normalized = deployment.lower()
    if any(token in normalized for token in _CHAT_DEPLOYMENT_DENYLIST):
        raise ValueError(f"{env_name} parece ser un deployment de audio, no de chat")
    return deployment


def validate_transcription_deployment_name(value: str, *, env_name: str) -> str:
    """Evita configurar el transcriptor con un deployment de chat por accidente."""

    deployment = str(value or "").strip().strip('"').strip("'")
    if not deployment:
        raise ValueError(f"Missing Azure OpenAI environment variable: {env_name}")
    normalized = deployment.lower()
    if not any(token in normalized for token in _TRANSCRIBE_DEPLOYMENT_HINTS):
        raise ValueError(
            f"{env_name} debe apuntar a un deployment de transcripcion de audio"
        )
    return deployment


__all__ = [
    "validate_azure_resource_endpoint",
    "validate_chat_deployment_name",
    "validate_transcription_deployment_name",
]
