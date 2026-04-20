BEGIN;

CREATE TABLE IF NOT EXISTS academic_activities (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    activity_uid TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    activity_title TEXT NULL,
    due_date DATE NULL,
    due_time TIME NULL,
    estimated_effort_minutes INTEGER NULL,
    priority_level TEXT NULL,
    difficulty_level SMALLINT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(activity_uid)) BETWEEN 8 AND 80),
    CHECK (char_length(trim(subject_name)) BETWEEN 1 AND 120),
    CHECK (
        activity_type IN (
            'parcial',
            'quiz',
            'tarea',
            'taller',
            'entrega',
            'exposicion',
            'proyecto',
            'estudio_pendiente'
        )
    ),
    CHECK (activity_title IS NULL OR char_length(trim(activity_title)) BETWEEN 1 AND 180),
    CHECK (estimated_effort_minutes IS NULL OR estimated_effort_minutes > 0),
    CHECK (priority_level IS NULL OR priority_level IN ('alta', 'media', 'baja')),
    CHECK (difficulty_level IS NULL OR difficulty_level BETWEEN 1 AND 5),
    CHECK (status IN ('pending', 'completed', 'deleted')),
    UNIQUE (student_id, activity_uid)
);

CREATE INDEX IF NOT EXISTS idx_academic_activities_student_due
    ON academic_activities (student_id, due_date, due_time)
    WHERE status <> 'deleted';

CREATE INDEX IF NOT EXISTS idx_academic_activities_student_subject
    ON academic_activities (student_id, lower(subject_name))
    WHERE status <> 'deleted';

DROP TRIGGER IF EXISTS trg_academic_activities_updated_at ON academic_activities;
CREATE TRIGGER trg_academic_activities_updated_at
BEFORE UPDATE ON academic_activities
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOR target_role IN
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_schema = current_schema()
          AND table_name IN ('study_priority_profiles', 'study_plan_profiles')
          AND privilege_type = 'INSERT'
          AND grantee <> 'PUBLIC'
    LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE academic_activities TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON SEQUENCE academic_activities_id_seq TO %I',
            target_role
        );
    END LOOP;
END $$;

COMMIT;
