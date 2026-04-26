"""Almacenamiento local de imagenes para evitar base64 en checkpoints."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
from pathlib import Path

_DATA_IMAGE_RE = re.compile(
    r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.*)$",
    re.DOTALL,
)


def project_media_dir() -> Path:
    """Directorio local para artefactos multimedia ligeros de desarrollo."""

    configured = os.getenv("ACADEMIC_AGENT_MEDIA_DIR")
    if configured:
        root = Path(configured)
    else:
        root = Path.cwd() / ".langgraph_media"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def is_data_image_url(value: object) -> bool:
    return isinstance(value, str) and bool(_DATA_IMAGE_RE.match(value.strip()))


def is_inline_preview_enabled() -> bool:
    """Retorna True si MEDIA_INLINE_PREVIEW=true (para debuggear en LangSmith)."""
    return os.getenv("MEDIA_INLINE_PREVIEW", "").lower() in {"1", "true", "yes"}


def path_to_data_url(path: str) -> str:
    """Convierte una ruta local de imagen a data: URL (base64). Util para debugging."""
    raw = str(path or "").strip()
    if not raw or not os.path.exists(raw):
        return raw
    mime_type = mimetypes.guess_type(raw)[0] or "image/png"
    with open(raw, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def materialize_image_reference(value: str | None) -> str:
    """Convierte data URLs de imagen en rutas locales; deja URLs/rutas intactas.

    Con MEDIA_INLINE_PREVIEW=true:
    - Las data: URLs se conservan inline (no se escriben a disco).
    - Las rutas locales de archivo se convierten a data: URLs.
    Esto permite que LangSmith renderice todas las imagenes en modo debug.
    """

    raw = str(value or "").strip()
    if not raw:
        return ""

    match = _DATA_IMAGE_RE.match(raw)
    if match is None:
        if is_inline_preview_enabled() and os.path.isfile(raw):
            return path_to_data_url(raw)
        return raw

    if is_inline_preview_enabled():
        return raw

    return materialize_base64_image(
        match.group("data"),
        mime_type=match.group("mime"),
    )


def materialize_base64_image(data: str, *, mime_type: str = "image/png") -> str:
    """Persiste bytes base64 como archivo local y retorna la ruta absoluta."""

    raw_data = str(data or "").strip()
    normalized_mime = _normalize_image_mime(mime_type)
    decoded = _decode_base64(raw_data)
    digest = hashlib.sha256(decoded).hexdigest()
    extension = _extension_for_mime(normalized_mime)
    path = project_media_dir() / f"{digest}{extension}"
    if not path.exists():
        path.write_bytes(decoded)
    return str(path)


def _decode_base64(raw_data: str) -> bytes:
    compact = re.sub(r"\s+", "", raw_data)
    if not compact:
        return b""
    padded = compact + ("=" * (-len(compact) % 4))
    try:
        return base64.b64decode(padded, validate=False)
    except Exception:
        return raw_data.encode("utf-8", errors="ignore")


def _normalize_image_mime(mime_type: str | None) -> str:
    raw = str(mime_type or "image/png").strip().lower()
    if not raw.startswith("image/"):
        return "image/png"
    return raw


def _extension_for_mime(mime_type: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    extension = mimetypes.guess_extension(mime_type) or ".img"
    if extension == ".jpe":
        return ".jpg"
    return extension
