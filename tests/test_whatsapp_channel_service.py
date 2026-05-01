"""Pruebas del servicio de canal WhatsApp."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import AIMessage

from integrations.whatsapp import (
    WhatsAppInboundMedia,
    WhatsAppInboundMessage,
    WhatsAppMediaDownload,
    WhatsAppMessageSend,
    WhatsAppUploadedMedia,
)
from schemas.channels import ChannelInboundMessage, ChannelMedia
from services.channels import (
    MessageBuffer,
    WhatsAppChannelService,
    agent_message_to_channel_messages,
    aggregated_input_to_human_message,
    whatsapp_inbound_to_human_message,
)


@dataclass
class _FakeWhatsAppClient:
    uploads: list[tuple[str, str | None]]
    texts: list[tuple[str, str]]
    images: list[dict[str, str | None]]
    downloads: dict[str, Path]

    def upload_media(self, path, *, mime_type=None):
        self.uploads.append((str(path), mime_type))
        return WhatsAppUploadedMedia(id=f"media:{Path(path).name}")

    def send_text(self, to, text):
        self.texts.append((to, text))
        return WhatsAppMessageSend(message_id="wamid.text", raw_payload={})

    def send_image(self, to, *, media_id=None, link=None, caption=None):
        self.images.append(
            {
                "to": to,
                "media_id": media_id,
                "link": link,
                "caption": caption,
            }
        )
        return WhatsAppMessageSend(message_id="wamid.image", raw_payload={})

    def send_document(self, to, *, media_id=None, link=None, caption=None, filename=None):
        raise AssertionError("not used")

    def download_media(self, media_id, *, out_dir=None, filename=None):
        path = self.downloads[media_id]
        return WhatsAppMediaDownload(media_id=media_id, path=path, mime_type="image/png")


def _fake_client(downloads: dict[str, Path] | None = None) -> _FakeWhatsAppClient:
    return _FakeWhatsAppClient(
        uploads=[],
        texts=[],
        images=[],
        downloads=downloads or {},
    )


def test_agent_message_to_channel_messages_maps_text_and_local_image(tmp_path: Path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"image")
    message = AIMessage(
        content=[
            {"type": "text", "text": "Este es tu horario"},
            {"type": "image_url", "image_url": {"url": str(image_path)}},
        ]
    )

    outbound = agent_message_to_channel_messages(message, recipient_id="573001112233")

    assert len(outbound) == 1
    assert outbound[0].kind == "image"
    assert outbound[0].text == "Este es tu horario"
    assert outbound[0].media is not None
    assert outbound[0].media.reference == str(image_path)


def test_whatsapp_channel_service_uploads_local_image_before_sending(tmp_path: Path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"image")
    client = _fake_client()
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    results = service.send_agent_messages(
        recipient_id="573001112233",
        messages=[
            AIMessage(
                content=[
                    {"type": "text", "text": "Este es tu horario"},
                    {"type": "image_url", "image_url": {"url": str(image_path)}},
                ]
            )
        ],
    )

    assert len(results) == 1
    assert results[0].provider_message_id == "wamid.image"
    assert client.uploads == [(str(image_path), "image/png")]
    assert client.images == [
        {
            "to": "573001112233",
            "media_id": "media:schedule.png",
            "link": None,
            "caption": "Este es tu horario",
        }
    ]


def test_whatsapp_channel_service_materializes_inline_preview_before_upload() -> None:
    client = _fake_client()
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    results = service.send_agent_messages(
        recipient_id="573001112233",
        messages=[
            AIMessage(
                content=[
                    {"type": "text", "text": "Este es tu horario"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aW1hZ2U="},
                    },
                ]
            )
        ],
    )

    assert len(results) == 1
    assert results[0].provider_message_id == "wamid.image"
    assert len(client.uploads) == 1
    uploaded_path, mime_type = client.uploads[0]
    assert not uploaded_path.startswith("data:image")
    assert Path(uploaded_path).exists()
    assert mime_type == "image/png"
    assert client.images[0]["caption"] == "Este es tu horario"


def test_whatsapp_channel_service_uses_public_image_link_without_upload() -> None:
    client = _fake_client()
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    service.send_agent_messages(
        recipient_id="573001112233",
        messages=[
            AIMessage(
                content=[
                    {"type": "text", "text": "Imagen"},
                    {"type": "image_url", "image_url": {"url": "https://cdn.test/a.png"}},
                ]
            )
        ],
    )

    assert client.uploads == []
    assert client.images[0]["link"] == "https://cdn.test/a.png"


def test_whatsapp_channel_service_downloads_inbound_media_to_channel_message(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "incoming.png"
    image_path.write_bytes(b"image")
    client = _fake_client(downloads={"media-123": image_path})
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    inbound = service.download_inbound(
        WhatsAppInboundMessage(
            from_number="573001112233",
            message_id="wamid.image",
            text="mi horario",
            media=WhatsAppInboundMedia(
                id="media-123",
                media_type="image",
                mime_type="image/png",
                caption="mi horario",
            ),
        )
    )

    assert inbound.sender_id == "573001112233"
    assert inbound.media[0].reference == str(image_path)
    assert inbound.media[0].provider_media_id == "media-123"


def test_whatsapp_inbound_to_human_message_preserves_text_and_image(tmp_path: Path) -> None:
    image_path = tmp_path / "incoming.png"
    image_path.write_bytes(b"image")
    inbound = ChannelInboundMessage(
        channel="whatsapp",
        sender_id="573001112233",
        text="mi horario",
        media=[
            ChannelMedia(
                media_type="image",
                reference=str(image_path),
                mime_type="image/png",
            )
        ],
    )

    human = whatsapp_inbound_to_human_message(inbound)

    assert isinstance(human.content, list)
    assert human.content[0] == {"type": "text", "text": "mi horario"}
    assert human.content[1]["type"] == "input_image"
    assert human.content[1]["image_url"]["url"] == str(image_path)


def test_whatsapp_channel_service_buffers_inbound_messages_until_manual_flush() -> None:
    client = _fake_client()
    service = WhatsAppChannelService(
        client,  # type: ignore[arg-type]
        message_buffer=MessageBuffer(flush_timeout_seconds=30),
    )

    first = service.buffer_inbound(
        ChannelInboundMessage(
            channel="whatsapp",
            sender_id="573001112233",
            message_id="wamid.1",
            text="Andres",
        )
    )
    second = service.buffer_inbound(
        ChannelInboundMessage(
            channel="whatsapp",
            sender_id="573001112233",
            message_id="wamid.2",
            text="Gomez",
        )
    )

    assert first == []
    assert second == []

    aggregated = service.flush_inbound_buffer("573001112233")

    assert aggregated is not None
    assert aggregated.text == "Andres\nGomez"
    assert aggregated.message_count == 2


def test_whatsapp_channel_service_immediately_flushes_inbound_confirmation() -> None:
    client = _fake_client()
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    outputs = service.buffer_inbound(
        ChannelInboundMessage(
            channel="whatsapp",
            sender_id="573001112233",
            message_id="wamid.confirm",
            text="si",
        )
    )

    assert len(outputs) == 1
    assert outputs[0].text == "si"
    assert outputs[0].flush_reason == "confirmation"


def test_aggregated_input_to_human_message_preserves_text_and_image(tmp_path: Path) -> None:
    image_path = tmp_path / "incoming.png"
    image_path.write_bytes(b"image")
    client = _fake_client()
    service = WhatsAppChannelService(client)  # type: ignore[arg-type]

    outputs = service.buffer_inbound(
        ChannelInboundMessage(
            channel="whatsapp",
            sender_id="573001112233",
            message_id="wamid.image",
            text="mi horario",
            media=[
                ChannelMedia(
                    media_type="image",
                    reference=str(image_path),
                    mime_type="image/png",
                )
            ],
        )
    )

    human = aggregated_input_to_human_message(outputs[0])

    assert isinstance(human.content, list)
    assert human.content[0] == {"type": "text", "text": "mi horario"}
    assert human.content[1]["type"] == "input_image"
