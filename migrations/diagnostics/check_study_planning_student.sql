\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -v student_id=15 \
--     -f migrations/diagnostics/check_study_planning_student.sql

\if :{?student_id}
\else
\echo 'Falta la variable student_id.'
\echo 'Ejemplo: psql "$ACADEMIC_AGENT_DATABASE_URL" -v student_id=15 -f migrations/diagnostics/check_study_planning_student.sql'
\quit 1
\endif

\echo '== Estudiante =='
SELECT
    id,
    full_name,
    student_code,
    institutional_email,
    semester,
    average_grade,
    created_at,
    updated_at
FROM students
WHERE id = :student_id;

\echo ''
\echo '== Historial de perfiles de prioridad =='
SELECT
    id,
    version_number,
    status,
    source,
    prompt_version,
    schedule_profile_id,
    personalization_profile_id,
    is_current,
    created_at,
    updated_at
FROM study_priority_profiles
WHERE student_id = :student_id
ORDER BY version_number DESC;

\echo ''
\echo '== Materias del perfil de prioridad actual =='
WITH current_priority AS (
    SELECT id
    FROM study_priority_profiles
    WHERE student_id = :student_id
      AND is_current = TRUE
)
SELECT
    sps.priority_profile_id,
    sps.position,
    sps.subject_name,
    sps.priority,
    sps.difficulty,
    sps.urgency,
    sps.weekly_load_min,
    sps.origin,
    sps.created_at
FROM study_priority_subjects AS sps
JOIN current_priority AS cp
    ON cp.id = sps.priority_profile_id
ORDER BY sps.position;

\echo ''
\echo '== Payload del perfil de prioridad actual =='
SELECT
    id AS priority_profile_id,
    jsonb_pretty(result_payload) AS result_payload
FROM study_priority_profiles
WHERE student_id = :student_id
  AND is_current = TRUE;

\echo ''
\echo '== Historial de perfiles de planificacion =='
SELECT
    id,
    priority_profile_id,
    version_number,
    status,
    planner_version,
    timezone,
    schedule_profile_id,
    personalization_profile_id,
    is_current,
    created_at,
    updated_at
FROM study_plan_profiles
WHERE student_id = :student_id
ORDER BY version_number DESC;

\echo ''
\echo '== Eventos del plan actual =='
WITH current_plan AS (
    SELECT id
    FROM study_plan_profiles
    WHERE student_id = :student_id
      AND is_current = TRUE
)
SELECT
    spe.study_plan_profile_id,
    spe.position,
    spe.source_event_id,
    spe.day_label,
    spe.start_time,
    spe.end_time,
    spe.title,
    spe.event_type,
    spe.category,
    spe.origin,
    spe.priority,
    spe.difficulty,
    spe.timezone,
    spe.created_at
FROM study_plan_events AS spe
JOIN current_plan AS cp
    ON cp.id = spe.study_plan_profile_id
ORDER BY
    CASE spe.day_label
        WHEN 'Lunes' THEN 1
        WHEN 'Martes' THEN 2
        WHEN 'Miercoles' THEN 3
        WHEN 'Jueves' THEN 4
        WHEN 'Viernes' THEN 5
        WHEN 'Sabado' THEN 6
        WHEN 'Domingo' THEN 7
        ELSE 8
    END,
    spe.start_time,
    spe.position;

\echo ''
\echo '== Rules y payload del plan actual =='
SELECT
    id AS study_plan_profile_id,
    jsonb_pretty(rules) AS rules,
    jsonb_pretty(result_payload) AS result_payload
FROM study_plan_profiles
WHERE student_id = :student_id
  AND is_current = TRUE;
