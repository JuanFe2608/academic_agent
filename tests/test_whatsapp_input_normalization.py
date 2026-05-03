"""Pruebas de normalización multimodal antes del agente."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from api.agent_runner import AgentRunner
from integrations.whatsapp import WhatsAppInboundMedia, WhatsAppInboundMessage
from schemas.channels import ChannelInboundMessage, ChannelMedia
from services.channels.input_normalization import NormalizedAgentInput, WhatsAppInputNormalizer


@dataclass
class _FakeWhatsAppService:
    downloaded_path: str = "/tmp/audio.ogg"
    download_calls: int = 0

    def download_inbound(self, inbound):
        self.download_calls += 1
        return ChannelInboundMessage(
            channel="whatsapp",
            sender_id=inbound.from_number,
            message_id=inbound.message_id,
            text=inbound.text,
            media=[
                ChannelMedia(
                    media_type=inbound.media.media_type,
                    reference=self.downloaded_path,
                    mime_type=inbound.media.mime_type,
                    provider_media_id=inbound.media.id,
                )
            ],
        )


class _FakeTranscriber:
    def __init__(self, *, ok: bool = True, text: str = "Tengo parcial de cálculo mañana") -> None:
        self.ok = ok
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def transcribe(self, path: str, *, language: str = "es"):
        self.calls.append((path, language))
        return SimpleNamespace(ok=self.ok, text=self.text)


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    def invoke(self, input_data: dict, *, config: dict):
        self.calls.append((input_data, config))
        return {
            "messages": [
                *input_data["messages"],
                AIMessage(content="Listo, lo organicé."),
            ]
        }


class _FakeDirectNormalizer:
    def normalize(self, _message):
        return NormalizedAgentInput(direct_response="No puedo recibir ese contenido.")


class _FakeAgentNormalizer:
    def normalize(self, _message):
        return NormalizedAgentInput(human_message=HumanMessage(content="si"))


@dataclass
class _FakeSendService:
    sent: list[tuple[str, list]] | None = None

    def __post_init__(self) -> None:
        if self.sent is None:
            self.sent = []

    def send_agent_messages(self, *, recipient_id: str, messages: list):
        assert self.sent is not None
        self.sent.append((recipient_id, messages))
        return []


def _message(
    *,
    text: str | None = None,
    media_type: str | None = None,
    mime_type: str | None = None,
) -> WhatsAppInboundMessage:
    media = (
        WhatsAppInboundMedia(
            id="media-123",
            media_type=media_type,
            mime_type=mime_type,
        )
        if media_type
        else None
    )
    return WhatsAppInboundMessage(
        from_number="573001112233",
        message_id="wamid.1",
        text=text,
        media=media,
    )


def test_normalizer_rejects_links_without_invoking_agent() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    result = normalizer.normalize(_message(text="Mira https://example.com/tarea"))

    assert result is not None
    assert result.direct_response is not None
    assert "no puedo abrir ni revisar links" in result.direct_response
    assert result.human_message is None


def test_normalizer_does_not_treat_email_as_link() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    result = normalizer.normalize(_message(text="mi correo es estudiante@universidad.edu.co"))

    assert result is not None
    assert result.direct_response is None
    assert result.human_message is not None
    assert "estudiante@universidad.edu.co" in result.human_message.content


def test_normalizer_rejects_video_and_sticker() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    video = normalizer.normalize(_message(media_type="video", mime_type="video/mp4"))
    sticker = normalizer.normalize(_message(media_type="sticker", mime_type="image/webp"))

    assert video is not None
    assert video.direct_response is not None
    assert "no puedo analizar videos" in video.direct_response
    assert sticker is not None
    assert sticker.direct_response is not None
    assert "Recibí tu sticker" in sticker.direct_response


def test_normalizer_rejects_documents_without_invoking_agent() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    result = normalizer.normalize(
        _message(media_type="document", mime_type="application/pdf")
    )

    assert result is not None
    assert result.human_message is None
    assert result.direct_response is not None
    assert "no puedo leer documentos adjuntos" in result.direct_response


def test_normalizer_maps_confirmation_emojis_to_yes_no_text() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    yes = normalizer.normalize(_message(text="👍🏽"))
    no = normalizer.normalize(_message(text="👎"))

    assert yes is not None
    assert yes.human_message is not None
    assert yes.human_message.content == "si"
    assert no is not None
    assert no.human_message is not None
    assert no.human_message.content == "no"


def test_normalizer_passes_non_confirmation_emoji_to_agent() -> None:
    normalizer = WhatsAppInputNormalizer(whatsapp_service=_FakeWhatsAppService())  # type: ignore[arg-type]

    result = normalizer.normalize(_message(text="😊🎓"))

    assert result is not None
    assert result.direct_response is None
    assert result.human_message is not None
    assert result.human_message.content == "😊🎓"


def test_normalizer_transcribes_audio_to_text_for_agent() -> None:
    whatsapp_service = _FakeWhatsAppService(downloaded_path="/tmp/audio.ogg")
    transcriber = _FakeTranscriber(text="Agrega parcial de física el viernes")
    normalizer = WhatsAppInputNormalizer(
        whatsapp_service=whatsapp_service,  # type: ignore[arg-type]
        audio_transcriber=transcriber,
    )

    result = normalizer.normalize(
        _message(
            text="Esto es para mi agenda",
            media_type="audio",
            mime_type="audio/ogg",
        )
    )

    assert result is not None
    assert result.direct_response is None
    assert result.human_message is not None
    assert "Transcripcion de audio" in result.human_message.content
    assert "Esto es para mi agenda" in result.human_message.content
    assert "Agrega parcial de física el viernes" in result.human_message.content
    assert transcriber.calls == [("/tmp/audio.ogg", "es")]
    assert whatsapp_service.download_calls == 1


def test_normalizer_falls_back_when_audio_transcription_fails() -> None:
    normalizer = WhatsAppInputNormalizer(
        whatsapp_service=_FakeWhatsAppService(),  # type: ignore[arg-type]
        audio_transcriber=_FakeTranscriber(ok=False),
    )

    result = normalizer.normalize(_message(media_type="audio", mime_type="audio/ogg"))

    assert result is not None
    assert result.direct_response is not None
    assert "no pude transcribirlo" in result.direct_response


def test_agent_runner_sends_direct_response_without_invoking_graph() -> None:
    runner = AgentRunner.__new__(AgentRunner)
    runner._whatsapp_service = _FakeSendService()
    runner._input_normalizer = _FakeDirectNormalizer()
    runner._agent = _FakeAgent()

    runner._run_agent_sync(_message(text="https://example.com"))

    assert runner._agent.calls == []
    assert runner._whatsapp_service.sent == [
        ("573001112233", ["No puedo recibir ese contenido."])
    ]


def test_agent_runner_invokes_graph_with_normalized_text() -> None:
    runner = AgentRunner.__new__(AgentRunner)
    runner._whatsapp_service = _FakeSendService()
    runner._input_normalizer = _FakeAgentNormalizer()
    runner._agent = _FakeAgent()

    runner._run_agent_sync(_message(text="✅"))

    assert len(runner._agent.calls) == 1
    input_data, config = runner._agent.calls[0]
    assert config == {"configurable": {"thread_id": "573001112233"}}
    assert input_data["messages"][0].content == "si"
    assert runner._whatsapp_service.sent == [
        ("573001112233", [AIMessage(content="Listo, lo organicé.")])
    ]
