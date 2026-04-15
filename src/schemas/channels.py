"""Contratos genericos para canales conversacionales externos."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import BaseSchemaModel

ChannelName = Literal["whatsapp"]
ChannelMediaType = Literal["image", "document", "audio", "video"]
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


__all__ = [
    "ChannelInboundMessage",
    "ChannelMedia",
    "ChannelMediaType",
    "ChannelName",
    "ChannelOutboundMessage",
    "ChannelSendResult",
    "OutboundMessageKind",
]
