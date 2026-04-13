BEGIN;

ALTER TABLE schedule_profiles
ADD COLUMN IF NOT EXISTS schedule_end_date DATE NULL;

COMMIT;
