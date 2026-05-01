BEGIN;

-- Deduplicación durable de mensajes entrantes de WhatsApp.
--
-- Meta puede reintentar un webhook hasta 72 horas después del envío original.
-- Esta tabla persiste los message_id ya procesados para que cualquier réplica
-- rechace el reintento sin volver a ejecutar el agente.
--
-- La operación central es:
--   INSERT INTO processed_webhook_messages (message_id)
--   VALUES ($1)
--   ON CONFLICT (message_id) DO NOTHING
-- Si rowcount = 0 → duplicado. Si rowcount = 1 → nuevo.

CREATE TABLE IF NOT EXISTS processed_webhook_messages (
    message_id   TEXT        NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_processed_webhook_messages PRIMARY KEY (message_id)
);

-- Índice para limpiezas periódicas por antigüedad (TTL 72 h).
CREATE INDEX IF NOT EXISTS idx_pwm_processed_at
    ON processed_webhook_messages (processed_at);

-- Comentario: el mantenimiento (DELETE WHERE processed_at < now() - interval '72 hours')
-- puede ejecutarse desde un Container Apps Job o un script periódico.
-- No es necesario para la corrección, solo para controlar el tamaño de la tabla.

COMMIT;
