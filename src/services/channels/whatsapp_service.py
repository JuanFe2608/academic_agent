"""Servicio de canal que conecta mensajes del agente con WhatsApp."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from integrations.whatsapp import (
    WhatsAppCloudClient,
    WhatsAppInboundMessage,
    WhatsAppMessageSend,
)
from schemas.channels import (
    ChannelInboundMessage,
    ChannelMedia,
    ChannelOutboundMessage,
    ChannelSendResult,
)
from utils.media_artifacts import materialize_image_reference

_WHATSAPP_IMAGE_CAPTION_LIMIT = 1024


class WhatsAppChannelService:
    """Orquesta envio y recepcion de mensajes WhatsApp sin acoplar el agente."""

    def __init__(self, client: WhatsAppCloudClient) -> None:
        self.client = client

    def send_agent_messages(
        self,
        *,
        recipient_id: str,
        messages: list[BaseMessage] | list[dict[str, Any]] | list[str],
    ) -> list[ChannelSendResult]:
        results: list[ChannelSendResult] = []
        for message in messages:
            for outbound in agent_message_to_channel_messages(
                message,
                recipient_id=recipient_id,
            ):
                results.append(self.send_outbound(outbound))
        return results

    def send_outbound(self, outbound: ChannelOutboundMessage) -> ChannelSendResult:
        if outbound.kind == "text":
            response = self.client.send_text(
                outbound.recipient_id,
                str(outbound.text or ""),
            )
            return _send_result(outbound, response)

        if outbound.kind == "image" and outbound.media is not None:
            response = self._send_image(outbound)
            return _send_result(outbound, response)

        if outbound.kind == "document" and outbound.media is not None:
            response = self._send_document(outbound)
            return _send_result(outbound, response)

        return ChannelSendResult(
            channel="whatsapp",
            recipient_id=outbound.recipient_id,
            status="failed",
            detail=f"Tipo de mensaje no soportado: {outbound.kind}",
        )

    def download_inbound(
        self,
        inbound: WhatsAppInboundMessage,
    ) -> ChannelInboundMessage:
        media: list[ChannelMedia] = []
        if inbound.media is not None:
            downloaded = self.client.download_media(
                inbound.media.id,
                filename=_download_filename(inbound),
            )
            media.append(
                ChannelMedia(
                    media_type=_channel_media_type(inbound.media.media_type),
                    reference=str(downloaded.path),
                    mime_type=downloaded.mime_type or inbound.media.mime_type,
                    filename=inbound.media.filename,
                    caption=inbound.media.caption,
                    provider_media_id=inbound.media.id,
                )
            )
        return ChannelInboundMessage(
            channel="whatsapp",
            sender_id=inbound.from_number,
            message_id=inbound.message_id,
            text=inbound.text,
            media=media,
            raw_payload=inbound.raw_message or {},
        )

    def _send_image(self, outbound: ChannelOutboundMessage) -> WhatsAppMessageSend:
        media = outbound.media
        assert media is not None
        reference = str(media.reference or "").strip()
        caption = media.caption or outbound.text
        if _is_http_url(reference):
            return self.client.send_image(
                outbound.recipient_id,
                link=reference,
                caption=caption,
            )
        upload = self.client.upload_media(reference, mime_type=media.mime_type)
        return self.client.send_image(
            outbound.recipient_id,
            media_id=upload.id,
            caption=caption,
        )

    def _send_document(self, outbound: ChannelOutboundMessage) -> WhatsAppMessageSend:
        media = outbound.media
        assert media is not None
        reference = str(media.reference or "").strip()
        caption = media.caption or outbound.text
        if _is_http_url(reference):
            return self.client.send_document(
                outbound.recipient_id,
                link=reference,
                caption=caption,
                filename=media.filename,
            )
        upload = self.client.upload_media(reference, mime_type=media.mime_type)
        return self.client.send_document(
            outbound.recipient_id,
            media_id=upload.id,
            caption=caption,
            filename=media.filename,
        )


def agent_message_to_channel_messages(
    message: BaseMessage | dict[str, Any] | str,
    *,
    recipient_id: str,
) -> list[ChannelOutboundMessage]:
    """Convierte un mensaje del agente en uno o mas mensajes WhatsApp."""

    content = _message_content(message)
    blocks = _content_blocks(content)
    text_parts: list[str] = []
    media_blocks: list[ChannelMedia] = []

    for block in blocks:
        if isinstance(block, str):
            if block.strip():
                text_parts.append(block.strip())
            continue
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type == "text":
            text = str(block.get("text") or "").strip()
            if text:
                text_parts.append(text)
            continue
        media = _media_from_content_block(block)
        if media is not None:
            media_blocks.append(media)

    text = "\n\n".join(text_parts).strip()
    outbound: list[ChannelOutboundMessage] = []

    if not media_blocks:
        if text:
            outbound.append(
                ChannelOutboundMessage(
                    channel="whatsapp",
                    recipient_id=recipient_id,
                    kind="text",
                    text=text,
                )
            )
        return outbound

    caption = text if len(text) <= _WHATSAPP_IMAGE_CAPTION_LIMIT else None
    if text and caption is None:
        outbound.append(
            ChannelOutboundMessage(
                channel="whatsapp",
                recipient_id=recipient_id,
                kind="text",
                text=text,
            )
        )

    for index, media in enumerate(media_blocks):
        media_caption = caption if index == 0 else None
        outbound.append(
            ChannelOutboundMessage(
                channel="whatsapp",
                recipient_id=recipient_id,
                kind="image" if media.media_type == "image" else "document",
                text=media_caption,
                media=media.model_copy(update={"caption": media_caption}),
            )
        )

    return outbound


def whatsapp_inbound_to_human_message(inbound: ChannelInboundMessage) -> HumanMessage:
    """Convierte un mensaje WhatsApp normalizado al formato que consume el grafo."""

    content: list[dict[str, Any]] = []
    text = str(inbound.text or "").strip()
    if text:
        content.append({"type": "text", "text": text})
    for media in inbound.media:
        if media.media_type == "image":
            content.append(
                {
                    "type": "input_image",
                    "image_url": {"url": materialize_image_reference(media.reference)},
                }
            )
        elif media.caption and not text:
            content.append({"type": "text", "text": media.caption})

    if not content:
        return HumanMessage(content="")
    if len(content) == 1 and content[0].get("type") == "text":
        return HumanMessage(content=str(content[0].get("text") or ""))
    return HumanMessage(content=content)


def _message_content(message: BaseMessage | dict[str, Any] | str) -> Any:
    if isinstance(message, BaseMessage):
        return message.content
    if isinstance(message, dict):
        return message.get("content") or message.get("text") or ""
    return message


def _content_blocks(content: Any) -> list[Any]:
    if isinstance(content, list):
        return content
    if isinstance(content, tuple):
        return list(content)
    if content is None:
        return []
    return [content]


def _media_from_content_block(block: dict[str, Any]) -> ChannelMedia | None:
    image_ref = _image_reference(block)
    if image_ref:
        reference = materialize_image_reference(image_ref)
        return ChannelMedia(
            media_type="image",
            reference=reference,
            mime_type=_mime_type_for_reference(reference),
            filename=Path(reference).name if not _is_http_url(reference) else None,
        )
    return None


def _image_reference(block: dict[str, Any]) -> str:
    image_url = block.get("image_url")
    if isinstance(image_url, dict):
        return str(image_url.get("url") or "").strip()
    if image_url:
        return str(image_url).strip()
    if str(block.get("type") or "") in {"image", "input_image", "image_url"}:
        return str(block.get("url") or block.get("file") or "").strip()
    return ""


def _mime_type_for_reference(reference: str) -> str | None:
    if _is_http_url(reference):
        return mimetypes.guess_type(reference)[0]
    return mimetypes.guess_type(str(Path(reference)))[0]


def _send_result(
    outbound: ChannelOutboundMessage,
    response: WhatsAppMessageSend,
) -> ChannelSendResult:
    return ChannelSendResult(
        channel="whatsapp",
        recipient_id=outbound.recipient_id,
        provider_message_id=response.message_id,
        provider_media_id=outbound.media.provider_media_id if outbound.media else None,
        status="sent",
    )


def _download_filename(inbound: WhatsAppInboundMessage) -> str | None:
    if inbound.media is None:
        return None
    if inbound.media.filename:
        return inbound.media.filename
    extension = mimetypes.guess_extension(str(inbound.media.mime_type or "")) or ".bin"
    return f"{inbound.media.id}{extension}"


def _channel_media_type(value: str) -> str:
    return value if value in {"image", "document", "audio", "video"} else "document"


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


__all__ = [
    "WhatsAppChannelService",
    "agent_message_to_channel_messages",
    "whatsapp_inbound_to_human_message",
]
