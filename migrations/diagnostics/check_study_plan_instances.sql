\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_study_plan_instances.sql

\echo '== Conteo general de instancias y checkins =='
SELECT 'study_plan_profiles' AS table_name, COUNT(*) AS total_rows FROM study_plan_profiles
UNION ALL
SELECT 'study_plan_event_instances', COUNT(*) FROM study_plan_event_instances
UNION ALL
SELECT 'study_session_checkins', COUNT(*) FROM study_session_checkins
ORDER BY table_name;

\echo ''
\echo '== Instancias por estado =='
SELECT
    status,
    COUNT(*) AS total_instances,
    MIN(planned_date) AS first_date,
    MAX(planned_date) AS last_date
FROM study_plan_event_instances
GROUP BY status
ORDER BY status;

\echo ''
\echo '== Proximas instancias por estudiante =='
SELECT
    spi.student_id,
    s.full_name,
    spi.id AS instance_id,
    spi.study_plan_profile_id,
    spi.study_plan_event_id,
    spi.planned_date,
    spi.starts_at,
    spi.ends_at,
    spi.status,
    spi.source,
    spi.completion_pct
FROM study_plan_event_instances AS spi
JOIN students AS s
    ON s.id = spi.student_id
WHERE spi.planned_date >= CURRENT_DATE
ORDER BY spi.student_id, spi.starts_at
LIMIT 100;

\echo ''
\echo '== Ultimo checkin por instancia =='
SELECT DISTINCT ON (ssc.study_plan_event_instance_id)
    ssc.study_plan_event_instance_id,
    ssc.student_id,
    s.full_name,
    ssc.checkin_type,
    ssc.actor_type,
    ssc.reported_at,
    ssc.completion_pct,
    ssc.comprehension_score,
    ssc.energy_score
FROM study_session_checkins AS ssc
JOIN students AS s
    ON s.id = ssc.student_id
ORDER BY ssc.study_plan_event_instance_id, ssc.reported_at DESC, ssc.id DESC;
