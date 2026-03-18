BEGIN;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS academic_programs (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(name)) BETWEEN 3 AND 120)
);

CREATE TABLE IF NOT EXISTS students (
    id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    student_code VARCHAR(20) NOT NULL UNIQUE,
    age SMALLINT NOT NULL,
    institutional_email TEXT NOT NULL UNIQUE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ NULL,
    program_id BIGINT NULL REFERENCES academic_programs(id),
    supported_program BOOLEAN NOT NULL DEFAULT FALSE,
    semester SMALLINT NOT NULL,
    average_grade NUMERIC(5, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(full_name)) BETWEEN 2 AND 100),
    CHECK (student_code ~ '^[0-9]+$' AND char_length(student_code) BETWEEN 6 AND 20),
    CHECK (age BETWEEN 15 AND 60),
    CHECK (institutional_email = lower(institutional_email)),
    CHECK (position(' ' in institutional_email) = 0),
    CHECK (char_length(institutional_email) <= 320),
    CHECK (semester BETWEEN 1 AND 15),
    CHECK (average_grade >= 0 AND average_grade <= 100),
    CHECK (
        (email_verified = FALSE AND email_verified_at IS NULL)
        OR email_verified = TRUE
    )
);

CREATE TABLE IF NOT EXISTS email_verification_challenges (
    institutional_email TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0,
    max_attempts SMALLINT NOT NULL DEFAULT 5,
    resend_count SMALLINT NOT NULL DEFAULT 0,
    last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (institutional_email = lower(institutional_email)),
    CHECK (position(' ' in institutional_email) = 0),
    CHECK (char_length(institutional_email) <= 320),
    CHECK (attempts >= 0),
    CHECK (max_attempts BETWEEN 1 AND 10),
    CHECK (resend_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_students_program_id
    ON students (program_id);

CREATE INDEX IF NOT EXISTS idx_students_supported_program
    ON students (supported_program);

CREATE INDEX IF NOT EXISTS idx_email_verification_expires_at
    ON email_verification_challenges (expires_at);

DROP TRIGGER IF EXISTS trg_academic_programs_updated_at ON academic_programs;
CREATE TRIGGER trg_academic_programs_updated_at
BEFORE UPDATE ON academic_programs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_students_updated_at ON students;
CREATE TRIGGER trg_students_updated_at
BEFORE UPDATE ON students
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_email_verification_challenges_updated_at
    ON email_verification_challenges;
CREATE TRIGGER trg_email_verification_challenges_updated_at
BEFORE UPDATE ON email_verification_challenges
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

INSERT INTO academic_programs (code, name)
VALUES ('ISC', 'Ingenieria de Sistemas y Computacion')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    is_active = TRUE;

COMMIT;
