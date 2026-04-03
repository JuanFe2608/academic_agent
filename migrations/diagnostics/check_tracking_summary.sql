\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_tracking_summary.sql

\echo '== Resumen de seguimiento por estudiante =='
SELECT
    spi.student_id,
    s.full_name,
    COUNT(*) AS total_instances,
    COUNT(*) FILTER (WHERE spi.status = 'scheduled') AS scheduled_instances,
    COUNT(*) FILTER (WHERE spi.status = 'in_progress') AS in_progress_instances,
    COUNT(*) FILTER (WHERE spi.status = 'completed') AS completed_instances,
    COUNT(*) FILTER (WHERE spi.status = 'skipped') AS skipped_instances,
    COUNT(*) FILTER (WHERE spi.status = 'missed') AS missed_instances,
    COUNT(*) FILTER (WHERE spi.status = 'superseded') AS superseded_instances,
    AVG(spi.completion_pct) FILTER (WHERE spi.completion_pct IS NOT NULL) AS avg_completion_pct
FROM study_plan_event_instances AS spi
JOIN students AS s
    ON s.id = spi.student_id
GROUP BY spi.student_id, s.full_name
ORDER BY spi.student_id;

\echo ''
\echo '== Checkins por tipo y actor =='
SELECT
    checkin_type,
    actor_type,
    COUNT(*) AS total_checkins,
    MIN(reported_at) AS first_reported_at,
    MAX(reported_at) AS last_reported_at
FROM study_session_checkins
GROUP BY checkin_type, actor_type
ORDER BY checkin_type, actor_type;

\echo ''
\echo '== Instancias completadas sin checkin complete =='
SELECT
    spi.id AS instance_id,
    spi.student_id,
    s.full_name,
    spi.completed_at,
    spi.completion_pct
FROM study_plan_event_instances AS spi
JOIN students AS s
    ON s.id = spi.student_id
WHERE spi.status = 'completed'
  AND NOT EXISTS (
      SELECT 1
      FROM study_session_checkins AS ssc
      WHERE ssc.study_plan_event_instance_id = spi.id
        AND ssc.checkin_type = 'complete'
  )
ORDER BY spi.student_id, spi.id;
