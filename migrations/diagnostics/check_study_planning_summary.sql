\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_study_planning_summary.sql

\echo '== Conteo general de tablas =='
SELECT 'students' AS table_name, COUNT(*) AS total_rows FROM students
UNION ALL
SELECT 'study_priority_profiles', COUNT(*) FROM study_priority_profiles
UNION ALL
SELECT 'study_priority_subjects', COUNT(*) FROM study_priority_subjects
UNION ALL
SELECT 'study_plan_profiles', COUNT(*) FROM study_plan_profiles
UNION ALL
SELECT 'study_plan_events', COUNT(*) FROM study_plan_events
ORDER BY table_name;

\echo ''
\echo '== Prioridades actuales por estudiante =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS priority_profile_id,
    spp.version_number,
    spp.status,
    spp.source,
    spp.prompt_version,
    spp.schedule_profile_id,
    spp.personalization_profile_id,
    COUNT(sps.id) AS subject_count,
    spp.created_at,
    spp.updated_at
FROM study_priority_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_priority_subjects AS sps
    ON sps.priority_profile_id = spp.id
WHERE spp.is_current = TRUE
GROUP BY
    spp.student_id,
    s.full_name,
    spp.id,
    spp.version_number,
    spp.status,
    spp.source,
    spp.prompt_version,
    spp.schedule_profile_id,
    spp.personalization_profile_id,
    spp.created_at,
    spp.updated_at
ORDER BY spp.updated_at DESC, spp.student_id;

\echo ''
\echo '== Planes actuales por estudiante =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS study_plan_profile_id,
    spp.priority_profile_id,
    spp.version_number,
    spp.status,
    spp.planner_version,
    spp.timezone,
    COUNT(spe.id) AS event_count,
    spp.created_at,
    spp.updated_at
FROM study_plan_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_plan_events AS spe
    ON spe.study_plan_profile_id = spp.id
WHERE spp.is_current = TRUE
GROUP BY
    spp.student_id,
    s.full_name,
    spp.id,
    spp.priority_profile_id,
    spp.version_number,
    spp.status,
    spp.planner_version,
    spp.timezone,
    spp.created_at,
    spp.updated_at
ORDER BY spp.updated_at DESC, spp.student_id;

\echo ''
\echo '== Relacion entre prioridad actual y plan actual =='
SELECT
    s.id AS student_id,
    s.full_name,
    priority_current.id AS current_priority_profile_id,
    priority_current.version_number AS priority_version,
    priority_current.status AS priority_status,
    plan_current.id AS current_plan_profile_id,
    plan_current.version_number AS plan_version,
    plan_current.status AS plan_status,
    plan_current.priority_profile_id AS plan_links_to_priority_id,
    CASE
        WHEN priority_current.id IS NULL THEN 'missing_priority'
        WHEN plan_current.id IS NULL THEN 'missing_plan'
        WHEN plan_current.priority_profile_id = priority_current.id THEN 'ok'
        ELSE 'mismatch'
    END AS linkage_status
FROM students AS s
LEFT JOIN study_priority_profiles AS priority_current
    ON priority_current.student_id = s.id
   AND priority_current.is_current = TRUE
LEFT JOIN study_plan_profiles AS plan_current
    ON plan_current.student_id = s.id
   AND plan_current.is_current = TRUE
WHERE priority_current.id IS NOT NULL
   OR plan_current.id IS NOT NULL
ORDER BY s.id;
