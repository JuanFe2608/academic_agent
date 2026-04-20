BEGIN;

ALTER TABLE students
    ALTER COLUMN semester DROP NOT NULL,
    ALTER COLUMN average_grade DROP NOT NULL;

CREATE TABLE IF NOT EXISTS microsoft_oauth_pending_states (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    institutional_email TEXT NULL,
    state_token TEXT NOT NULL UNIQUE,
    scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    authorization_url TEXT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(state_token)) BETWEEN 32 AND 300),
    CHECK (institutional_email IS NULL OR institutional_email = lower(institutional_email)),
    CHECK (institutional_email IS NULL OR position(' ' in institutional_email) = 0),
    CHECK (institutional_email IS NULL OR char_length(institutional_email) <= 320),
    CHECK (jsonb_typeof(scopes_json) = 'array'),
    CHECK (status IN ('pending', 'completed', 'failed')),
    CHECK (last_error IS NULL OR char_length(trim(last_error)) BETWEEN 1 AND 1000)
);

CREATE INDEX IF NOT EXISTS idx_microsoft_oauth_pending_student_status
    ON microsoft_oauth_pending_states (student_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_microsoft_oauth_pending_expires_at
    ON microsoft_oauth_pending_states (expires_at);

DROP TRIGGER IF EXISTS trg_microsoft_oauth_pending_states_updated_at
    ON microsoft_oauth_pending_states;
CREATE TRIGGER trg_microsoft_oauth_pending_states_updated_at
BEFORE UPDATE ON microsoft_oauth_pending_states
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
