"""Normalizacion defensiva de entradas WhatsApp antes del grafo."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from langchain_core.messages import HumanMessage

from integrations.whatsapp import WhatsAppInboundMessage
from schemas.channels import ChannelInboundMessage

if TYPE_CHECKING:
    from services.channels.whatsapp_service import WhatsAppChannelService


_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_LINK_RE = re.compile(
    r"(?i)(?:https?://|www\.)\S+|(?<!@)\b[A-Z0-9][A-Z0-9.-]*\."
    r"(?:com|co|edu|org|net|io|gov|app|ai|dev|info|me)\b(?:/\S*)?"
)
_POSITIVE_EMOJI = {"👍", "✅", "✔", "☑", "👌"}
_NEGATIVE_EMOJI = {"👎", "❌", "✖"}
_IGNORED_EMOJI_CHARS = {"\ufe0f", "\u200d"}
_EMOJI_MODIFIER_START = 0x1F3FB
_EMOJI_MODIFIER_END = 0x1F3FF


class AudioTranscriber(Protocol):
    def transcribe(self, path: str, *, language: str = "es") -> object: ...


@dataclass(frozen=True)
class NormalizedAgentInput:
    """Entrada lista para AgentRunner."""

    human_message: HumanMessage | None = None
    image_refs: list[str] = field(default_factory=list)
    direct_response: str | None = None

    @property
    def should_invoke_agent(self) -> bool:
        return self.human_message is not None


class WhatsAppInputNormalizer:
    """Convierte media/links/emojis en entradas seguras para el agente."""

    def __init__(
        self,
        *,
        whatsapp_service: "WhatsAppChannelService",
        audio_transcriber: AudioTranscriber | None = None,
    ) -> None:
        self.whatsapp_service = whatsapp_service
        self.audio_transcriber = audio_transcriber

    def normalize(self, message: WhatsAppInboundMessage) -> NormalizedAgentInput | None:
        text = str(message.text or "").strip()

        if _contains_link(text):
            return NormalizedAgentInput(direct_response=_links_not_supported_message())

        emoji_confirmation = _emoji_confirmation_text(text)
        if emoji_confirmation:
            return NormalizedAgentInput(human_message=HumanMessage(content=emoji_confirmation))
        if _is_emoji_only(text):
            return NormalizedAgentInput(direct_response=_emoji_context_message())

        if message.media is None:
            if not text:
                return None
            return NormalizedAgentInput(human_message=HumanMessage(content=text))

        media_type = str(message.media.media_type or "").strip().lower()
        if media_type == "audio":
            return self._normalize_audio(message)
        if media_type == "video":
            return NormalizedAgentInput(direct_response=_videos_not_supported_message())
        if media_type == "sticker":
            return NormalizedAgentInput(direct_response=_sticker_context_message())

        return None

    def _normalize_audio(self, message: WhatsAppInboundMessage) -> NormalizedAgentInput:
        if self.audio_transcriber is None:
            return NormalizedAgentInput(direct_response=_audio_not_available_message())
        try:
            downloaded = self.whatsapp_service.download_inbound(message)
        except Exception:
            return NormalizedAgentInput(direct_response=_audio_download_failed_message())

        audio_path = _first_media_reference(downloaded)
        if not audio_path:
            return NormalizedAgentInput(direct_response=_audio_download_failed_message())

        result = self.audio_transcriber.transcribe(audio_path, language="es")
        if not getattr(result, "ok", False):
            return NormalizedAgentInput(direct_response=_audio_transcription_failed_message())

        transcript = str(getattr(result, "text", "") or "").strip()
        if not transcript:
            return NormalizedAgentInput(direct_response=_audio_transcription_failed_message())

        text = str(message.text or "").strip()
        content = (
            "Transcripcion de audio enviada por el estudiante:\n"
            f"{transcript}"
        )
        if text:
            content = (
                f"Texto que acompaña el audio:\n{text}\n\n"
                f"{content}"
            )
        return NormalizedAgentInput(human_message=HumanMessage(content=content))


def _first_media_reference(inbound: ChannelInboundMessage) -> str | None:
    for media in list(inbound.media or []):
        reference = str(media.reference or "").strip()
        if reference:
            return reference
    return None


def _contains_link(text: str) -> bool:
    if not text:
        return False
    without_emails = _EMAIL_RE.sub("", text)
    return bool(_LINK_RE.search(without_emails))


def _emoji_confirmation_text(text: str) -> str | None:
    chars = _meaningful_chars(text)
    if not chars:
        return None
    if all(char in _POSITIVE_EMOJI for char in chars):
        return "si"
    if all(char in _NEGATIVE_EMOJI for char in chars):
        return "no"
    return None


def _is_emoji_only(text: str) -> bool:
    chars = _meaningful_chars(text)
    if not chars:
        return False
    return all(_looks_like_emoji(char) for char in chars)


def _meaningful_chars(text: str) -> list[str]:
    chars: list[str] = []
    for char in str(text or "").strip():
        if char.isspace() or char in _IGNORED_EMOJI_CHARS:
            continue
        if _is_emoji_modifier(char):
            continue
        if unicodedata.category(char).startswith("M"):
            continue
        chars.append(char)
    return chars


def _is_emoji_modifier(char: str) -> bool:
    codepoint = ord(char)
    return _EMOJI_MODIFIER_START <= codepoint <= _EMOJI_MODIFIER_END


def _looks_like_emoji(char: str) -> bool:
    category = unicodedata.category(char)
    return category in {"So", "Sk"} or char in _POSITIVE_EMOJI or char in _NEGATIVE_EMOJI


def _links_not_supported_message() -> str:
    return (
        "🔗 Por ahora no puedo abrir ni revisar links externos.\n\n"
        "Para ayudarte bien, copia aquí el contenido importante: fecha, actividad, "
        "instrucciones o el fragmento académico que quieres organizar. 📚"
    )


def _videos_not_supported_message() -> str:
    return (
        "🎥 Recibí un video, pero por ahora no puedo analizar videos.\n\n"
        "Si el video contiene una actividad, una fecha o instrucciones académicas, "
        "envíame un audio corto, una imagen clara o escríbeme los datos principales. 📚"
    )


def _sticker_context_message() -> str:
    return (
        "😊 Recibí tu sticker.\n\n"
        "Para ayudarte con tu horario, pendientes o plan de estudio, escríbeme qué necesitas."
    )


def _emoji_context_message() -> str:
    return (
        "😊 Recibí tu emoji.\n\n"
        "Si quieres confirmar algo, puedes responder con “sí” o “no”. "
        "Si necesitas organizar una actividad, escríbeme los detalles. 📚"
    )


def _audio_not_available_message() -> str:
    return (
        "🎙️ Recibí tu audio, pero la transcripción aún no está disponible.\n\n"
        "Por ahora escríbeme el mensaje o envíame una imagen/documento académico claro. 📚"
    )


def _audio_download_failed_message() -> str:
    return (
        "🎙️ Recibí tu audio, pero no pude descargarlo correctamente.\n\n"
        "Intenta enviarlo de nuevo o escríbeme el contenido para ayudarte."
    )


def _audio_transcription_failed_message() -> str:
    return (
        "🎙️ Recibí tu audio, pero no pude transcribirlo con suficiente claridad.\n\n"
        "¿Me lo puedes escribir o enviarlo de nuevo más claro? 📚"
    )


__all__ = [
    "NormalizedAgentInput",
    "WhatsAppInputNormalizer",
]
