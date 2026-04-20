"""Mapeo de webhooks de WhatsApp a modelos internos del adaptador."""

from __future__ import annotations

from typing import Any

from .models import WhatsAppInboundMedia, WhatsAppInboundMessage


def extract_inbound_messages(payload: dict[str, Any]) -> list[WhatsAppInboundMessage]:
    """Extrae mensajes entrantes de un webhook de WhatsApp Cloud API."""

    messages: list[WhatsAppInboundMessage] = []
    for entry in _as_list(payload.get("entry")):
        for change in _as_list(_as_dict(entry).get("changes")):
            value = _as_dict(_as_dict(change).get("value"))
            for raw_message in _as_list(value.get("messages")):
                message = _message_from_payload(_as_dict(raw_message))
                if message is not None:
                    messages.append(message)
    return messages


def _message_from_payload(message: dict[str, Any]) -> WhatsAppInboundMessage | None:
    sender = str(message.get("from") or "").strip()
    message_id = str(message.get("id") or "").strip()
    message_type = str(message.get("type") or "").strip()
    if not sender or not message_id:
        return None

    if message_type == "text":
        text_payload = _as_dict(message.get("text"))
        return WhatsAppInboundMessage(
            from_number=sender,
            message_id=message_id,
            text=str(text_payload.get("body") or "").strip() or None,
            raw_message=message,
        )

    media = _media_from_payload(message_type, _as_dict(message.get(message_type)))
    if media is None:
        return WhatsAppInboundMessage(
            from_number=sender,
            message_id=message_id,
            raw_message=message,
        )

    return WhatsAppInboundMessage(
        from_number=sender,
        message_id=message_id,
        text=media.caption,
        media=media,
        raw_message=message,
    )


def _media_from_payload(
    message_type: str,
    payload: dict[str, Any],
) -> WhatsAppInboundMedia | None:
    if message_type not in {"image", "document", "audio", "video", "sticker"}:
        return None
    media_id = str(payload.get("id") or "").strip()
    if not media_id:
        return None
    return WhatsAppInboundMedia(
        id=media_id,
        media_type=message_type,
        mime_type=str(payload.get("mime_type") or "").strip() or None,
        caption=str(payload.get("caption") or "").strip() or None,
        filename=str(payload.get("filename") or "").strip() or None,
    )


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = ["extract_inbound_messages"]
