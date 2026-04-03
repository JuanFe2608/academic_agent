BEGIN;

CREATE TABLE IF NOT EXISTS study_replan_requests (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    current_study_plan_profile_id BIGINT NOT NULL,
    source_study_plan_event_instance_id BIGINT NULL,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL,
    reason_text TEXT NULL,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (trigger_type IN ('user_request', 'missed_session', 'schedule_change', 'calendar_conflict', 'overload', 'manual_review')),
    CHECK (status IN ('pending', 'processing', 'proposed', 'accepted', 'rejected', 'applied', 'failed', 'canceled')),
    CHECK (reason_text IS NULL OR char_length(trim(reason_text)) BETWEEN 1 AND 500),
    CHECK (jsonb_typeof(request_payload) = 'object'),
    CHECK (resolved_at IS NULL OR status IN ('accepted', 'rejected', 'applied', 'failed', 'canceled')),
    CHECK (status <> 'applied' OR resolved_at IS NOT NULL),
    CHECK (trigger_type <> 'missed_session' OR source_study_plan_event_instance_id IS NOT NULL),
    UNIQUE (id, student_id),
    CONSTRAINT fk_study_replan_requests_current_plan_student
        FOREIGN KEY (current_study_plan_profile_id, student_id)
        REFERENCES study_plan_profiles(id, student_id),
    CONSTRAINT fk_study_replan_requests_source_instance_student
        FOREIGN KEY (source_study_plan_event_instance_id, student_id)
        REFERENCES study_plan_event_instances(id, student_id)
);

ALTER TABLE study_plan_profiles
    ADD COLUMN IF NOT EXISTS replan_request_id BIGINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_study_plan_profiles_replan_request'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT fk_study_plan_profiles_replan_request
            FOREIGN KEY (replan_request_id, student_id)
            REFERENCES study_replan_requests(id, student_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_study_plan_profiles_id_replan_request'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT uq_study_plan_profiles_id_replan_request
            UNIQUE (id, replan_request_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_plan_profiles_replan_origin'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT chk_study_plan_profiles_replan_origin
            CHECK (
                (origin_type = 'replan' AND replan_request_id IS NOT NULL)
                OR (origin_type <> 'replan' AND replan_request_id IS NULL)
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_plan_profiles_replan_supersedes'
          AND conrelid = 'study_plan_profiles'::regclass
    ) THEN
        ALTER TABLE study_plan_profiles
            ADD CONSTRAINT chk_study_plan_profiles_replan_supersedes
            CHECK (
                origin_type <> 'replan'
                OR supersedes_study_plan_profile_id IS NOT NULL
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS study_replan_proposals (
    id BIGSERIAL PRIMARY KEY,
    replan_request_id BIGINT NOT NULL REFERENCES study_replan_requests(id) ON DELETE CASCADE,
    proposal_number SMALLINT NOT NULL,
    status TEXT NOT NULL,
    summary_text TEXT NULL,
    proposal_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    impact_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    resulting_study_plan_profile_id BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (proposal_number >= 1),
    CHECK (status IN ('generated', 'selected', 'discarded', 'applied')),
    CHECK (summary_text IS NULL OR char_length(trim(summary_text)) BETWEEN 1 AND 1000),
    CHECK (jsonb_typeof(proposal_payload) = 'object'),
    CHECK (jsonb_typeof(impact_payload) = 'object'),
    CHECK (
        (status = 'applied' AND resulting_study_plan_profile_id IS NOT NULL)
        OR (status <> 'applied' AND resulting_study_plan_profile_id IS NULL)
    ),
    CONSTRAINT fk_study_replan_proposals_resulting_plan_request
        FOREIGN KEY (resulting_study_plan_profile_id, replan_request_id)
        REFERENCES study_plan_profiles(id, replan_request_id),
    UNIQUE (replan_request_id, proposal_number)
);

CREATE INDEX IF NOT EXISTS idx_study_replan_requests_student_created_at
    ON study_replan_requests (student_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_study_replan_requests_status
    ON study_replan_requests (status);

CREATE INDEX IF NOT EXISTS idx_study_replan_requests_source_instance
    ON study_replan_requests (source_study_plan_event_instance_id);

CREATE INDEX IF NOT EXISTS idx_study_replan_requests_current_plan
    ON study_replan_requests (current_study_plan_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_replan_proposals_request_status
    ON study_replan_proposals (replan_request_id, status);

CREATE INDEX IF NOT EXISTS idx_study_replan_proposals_resulting_plan
    ON study_replan_proposals (resulting_study_plan_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_plan_profiles_replan_request
    ON study_plan_profiles (replan_request_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_plan_profiles_replan_request_unique
    ON study_plan_profiles (replan_request_id)
    WHERE replan_request_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_replan_proposals_one_selected_per_request
    ON study_replan_proposals (replan_request_id)
    WHERE status = 'selected';

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_replan_proposals_one_applied_per_request
    ON study_replan_proposals (replan_request_id)
    WHERE status = 'applied';

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_replan_proposals_unique_resulting_plan
    ON study_replan_proposals (resulting_study_plan_profile_id)
    WHERE resulting_study_plan_profile_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_study_replan_requests_updated_at ON study_replan_requests;
CREATE TRIGGER trg_study_replan_requests_updated_at
BEFORE UPDATE ON study_replan_requests
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_study_replan_proposals_updated_at ON study_replan_proposals;
CREATE TRIGGER trg_study_replan_proposals_updated_at
BEFORE UPDATE ON study_replan_proposals
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
