"""Utilidades comunes para los nodos del agente."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from services.scheduling.text_parser import is_ambiguous_time_range

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
_AMBIGUOUS_TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(?:\b([ap]m?)\b)?\s*(?:-|a|hasta)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(?:\b([ap]m?)\b)?"
)
_URL_PATTERN = re.compile(r"https?://[^\s\]>\"')]+")


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
        if isinstance(message, BaseMessage):
            role = getattr(message, "type", None)
            if role in {"ai", "assistant"}:
                continue
            return _coerce_text(getattr(message, "content", None))
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
        if isinstance(message, BaseMessage):
            role = getattr(message, "type", None)
            if role in {"ai", "assistant"}:
                continue
            return _extract_images(getattr(message, "content", None))
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
        nested = content.get("content")
        if nested is not None:
            images.extend(_extract_images(nested))
        return images
    if isinstance(content, (list, tuple)):
        for item in content:
            if isinstance(item, dict):
                url = _image_from_dict(item)
                if url:
                    images.append(url)
                nested = item.get("content")
                if nested is not None:
                    images.extend(_extract_images(nested))
            elif isinstance(item, str):
                images.extend(_extract_images(item))
        return images
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return images
        if text.startswith("data:image") or text.startswith(("http://", "https://")):
            images.append(text)
            return images
        images.extend(_URL_PATTERN.findall(text))
    if images:
        return list(dict.fromkeys(image for image in images if image))
    return images


def _image_from_dict(item: dict) -> str:
    if "image_url" in item:
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            return str(image_url.get("url") or "")
        return str(image_url)
    if item.get("type") in {"input_image", "image", "image_url"}:
        url = str(item.get("url") or "").strip()
        if url:
            return url
    if "image" in item:
        return str(item.get("image") or "")
    source = item.get("source")
    if isinstance(source, dict):
        source_url = str(source.get("url") or "").strip()
        if source_url:
            return source_url
        source_data = str(source.get("data") or source.get("base64") or "").strip()
        if source_data:
            media_type = str(source.get("media_type") or source.get("mime_type") or "image/png")
            return _build_data_url(source_data, media_type)
    raw_data = str(item.get("data") or item.get("base64") or "").strip()
    if raw_data:
        media_type = str(item.get("media_type") or item.get("mime_type") or "image/png")
        return _build_data_url(raw_data, media_type)
    if "file" in item:
        return str(item.get("file") or "")
    if "url" in item and str(item.get("url", "")).startswith(
        ("data:image", "http://", "https://")
    ):
        return str(item.get("url"))
    return ""


def _build_data_url(data: str, media_type: str) -> str:
    raw_data = str(data or "").strip()
    if not raw_data:
        return ""
    if raw_data.startswith("data:image"):
        return raw_data
    mime = str(media_type or "image/png").strip() or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{raw_data}"


def count_user_messages(messages: list[BaseMessage] | list) -> int:
    """Cuenta mensajes de usuario para detectar nueva entrada."""
    count = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            count += 1
        elif isinstance(message, BaseMessage):
            role = getattr(message, "type", None)
            if role in (None, "user", "human"):
                count += 1
        elif isinstance(message, dict):
            role = message.get("role") or message.get("type")
            if role in (None, "user", "human"):
                count += 1
        elif isinstance(message, str):
            count += 1
    return count


def append_message(
    messages: list[BaseMessage] | list,
    role: str,
    content: str | list[dict[str, Any]],
) -> list[BaseMessage]:
    """Retorna el/los mensajes nuevos para ser agregados por el reducer."""
    if role in ("user", "human"):
        return [HumanMessage(content=content)]
    return [AIMessage(content=content)]


def copy_onboarding_state(state: Any) -> dict[str, Any]:
    """Copia el bloque `onboarding` preservando el dict anidado de verificación.

    Los nodos de onboarding mutan una copia temporal del estado antes de devolver
    el `update` parcial al grafo. Este helper evita compartir referencias del
    sub-objeto `email_verification` entre turnos y centraliza una lógica que se
    repetía en varios nodos.
    """

    onboarding_state = state.get("onboarding", {}) if hasattr(state, "get") else {}
    onboarding = dict(onboarding_state)
    onboarding["email_verification"] = dict(
        onboarding_state.get("email_verification", {})
    )
    return onboarding


def parse_yes_no(text: str) -> Optional[bool]:
    """Interpreta respuestas simples de si/no."""
    if not text:
        return None
    normalized = normalize_text(text)
    for token in _YES_TOKENS:
        if contains_normalized_phrase(normalized, token):
            return True
    for token in _NO_TOKENS:
        if contains_normalized_phrase(normalized, token):
            return False
    return None


def parse_numbered_option(text: str | None) -> int | None:
    """Extrae una opción numérica simple al inicio de la respuesta."""

    raw = str(text or "").strip()
    if not raw:
        return None

    first_line = raw.splitlines()[0].strip()
    normalized = normalize_text(first_line)
    match = re.match(r"^(?:la\s+)?(?:opcion\s+)?(\d+)\b", normalized)
    if match is None:
        return None
    return int(match.group(1))


def contains_normalized_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = normalize_text(phrase)
    if not normalized_text or not normalized_phrase:
        return False
    return bool(
        re.search(
            rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
            normalized_text,
        )
    )


def detect_new_input(
    messages: list[BaseMessage] | list,
    last_count: int,
    awaiting_user_input: bool,
    last_user_text: Optional[str],
    last_user_images: Optional[list[str]] = None,
) -> tuple[bool, str, int]:
    """Detecta si hay nueva entrada del usuario aunque no crezca el contador."""
    current_count = count_user_messages(messages)
    last_text = get_last_user_text(messages)
    current_images = get_last_user_images(messages)
    has_new_input = current_count > last_count
    if not has_new_input and last_text and awaiting_user_input:
        if last_text != (last_user_text or ""):
            has_new_input = True
    if (
        not has_new_input
        and current_images
        and awaiting_user_input
        and last_user_images is not None
    ):
        if current_images != (last_user_images or []):
            has_new_input = True
    return has_new_input, last_text, current_count


def has_time_range(text: str) -> bool:
    """Detecta si el texto contiene un rango de horas."""
    if not text:
        return False
    return bool(_TIME_RANGE_PATTERN.search(normalize_text(text)))


def has_ambiguous_time_range(text: str) -> bool:
    """Detecta rangos ambiguos sin AM/PM (ej: 9-10)."""
    if not text:
        return False
    return is_ambiguous_time_range(text)
