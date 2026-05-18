"""Tests de validacion de firma HMAC-SHA256 del webhook de WhatsApp."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper directo
# ---------------------------------------------------------------------------

from api.app import _verify_whatsapp_signature


class TestVerifyWhatsappSignature:
    def _sign(self, body: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_firma_valida(self) -> None:
        body = b'{"object":"whatsapp_business_account"}'
        secret = "mi_secreto"
        header = self._sign(body, secret)
        assert _verify_whatsapp_signature(body, header, secret) is True

    def test_secreto_incorrecto(self) -> None:
        body = b'{"object":"whatsapp_business_account"}'
        header = self._sign(body, "secreto_correcto")
        assert _verify_whatsapp_signature(body, header, "secreto_equivocado") is False

    def test_cuerpo_alterado(self) -> None:
        original = b'{"object":"whatsapp_business_account"}'
        secret = "mi_secreto"
        header = self._sign(original, secret)
        tampered = b'{"object":"whatsapp_business_account","extra":true}'
        assert _verify_whatsapp_signature(tampered, header, secret) is False

    def test_header_sin_prefijo_sha256(self) -> None:
        body = b'{"object":"whatsapp_business_account"}'
        secret = "mi_secreto"
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        assert _verify_whatsapp_signature(body, digest, secret) is False

    def test_header_vacio(self) -> None:
        body = b'{"object":"whatsapp_business_account"}'
        assert _verify_whatsapp_signature(body, "", "mi_secreto") is False

    def test_body_vacio_firma_valida(self) -> None:
        body = b""
        secret = "mi_secreto"
        header = self._sign(body, secret)
        assert _verify_whatsapp_signature(body, header, secret) is True


# ---------------------------------------------------------------------------
# Endpoint POST /webhook
# ---------------------------------------------------------------------------


def _make_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Crea un TestClient con _runner simulado para no necesitar DB."""
    import api.app as app_module

    monkeypatch.setattr(app_module, "_runner", None)
    return TestClient(app_module.app, raise_server_exceptions=True)


def _signed_headers(body: bytes, secret: str) -> dict[str, str]:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}", "Content-Type": "application/json"}


_PAYLOAD = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
_SECRET = "test_app_secret"


class TestWebhookEndpoint:
    def test_firma_valida_retorna_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", _SECRET)
        client = _make_client(monkeypatch)
        headers = _signed_headers(_PAYLOAD, _SECRET)
        response = client.post("/webhook", content=_PAYLOAD, headers=headers)
        assert response.status_code == 200

    def test_firma_invalida_retorna_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", _SECRET)
        client = _make_client(monkeypatch)
        bad_headers = {
            "X-Hub-Signature-256": "sha256=aaaabbbbcccc",
            "Content-Type": "application/json",
        }
        response = client.post("/webhook", content=_PAYLOAD, headers=bad_headers)
        assert response.status_code == 403

    def test_header_ausente_con_secret_retorna_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", _SECRET)
        client = _make_client(monkeypatch)
        response = client.post(
            "/webhook",
            content=_PAYLOAD,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403

    def test_sin_secret_configurado_retorna_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
        client = _make_client(monkeypatch)
        response = client.post(
            "/webhook",
            content=_PAYLOAD,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 503

    def test_payload_invalido_con_firma_valida_retorna_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", _SECRET)
        client = _make_client(monkeypatch)
        invalid_json = b"no es json"
        headers = _signed_headers(invalid_json, _SECRET)
        response = client.post("/webhook", content=invalid_json, headers=headers)
        # Payload invalido: la firma pasa pero JSON falla → 200 para no reintentar
        assert response.status_code == 200

    def test_firma_valida_secreto_distinto_retorna_403(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", _SECRET)
        client = _make_client(monkeypatch)
        # Firmado con un secreto diferente al configurado
        headers = _signed_headers(_PAYLOAD, "otro_secreto")
        response = client.post("/webhook", content=_PAYLOAD, headers=headers)
        assert response.status_code == 403
