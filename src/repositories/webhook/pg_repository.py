"""Implementación PostgreSQL del repositorio de deduplicación de webhooks."""

from __future__ import annotations

from repositories.common import postgres_connection, require_database_url


class PostgresWebhookMessageRepository:
    """Deduplicación de message_ids respaldada en PostgreSQL.

    Usa INSERT ... ON CONFLICT DO NOTHING como operación atómica.
    rowcount == 0 → conflicto → mensaje ya procesado (duplicado).
    rowcount == 1 → fila insertada → mensaje nuevo.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = require_database_url(database_url)

    def is_duplicate_and_register(self, message_id: str) -> bool:
        with postgres_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO processed_webhook_messages (message_id)
                    VALUES (%s)
                    ON CONFLICT (message_id) DO NOTHING
                    """,
                    (message_id,),
                )
                return cur.rowcount == 0

    def cleanup_expired(self, max_age_hours: int = 72) -> int:
        with postgres_connection(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM processed_webhook_messages
                    WHERE processed_at < now() - make_interval(hours => %s)
                    """,
                    (max_age_hours,),
                )
                return cur.rowcount
