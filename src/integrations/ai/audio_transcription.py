"""Transcripcion de audio con Azure OpenAI."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from openai import AzureOpenAI

from integrations.ai.azure_config import (
    validate_azure_resource_endpoint,
    validate_transcription_deployment_name,
)

logger = logging.getLogger(__name__)


_MAX_AUDIO_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class AudioTranscriptionResult:
    """Resultado normalizado de una transcripcion de audio."""

    ok: bool
    text: str | None = None
    error_code: str | None = None
    detail: str | None = None


class AzureOpenAIAudioTranscriptionService:
    """Cliente fino para transcribir notas de voz antes de invocar el agente."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        api_version: str,
    ) -> None:
        self.deployment_name = deployment_name
        self.client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    @classmethod
    def from_env(cls) -> "AzureOpenAIAudioTranscriptionService":
        api_key = os.getenv("AZURE_OPENAI_API_KEY_TRANSCRIBE", "").strip()
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT_TRANSCRIBE", "").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE", "").strip()
        api_version = os.getenv("OPENAI_API_VERSION_TRANSCRIBE", "").strip()
        if not (api_key and endpoint and deployment and api_version):
            raise ValueError("Missing Azure OpenAI transcription environment variables")
        return cls(
            api_key=api_key,
            endpoint=validate_azure_resource_endpoint(
                endpoint,
                env_name="AZURE_OPENAI_ENDPOINT_TRANSCRIBE",
            ),
            deployment_name=validate_transcription_deployment_name(
                deployment,
                env_name="AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE",
            ),
            api_version=api_version,
        )

    def transcribe(self, path: str | Path, *, language: str = "es") -> AudioTranscriptionResult:
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_file_not_found",
                detail=f"No existe el archivo de audio: {file_path}",
            )
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_file_stat_error",
                detail=str(exc),
            )
        if size <= 0:
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_file_empty",
                detail="El archivo de audio esta vacio.",
            )
        if size > _MAX_AUDIO_BYTES:
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_file_too_large",
                detail="El audio supera el limite de 25 MB.",
            )

        try:
            with file_path.open("rb") as audio_file:
                result = self.client.audio.transcriptions.create(
                    model=self.deployment_name,
                    file=audio_file,
                    language=language,
                )
        except Exception as exc:
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_transcription_failed",
                detail=str(exc),
            )

        text = _transcription_text(result)
        if not text:
            return AudioTranscriptionResult(
                ok=False,
                error_code="audio_transcription_empty",
                detail="La transcripcion no retorno texto util.",
            )
        return AudioTranscriptionResult(ok=True, text=text)


def maybe_build_audio_transcription_service() -> AzureOpenAIAudioTranscriptionService | None:
    """Retorna el transcriptor si la configuracion existe; si no, None."""

    try:
        return AzureOpenAIAudioTranscriptionService.from_env()
    except ValueError as exc:
        logger.warning(
            "Audio transcription unavailable — check AZURE_OPENAI_ENDPOINT_TRANSCRIBE (no path), "
            "AZURE_OPENAI_API_KEY_TRANSCRIBE, AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE "
            "(must contain 'transcribe'/'transcription'/'whisper'), "
            "OPENAI_API_VERSION_TRANSCRIBE. Error: %s",
            exc,
        )
        return None


def _transcription_text(result: object) -> str:
    if isinstance(result, str):
        return result.strip()
    text = getattr(result, "text", None)
    if text:
        return str(text).strip()
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return ""


__all__ = [
    "AudioTranscriptionResult",
    "AzureOpenAIAudioTranscriptionService",
    "maybe_build_audio_transcription_service",
]
