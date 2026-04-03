\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_replan_requests.sql

\echo '== Conteo general de replanificacion =='
SELECT 'study_replan_requests' AS table_name, COUNT(*) AS total_rows FROM study_replan_requests
UNION ALL
SELECT 'study_replan_proposals', COUNT(*) FROM study_replan_proposals
ORDER BY table_name;

\echo ''
\echo '== Requests por estado =='
SELECT
    status,
    COUNT(*) AS total_requests,
    MIN(created_at) AS first_created_at,
    MAX(created_at) AS last_created_at
FROM study_replan_requests
GROUP BY status
ORDER BY status;

\echo ''
\echo '== Requests recientes con plan actual y fuente =='
SELECT
    rr.id AS replan_request_id,
    rr.student_id,
    s.full_name,
    rr.current_study_plan_profile_id,
    rr.source_study_plan_event_instance_id,
    rr.trigger_type,
    rr.status,
    rr.reason_text,
    rr.resolved_at,
    rr.created_at
FROM study_replan_requests AS rr
JOIN students AS s
    ON s.id = rr.student_id
ORDER BY rr.created_at DESC, rr.id DESC
LIMIT 100;

\echo ''
\echo '== Propuestas y plan resultante =='
SELECT
    rp.replan_request_id,
    rp.id AS proposal_id,
    rp.proposal_number,
    rp.status,
    rp.resulting_study_plan_profile_id,
    spp.version_number AS resulting_plan_version,
    spp.origin_type AS resulting_plan_origin_type,
    spp.supersedes_study_plan_profile_id
FROM study_replan_proposals AS rp
LEFT JOIN study_plan_profiles AS spp
    ON spp.id = rp.resulting_study_plan_profile_id
ORDER BY rp.replan_request_id, rp.proposal_number;
