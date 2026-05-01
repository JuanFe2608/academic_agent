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
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE microsoft_graph_connections, outlook_calendar_event_links, microsoft_todo_task_links TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON SEQUENCE microsoft_graph_connections_id_seq, outlook_calendar_event_links_id_seq, microsoft_todo_task_links_id_seq TO %I',
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
