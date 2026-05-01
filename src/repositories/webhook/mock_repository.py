"""Implementación in-memory del repositorio de deduplicación (para tests)."""

from __future__ import annotations

from datetime import datetime, timezone


class InMemoryWebhookMessageRepository:
    """Deduplicación en memoria para tests unitarios.

    No es thread-safe intencionalmente: los tests son de un solo hilo.
    """

    def __init__(self) -> None:
        self._seen: dict[str, datetime] = {}

    def is_duplicate_and_register(self, message_id: str) -> bool:
        if message_id in self._seen:
            return True
        self._seen[message_id] = datetime.now(tz=timezone.utc)
        return False

    def cleanup_expired(self, max_age_hours: int = 72) -> int:
        from datetime import timedelta

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)
        expired = [mid for mid, ts in self._seen.items() if ts < cutoff]
        for mid in expired:
            del self._seen[mid]
        return len(expired)

    # ------------------------------------------------------------------
    # Helpers de inspección exclusivos para tests
    # ------------------------------------------------------------------

    def registered_ids(self) -> set[str]:
        return set(self._seen.keys())
