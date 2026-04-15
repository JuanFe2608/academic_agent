"""Modelos del adaptador WhatsApp Cloud API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WhatsAppConfig:
    """Configuracion minima para WhatsApp Cloud API."""

    access_token: str
    phone_number_id: str
    api_version: str = "v20.0"
    graph_base_url: str = "https://graph.facebook.com"


@dataclass(frozen=True)
class WhatsAppHttpResponse:
    """Respuesta HTTP cruda usada por el cliente."""

    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class WhatsAppUploadedMedia:
    """Media subido a WhatsApp."""

    id: str


@dataclass(frozen=True)
class WhatsAppMediaDownload:
    """Archivo descargado desde WhatsApp."""

    media_id: str
    path: Path
    mime_type: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class WhatsAppMessageSend:
    """Resultado de envio de un mensaje WhatsApp."""

    message_id: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class WhatsAppInboundMedia:
    """Media recibido en un webhook WhatsApp."""

    id: str
    media_type: str
    mime_type: str | None = None
    caption: str | None = None
    filename: str | None = None


@dataclass(frozen=True)
class WhatsAppInboundMessage:
    """Mensaje entrante extraido desde un webhook WhatsApp."""

    from_number: str
    message_id: str
    text: str | None = None
    media: WhatsAppInboundMedia | None = None
    raw_message: dict[str, Any] | None = None


class WhatsAppClientError(RuntimeError):
    """Error de comunicacion o payload invalido de WhatsApp Cloud API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_payload: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_payload = response_payload


__all__ = [
    "WhatsAppClientError",
    "WhatsAppConfig",
    "WhatsAppHttpResponse",
    "WhatsAppInboundMedia",
    "WhatsAppInboundMessage",
    "WhatsAppMediaDownload",
    "WhatsAppMessageSend",
    "WhatsAppUploadedMedia",
]
