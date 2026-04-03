\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/backfill_study_planning_payload_metadata.sql

BEGIN;

\echo '== Backfill study_priority_profiles.result_payload =='
WITH updated AS (
    UPDATE study_priority_profiles
    SET result_payload = result_payload
        || jsonb_build_object(
            'persisted_profile_id', id,
            'version_number', version_number
        )
    WHERE COALESCE(result_payload ->> 'persisted_profile_id', '') <> id::text
       OR COALESCE(result_payload ->> 'version_number', '') <> version_number::text
    RETURNING id
)
SELECT COUNT(*) AS updated_priority_profiles
FROM updated;

\echo ''
\echo '== Backfill study_plan_profiles.result_payload =='
WITH updated AS (
    UPDATE study_plan_profiles
    SET result_payload = result_payload
        || jsonb_build_object(
            'persisted_profile_id', id,
            'version_number', version_number
        )
    WHERE COALESCE(result_payload ->> 'persisted_profile_id', '') <> id::text
       OR COALESCE(result_payload ->> 'version_number', '') <> version_number::text
    RETURNING id
)
SELECT COUNT(*) AS updated_study_plan_profiles
FROM updated;

COMMIT;
