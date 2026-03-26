BEGIN;

CREATE TABLE IF NOT EXISTS study_personalization_profiles (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    schedule_profile_id BIGINT NULL REFERENCES schedule_profiles(id) ON DELETE SET NULL,
    version_number INTEGER NOT NULL,
    questionnaire_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    status TEXT NOT NULL,
    top_techniques JSONB NOT NULL DEFAULT '[]'::jsonb,
    weakness_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (version_number >= 1),
    CHECK (status IN ('completed', 'superseded')),
    CHECK (jsonb_typeof(top_techniques) = 'array'),
    CHECK (jsonb_typeof(weakness_tags) = 'array'),
    CHECK (jsonb_typeof(result_payload) = 'object'),
    UNIQUE (student_id, version_number)
);

CREATE TABLE IF NOT EXISTS study_personalization_answers (
    id BIGSERIAL PRIMARY KEY,
    personalization_profile_id BIGINT NOT NULL REFERENCES study_personalization_profiles(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    option_id TEXT NULL,
    answer_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(question_id)) BETWEEN 2 AND 50),
    CHECK (answer_value IS NOT NULL),
    UNIQUE (personalization_profile_id, question_id)
);

CREATE TABLE IF NOT EXISTS study_personalization_scores (
    id BIGSERIAL PRIMARY KEY,
    personalization_profile_id BIGINT NOT NULL REFERENCES study_personalization_profiles(id) ON DELETE CASCADE,
    technique_id TEXT NOT NULL,
    technique_name TEXT NOT NULL,
    score INTEGER NOT NULL,
    rank SMALLINT NOT NULL,
    rationale_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(technique_id)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(technique_name)) BETWEEN 2 AND 120),
    CHECK (score >= 0),
    CHECK (rank BETWEEN 1 AND 20),
    CHECK (jsonb_typeof(rationale_tags) = 'array'),
    UNIQUE (personalization_profile_id, technique_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_personalization_current_student
    ON study_personalization_profiles (student_id)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_study_personalization_student_version
    ON study_personalization_profiles (student_id, version_number DESC);

CREATE INDEX IF NOT EXISTS idx_study_personalization_schedule_profile
    ON study_personalization_profiles (schedule_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_personalization_answers_profile
    ON study_personalization_answers (personalization_profile_id);

CREATE INDEX IF NOT EXISTS idx_study_personalization_scores_profile_rank
    ON study_personalization_scores (personalization_profile_id, rank);

DROP TRIGGER IF EXISTS trg_study_personalization_profiles_updated_at
    ON study_personalization_profiles;
CREATE TRIGGER trg_study_personalization_profiles_updated_at
BEFORE UPDATE ON study_personalization_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
