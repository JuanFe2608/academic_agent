\pset pager off
\pset null '(null)'

\echo '== Conteo de conexiones y links Microsoft Graph =='
SELECT 'microsoft_graph_connections' AS table_name, COUNT(*) AS total_rows FROM microsoft_graph_connections
UNION ALL
SELECT 'outlook_calendar_event_links', COUNT(*) FROM outlook_calendar_event_links
UNION ALL
SELECT 'microsoft_todo_task_links', COUNT(*) FROM microsoft_todo_task_links
ORDER BY table_name;

\echo ''
\echo '== Conexiones Microsoft por estudiante =='
SELECT
    mgc.student_id,
    s.full_name,
    mgc.email,
    mgc.user_principal_name,
    mgc.calendar_id,
    mgc.todo_task_list_id,
    mgc.expires_at
FROM microsoft_graph_connections AS mgc
JOIN students AS s
    ON s.id = mgc.student_id
ORDER BY mgc.student_id;

\echo ''
\echo '== Links activos de Outlook Calendar =='
SELECT
    student_id,
    source_instance_key,
    calendar_id,
    external_event_id,
    sync_status,
    last_synced_at
FROM outlook_calendar_event_links
ORDER BY student_id, last_synced_at DESC
LIMIT 100;

\echo ''
\echo '== Links activos de Microsoft To Do =='
SELECT
    student_id,
    source_instance_key,
    task_list_id,
    external_task_id,
    sync_status,
    last_synced_at
FROM microsoft_todo_task_links
ORDER BY student_id, last_synced_at DESC
LIMIT 100;
