"""Adaptadores de proveedor para WhatsApp Cloud API."""

from .client import (
    UrllibWhatsAppTransport,
    WhatsAppCloudClient,
    WhatsAppHttpTransport,
    verify_webhook_challenge,
)
from .message_mapper import extract_inbound_messages
from .models import (
    WhatsAppClientError,
    WhatsAppConfig,
    WhatsAppHttpResponse,
    WhatsAppInboundMedia,
    WhatsAppInboundMessage,
    WhatsAppMediaDownload,
    WhatsAppMessageSend,
    WhatsAppUploadedMedia,
)

__all__ = [
    "UrllibWhatsAppTransport",
    "WhatsAppClientError",
    "WhatsAppCloudClient",
    "WhatsAppConfig",
    "WhatsAppHttpResponse",
    "WhatsAppHttpTransport",
    "WhatsAppInboundMedia",
    "WhatsAppInboundMessage",
    "WhatsAppMediaDownload",
    "WhatsAppMessageSend",
    "WhatsAppUploadedMedia",
    "extract_inbound_messages",
    "verify_webhook_challenge",
]
