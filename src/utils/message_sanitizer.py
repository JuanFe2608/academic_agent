"""Sanitizacion generica de mensajes para mantener estados livianos.

El reducer add_sanitized_messages NO hace I/O — reemplaza datos de imagen
con IMAGE_RECEIVED_MARKER para evitar que blockbuster lance BlockingError
en el event loop async de LangGraph API.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from utils.media_artifacts import IMAGE_RECEIVED_MARKER, strip_image_to_marker


def add_sanitized_messages(left: Any, right: Any) -> list[BaseMessage]:
    """Reducer LangGraph: strip imagen a marcador en memoria. Sin I/O."""
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
    """Reemplaza datos de imagen con marcador. Sin I/O."""
    return strip_image_to_marker(content)


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
        return IMAGE_RECEIVED_MARKER if _is_data_image_url_fast(payload) else payload
    return payload


def _sanitize_message(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        return message.model_copy(
            update={"content": sanitize_message_content(message.content)}
        )
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            return {**message, "content": sanitize_message_content(content)}
    return message


def _is_data_image_url_fast(value: str) -> bool:
    return value.lstrip().startswith("data:image")
