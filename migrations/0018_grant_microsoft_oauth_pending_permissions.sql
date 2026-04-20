BEGIN;

DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOR target_role IN
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_schema = current_schema()
          AND table_name IN ('microsoft_graph_connections', 'students')
          AND privilege_type = 'INSERT'
          AND grantee <> 'PUBLIC'
    LOOP
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE microsoft_oauth_pending_states TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON SEQUENCE microsoft_oauth_pending_states_id_seq TO %I',
            target_role
        );
    END LOOP;
END $$;

COMMIT;
