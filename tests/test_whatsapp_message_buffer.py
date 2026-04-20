"""Pruebas del buffer de mensajes WhatsApp."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from schemas.channels import BufferedMessage, ChannelMedia
from services.channels.message_buffer import MessageBuffer


def _message(
    text: str | None = None,
    *,
    media: list[ChannelMedia] | None = None,
    received_at: datetime | None = None,
    message_id: str | None = None,
) -> BufferedMessage:
    return BufferedMessage(
        conversation_id="573001112233",
        sender_id="573001112233",
        message_id=message_id,
        text=text,
        media=media or [],
        received_at=received_at or datetime(2026, 4, 18, tzinfo=UTC),
    )


def test_message_buffer_aggregates_fragmented_profile_messages_with_newlines() -> None:
    buffer = MessageBuffer(flush_timeout_seconds=30)

    assert buffer.add_message(_message(" Andres ", message_id="1")) == []
    assert buffer.add_message(_message("Gomez", message_id="2")) == []
    assert buffer.add_message(_message("67000921", message_id="3")) == []

    aggregated = buffer.flush("573001112233", reason="manual")

    assert aggregated is not None
    assert aggregated.text == "Andres\nGomez\n67000921"
    assert aggregated.message_count == 3
    assert aggregated.latest_message_id == "3"
    assert buffer.pending_count("573001112233") == 0


def test_message_buffer_flushes_confirmation_and_critical_commands_immediately() -> None:
    buffer = MessageBuffer()

    confirmation = buffer.add_message(_message("si"))
    delete_command = buffer.add_message(_message("borra ese evento"))
    cancel_command = buffer.add_message(_message("cancelar"))
    replan_command = buffer.add_message(_message("reagenda el parcial"))

    assert confirmation[0].text == "si"
    assert confirmation[0].flush_reason == "confirmation"
    assert delete_command[0].flush_reason == "critical_command"
    assert cancel_command[0].flush_reason == "critical_command"
    assert replan_command[0].flush_reason == "critical_command"


def test_message_buffer_does_not_flush_useful_phrases_that_contain_confirmation_words() -> None:
    buffer = MessageBuffer()

    outputs = buffer.add_message(_message("No entiendo calculo"))

    assert outputs == []
    assert buffer.pending_count("573001112233") == 1


def test_message_buffer_does_not_join_immediate_confirmation_with_pending_fragments() -> None:
    buffer = MessageBuffer(flush_timeout_seconds=30)

    assert buffer.add_message(_message("Andres")) == []
    outputs = buffer.add_message(_message("si"))

    assert len(outputs) == 2
    assert outputs[0].text == "Andres"
    assert outputs[0].flush_reason == "interrupted_by_immediate_input"
    assert outputs[1].text == "si"
    assert outputs[1].flush_reason == "confirmation"


def test_message_buffer_flushes_image_immediately_and_preserves_media() -> None:
    buffer = MessageBuffer()
    image = ChannelMedia(media_type="image", reference="/tmp/schedule.png")

    outputs = buffer.add_message(_message("mi horario", media=[image]))

    assert len(outputs) == 1
    assert outputs[0].flush_reason == "media:image"
    assert outputs[0].text == "mi horario"
    assert outputs[0].media == [image]
    assert outputs[0].classification.input_type == "mixed"
    assert outputs[0].classification.is_useful is True


def test_message_buffer_marks_sticker_as_non_useful_immediate_payload() -> None:
    buffer = MessageBuffer()
    sticker = ChannelMedia(media_type="sticker", reference="/tmp/sticker.webp")

    outputs = buffer.add_message(_message(media=[sticker]))

    assert len(outputs) == 1
    assert outputs[0].flush_reason == "media:sticker"
    assert outputs[0].classification.input_type == "sticker_only"
    assert outputs[0].classification.is_useful is False


def test_message_buffer_timeout_flushes_previous_batch_before_new_message() -> None:
    buffer = MessageBuffer(flush_timeout_seconds=5)
    first_at = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
    second_at = first_at + timedelta(seconds=10)

    assert buffer.add_message(_message("Andres", received_at=first_at)) == []
    outputs = buffer.add_message(_message("Gomez", received_at=second_at))

    assert len(outputs) == 1
    assert outputs[0].text == "Andres"
    assert outputs[0].flush_reason == "timeout"
    assert buffer.pending_count("573001112233") == 1

    second = buffer.flush("573001112233", reason="manual")
    assert second is not None
    assert second.text == "Gomez"
