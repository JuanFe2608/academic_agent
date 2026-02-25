"""Utilidades comunes para los nodos del agente."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

_YES_TOKENS = {
    "si",
    "sip",
    "claro",
    "acepto",
    "de acuerdo",
    "ok",
    "vale",
}
_NO_TOKENS = {"no", "nop", "rechazo", "no acepto", "negativo"}

_TIME_RANGE_PATTERN = re.compile(
    r"\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?\s*(?:-|a|hasta)\s*\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?"
)


def strip_accents(value: str) -> str:
    """Elimina acentos y devuelve una version ASCII."""
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_text(value: str) -> str:
    """Normaliza texto para comparaciones simples."""
    return strip_accents(value).lower().strip()


def get_last_user_text(messages: list[BaseMessage] | list) -> str:
    """Devuelve el ultimo texto del usuario en una lista de mensajes."""
    if not messages:
        return ""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _coerce_text(message.content)
        if isinstance(message, AIMessage):
            continue
        if isinstance(message, str):
            return message.strip()
        if isinstance(message, dict):
            role = message.get("role") or message.get("type")
            if role in (None, "user", "human"):
                content = message.get("content") or message.get("text") or ""
                return _coerce_text(content)
        content = getattr(message, "content", None)
        if content is not None:
            return _coerce_text(content)
    return ""


def get_last_user_images(messages: list[BaseMessage] | list) -> list[str]:
    """Devuelve urls/base64 de imagenes del ultimo mensaje de usuario."""
    if not messages:
        return []

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            continue
        if isinstance(message, HumanMessage):
            return _extract_images(message.content)
        if isinstance(message, dict):
            role = message.get("role") or message.get("type")
            if role in (None, "user", "human"):
                content = message.get("content") or message.get("text") or ""
                return _extract_images(content)
        content = getattr(message, "content", None)
        if content is not None:
            return _extract_images(content)
    return []


def _coerce_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text", "")).strip()
        if "content" in content:
            return str(content.get("content", "")).strip()
        return str(content).strip()
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(str(item.get("content", "")))
        return " ".join(part.strip() for part in parts if part and str(part).strip())
    return str(content).strip()


def _extract_images(content: object) -> list[str]:
    images: list[str] = []
    if content is None:
        return images
    if isinstance(content, dict):
        url = _image_from_dict(content)
        if url:
            images.append(url)
        return images
    if isinstance(content, (list, tuple)):
        for item in content:
            if isinstance(item, dict):
                url = _image_from_dict(item)
                if url:
                    images.append(url)
            elif isinstance(item, str) and item.startswith("data:image"):
                images.append(item)
        return images
    if isinstance(content, str) and content.startswith("data:image"):
        images.append(content)
    return images


def _image_from_dict(item: dict) -> str:
    if "image_url" in item:
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            return str(image_url.get("url") or "")
        return str(image_url)
    if "image" in item:
        return str(item.get("image") or "")
    if "file" in item:
        return str(item.get("file") or "")
    if "url" in item and str(item.get("url", "")).startswith("data:image"):
        return str(item.get("url"))
    return ""


def count_user_messages(messages: list[BaseMessage] | list) -> int:
    """Cuenta mensajes de usuario para detectar nueva entrada."""
    count = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            count += 1
        elif isinstance(message, dict):
            role = message.get("role") or message.get("type")
            if role in (None, "user", "human"):
                count += 1
        elif isinstance(message, str):
            count += 1
    return count


def append_message(messages: list[BaseMessage] | list, role: str, content: str) -> list[BaseMessage]:
    """Retorna el/los mensajes nuevos para ser agregados por el reducer."""
    if role in ("user", "human"):
        return [HumanMessage(content=content)]
    return [AIMessage(content=content)]


def parse_yes_no(text: str) -> Optional[bool]:
    """Interpreta respuestas simples de si/no."""
    if not text:
        return None
    normalized = normalize_text(text)
    for token in _YES_TOKENS:
        if token in normalized:
            return True
    for token in _NO_TOKENS:
        if token in normalized:
            return False
    return None


def detect_new_input(
    messages: list[BaseMessage] | list,
    last_count: int,
    awaiting_user_input: bool,
    last_user_text: Optional[str],
) -> tuple[bool, str, int]:
    """Detecta si hay nueva entrada del usuario aunque no crezca el contador."""
    current_count = count_user_messages(messages)
    last_text = get_last_user_text(messages)
    has_new_input = current_count > last_count
    if not has_new_input and last_text and awaiting_user_input:
        if last_text != (last_user_text or ""):
            has_new_input = True
    return has_new_input, last_text, current_count


def has_time_range(text: str) -> bool:
    """Detecta si el texto contiene un rango de horas."""
    if not text:
        return False
    return bool(_TIME_RANGE_PATTERN.search(normalize_text(text)))
