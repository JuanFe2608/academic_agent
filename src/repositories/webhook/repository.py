"""Protocol del repositorio de deduplicación de mensajes webhook."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WebhookMessageRepository(Protocol):
    """Registra message_ids de WhatsApp para evitar procesamiento duplicado.

    La operación central es atómica: verifica y registra en un solo paso,
    garantizando que dos réplicas concurrentes no procesen el mismo mensaje.
    """

    def is_duplicate_and_register(self, message_id: str) -> bool:
        """Retorna True si el message_id ya fue procesado (duplicado).

        Si es nuevo, lo registra y retorna False.
        La operación es atómica: segura bajo concurrencia y múltiples réplicas.
        """
        ...

    def cleanup_expired(self, max_age_hours: int = 72) -> int:
        """Elimina registros más antiguos que max_age_hours.

        Retorna el número de filas eliminadas.
        Puede ejecutarse desde un job de mantenimiento periódico.
        """
        ...
