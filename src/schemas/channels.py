"""Contratos genericos para canales conversacionales externos."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from .common import BaseSchemaModel
from .conversation import InputClassification

ChannelName = Literal["whatsapp"]
ChannelMediaType = Literal["image", "document", "audio", "video", "sticker"]
OutboundMessageKind = Literal["text", "image", "document"]


class ChannelMedia(BaseSchemaModel):
    """Referencia liviana a un archivo o media remoto."""

    media_type: ChannelMediaType
    reference: str
    mime_type: str | None = None
    filename: str | None = None
    caption: str | None = None
    provider_media_id: str | None = None


class ChannelInboundMessage(BaseSchemaModel):
    """Mensaje entrante normalizado desde un canal externo."""

    channel: ChannelName
    sender_id: str
    message_id: str | None = None
    text: str | None = None
    media: list[ChannelMedia] = Field(default_factory=list)
    raw_payload: dict[str, object] = Field(default_factory=dict)


class ChannelOutboundMessage(BaseSchemaModel):
    """Mensaje saliente normalizado antes de enviarlo por un canal."""

    channel: ChannelName
    recipient_id: str
    kind: OutboundMessageKind
    text: str | None = None
    media: ChannelMedia | None = None


class ChannelSendResult(BaseSchemaModel):
    """Resultado minimo de envio de un mensaje por canal."""

    channel: ChannelName
    recipient_id: str
    provider_message_id: str | None = None
    provider_media_id: str | None = None
    status: Literal["sent", "failed"] = "sent"
    detail: str | None = None


class BufferedMessage(BaseSchemaModel):
    """Mensaje entrante pendiente de agregacion por conversacion."""

    channel: ChannelName = "whatsapp"
    conversation_id: str
    sender_id: str
    message_id: str | None = None
    text: str | None = None
    media: list[ChannelMedia] = Field(default_factory=list)
    raw_payload: dict[str, object] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_channel_inbound(
        cls,
        inbound: ChannelInboundMessage,
        *,
        conversation_id: str | None = None,
        received_at: datetime | None = None,
    ) -> "BufferedMessage":
        """Construye un mensaje de buffer desde el contrato normalizado del canal."""

        return cls(
            channel=inbound.channel,
            conversation_id=conversation_id or inbound.sender_id,
            sender_id=inbound.sender_id,
            message_id=inbound.message_id,
            text=inbound.text,
            media=list(inbound.media),
            raw_payload=dict(inbound.raw_payload),
            received_at=received_at or datetime.now(UTC),
        )


class AggregatedInput(BaseSchemaModel):
    """Payload agregado que queda listo para entrar al grafo."""

    channel: ChannelName = "whatsapp"
    conversation_id: str
    sender_id: str
    text: str = ""
    media: list[ChannelMedia] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    messages: list[BufferedMessage] = Field(default_factory=list)
    message_count: int = 0
    latest_message_id: str | None = None
    flush_reason: str
    classification: InputClassification = Field(default_factory=InputClassification)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "AggregatedInput",
    "BufferedMessage",
    "ChannelInboundMessage",
    "ChannelMedia",
    "ChannelMediaType",
    "ChannelName",
    "ChannelOutboundMessage",
    "ChannelSendResult",
    "OutboundMessageKind",
]
