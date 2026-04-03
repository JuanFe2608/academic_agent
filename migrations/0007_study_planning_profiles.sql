BEGIN;

CREATE TABLE IF NOT EXISTS study_priority_profiles (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    schedule_profile_id BIGINT NULL REFERENCES schedule_profiles(id) ON DELETE SET NULL,
    personalization_profile_id BIGINT NULL REFERENCES study_personalization_profiles(id) ON DELETE SET NULL,
    version_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    source TEXT NULL,
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (version_number >= 1),
    CHECK (status IN ('idle', 'collecting', 'completed', 'skipped', 'superseded')),
    CHECK (source IS NULL OR char_length(trim(source)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(prompt_version)) BETWEEN 1 AND 30),
    CHECK (jsonb_typeof(result_payload) = 'object'),
    UNIQUE (student_id, version_number)
);

CREATE TABLE IF NOT EXISTS study_priority_subjects (
    id BIGSERIAL PRIMARY KEY,
    priority_profile_id BIGINT NOT NULL REFERENCES study_priority_profiles(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL,
    subject_name TEXT NOT NULL,
    priority TEXT NOT NULL,
    difficulty SMALLINT NOT NULL,
    urgency TEXT NULL,
    weekly_load_min INTEGER NULL,
    origin TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (position >= 1),
    CHECK (char_length(trim(subject_name)) BETWEEN 1 AND 120),
    CHECK (priority IN ('alta', 'media', 'baja')),
    CHECK (difficulty BETWEEN 1 AND 5),
    CHECK (urgency IS NULL OR urgency IN ('alta', 'media', 'baja')),
    CHECK (weekly_load_min IS NULL OR weekly_load_min >= 0),
    CHECK (origin IS NULL OR char_length(trim(origin)) BETWEEN 2 AND 80),
    UNIQUE (priority_profile_id, position)
);

CREATE TABLE IF NOT EXISTS study_plan_profiles (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    schedule_profile_id BIGINT NULL REFERENCES schedule_profiles(id) ON DELETE SET NULL,
    personalization_profile_id BIGINT NULL REFERENCES study_personalization_profiles(id) ON DELETE SET NULL,
    priority_profile_id BIGINT NULL REFERENCES study_priority_profiles(id) ON DELETE SET NULL,
    version_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    planner_version TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (version_number >= 1),
    CHECK (char_length(trim(status)) BETWEEN 2 AND 50),
    CHECK (char_length(trim(planner_version)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(timezone)) BETWEEN 3 AND 80),
    CHECK (jsonb_typeof(rules) = 'object'),
    CHECK (jsonb_typeof(result_payload) = 'object'),
    UNIQUE (student_id, version_number)
);

CREATE TABLE IF NOT EXISTS study_plan_events (
    id BIGSERIAL PRIMARY KEY,
    study_plan_profile_id BIGINT NOT NULL REFERENCES study_plan_profiles(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL,
    source_event_id TEXT NOT NULL,
    day_label TEXT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    category TEXT NOT NULL,
    origin TEXT NOT NULL,
    priority TEXT NULL,
    difficulty SMALLINT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (position >= 1),
    CHECK (char_length(trim(source_event_id)) BETWEEN 2 AND 120),
    CHECK (day_label IN ('Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo')),
    CHECK (start_time < end_time),
    CHECK (char_length(trim(title)) BETWEEN 1 AND 160),
    CHECK (event_type IN ('confirmado', 'tentativo')),
    CHECK (category IN ('academico', 'laboral', 'extracurricular', 'estudio')),
    CHECK (char_length(trim(origin)) BETWEEN 2 AND 80),
    CHECK (priority IS NULL OR priority IN ('alta', 'media', 'baja')),
    CHECK (difficulty IS NULL OR difficulty BETWEEN 1 AND 5),
    CHECK (char_length(trim(timezone)) BETWEEN 3 AND 80),
    CHECK (jsonb_typeof(event_payload) = 'object'),
    UNIQUE (study_plan_profile_id, position)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_priority_profiles_current_student
    ON study_priority_profiles (student_id)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_study_priority_profiles_student_version
    ON study_priority_profiles (student_id, version_number DESC);

CREATE INDEX IF NOT EXISTS idx_study_priority_profiles_schedule
    ON study_priority_profiles (schedule_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_priority_profiles_personalization
    ON study_priority_profiles (personalization_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_priority_subjects_profile_position
    ON study_priority_subjects (priority_profile_id, position);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_plan_profiles_current_student
    ON study_plan_profiles (student_id)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_student_version
    ON study_plan_profiles (student_id, version_number DESC);

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_schedule
    ON study_plan_profiles (schedule_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_priority_profile
    ON study_plan_profiles (priority_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_plan_events_profile_position
    ON study_plan_events (study_plan_profile_id, position);

DROP TRIGGER IF EXISTS trg_study_priority_profiles_updated_at ON study_priority_profiles;
CREATE TRIGGER trg_study_priority_profiles_updated_at
BEFORE UPDATE ON study_priority_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_study_plan_profiles_updated_at ON study_plan_profiles;
CREATE TRIGGER trg_study_plan_profiles_updated_at
BEFORE UPDATE ON study_plan_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
