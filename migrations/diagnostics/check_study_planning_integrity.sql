\pset pager off
\pset null '(null)'

-- Uso:
--   psql "$ACADEMIC_AGENT_DATABASE_URL" \
--     -f migrations/diagnostics/check_study_planning_integrity.sql

\echo '== Estudiantes con mas de un perfil de prioridad actual =='
SELECT
    student_id,
    COUNT(*) AS current_priority_profiles,
    ARRAY_AGG(id ORDER BY id) AS profile_ids
FROM study_priority_profiles
WHERE is_current = TRUE
GROUP BY student_id
HAVING COUNT(*) > 1
ORDER BY student_id;

\echo ''
\echo '== Estudiantes con mas de un plan actual =='
SELECT
    student_id,
    COUNT(*) AS current_plan_profiles,
    ARRAY_AGG(id ORDER BY id) AS profile_ids
FROM study_plan_profiles
WHERE is_current = TRUE
GROUP BY student_id
HAVING COUNT(*) > 1
ORDER BY student_id;

\echo ''
\echo '== Perfiles de prioridad actuales sin materias =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS priority_profile_id,
    spp.version_number
FROM study_priority_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_priority_subjects AS sps
    ON sps.priority_profile_id = spp.id
WHERE spp.is_current = TRUE
GROUP BY spp.student_id, s.full_name, spp.id, spp.version_number
HAVING COUNT(sps.id) = 0
ORDER BY spp.student_id;

\echo ''
\echo '== Planes actuales sin eventos =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS study_plan_profile_id,
    spp.version_number
FROM study_plan_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_plan_events AS spe
    ON spe.study_plan_profile_id = spp.id
WHERE spp.is_current = TRUE
GROUP BY spp.student_id, s.full_name, spp.id, spp.version_number
HAVING COUNT(spe.id) = 0
ORDER BY spp.student_id;

\echo ''
\echo '== Planes actuales sin prioridad enlazada =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS study_plan_profile_id,
    spp.version_number,
    spp.priority_profile_id
FROM study_plan_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_priority_profiles AS pr
    ON pr.id = spp.priority_profile_id
WHERE spp.is_current = TRUE
  AND (spp.priority_profile_id IS NULL OR pr.id IS NULL)
ORDER BY spp.student_id;

\echo ''
\echo '== Planes enlazados a prioridades de otro estudiante =='
SELECT
    spp.student_id AS study_plan_student_id,
    plan_student.full_name AS study_plan_student_name,
    spp.id AS study_plan_profile_id,
    spp.priority_profile_id,
    pr.student_id AS priority_student_id,
    priority_student.full_name AS priority_student_name
FROM study_plan_profiles AS spp
JOIN study_priority_profiles AS pr
    ON pr.id = spp.priority_profile_id
JOIN students AS plan_student
    ON plan_student.id = spp.student_id
JOIN students AS priority_student
    ON priority_student.id = pr.student_id
WHERE spp.student_id <> pr.student_id
ORDER BY spp.student_id, spp.id;

\echo ''
\echo '== Planes actuales apuntando a una prioridad no actual =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS study_plan_profile_id,
    spp.priority_profile_id,
    pr.is_current AS linked_priority_is_current
FROM study_plan_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
LEFT JOIN study_priority_profiles AS pr
    ON pr.id = spp.priority_profile_id
WHERE spp.is_current = TRUE
  AND (pr.id IS NULL OR pr.is_current = FALSE)
ORDER BY spp.student_id;

\echo ''
\echo '== Perfiles de prioridad con metadata JSONB desalineada =='
SELECT
    id AS priority_profile_id,
    student_id,
    version_number AS row_version_number,
    result_payload ->> 'persisted_profile_id' AS payload_profile_id,
    result_payload ->> 'version_number' AS payload_version_number
FROM study_priority_profiles
WHERE COALESCE(result_payload ->> 'persisted_profile_id', '') <> id::text
   OR COALESCE(result_payload ->> 'version_number', '') <> version_number::text
ORDER BY student_id, id;

\echo ''
\echo '== Planes con metadata JSONB desalineada =='
SELECT
    id AS study_plan_profile_id,
    student_id,
    version_number AS row_version_number,
    result_payload ->> 'persisted_profile_id' AS payload_profile_id,
    result_payload ->> 'version_number' AS payload_version_number
FROM study_plan_profiles
WHERE COALESCE(result_payload ->> 'persisted_profile_id', '') <> id::text
   OR COALESCE(result_payload ->> 'version_number', '') <> version_number::text
ORDER BY student_id, id;

\echo ''
\echo '== Perfiles de prioridad con posiciones de materias inconsistentes =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS priority_profile_id,
    COUNT(sps.id) AS subject_rows,
    MIN(sps.position) AS min_position,
    MAX(sps.position) AS max_position
FROM study_priority_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
JOIN study_priority_subjects AS sps
    ON sps.priority_profile_id = spp.id
GROUP BY spp.student_id, s.full_name, spp.id
HAVING MIN(sps.position) <> 1
    OR MAX(sps.position) <> COUNT(sps.id)
ORDER BY spp.student_id, spp.id;

\echo ''
\echo '== Planes con posiciones de eventos inconsistentes =='
SELECT
    spp.student_id,
    s.full_name,
    spp.id AS study_plan_profile_id,
    COUNT(spe.id) AS event_rows,
    MIN(spe.position) AS min_position,
    MAX(spe.position) AS max_position
FROM study_plan_profiles AS spp
JOIN students AS s
    ON s.id = spp.student_id
JOIN study_plan_events AS spe
    ON spe.study_plan_profile_id = spp.id
GROUP BY spp.student_id, s.full_name, spp.id
HAVING MIN(spe.position) <> 1
    OR MAX(spe.position) <> COUNT(spe.id)
ORDER BY spp.student_id, spp.id;
