"""Servicios de canal conversacional."""

from .whatsapp_service import (
    WhatsAppChannelService,
    agent_message_to_channel_messages,
    whatsapp_inbound_to_human_message,
)

__all__ = [
    "WhatsAppChannelService",
    "agent_message_to_channel_messages",
    "whatsapp_inbound_to_human_message",
]
