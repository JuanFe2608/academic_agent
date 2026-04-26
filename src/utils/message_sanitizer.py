"""Sanitizacion generica de mensajes para mantener estados livianos."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from utils.media_artifacts import (
    is_data_image_url,
    materialize_base64_image,
    materialize_image_reference,
)


def add_sanitized_messages(left: Any, right: Any) -> list[BaseMessage]:
    """Reducer compatible con LangGraph que materializa imagenes antes de guardar."""

    return add_messages(left, sanitize_messages(right))


def sanitize_messages(messages: Any) -> Any:
    if messages is None:
        return messages
    if isinstance(messages, BaseMessage):
        return _sanitize_message(messages)
    if isinstance(messages, list):
        return [_sanitize_message(message) for message in messages]
    if isinstance(messages, tuple):
        return tuple(_sanitize_message(message) for message in messages)
    return _sanitize_message(messages)


def sanitize_message_content(content: Any) -> Any:
    if isinstance(content, str):
        return materialize_image_reference(content)
    if isinstance(content, list):
        return [sanitize_message_content(item) for item in content]
    if isinstance(content, tuple):
        return tuple(sanitize_message_content(item) for item in content)
    if isinstance(content, dict):
        return _sanitize_content_dict(content)
    return content


def sanitize_persisted_payload(payload: Any) -> Any:
    """Sanitiza estructuras arbitrarias antes de serializarlas en checkpoints."""

    if isinstance(payload, BaseMessage):
        return _sanitize_message(payload)
    if isinstance(payload, dict):
        return {key: sanitize_persisted_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [sanitize_persisted_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_persisted_payload(item) for item in payload)
    if isinstance(payload, str):
        # Solo materializar base64 crudo; las rutas locales se dejan intactas
        # para evitar que el checkpointer infle el estado con imágenes inline.
        if is_data_image_url(payload):
            return materialize_image_reference(payload)
        return payload
    return payload


def _sanitize_message(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        return message.model_copy(
            update={"content": sanitize_message_content(message.content)}
        )
    if isinstance(message, dict):
        return _sanitize_content_dict(message)
    return message


def _sanitize_content_dict(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: sanitize_message_content(value) for key, value in item.items()}

    image_url = sanitized.get("image_url")
    if isinstance(image_url, dict):
        url = materialize_image_reference(str(image_url.get("url") or ""))
        if url:
            image_url = dict(image_url)
            image_url["url"] = url
            sanitized["image_url"] = image_url
    elif isinstance(image_url, str):
        sanitized["image_url"] = materialize_image_reference(image_url)

    source = item.get("source")
    if isinstance(source, dict):
        source_ref = _materialize_source_dict(source)
        if source_ref:
            sanitized["image_url"] = {"url": source_ref}
            sanitized["source"] = {
                "type": "file",
                "media_type": str(
                    source.get("media_type") or source.get("mime_type") or "image/png"
                ),
                "path": source_ref,
            }

    inline_ref = _materialize_inline_image_dict(item)
    if inline_ref:
        sanitized["image_url"] = {"url": inline_ref}
        sanitized.pop("data", None)
        sanitized.pop("base64", None)

    return sanitized


def _materialize_source_dict(source: dict[str, Any]) -> str:
    data = source.get("data") or source.get("base64")
    if not data:
        path = source.get("path") or source.get("file")
        return str(path or "").strip()
    media_type = str(source.get("media_type") or source.get("mime_type") or "image/png")
    raw = str(data or "").strip()
    if raw.startswith("data:image"):
        return materialize_image_reference(raw)
    return materialize_base64_image(raw, mime_type=media_type)


def _materialize_inline_image_dict(item: dict[str, Any]) -> str:
    if str(item.get("type") or "") not in {"image", "input_image", "image_url"}:
        return ""
    data = item.get("data") or item.get("base64")
    if not data:
        return ""
    media_type = str(item.get("media_type") or item.get("mime_type") or "image/png")
    raw = str(data or "").strip()
    if raw.startswith("data:image"):
        return materialize_image_reference(raw)
    return materialize_base64_image(raw, mime_type=media_type)
