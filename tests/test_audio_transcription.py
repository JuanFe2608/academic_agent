"""Pruebas del servicio de transcripción de audio."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from integrations.ai.audio_transcription import (
    _MAX_AUDIO_BYTES,
    AzureOpenAIAudioTranscriptionService,
)


class _FakeTranscriptions:
    def __init__(self, *, result: object | None = None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.result


def _service(transcriptions: _FakeTranscriptions) -> AzureOpenAIAudioTranscriptionService:
    service = AzureOpenAIAudioTranscriptionService.__new__(
        AzureOpenAIAudioTranscriptionService
    )
    service.deployment_name = "gpt-4o-mini-transcribe"
    service.client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=transcriptions)
    )
    return service


def test_audio_transcription_rejects_empty_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "empty.ogg"
    audio_path.write_bytes(b"")
    transcriptions = _FakeTranscriptions(result=SimpleNamespace(text="hola"))

    result = _service(transcriptions).transcribe(audio_path)

    assert result.ok is False
    assert result.error_code == "audio_file_empty"
    assert transcriptions.calls == []


def test_audio_transcription_rejects_file_over_25_mb(tmp_path: Path) -> None:
    audio_path = tmp_path / "large.ogg"
    with audio_path.open("wb") as file:
        file.truncate(_MAX_AUDIO_BYTES + 1)
    transcriptions = _FakeTranscriptions(result=SimpleNamespace(text="hola"))

    result = _service(transcriptions).transcribe(audio_path)

    assert result.ok is False
    assert result.error_code == "audio_file_too_large"
    assert transcriptions.calls == []


def test_audio_transcription_returns_empty_error_when_azure_text_is_blank(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "blank.ogg"
    audio_path.write_bytes(b"audio")
    transcriptions = _FakeTranscriptions(result=SimpleNamespace(text="   "))

    result = _service(transcriptions).transcribe(audio_path, language="es")

    assert result.ok is False
    assert result.error_code == "audio_transcription_empty"
    assert transcriptions.calls[0]["model"] == "gpt-4o-mini-transcribe"
    assert transcriptions.calls[0]["language"] == "es"


def test_audio_transcription_classifies_azure_format_rejection(
    tmp_path: Path,
    caplog,
) -> None:
    audio_path = tmp_path / "voice.ogg"
    audio_path.write_bytes(b"audio")
    transcriptions = _FakeTranscriptions(
        exc=RuntimeError("Invalid file format. Supported formats: mp3, wav, webm.")
    )

    caplog.set_level(logging.WARNING, logger="integrations.ai.audio_transcription")
    result = _service(transcriptions).transcribe(audio_path)

    assert result.ok is False
    assert result.error_code == "audio_format_rejected"
    assert ".ogg" in str(result.detail)
    assert "Azure rejected audio format" in caplog.text


def test_audio_transcription_keeps_generic_azure_error_clear_in_logs(
    tmp_path: Path,
    caplog,
) -> None:
    audio_path = tmp_path / "voice.ogg"
    audio_path.write_bytes(b"audio")
    transcriptions = _FakeTranscriptions(exc=RuntimeError("Azure timeout"))

    caplog.set_level(logging.WARNING, logger="integrations.ai.audio_transcription")
    result = _service(transcriptions).transcribe(audio_path)

    assert result.ok is False
    assert result.error_code == "audio_transcription_failed"
    assert "Azure audio transcription failed" in caplog.text
