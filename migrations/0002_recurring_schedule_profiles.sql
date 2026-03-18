BEGIN;

CREATE TABLE IF NOT EXISTS schedule_profiles (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    occupation TEXT NOT NULL,
    base_timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    summary_text TEXT NULL,
    has_conflicts BOOLEAN NOT NULL DEFAULT FALSE,
    conflicts_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT TRUE,
    confirmed_at TIMESTAMPTZ NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (occupation IN ('solo_estudio', 'ambos', 'ninguna')),
    CHECK (char_length(base_timezone) BETWEEN 3 AND 80),
    UNIQUE (student_id, version_number)
);

CREATE TABLE IF NOT EXISTS recurring_schedule_blocks (
    id BIGSERIAL PRIMARY KEY,
    schedule_profile_id BIGINT NOT NULL REFERENCES schedule_profiles(id) ON DELETE CASCADE,
    source_block_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    title TEXT NOT NULL,
    day_of_week TEXT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'weekly',
    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    source_text TEXT NOT NULL,
    normalized_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence NUMERIC(4, 3) NULL,
    ambiguity_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    needs_clarification BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT TRUE,
    has_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    conflict_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    external_provider TEXT NULL,
    external_series_id TEXT NULL,
    external_event_id TEXT NULL,
    external_sync_status TEXT NULL,
    external_sync_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (block_type IN ('academic', 'work', 'extracurricular')),
    CHECK (day_of_week IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')),
    CHECK (frequency = 'weekly'),
    CHECK (start_time < end_time),
    CHECK (char_length(trim(title)) BETWEEN 1 AND 120),
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CHECK (external_provider IS NULL OR external_provider IN ('outlook', 'google'))
);

CREATE TABLE IF NOT EXISTS schedule_conflicts (
    id BIGSERIAL PRIMARY KEY,
    schedule_profile_id BIGINT NOT NULL REFERENCES schedule_profiles(id) ON DELETE CASCADE,
    left_block_id BIGINT NOT NULL REFERENCES recurring_schedule_blocks(id) ON DELETE CASCADE,
    right_block_id BIGINT NOT NULL REFERENCES recurring_schedule_blocks(id) ON DELETE CASCADE,
    day_of_week TEXT NOT NULL,
    overlap_start TIME NOT NULL,
    overlap_end TIME NOT NULL,
    user_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (day_of_week IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')),
    CHECK (left_block_id <> right_block_id),
    CHECK (overlap_start < overlap_end)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_profiles_current_student
    ON schedule_profiles (student_id)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_schedule_profiles_student_version
    ON schedule_profiles (student_id, version_number DESC);

CREATE INDEX IF NOT EXISTS idx_recurring_schedule_blocks_profile_day_time
    ON recurring_schedule_blocks (schedule_profile_id, day_of_week, start_time);

CREATE INDEX IF NOT EXISTS idx_recurring_schedule_blocks_type
    ON recurring_schedule_blocks (block_type);

CREATE INDEX IF NOT EXISTS idx_schedule_conflicts_profile
    ON schedule_conflicts (schedule_profile_id);

DROP TRIGGER IF EXISTS trg_schedule_profiles_updated_at ON schedule_profiles;
CREATE TRIGGER trg_schedule_profiles_updated_at
BEFORE UPDATE ON schedule_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_recurring_schedule_blocks_updated_at ON recurring_schedule_blocks;
CREATE TRIGGER trg_recurring_schedule_blocks_updated_at
BEFORE UPDATE ON recurring_schedule_blocks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
