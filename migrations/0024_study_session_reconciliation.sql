-- Reconciliación de sesiones de estudio modificadas o eliminadas en Outlook Calendar.
CREATE TABLE IF NOT EXISTS study_session_reconciliation_pending (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    outlook_event_id TEXT NOT NULL,
    drift_kind TEXT NOT NULL CHECK (drift_kind IN ('moved', 'deleted')),
    session_title TEXT,
    original_start TIMESTAMPTZ,
    original_end TIMESTAMPTZ,
    new_start TIMESTAMPTZ,
    new_end TIMESTAMPTZ,
    notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution TEXT CHECK (resolution IN ('accepted', 'rejected')),
    UNIQUE(student_id, instance_id, drift_kind)
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_student_unresolved
    ON study_session_reconciliation_pending (student_id)
    WHERE resolved_at IS NULL;
