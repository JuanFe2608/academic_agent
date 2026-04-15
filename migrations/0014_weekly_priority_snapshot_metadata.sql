ALTER TABLE study_priority_profiles
    ADD COLUMN IF NOT EXISTS week_start DATE NULL,
    ADD COLUMN IF NOT EXISTS week_end DATE NULL,
    ADD COLUMN IF NOT EXISTS snapshot_kind TEXT NOT NULL DEFAULT 'weekly',
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS update_reason TEXT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_profiles_week_bounds'
    ) THEN
        ALTER TABLE study_priority_profiles
            ADD CONSTRAINT ck_study_priority_profiles_week_bounds
            CHECK (week_start IS NULL OR week_end IS NULL OR week_start <= week_end);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_profiles_snapshot_kind'
    ) THEN
        ALTER TABLE study_priority_profiles
            ADD CONSTRAINT ck_study_priority_profiles_snapshot_kind
            CHECK (snapshot_kind IN ('weekly', 'event_update', 'legacy', 'schedule_base'));
    END IF;
END $$;

ALTER TABLE study_priority_subjects
    ADD COLUMN IF NOT EXISTS importance_rank_selected_by_student SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS perceived_difficulty SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS urgency_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS urgency_due_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS computed_priority_score NUMERIC(6,3) NULL,
    ADD COLUMN IF NOT EXISTS priority_source TEXT NULL,
    ADD COLUMN IF NOT EXISTS is_priority_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS updated_from_flow_at TIMESTAMPTZ NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_subjects_importance_rank'
    ) THEN
        ALTER TABLE study_priority_subjects
            ADD CONSTRAINT ck_study_priority_subjects_importance_rank
            CHECK (
                importance_rank_selected_by_student IS NULL
                OR importance_rank_selected_by_student BETWEEN 1 AND 3
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_subjects_perceived_difficulty'
    ) THEN
        ALTER TABLE study_priority_subjects
            ADD CONSTRAINT ck_study_priority_subjects_perceived_difficulty
            CHECK (perceived_difficulty IS NULL OR perceived_difficulty BETWEEN 1 AND 5);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_subjects_urgency_type'
    ) THEN
        ALTER TABLE study_priority_subjects
            ADD CONSTRAINT ck_study_priority_subjects_urgency_type
            CHECK (
                urgency_type IS NULL
                OR urgency_type IN ('quiz', 'parcial', 'entrega', 'exposicion', 'actividad')
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_study_priority_subjects_computed_score'
    ) THEN
        ALTER TABLE study_priority_subjects
            ADD CONSTRAINT ck_study_priority_subjects_computed_score
            CHECK (
                computed_priority_score IS NULL
                OR computed_priority_score BETWEEN 0 AND 1
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_study_priority_profiles_student_week
    ON study_priority_profiles (student_id, week_start DESC, week_end DESC)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_study_priority_subjects_urgency_due_at
    ON study_priority_subjects (urgency_due_at)
    WHERE urgency_due_at IS NOT NULL;
