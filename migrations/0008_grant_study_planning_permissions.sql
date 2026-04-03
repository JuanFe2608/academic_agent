BEGIN;

DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOR target_role IN
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_schema = current_schema()
          AND table_name IN ('study_personalization_profiles', 'schedule_profiles')
          AND privilege_type = 'INSERT'
          AND grantee <> 'PUBLIC'
    LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE study_priority_profiles, study_priority_subjects, study_plan_profiles, study_plan_events TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON SEQUENCE study_priority_profiles_id_seq, study_priority_subjects_id_seq, study_plan_profiles_id_seq, study_plan_events_id_seq TO %I',
            target_role
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
            current_schema(),
            target_role
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I',
            current_schema(),
            target_role
        );
    END LOOP;
END $$;

COMMIT;
