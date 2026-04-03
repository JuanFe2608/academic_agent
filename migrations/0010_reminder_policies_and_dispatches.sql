BEGIN;

CREATE TABLE IF NOT EXISTS reminder_policies (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    reminder_type TEXT NOT NULL,
    lead_minutes INTEGER NOT NULL,
    followup_minutes INTEGER NULL,
    quiet_hours JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (channel IN ('in_app', 'email', 'whatsapp')),
    CHECK (reminder_type IN ('pre_session', 'followup', 'missed_session')),
    CHECK (lead_minutes >= 0),
    CHECK (followup_minutes IS NULL OR followup_minutes >= 0),
    CHECK (char_length(trim(timezone)) BETWEEN 3 AND 80),
    CHECK (jsonb_typeof(quiet_hours) = 'object'),
    CHECK (jsonb_typeof(metadata_json) = 'object'),
    UNIQUE (id, student_id),
    UNIQUE (id, student_id, channel),
    UNIQUE (student_id, channel, reminder_type, lead_minutes)
);

CREATE TABLE IF NOT EXISTS reminder_dispatches (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    reminder_policy_id BIGINT NULL,
    study_plan_event_instance_id BIGINT NULL,
    dispatch_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    leased_at TIMESTAMPTZ NULL,
    sent_at TIMESTAMPTZ NULL,
    acknowledged_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    provider_message_id TEXT NULL,
    failure_reason TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(dispatch_type)) BETWEEN 2 AND 80),
    CHECK (channel IN ('in_app', 'email', 'whatsapp')),
    CHECK (status IN ('pending', 'leased', 'sent', 'failed', 'canceled', 'acknowledged', 'expired')),
    CHECK (reminder_policy_id IS NOT NULL OR study_plan_event_instance_id IS NOT NULL),
    CHECK (leased_at IS NULL OR status IN ('leased', 'sent', 'failed', 'canceled', 'acknowledged', 'expired')),
    CHECK (sent_at IS NULL OR status IN ('sent', 'acknowledged')),
    CHECK (acknowledged_at IS NULL OR status = 'acknowledged'),
    CHECK (status <> 'leased' OR leased_at IS NOT NULL),
    CHECK (status <> 'sent' OR sent_at IS NOT NULL),
    CHECK (status <> 'acknowledged' OR acknowledged_at IS NOT NULL),
    CHECK (status <> 'failed' OR failure_reason IS NOT NULL),
    CHECK (acknowledged_at IS NULL OR sent_at IS NOT NULL),
    CHECK (leased_at IS NULL OR sent_at IS NULL OR leased_at <= sent_at),
    CHECK (sent_at IS NULL OR acknowledged_at IS NULL OR sent_at <= acknowledged_at),
    CHECK (provider_message_id IS NULL OR char_length(trim(provider_message_id)) BETWEEN 1 AND 160),
    CHECK (failure_reason IS NULL OR char_length(trim(failure_reason)) BETWEEN 1 AND 500),
    CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_reminder_dispatches_policy_student
        FOREIGN KEY (reminder_policy_id, student_id, channel)
        REFERENCES reminder_policies(id, student_id, channel),
    CONSTRAINT fk_reminder_dispatches_instance_student
        FOREIGN KEY (study_plan_event_instance_id, student_id)
        REFERENCES study_plan_event_instances(id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_reminder_policies_student_enabled
    ON reminder_policies (student_id, enabled);

CREATE INDEX IF NOT EXISTS idx_reminder_dispatches_status_scheduled_for
    ON reminder_dispatches (status, scheduled_for);

CREATE INDEX IF NOT EXISTS idx_reminder_dispatches_instance
    ON reminder_dispatches (study_plan_event_instance_id);

CREATE INDEX IF NOT EXISTS idx_reminder_dispatches_student_created_at
    ON reminder_dispatches (student_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reminder_dispatches_policy
    ON reminder_dispatches (reminder_policy_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reminder_dispatches_dedup
    ON reminder_dispatches (
        student_id,
        channel,
        COALESCE(reminder_policy_id, -1),
        COALESCE(study_plan_event_instance_id, -1),
        dispatch_type,
        scheduled_for
    );

DROP TRIGGER IF EXISTS trg_reminder_policies_updated_at ON reminder_policies;
CREATE TRIGGER trg_reminder_policies_updated_at
BEFORE UPDATE ON reminder_policies
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_reminder_dispatches_updated_at ON reminder_dispatches;
CREATE TRIGGER trg_reminder_dispatches_updated_at
BEFORE UPDATE ON reminder_dispatches
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
