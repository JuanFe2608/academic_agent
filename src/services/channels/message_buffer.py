"""Buffer in-memory para mensajes fragmentados de canales conversacionales."""

from __future__ import annotations

import re
from datetime import datetime

from schemas.channels import (
    AggregatedInput,
    BufferedMessage,
    ChannelInboundMessage,
    ChannelMedia,
)
from services.conversation.input_classifier import classify_input

_DEFAULT_TIMEOUT_SECONDS = 4.0
_MAX_PENDING_MESSAGES = 20


class MessageBuffer:
    """Agrega mensajes por conversacion antes de enviarlos al grafo."""

    def __init__(
        self,
        *,
        flush_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_pending_messages: int = _MAX_PENDING_MESSAGES,
    ) -> None:
        self.flush_timeout_seconds = max(0.0, float(flush_timeout_seconds))
        self.max_pending_messages = max(1, int(max_pending_messages))
        self._pending: dict[str, list[BufferedMessage]] = {}

    def add_message(
        self,
        message: BufferedMessage | ChannelInboundMessage,
        *,
        conversation_id: str | None = None,
        confirmation_pending: bool = False,
    ) -> list[AggregatedInput]:
        """Agrega un mensaje y devuelve payloads listos si alguna regla hace flush."""

        buffered = self._coerce_message(message, conversation_id=conversation_id)
        pending = list(self._pending.get(buffered.conversation_id, []))
        outputs: list[AggregatedInput] = []

        timeout_reason = self._timeout_reason(pending, buffered.received_at)
        if timeout_reason is not None:
            outputs.append(self._aggregate(pending, flush_reason=timeout_reason))
            pending = []

        immediate_reason = self.flush_reason(
            buffered,
            confirmation_pending=confirmation_pending,
        )
        if immediate_reason is not None:
            if pending:
                outputs.append(
                    self._aggregate(
                        pending,
                        flush_reason="interrupted_by_immediate_input",
                    )
                )
            outputs.append(self._aggregate([buffered], flush_reason=immediate_reason))
            self._pending.pop(buffered.conversation_id, None)
            return outputs

        pending.append(buffered)
        self._pending[buffered.conversation_id] = pending
        if len(pending) >= self.max_pending_messages:
            flushed = self.flush(buffered.conversation_id, reason="max_pending_messages")
            if flushed is not None:
                outputs.append(flushed)
        return outputs

    def should_flush(
        self,
        message: BufferedMessage | ChannelInboundMessage,
        *,
        conversation_id: str | None = None,
        confirmation_pending: bool = False,
    ) -> bool:
        """Indica si el mensaje actual debe disparar flush inmediato."""

        buffered = self._coerce_message(message, conversation_id=conversation_id)
        return self.flush_reason(
            buffered,
            confirmation_pending=confirmation_pending,
        ) is not None

    def flush_reason(
        self,
        message: BufferedMessage,
        *,
        confirmation_pending: bool = False,
    ) -> str | None:
        """Devuelve la razon de flush inmediato para un mensaje, si existe."""

        media_types = message_media_types(message)
        if media_types:
            return f"media:{media_types[0]}"

        classification = classify_input(message.text, media_types=media_types)
        if classification.utility == "command":
            return "critical_command"
        if classification.utility == "confirmation":
            return "confirmation_pending" if confirmation_pending else "confirmation"
        return None

    def flush(self, conversation_id: str, *, reason: str = "manual") -> AggregatedInput | None:
        """Fuerza el flush de los mensajes pendientes de una conversacion."""

        pending = self._pending.pop(conversation_id, [])
        if not pending:
            return None
        return self._aggregate(pending, flush_reason=reason)

    def reset(self, conversation_id: str) -> None:
        """Limpia los mensajes pendientes de una conversacion."""

        self._pending.pop(conversation_id, None)

    def pending_count(self, conversation_id: str) -> int:
        """Cantidad de mensajes pendientes para una conversacion."""

        return len(self._pending.get(conversation_id, []))

    def aggregate_text(self, messages: list[BufferedMessage]) -> str:
        """Une texto fragmentado preservando saltos de linea utiles."""

        fragments: list[str] = []
        for message in messages:
            fragment = _normalize_text_fragment(message.text)
            if fragment:
                fragments.append(fragment)
        return "\n".join(fragments)

    def _coerce_message(
        self,
        message: BufferedMessage | ChannelInboundMessage,
        *,
        conversation_id: str | None = None,
    ) -> BufferedMessage:
        if isinstance(message, BufferedMessage):
            if conversation_id and conversation_id != message.conversation_id:
                return message.model_copy(update={"conversation_id": conversation_id})
            return message
        return BufferedMessage.from_channel_inbound(
            message,
            conversation_id=conversation_id,
        )

    def _timeout_reason(
        self,
        pending: list[BufferedMessage],
        received_at: datetime,
    ) -> str | None:
        if not pending or self.flush_timeout_seconds <= 0:
            return None
        last_received_at = pending[-1].received_at
        elapsed = (received_at - last_received_at).total_seconds()
        return "timeout" if elapsed >= self.flush_timeout_seconds else None

    def _aggregate(
        self,
        messages: list[BufferedMessage],
        *,
        flush_reason: str,
    ) -> AggregatedInput:
        first = messages[0]
        media = _aggregate_media(messages)
        text = self.aggregate_text(messages)
        media_types = list(dict.fromkeys(media_item.media_type for media_item in media))
        classification = classify_input(text, media_types=media_types)
        return AggregatedInput(
            channel=first.channel,
            conversation_id=first.conversation_id,
            sender_id=first.sender_id,
            text=text,
            media=media,
            media_types=media_types,
            messages=list(messages),
            message_count=len(messages),
            latest_message_id=messages[-1].message_id,
            flush_reason=flush_reason,
            classification=classification,
            created_at=messages[-1].received_at,
        )


def message_media_types(message: BufferedMessage) -> list[str]:
    """Lista tipos de media normalizados en un mensaje de buffer."""

    return list(dict.fromkeys(media.media_type for media in message.media))


def _aggregate_media(messages: list[BufferedMessage]) -> list[ChannelMedia]:
    media: list[ChannelMedia] = []
    for message in messages:
        media.extend(message.media)
    return media


def _normalize_text_fragment(text: str | None) -> str:
    if not text:
        return ""
    normalized_lines: list[str] = []
    for line in str(text).splitlines():
        normalized = re.sub(r"[ \t]+", " ", line.strip())
        if normalized:
            normalized_lines.append(normalized)
    return "\n".join(normalized_lines)


__all__ = ["MessageBuffer", "message_media_types"]
