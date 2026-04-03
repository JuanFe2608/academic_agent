BEGIN;

ALTER TABLE study_plan_profiles
    ADD COLUMN IF NOT EXISTS origin_type TEXT NOT NULL DEFAULT 'initial',
    ADD COLUMN IF NOT EXISTS supersedes_study_plan_profile_id BIGINT NULL REFERENCES study_plan_profiles(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_plan_profiles_origin_type'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT chk_study_plan_profiles_origin_type
            CHECK (origin_type IN ('initial', 'replan', 'manual_adjustment', 'system_refresh'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_plan_profiles_supersedes_self'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT chk_study_plan_profiles_supersedes_self
            CHECK (
                supersedes_study_plan_profile_id IS NULL
                OR supersedes_study_plan_profile_id <> id
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_study_plan_profiles_id_student'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT uq_study_plan_profiles_id_student
            UNIQUE (id, student_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_study_plan_events_id_profile'
          AND conrelid = 'study_plan_events'::regclass
    ) THEN
        ALTER TABLE study_plan_events
            ADD CONSTRAINT uq_study_plan_events_id_profile
            UNIQUE (id, study_plan_profile_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_origin_type
    ON study_plan_profiles (origin_type);

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_supersedes
    ON study_plan_profiles (supersedes_study_plan_profile_id);

CREATE TABLE IF NOT EXISTS study_plan_event_instances (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    study_plan_profile_id BIGINT NOT NULL,
    study_plan_event_id BIGINT NULL,
    source_instance_key TEXT NOT NULL,
    planned_date DATE NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
    status TEXT NOT NULL DEFAULT 'scheduled',
    source TEXT NOT NULL DEFAULT 'materialized_plan',
    completion_pct SMALLINT NULL,
    completed_at TIMESTAMPTZ NULL,
    instance_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(source_instance_key)) BETWEEN 3 AND 160),
    CHECK (starts_at < ends_at),
    CHECK (planned_date = (starts_at AT TIME ZONE timezone)::date),
    CHECK (char_length(trim(timezone)) BETWEEN 3 AND 80),
    CHECK (status IN ('scheduled', 'in_progress', 'completed', 'skipped', 'missed', 'canceled', 'superseded')),
    CHECK (source IN ('materialized_plan', 'replan', 'manual_adjustment')),
    CHECK (completion_pct IS NULL OR completion_pct BETWEEN 0 AND 100),
    CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    ),
    CHECK (completed_at IS NULL OR completed_at >= starts_at),
    CHECK (status <> 'completed' OR completion_pct IS NOT NULL),
    CHECK (jsonb_typeof(instance_payload) = 'object'),
    UNIQUE (source_instance_key),
    UNIQUE (id, student_id),
    CONSTRAINT fk_study_plan_event_instances_profile_student
        FOREIGN KEY (study_plan_profile_id, student_id)
        REFERENCES study_plan_profiles(id, student_id),
    CONSTRAINT fk_study_plan_event_instances_event_profile
        FOREIGN KEY (study_plan_event_id, study_plan_profile_id)
        REFERENCES study_plan_events(id, study_plan_profile_id)
);

CREATE TABLE IF NOT EXISTS study_session_checkins (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    study_plan_event_instance_id BIGINT NOT NULL,
    checkin_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actual_start_at TIMESTAMPTZ NULL,
    actual_end_at TIMESTAMPTZ NULL,
    completion_pct SMALLINT NULL,
    comprehension_score SMALLINT NULL,
    energy_score SMALLINT NULL,
    notes TEXT NULL,
    checkin_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (checkin_type IN ('start', 'complete', 'skip', 'missed_confirmation', 'feedback')),
    CHECK (actor_type IN ('student', 'agent', 'system')),
    CHECK (actual_start_at IS NULL OR actual_end_at IS NULL OR actual_start_at <= actual_end_at),
    CHECK (actual_end_at IS NULL OR actual_start_at IS NOT NULL),
    CHECK (completion_pct IS NULL OR completion_pct BETWEEN 0 AND 100),
    CHECK (comprehension_score IS NULL OR comprehension_score BETWEEN 1 AND 5),
    CHECK (energy_score IS NULL OR energy_score BETWEEN 1 AND 5),
    CHECK (checkin_type <> 'start' OR actual_start_at IS NOT NULL),
    CHECK (checkin_type <> 'complete' OR completion_pct IS NOT NULL),
    CHECK (notes IS NULL OR char_length(trim(notes)) BETWEEN 1 AND 1000),
    CHECK (jsonb_typeof(checkin_payload) = 'object'),
    CONSTRAINT fk_study_session_checkins_instance_student
        FOREIGN KEY (study_plan_event_instance_id, student_id)
        REFERENCES study_plan_event_instances(id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_study_plan_event_instances_student_date
    ON study_plan_event_instances (student_id, planned_date);

CREATE INDEX IF NOT EXISTS idx_study_plan_event_instances_status_starts_at
    ON study_plan_event_instances (status, starts_at);

CREATE INDEX IF NOT EXISTS idx_study_plan_event_instances_profile
    ON study_plan_event_instances (study_plan_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_plan_event_instances_event
    ON study_plan_event_instances (study_plan_event_id);

CREATE INDEX IF NOT EXISTS idx_study_session_checkins_instance_reported_at
    ON study_session_checkins (study_plan_event_instance_id, reported_at DESC);

CREATE INDEX IF NOT EXISTS idx_study_session_checkins_student_reported_at
    ON study_session_checkins (student_id, reported_at DESC);

DROP TRIGGER IF EXISTS trg_study_plan_event_instances_updated_at ON study_plan_event_instances;
CREATE TRIGGER trg_study_plan_event_instances_updated_at
BEFORE UPDATE ON study_plan_event_instances
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
