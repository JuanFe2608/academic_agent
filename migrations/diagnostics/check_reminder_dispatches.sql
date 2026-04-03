\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_reminder_dispatches.sql

\echo '== Conteo general de politicas y despachos =='
SELECT 'reminder_policies' AS table_name, COUNT(*) AS total_rows FROM reminder_policies
UNION ALL
SELECT 'reminder_dispatches', COUNT(*) FROM reminder_dispatches
ORDER BY table_name;

\echo ''
\echo '== Politicas activas por estudiante =='
SELECT
    rp.student_id,
    s.full_name,
    rp.channel,
    rp.reminder_type,
    rp.lead_minutes,
    rp.followup_minutes,
    rp.enabled,
    rp.timezone,
    rp.updated_at
FROM reminder_policies AS rp
JOIN students AS s
    ON s.id = rp.student_id
WHERE rp.enabled = TRUE
ORDER BY rp.student_id, rp.channel, rp.reminder_type, rp.lead_minutes;

\echo ''
\echo '== Despachos por estado y canal =='
SELECT
    status,
    channel,
    COUNT(*) AS total_dispatches,
    MIN(scheduled_for) AS first_scheduled_for,
    MAX(scheduled_for) AS last_scheduled_for
FROM reminder_dispatches
GROUP BY status, channel
ORDER BY status, channel;

\echo ''
\echo '== Despachos pendientes vencidos o listos para worker =='
SELECT
    rd.id AS dispatch_id,
    rd.student_id,
    s.full_name,
    rd.channel,
    rd.dispatch_type,
    rd.scheduled_for,
    rd.status,
    rd.study_plan_event_instance_id,
    rd.reminder_policy_id
FROM reminder_dispatches AS rd
JOIN students AS s
    ON s.id = rd.student_id
WHERE rd.status = 'pending'
  AND rd.scheduled_for <= NOW()
ORDER BY rd.scheduled_for, rd.id;
