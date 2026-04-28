"""Cliente sincrono para WhatsApp Cloud API."""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from utils.media_artifacts import project_media_dir

from .models import (
    WhatsAppClientError,
    WhatsAppConfig,
    WhatsAppHttpResponse,
    WhatsAppMediaDownload,
    WhatsAppMessageSend,
    WhatsAppUploadedMedia,
)


class WhatsAppHttpTransport(Protocol):
    """Transporte HTTP intercambiable para pruebas y despliegue."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> WhatsAppHttpResponse:
        """Ejecuta una solicitud HTTP."""


class UrllibWhatsAppTransport:
    """Transporte HTTP basado en la libreria estandar."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> WhatsAppHttpResponse:
        request = Request(
            url,
            data=body,
            method=method.upper(),
            headers=dict(headers or {}),
        )
        try:
            with urlopen(request, timeout=30) as response:
                return WhatsAppHttpResponse(
                    status_code=int(response.status),
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return WhatsAppHttpResponse(
                status_code=int(exc.code),
                headers=dict(exc.headers.items()),
                body=exc.read(),
            )


class WhatsAppCloudClient:
    """Adaptador de bajo nivel para enviar y descargar media en WhatsApp."""

    def __init__(
        self,
        config: WhatsAppConfig,
        *,
        transport: WhatsAppHttpTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibWhatsAppTransport()

    @classmethod
    def from_env(
        cls,
        *,
        transport: WhatsAppHttpTransport | None = None,
    ) -> "WhatsAppCloudClient":
        token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        if not token or not phone_number_id:
            raise WhatsAppClientError(
                "Configura WHATSAPP_ACCESS_TOKEN y WHATSAPP_PHONE_NUMBER_ID."
            )
        return cls(
            WhatsAppConfig(
                access_token=token,
                phone_number_id=phone_number_id,
                api_version=os.getenv("WHATSAPP_GRAPH_API_VERSION", "v20.0").strip()
                or "v20.0",
                graph_base_url=os.getenv(
                    "WHATSAPP_GRAPH_BASE_URL",
                    "https://graph.facebook.com",
                ).strip()
                or "https://graph.facebook.com",
            ),
            transport=transport,
        )

    def upload_media(
        self,
        path: str | Path,
        *,
        mime_type: str | None = None,
    ) -> WhatsAppUploadedMedia:
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            raise WhatsAppClientError(
                f"No existe el archivo para subir a WhatsApp: {file_path}"
            )

        resolved_mime = (
            mime_type
            or mimetypes.guess_type(str(file_path))[0]
            or "application/octet-stream"
        )
        boundary = f"academic-agent-{uuid.uuid4().hex}"
        body = _build_multipart_body(
            boundary=boundary,
            fields={
                "messaging_product": "whatsapp",
                "type": resolved_mime,
            },
            file_field="file",
            file_path=file_path,
            file_mime_type=resolved_mime,
        )
        payload = self._request_json(
            "POST",
            self._phone_url("media"),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body,
        )
        media_id = str(payload.get("id") or "").strip()
        if not media_id:
            raise WhatsAppClientError(
                "WhatsApp no retorno id al subir media.",
                response_payload=payload,
            )
        return WhatsAppUploadedMedia(id=media_id)

    def send_text(self, to: str, text: str) -> WhatsAppMessageSend:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return self._send_message_payload(payload)

    def send_image(
        self,
        to: str,
        *,
        media_id: str | None = None,
        link: str | None = None,
        caption: str | None = None,
    ) -> WhatsAppMessageSend:
        image_payload: dict[str, str] = {}
        if media_id:
            image_payload["id"] = media_id
        elif link:
            image_payload["link"] = link
        else:
            raise WhatsAppClientError("send_image requiere media_id o link.")
        if caption:
            image_payload["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
        return self._send_message_payload(payload)

    def send_document(
        self,
        to: str,
        *,
        media_id: str | None = None,
        link: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
    ) -> WhatsAppMessageSend:
        document_payload: dict[str, str] = {}
        if media_id:
            document_payload["id"] = media_id
        elif link:
            document_payload["link"] = link
        else:
            raise WhatsAppClientError("send_document requiere media_id o link.")
        if caption:
            document_payload["caption"] = caption
        if filename:
            document_payload["filename"] = filename
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": document_payload,
        }
        return self._send_message_payload(payload)

    def mark_as_read(self, message_id: str) -> None:
        """Marca un mensaje entrante como leido (checkmarks azules en WhatsApp)."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            self._request_json("POST", self._phone_url("messages"), json_payload=payload)
        except Exception:
            pass  # Best-effort — no interrumpir el flujo si falla

    def get_media_url(self, media_id: str) -> dict[str, Any]:
        return self._request_json("GET", self._graph_url(media_id))

    def download_media(
        self,
        media_id: str,
        *,
        out_dir: str | Path | None = None,
        filename: str | None = None,
    ) -> WhatsAppMediaDownload:
        media_info = self.get_media_url(media_id)
        media_url = str(media_info.get("url") or "").strip()
        if not media_url:
            raise WhatsAppClientError(
                "WhatsApp no retorno URL para descargar media.",
                response_payload=media_info,
            )

        response = self._request_bytes("GET", media_url)
        content_type = _header_lookup(response.headers, "content-type") or str(
            media_info.get("mime_type") or "application/octet-stream"
        )
        extension = (
            mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
        )
        target_dir = (
            Path(out_dir) if out_dir is not None else project_media_dir() / "whatsapp"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = filename or f"{media_id}{extension}"
        path = target_dir / safe_filename
        path.write_bytes(response.body)
        return WhatsAppMediaDownload(
            media_id=media_id,
            path=path.resolve(),
            mime_type=content_type,
            sha256=str(media_info.get("sha256") or "") or None,
        )

    def _send_message_payload(self, payload: dict[str, Any]) -> WhatsAppMessageSend:
        response_payload = self._request_json(
            "POST",
            self._phone_url("messages"),
            json_payload=payload,
        )
        messages = response_payload.get("messages")
        message_id = None
        if isinstance(messages, list) and messages:
            first_message = messages[0]
            if isinstance(first_message, dict):
                message_id = str(first_message.get("id") or "") or None
        return WhatsAppMessageSend(
            message_id=message_id,
            raw_payload=response_payload,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_payload: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        request_headers = self._auth_headers(headers)
        request_body = body
        if json_payload is not None:
            request_headers["Content-Type"] = "application/json"
            request_body = json.dumps(json_payload).encode("utf-8")
        response = self.transport.request(
            method,
            url,
            headers=request_headers,
            body=request_body,
        )
        self._raise_for_error(response)
        if not response.body:
            return {}
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WhatsAppClientError("Respuesta JSON invalida de WhatsApp.") from exc
        if not isinstance(payload, dict):
            raise WhatsAppClientError("Respuesta inesperada de WhatsApp.", response_payload=payload)
        return payload

    def _request_bytes(self, method: str, url: str) -> WhatsAppHttpResponse:
        response = self.transport.request(
            method,
            url,
            headers=self._auth_headers(),
        )
        self._raise_for_error(response)
        return response

    def _raise_for_error(self, response: WhatsAppHttpResponse) -> None:
        if response.status_code < 400:
            return
        payload: object
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except Exception:
            payload = response.body.decode("utf-8", errors="replace")
        raise WhatsAppClientError(
            "WhatsApp Cloud API rechazo la solicitud.",
            status_code=response.status_code,
            response_payload=payload,
        )

    def _auth_headers(self, headers: Mapping[str, str] | None = None) -> dict[str, str]:
        current = dict(headers or {})
        current["Authorization"] = f"Bearer {self.config.access_token}"
        return current

    def _phone_url(self, path: str) -> str:
        return self._graph_url(f"{self.config.phone_number_id}/{path}")

    def _graph_url(self, path: str) -> str:
        base = self.config.graph_base_url.rstrip("/")
        version = self.config.api_version.strip("/")
        suffix = str(path).strip("/")
        return f"{base}/{version}/{suffix}"


def _build_multipart_body(
    *,
    boundary: str,
    fields: Mapping[str, str],
    file_field: str,
    file_path: Path,
    file_mime_type: str,
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {file_mime_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def _header_lookup(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def verify_webhook_challenge(
    *,
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    expected_verify_token: str,
) -> str | None:
    """Valida el handshake GET del webhook de WhatsApp."""

    if mode != "subscribe":
        return None
    if not expected_verify_token or verify_token != expected_verify_token:
        return None
    return str(challenge or "")


__all__ = [
    "UrllibWhatsAppTransport",
    "WhatsAppCloudClient",
    "WhatsAppHttpTransport",
    "verify_webhook_challenge",
]
