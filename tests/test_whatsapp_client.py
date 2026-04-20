"""Pruebas del adaptador WhatsApp Cloud API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.whatsapp import (
    WhatsAppClientError,
    WhatsAppCloudClient,
    WhatsAppConfig,
    WhatsAppHttpResponse,
    extract_inbound_messages,
    verify_webhook_challenge,
)


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses: list[WhatsAppHttpResponse] = []

    def queue_json(self, payload: dict[str, object], *, status_code: int = 200) -> None:
        self.responses.append(
            WhatsAppHttpResponse(
                status_code=status_code,
                headers={"Content-Type": "application/json"},
                body=json.dumps(payload).encode("utf-8"),
            )
        )

    def queue_bytes(
        self,
        payload: bytes,
        *,
        status_code: int = 200,
        content_type: str = "image/png",
    ) -> None:
        self.responses.append(
            WhatsAppHttpResponse(
                status_code=status_code,
                headers={"Content-Type": content_type},
                body=payload,
            )
        )

    def request(self, method, url, *, headers=None, body=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "body": body,
            }
        )
        return self.responses.pop(0)


def _client(transport: _FakeTransport) -> WhatsAppCloudClient:
    return WhatsAppCloudClient(
        WhatsAppConfig(
            access_token="token-123",
            phone_number_id="phone-123",
            api_version="v20.0",
            graph_base_url="https://graph.test",
        ),
        transport=transport,
    )


def test_whatsapp_client_uploads_media_with_multipart_body(tmp_path: Path) -> None:
    transport = _FakeTransport()
    transport.queue_json({"id": "media-123"})
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"png-bytes")

    uploaded = _client(transport).upload_media(image_path, mime_type="image/png")

    assert uploaded.id == "media-123"
    call = transport.calls[0]
    body = call["body"]
    assert call["method"] == "POST"
    assert call["url"] == "https://graph.test/v20.0/phone-123/media"
    assert call["headers"]["Authorization"] == "Bearer token-123"
    assert "multipart/form-data" in call["headers"]["Content-Type"]
    assert isinstance(body, bytes)
    assert b'name="messaging_product"' in body
    assert b"whatsapp" in body
    assert b'name="type"' in body
    assert b"image/png" in body
    assert b'filename="schedule.png"' in body
    assert b"png-bytes" in body


def test_whatsapp_client_sends_uploaded_image_message() -> None:
    transport = _FakeTransport()
    transport.queue_json({"messages": [{"id": "wamid.1"}]})

    sent = _client(transport).send_image(
        "573001112233",
        media_id="media-123",
        caption="Tu horario",
    )

    assert sent.message_id == "wamid.1"
    body = json.loads(transport.calls[0]["body"].decode("utf-8"))
    assert transport.calls[0]["url"] == "https://graph.test/v20.0/phone-123/messages"
    assert body["messaging_product"] == "whatsapp"
    assert body["to"] == "573001112233"
    assert body["type"] == "image"
    assert body["image"] == {"id": "media-123", "caption": "Tu horario"}


def test_whatsapp_client_downloads_inbound_media(tmp_path: Path) -> None:
    transport = _FakeTransport()
    transport.queue_json(
        {
            "url": "https://lookaside.test/media",
            "mime_type": "image/png",
            "sha256": "abc",
        }
    )
    transport.queue_bytes(b"image-bytes", content_type="image/png")

    downloaded = _client(transport).download_media(
        "media-123",
        out_dir=tmp_path,
    )

    assert downloaded.media_id == "media-123"
    assert downloaded.path.read_bytes() == b"image-bytes"
    assert downloaded.path.name == "media-123.png"
    assert transport.calls[0]["url"] == "https://graph.test/v20.0/media-123"
    assert transport.calls[1]["url"] == "https://lookaside.test/media"


def test_whatsapp_client_raises_on_api_error() -> None:
    transport = _FakeTransport()
    transport.queue_json({"error": {"message": "bad token"}}, status_code=401)

    with pytest.raises(WhatsAppClientError) as exc_info:
        _client(transport).send_text("573001112233", "hola")

    assert exc_info.value.status_code == 401
    assert "rechazo" in str(exc_info.value)


def test_extract_inbound_messages_maps_text_and_image_webhook() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "573001112233",
                                    "id": "wamid.text",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                },
                                {
                                    "from": "573001112233",
                                    "id": "wamid.image",
                                    "type": "image",
                                    "image": {
                                        "id": "media-123",
                                        "mime_type": "image/png",
                                        "caption": "mi horario",
                                    },
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }

    messages = extract_inbound_messages(payload)

    assert len(messages) == 2
    assert messages[0].text == "hola"
    assert messages[1].media is not None
    assert messages[1].media.id == "media-123"
    assert messages[1].media.caption == "mi horario"


def test_extract_inbound_messages_maps_sticker_webhook_for_buffer_policy() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "573001112233",
                                    "id": "wamid.sticker",
                                    "type": "sticker",
                                    "sticker": {
                                        "id": "sticker-123",
                                        "mime_type": "image/webp",
                                    },
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }

    messages = extract_inbound_messages(payload)

    assert len(messages) == 1
    assert messages[0].media is not None
    assert messages[0].media.media_type == "sticker"
    assert messages[0].media.id == "sticker-123"


def test_verify_webhook_challenge_accepts_expected_token() -> None:
    assert (
        verify_webhook_challenge(
            mode="subscribe",
            verify_token="verify-123",
            challenge="challenge-value",
            expected_verify_token="verify-123",
        )
        == "challenge-value"
    )
    assert (
        verify_webhook_challenge(
            mode="subscribe",
            verify_token="wrong",
            challenge="challenge-value",
            expected_verify_token="verify-123",
        )
        is None
    )
