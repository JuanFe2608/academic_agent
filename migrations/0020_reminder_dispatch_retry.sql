BEGIN;

ALTER TABLE reminder_dispatches
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NULL;

ALTER TABLE reminder_dispatches
    DROP CONSTRAINT IF EXISTS reminder_dispatches_status_check;

ALTER TABLE reminder_dispatches
    ADD CONSTRAINT reminder_dispatches_status_check
    CHECK (status IN (
        'pending',
        'leased',
        'sent',
        'failed',
        'retryable',
        'canceled',
        'acknowledged',
        'expired'
    ));

ALTER TABLE reminder_dispatches
    DROP CONSTRAINT IF EXISTS reminder_dispatches_attempt_count_check;

ALTER TABLE reminder_dispatches
    ADD CONSTRAINT reminder_dispatches_attempt_count_check
    CHECK (attempt_count >= 0);

ALTER TABLE reminder_dispatches
    DROP CONSTRAINT IF EXISTS reminder_dispatches_next_attempt_status_check;

ALTER TABLE reminder_dispatches
    ADD CONSTRAINT reminder_dispatches_next_attempt_status_check
    CHECK (next_attempt_at IS NULL OR status = 'retryable');

CREATE INDEX IF NOT EXISTS idx_reminder_dispatches_retryable_next_attempt
    ON reminder_dispatches (status, next_attempt_at)
    WHERE status = 'retryable';

COMMIT;
