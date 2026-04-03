BEGIN;

DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOR target_role IN
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_schema = current_schema()
          AND table_name IN ('study_plan_profiles', 'schedule_profiles')
          AND privilege_type = 'INSERT'
          AND grantee <> 'PUBLIC'
    LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE study_plan_event_instances, study_session_checkins, reminder_policies, reminder_dispatches, study_replan_requests, study_replan_proposals TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON SEQUENCE study_plan_event_instances_id_seq, study_session_checkins_id_seq, reminder_policies_id_seq, reminder_dispatches_id_seq, study_replan_requests_id_seq, study_replan_proposals_id_seq TO %I',
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
