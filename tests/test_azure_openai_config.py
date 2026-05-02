"""Regresiones para evitar cruces de configuracion Azure OpenAI."""

from __future__ import annotations

import pytest

from integrations.ai._llm_impl import get_azure_llm, maybe_get_llm
from integrations.ai.audio_transcription import AzureOpenAIAudioTranscriptionService
from integrations.ai.azure_config import (
    validate_azure_resource_endpoint,
    validate_chat_deployment_name,
    validate_transcription_deployment_name,
)


def test_validate_azure_resource_endpoint_rejects_full_deployment_url() -> None:
    with pytest.raises(ValueError, match="endpoint base"):
        validate_azure_resource_endpoint(
            "https://example.cognitiveservices.azure.com/openai/deployments/model/chat/completions?api-version=2025-01-01-preview",
            env_name="AZURE_OPENAI_ENDPOINT",
        )


def test_validate_chat_deployment_rejects_audio_deployment() -> None:
    with pytest.raises(ValueError, match="deployment de audio"):
        validate_chat_deployment_name(
            "gpt-4o-mini-transcribe",
            env_name="AZURE_OPENAI_DEPLOYMENT_NAME",
        )


def test_validate_transcription_deployment_rejects_chat_deployment() -> None:
    with pytest.raises(ValueError, match="transcripcion"):
        validate_transcription_deployment_name(
            "gpt-4o-mini",
            env_name="AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE",
        )


def test_get_azure_llm_fails_before_client_creation_for_malformed_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://example.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini-transcribe/audio/transcriptions",
    )
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION", "2024-12-01-preview")

    with pytest.raises(ValueError, match="endpoint base"):
        get_azure_llm()


def test_maybe_get_llm_returns_none_for_crossed_audio_chat_config(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://example.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini-transcribe")
    monkeypatch.setenv("OPENAI_API_VERSION", "2024-12-01-preview")

    assert maybe_get_llm() is None


def test_audio_transcription_from_env_rejects_chat_deployment(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY_TRANSCRIBE", "secret")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT_TRANSCRIBE",
        "https://example.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_VERSION_TRANSCRIBE", "2025-03-01-preview")

    with pytest.raises(ValueError, match="transcripcion"):
        AzureOpenAIAudioTranscriptionService.from_env()
