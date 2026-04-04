"""Abstracciones para envio del codigo de verificacion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class EmailSender(Protocol):
    """Contrato minimo para enviar correos de verificacion."""

    def send_verification_code(
        self,
        institutional_email: str,
        verification_code: str,
        expires_at: datetime,
    ) -> bool: ...


class DisabledEmailSender:
    """Sender por defecto: deja el flujo preparado, pero no envia nada."""

    def send_verification_code(
        self,
        institutional_email: str,
        verification_code: str,
        expires_at: datetime,
    ) -> bool:
        _ = institutional_email
        _ = verification_code
        _ = expires_at
        return False


@dataclass
class InMemoryEmailSender:
    """Sender de pruebas que conserva el ultimo codigo enviado en memoria."""

    sent_messages: list[tuple[str, str, datetime]] = field(default_factory=list)

    def send_verification_code(
        self,
        institutional_email: str,
        verification_code: str,
        expires_at: datetime,
    ) -> bool:
        self.sent_messages.append((institutional_email, verification_code, expires_at))
        return True
