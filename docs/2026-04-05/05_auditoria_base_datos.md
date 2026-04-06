# Auditoria De Base De Datos Y Modelo De Datos

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Resumen del modelo de datos

El proyecto usa PostgreSQL como persistencia durable principal y modela el negocio con SQL explicito, repositorios por dominio y un uso pragmatico de JSONB para snapshots y trazabilidad. El modelo actual soporta bien el flujo MVP ya implementado: onboarding, horario recurrente, personalizacion, prioridades, plan semanal, materializacion de instancias y recordatorios. Tambien deja preparada la base para tracking de sesiones, replanificacion y sincronizacion con Microsoft Graph, aunque esas capacidades no aparecen todavia activas en la muestra de datos auditada.

Hechos observados:

- La fuente de verdad del esquema son las migraciones SQL en `migrations/0001_onboarding_students.sql` a `migrations/0014_grant_microsoft_graph_permissions.sql`.
- La capa de acceso a datos usa `psycopg` y SQL manual en `src/repositories/common/postgres.py`; no hay ORM en `pyproject.toml`.
- El runtime resuelve la URL de base de datos desde `src/bootstrap/settings.py`, construye servicios desde `src/bootstrap/container.py` y los nodos del agente consumen esos servicios via `src/agents/support/dependencies.py`.
- La persistencia conversacional de LangGraph vive aparte en `migrations/0003_langgraph_thread_persistence.sql` y `src/integrations/langgraph/checkpointer.py`.
- La base real contiene 24 tablas publicas.
- La extension `pgvector` no esta instalada en la base auditada. La consulta de `pg_extension` devolvio solo `plpgsql`.

Lectura general:

- El diseño es relacional para identidad, ownership, versionado y estados operativos.
- El diseño es semi-estructurado para snapshots, explicaciones, scoring, metadata de integraciones y payloads de worker.
- No existe hoy persistencia vectorial real. `src/rag/` esta reservado, pero no hay tablas vectoriales, columnas `vector`, indices ANN ni migraciones asociadas.

## 2. Como se conecta la base de datos con el agente y por que no hay ORM

### 2.1 Flujo real de conexion

```text
.env / variables de entorno
        |
        v
src/bootstrap/settings.py
  - database_url_from_env()
  - checkpoint_database_url_from_env()
        |
        v
src/bootstrap/container.py
  - build_*_service()
        |
        v
src/agents/support/dependencies.py
        |
        v
Nodos LangGraph / flows del agente
        |
        v
Servicios de aplicacion
        |
        v
Repositorios PostgreSQL
        |
        v
src/repositories/common/postgres.py
  - psycopg.connect(...)
        |
        v
PostgreSQL
```

Evidencia directa:

- `src/bootstrap/settings.py` resuelve `ACADEMIC_AGENT_DATABASE_URL` o arma la URL desde `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` y `PGPASSWORD`.
- `src/bootstrap/container.py` construye `OnboardingService`, `ScheduleService`, `PersonalizationService`, `StudyPlanningPersistenceService`, `StudyPlanMaterializationService`, `StudyPlanRemindersService`, `StudySessionTrackingService` y repositorios Microsoft.
- `src/agents/support/nodes/persist_profile/node.py` escribe `persisted_student_id` en `student_profile`.
- `src/agents/support/nodes/persist_schedule/node.py` escribe `persisted_profile_id` en `schedule`.
- `src/agents/support/nodes/persist_study_profile/node.py` escribe `persisted_profile_id` en `study_profile` y luego dispara persistencia de planning.
- `src/agents/support/flows/planning/persistence_support.py` persiste priorities y study plan, luego materializa instancias y luego sincroniza reminders.

### 2.2 Por que no se usa ORM

Hechos observados:

- `pyproject.toml` declara `psycopg[binary]` pero no declara `sqlalchemy`, `alembic`, `peewee`, `tortoise` ni otro ORM.
- Todos los repositorios productivos usan SQL explicito: `src/repositories/onboarding/repository.py`, `src/repositories/scheduling/repository.py`, `src/repositories/personalization/repository.py`, `src/repositories/planning/repository.py`, `src/repositories/planning/instances_repository.py`, `src/repositories/planning/tracking_repository.py`, `src/repositories/reminders/repository.py`, `src/repositories/microsoft_graph/state_repository.py` y `src/repositories/microsoft_graph/sync_repository.py`.
- Las migraciones estan escritas a mano y usan caracteristicas muy especificas de PostgreSQL: `JSONB`, `BYTEA`, `ON CONFLICT`, `FOR UPDATE SKIP LOCKED`, indices parciales, checks complejos y claves foraneas compuestas.

Inferencia honesta:

- El proyecto parece haber evitado un ORM por pragmatismo y control fino sobre PostgreSQL.
- Esa decision tiene sentido para este MVP porque el modelo usa bastante SQL expresivo y patrones que con ORM no simplificarian mucho: versionado por snapshots, workers con leasing, deduplicacion idempotente, payloads JSONB y checkpointer binario de LangGraph.

## 3. Entidades detectadas

### 3.1 Inventario real de tablas

La base auditada contiene estas 24 tablas:

- `academic_programs`
- `students`
- `email_verification_challenges`
- `schedule_profiles`
- `recurring_schedule_blocks`
- `schedule_conflicts`
- `study_personalization_profiles`
- `study_personalization_answers`
- `study_personalization_scores`
- `study_priority_profiles`
- `study_priority_subjects`
- `study_plan_profiles`
- `study_plan_events`
- `study_plan_event_instances`
- `study_session_checkins`
- `reminder_policies`
- `reminder_dispatches`
- `study_replan_requests`
- `study_replan_proposals`
- `microsoft_graph_connections`
- `outlook_calendar_event_links`
- `microsoft_todo_task_links`
- `langgraph_thread_checkpoints`
- `langgraph_checkpoint_writes`

### 3.2 Uso real observado en la base auditada

Snapshot de conteos durante esta auditoria:

| Tabla | Filas |
| --- | ---: |
| `academic_programs` | 1 |
| `students` | 2 |
| `schedule_profiles` | 2 |
| `recurring_schedule_blocks` | 34 |
| `schedule_conflicts` | 11 |
| `study_personalization_profiles` | 2 |
| `study_personalization_answers` | 23 |
| `study_personalization_scores` | 16 |
| `study_priority_profiles` | 6 |
| `study_priority_subjects` | 24 |
| `study_plan_profiles` | 6 |
| `study_plan_events` | 48 |
| `study_plan_event_instances` | 93 |
| `reminder_policies` | 8 |
| `reminder_dispatches` | 279 |
| `study_session_checkins` | 0 |
| `study_replan_requests` | 0 |
| `study_replan_proposals` | 0 |
| `microsoft_graph_connections` | 0 |
| `outlook_calendar_event_links` | 0 |
| `microsoft_todo_task_links` | 0 |
| `langgraph_thread_checkpoints` | 0 |
| `langgraph_checkpoint_writes` | 0 |
| `email_verification_challenges` | 0 |

Lectura de uso:

- El core del MVP ya se usa de verdad: estudiantes, horarios, personalizacion, prioridades, plan, instancias y reminders.
- Replanificacion, tracking de check-ins, Outlook/To Do y persistencia de threads LangGraph existen en esquema, pero no aparecen usados en la muestra actual.

## 4. Analisis de cada entidad y sus campos

### 4.1 Onboarding y catalogo academico

### `academic_programs`

Responsabilidad actual:

- Catalogo de programas academicos soportados o conocidos por el sistema.

Campos clave y funcion:

- `id`: PK tecnica.
- `code`: codigo unico del programa.
- `name`: nombre unico del programa.
- `is_active`: permite desactivar programas sin borrarlos.
- `created_at`, `updated_at`: auditoria temporal.

Notas:

- La migracion inicial siembra `ISC`.
- `students.program_id` referencia esta tabla, pero la captura conversacional hoy parece enfocarse a un conjunto muy acotado de programas.

### `students`

Responsabilidad actual:

- Entidad raiz del dominio operacional.

Campos clave y funcion:

- Identidad:
  - `id`
  - `full_name`
  - `student_code`
  - `institutional_email`
- Validacion y onboarding:
  - `email_verified`
  - `email_verified_at`
- Perfil academico:
  - `program_id`
  - `supported_program`
  - `semester`
  - `average_grade`
- Contexto basico:
  - `age`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- `student_code` numerico y de 6 a 20 caracteres.
- email en minusculas, sin espacios y unico.
- `semester` entre 1 y 15.
- `average_grade` entre 0 y 100.
- consistencia minima entre `email_verified` y `email_verified_at`.

Logica de negocio reflejada:

- el estudiante queda persistido solo despues de verificar correo, segun `src/services/onboarding/service.py` y `src/agents/support/nodes/persist_profile/node.py`.
- el resto del modelo cuelga practicamente de `students.id`.

### `email_verification_challenges`

Responsabilidad actual:

- Estado transitorio del reto de verificacion de correo antes de crear al estudiante o antes de cerrar onboarding.

Campos clave y funcion:

- `institutional_email`: PK natural del reto.
- `code_hash`: hash del codigo, no se guarda el codigo en claro.
- `expires_at`
- `attempts`
- `max_attempts`
- `resend_count`
- `last_sent_at`
- `created_at`, `updated_at`

Restricciones visibles:

- email normalizado.
- intentos y reenvios no negativos.
- `max_attempts` entre 1 y 10.

Observacion:

- no tiene `student_id` porque opera antes de confirmar y persistir al estudiante.
- es un modelo transaccional de corto plazo y no una auditoria historica completa de retos emitidos.

### 4.2 Scheduling: horario fijo y actividades

### `schedule_profiles`

Responsabilidad actual:

- Snapshot versionado del horario semanal recurrente validado por el usuario.

Campos clave y funcion:

- Ownership y versionado:
  - `id`
  - `student_id`
  - `version_number`
  - `is_current`
  - `is_active`
- Negocio:
  - `occupation`
  - `base_timezone`
  - `summary_text`
  - `has_conflicts`
  - `conflicts_accepted`
  - `confirmed_by_user`
  - `confirmed_at`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- una sola version actual por estudiante via indice parcial.
- `occupation` en `solo_estudio`, `ambos`, `ninguna`.
- timezone de longitud valida.

Uso real visto:

- las 2 filas actuales tienen `has_conflicts = true` y `conflicts_accepted = true`.

### `recurring_schedule_blocks`

Responsabilidad actual:

- Bloques semanales normalizados del horario academico, laboral o extracurricular.

Campos clave y funcion:

- Relacion:
  - `schedule_profile_id`
  - `source_block_id`
- Semantica del bloque:
  - `block_type`
  - `title`
  - `day_of_week`
  - `start_time`
  - `end_time`
  - `frequency`
  - `timezone`
  - `source_text`
- Calidad de parseo:
  - `normalized_payload`
  - `confidence`
  - `ambiguity_flags`
  - `needs_clarification`
- Confirmacion:
  - `is_active`
  - `confirmed_by_user`
  - `has_conflict`
  - `conflict_accepted`
- Integracion futura de calendario:
  - `external_provider`
  - `external_series_id`
  - `external_event_id`
  - `external_sync_status`
  - `external_sync_metadata`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- `block_type` en `academic`, `work`, `extracurricular`.
- `day_of_week` en ingles, minuscula.
- `frequency = 'weekly'`.
- `start_time < end_time`.
- `confidence` entre 0 y 1 si existe.
- `external_provider` solo `outlook` o `google`.

Logica de negocio reflejada:

- El sistema persiste columnas relacionales para consultar y payload JSONB para conservar el bloque normalizado completo. Eso permite reconstruccion, debugging y reuso.
- Las actividades extracurriculares no tienen tabla aparte; se modelan como bloques del horario con `block_type = 'extracurricular'`.

### `schedule_conflicts`

Responsabilidad actual:

- Registro de solapamientos entre bloques del horario recurrente.

Campos clave y funcion:

- `schedule_profile_id`
- `left_block_id`
- `right_block_id`
- `day_of_week`
- `overlap_start`
- `overlap_end`
- `user_accepted`
- `created_at`

Restricciones visibles:

- bloques distintos.
- rango horario valido.

Observacion:

- El conflicto queda modelado como evidencia explicita y no solo como bandera en el perfil.

### 4.3 Personalizacion y scoring

### `study_personalization_profiles`

Responsabilidad actual:

- Resultado final versionado del Radar de estudio.

Campos clave y funcion:

- Ownership y versionado:
  - `id`
  - `student_id`
  - `schedule_profile_id`
  - `version_number`
  - `is_current`
- Versionado funcional:
  - `questionnaire_version`
  - `scoring_version`
- Estado:
  - `status`
- Resultado resumido:
  - `top_techniques`
  - `weakness_tags`
  - `result_payload`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- una sola version actual por estudiante.
- `status` solo `completed` o `superseded`.
- `top_techniques` y `weakness_tags` como arreglos JSONB.

Lectura importante:

- El schema conversacional de `src/schemas/personalization.py` contiene estados transitorios como `idle` o `collecting`, pero la tabla durable solo guarda resultados finales. Eso parece intencional y correcto.

### `study_personalization_answers`

Responsabilidad actual:

- Respuestas persistidas del cuestionario base y del desempate.

Campos clave y funcion:

- `personalization_profile_id`
- `question_id`
- `option_id`
- `answer_value`
- `created_at`

Restricciones visibles:

- una respuesta por pregunta dentro del mismo perfil.

Observacion:

- `answer_value` JSONB deja espacio para guardar no solo el valor numerico sino metadata como etapa, boosts o contexto del desempate.

### `study_personalization_scores`

Responsabilidad actual:

- Ranking de tecnicas por perfil persistido.

Campos clave y funcion:

- `personalization_profile_id`
- `technique_id`
- `technique_name`
- `score`
- `max_score`
- `normalized_score`
- `rank`
- `rationale_tags`
- `created_at`

Restricciones visibles:

- una tecnica por perfil.
- `score >= 0`
- `max_score >= 0`
- `normalized_score` entre 0 y 1
- `rank` entre 1 y 20

Logica de negocio reflejada:

- El sistema persiste tanto score bruto legacy como score normalizado; eso facilita ranking, comparacion entre versiones y analitica.

### 4.4 Priorizacion y planificacion

### `study_priority_profiles`

Responsabilidad actual:

- Snapshot versionado del estado de captura de prioridades academicas.

Campos clave y funcion:

- Ownership y versionado:
  - `id`
  - `student_id`
  - `schedule_profile_id`
  - `personalization_profile_id`
  - `version_number`
  - `is_current`
- Estado y origen:
  - `status`
  - `source`
  - `prompt_version`
- Snapshot:
  - `result_payload`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- una sola version actual por estudiante.
- `status` en `idle`, `collecting`, `completed`, `skipped`, `superseded`.

Uso real visto:

- hay 6 filas: 2 `completed` actuales y 4 `superseded`.

### `study_priority_subjects`

Responsabilidad actual:

- Materias priorizadas dentro de un snapshot de prioridades.

Campos clave y funcion:

- `priority_profile_id`
- `position`
- `subject_name`
- `priority`
- `difficulty`
- `urgency`
- `weekly_load_min`
- `origin`
- `created_at`

Restricciones visibles:

- una fila por posicion dentro del perfil.
- `priority` y `urgency` en `alta`, `media`, `baja`.
- `difficulty` entre 1 y 5.

### `study_plan_profiles`

Responsabilidad actual:

- Snapshot versionado del plan semanal generado.

Campos clave y funcion:

- Ownership y trazabilidad:
  - `id`
  - `student_id`
  - `schedule_profile_id`
  - `personalization_profile_id`
  - `priority_profile_id`
  - `replan_request_id`
  - `supersedes_study_plan_profile_id`
- Versionado:
  - `version_number`
  - `is_current`
  - `origin_type`
- Resultado:
  - `status`
  - `planner_version`
  - `timezone`
  - `rules`
  - `result_payload`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- una sola version actual por estudiante.
- `origin_type` en `initial`, `replan`, `manual_adjustment`, `system_refresh`.
- reglas de consistencia fuertes cuando `origin_type = 'replan'`.

Uso real visto:

- 6 filas: 2 `generated` y 4 `superseded`.
- todas son `origin_type = 'initial'`.

### `study_plan_events`

Responsabilidad actual:

- Eventos semanales abstractos que componen un `study_plan_profile`.

Campos clave y funcion:

- `study_plan_profile_id`
- `position`
- `source_event_id`
- `day_label`
- `start_time`
- `end_time`
- `title`
- `event_type`
- `category`
- `origin`
- `priority`
- `difficulty`
- `timezone`
- `event_payload`
- `created_at`

Restricciones visibles:

- una posicion por plan.
- `day_label` en espanol.
- `event_type` en `confirmado`, `tentativo`.
- `category` en `academico`, `laboral`, `extracurricular`, `estudio`.

Observacion:

- Se guarda el evento tanto en columnas como en `event_payload`. Es redundancia intencional para snapshot y reconstruccion.

### 4.5 Instancias fechadas y tracking de sesiones

### `study_plan_event_instances`

Responsabilidad actual:

- Materializacion de ocurrencias concretas del plan semanal dentro de un horizonte de fechas.

Campos clave y funcion:

- Ownership:
  - `id`
  - `student_id`
  - `study_plan_profile_id`
  - `study_plan_event_id`
- Identidad externa/estable:
  - `source_instance_key`
- Tiempo:
  - `planned_date`
  - `starts_at`
  - `ends_at`
  - `timezone`
- Estado operacional:
  - `status`
  - `source`
  - `completion_pct`
  - `completed_at`
- Snapshot:
  - `instance_payload`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- `source_instance_key` unico.
- `starts_at < ends_at`.
- `planned_date` consistente con `starts_at` y `timezone`.
- `status` en `scheduled`, `in_progress`, `completed`, `skipped`, `missed`, `canceled`, `superseded`.
- FK compuesta contra `(study_plan_profile_id, student_id)` y contra `(study_plan_event_id, study_plan_profile_id)`.

Uso real visto:

- 93 filas.
- `scheduled = 31`.
- `superseded = 62`.

Lectura:

- Esta es una entidad central y muy bien alineada con el flujo del agente porque conecta planeacion, reminders, tracking e integraciones externas.

### `study_session_checkins`

Responsabilidad actual:

- Bitacora de interacciones o resultados sobre una instancia de estudio.

Campos clave y funcion:

- Ownership:
  - `student_id`
  - `study_plan_event_instance_id`
- Tipo de check-in:
  - `checkin_type`
  - `actor_type`
- Tiempo real:
  - `reported_at`
  - `actual_start_at`
  - `actual_end_at`
- Resultado:
  - `completion_pct`
  - `comprehension_score`
  - `energy_score`
  - `notes`
  - `checkin_payload`
- Auditoria:
  - `created_at`

Restricciones visibles:

- tipos: `start`, `complete`, `skip`, `missed_confirmation`, `feedback`.
- actor: `student`, `agent`, `system`.
- validaciones cruzadas sobre tiempos y campos obligatorios por tipo.

Uso real visto:

- 0 filas.

Lectura:

- La entidad esta bien pensada, pero aun no aparece activada en datos reales.

### 4.6 Recordatorios

### `reminder_policies`

Responsabilidad actual:

- Politicas persistidas por estudiante, canal y tipo de recordatorio.

Campos clave y funcion:

- `student_id`
- `channel`
- `reminder_type`
- `lead_minutes`
- `followup_minutes`
- `quiet_hours`
- `enabled`
- `timezone`
- `metadata_json`
- `created_at`
- `updated_at`

Restricciones visibles:

- canales: `in_app`, `email`, `whatsapp`.
- tipos: `pre_session`, `followup`, `missed_session`.
- clave unica funcional: `(student_id, channel, reminder_type, lead_minutes)`.

Uso real visto:

- 8 filas.

### `reminder_dispatches`

Responsabilidad actual:

- Cola durable de despachos generados para workers.

Campos clave y funcion:

- Ownership y relacion:
  - `student_id`
  - `reminder_policy_id`
  - `study_plan_event_instance_id`
- Semantica:
  - `dispatch_type`
  - `channel`
  - `scheduled_for`
- Estado de ejecucion:
  - `leased_at`
  - `sent_at`
  - `acknowledged_at`
  - `status`
  - `provider_message_id`
  - `failure_reason`
- Payload:
  - `payload`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- estado en `pending`, `leased`, `sent`, `failed`, `canceled`, `acknowledged`, `expired`.
- checks temporales coherentes.
- deduplicacion por indice unico funcional.
- leasing concurrente via `FOR UPDATE SKIP LOCKED` en `src/repositories/reminders/repository.py`.

Uso real visto:

- 279 filas.
- todas en canal `in_app`.
- `pending = 93`.
- `canceled = 186`.

Lectura:

- La estructura soporta workers y re-materializaciones sin duplicar mensajes.

### 4.7 Replanificacion

### `study_replan_requests`

Responsabilidad actual:

- Solicitud durable de replanificacion causada por usuario o sistema.

Campos clave y funcion:

- `student_id`
- `current_study_plan_profile_id`
- `source_study_plan_event_instance_id`
- `trigger_type`
- `status`
- `reason_text`
- `request_payload`
- `resolved_at`
- `created_at`
- `updated_at`

Restricciones visibles:

- triggers: `user_request`, `missed_session`, `schedule_change`, `calendar_conflict`, `overload`, `manual_review`.
- `missed_session` exige `source_study_plan_event_instance_id`.

### `study_replan_proposals`

Responsabilidad actual:

- Propuestas derivadas de una solicitud de replanificacion.

Campos clave y funcion:

- `replan_request_id`
- `proposal_number`
- `status`
- `summary_text`
- `proposal_payload`
- `impact_payload`
- `resulting_study_plan_profile_id`
- `created_at`
- `updated_at`

Restricciones visibles:

- una propuesta numerada por request.
- un solo `selected` y un solo `applied` por request.
- el plan resultante aplicado queda ligado por FK compuesta.

Uso real visto:

- 0 filas en ambas tablas.

Lectura:

- El modelado es avanzado y consistente, pero hoy es capacidad futura o parcial, no capacidad activa.

### 4.8 Integraciones Microsoft

### `microsoft_graph_connections`

Responsabilidad actual:

- Estado OAuth y defaults operativos de la integracion Microsoft por estudiante.

Campos clave y funcion:

- Ownership:
  - `id`
  - `student_id`
- Identidad Microsoft:
  - `tenant_id`
  - `microsoft_user_id`
  - `user_principal_name`
  - `email`
  - `display_name`
- Credenciales:
  - `access_token`
  - `refresh_token`
  - `token_type`
  - `expires_at`
  - `scopes_json`
- Defaults de sync:
  - `calendar_id`
  - `todo_task_list_id`
  - `auth_metadata`
- Auditoria:
  - `created_at`
  - `updated_at`

Restricciones visibles:

- una conexion por estudiante.
- checks de longitud y formato basicos.

Uso real visto:

- 0 filas.

### `outlook_calendar_event_links`

Responsabilidad actual:

- Mapeo durable entre instancia interna y evento externo de Outlook Calendar.

Campos clave y funcion:

- `student_id`
- `microsoft_graph_connection_id`
- `study_plan_event_instance_id`
- `source_instance_key`
- `calendar_id`
- `external_event_id`
- `external_change_key`
- `sync_status`
- `last_error`
- `last_synced_at`
- `created_at`
- `updated_at`

### `microsoft_todo_task_links`

Responsabilidad actual:

- Mapeo durable entre instancia interna y tarea externa de Microsoft To Do.

Campos clave y funcion:

- `student_id`
- `microsoft_graph_connection_id`
- `study_plan_event_instance_id`
- `source_instance_key`
- `task_list_id`
- `external_task_id`
- `sync_status`
- `last_error`
- `last_synced_at`
- `created_at`
- `updated_at`

Restricciones visibles en ambos links:

- unicidad por `source_instance_key` dentro del estudiante.
- unicidad por identificador externo del proveedor.
- soft-delete por `sync_status`.

Uso real visto:

- 0 filas en ambos links.

### 4.9 Trazabilidad conversacional de LangGraph

### `langgraph_thread_checkpoints`

Responsabilidad actual:

- Persistencia binaria del estado de checkpoints por `thread_id`.

Campos clave y funcion:

- `thread_id`
- `checkpoint_ns`
- `checkpoint_id`
- `parent_checkpoint_id`
- `checkpoint_type`
- `checkpoint_payload`
- `metadata_json`
- `created_at`

### `langgraph_checkpoint_writes`

Responsabilidad actual:

- Persistencia de escrituras pendientes o intermedias por tarea/canal de LangGraph.

Campos clave y funcion:

- `thread_id`
- `checkpoint_ns`
- `checkpoint_id`
- `task_id`
- `task_path`
- `write_idx`
- `channel`
- `value_type`
- `value_payload`
- `created_at`

Uso real visto:

- 0 filas en ambas tablas.

Observacion:

- La trazabilidad conversacional existe a nivel tecnico de thread, pero no hay una relacion estructural con `students.id` o con planes persistidos.

## 5. Relacion entre entidades

### 5.1 Modelo entidad-relacion en ASCII

```text
academic_programs
        1
        |
        | 0..N
     students
        |
        | 1..N
        +------------------------------+
        |                              |
        v                              v
schedule_profiles                 email_verification_challenges
        |
        | 1..N
        +------------------+
        |                  |
        v                  v
recurring_schedule_blocks  schedule_conflicts
        |
        | schedule context for
        v
study_personalization_profiles
        | 1..N                     students
        +------------+                |
        |            |                | 1..N
        v            v                +----------------------------+
answers         scores               |                            |
                                     v                            v
                             study_priority_profiles       study_plan_profiles
                                     |                            |
                                     | 1..N                       | 1..N
                                     v                            v
                             study_priority_subjects       study_plan_events
                                                                  |
                                                                  | materialize
                                                                  v
                                                         study_plan_event_instances
                                                                  |
                         +----------------------------------------+----------------------+
                         |                                        |                      |
                         v                                        v                      v
                study_session_checkins                  reminder_dispatches      sync links
                                                                                 /       \
                                                                                v         v
                                                           outlook_calendar_event_links  microsoft_todo_task_links

study_replan_requests -> study_replan_proposals -> resulting study_plan_profiles

langgraph_thread_checkpoints / langgraph_checkpoint_writes
    separados del dominio operacional
```

### 5.2 Cardinalidades inferidas

Hechos observados:

- `students -> schedule_profiles`: 1 a N.
- `schedule_profiles -> recurring_schedule_blocks`: 1 a N.
- `schedule_profiles -> schedule_conflicts`: 1 a N.
- `students -> study_personalization_profiles`: 1 a N.
- `study_personalization_profiles -> study_personalization_answers`: 1 a N.
- `study_personalization_profiles -> study_personalization_scores`: 1 a N.
- `students -> study_priority_profiles`: 1 a N.
- `study_priority_profiles -> study_priority_subjects`: 1 a N.
- `students -> study_plan_profiles`: 1 a N.
- `study_plan_profiles -> study_plan_events`: 1 a N.
- `study_plan_profiles -> study_plan_event_instances`: 1 a N.
- `study_plan_event_instances -> study_session_checkins`: 1 a N.
- `students -> reminder_policies`: 1 a N.
- `study_plan_event_instances -> reminder_dispatches`: 1 a N.
- `students -> microsoft_graph_connections`: 1 a 0..1.
- `students -> outlook_calendar_event_links`: 1 a N.
- `students -> microsoft_todo_task_links`: 1 a N.
- `study_replan_requests -> study_replan_proposals`: 1 a N.

Inferencias razonables:

- un mismo `schedule_profile` puede ser referenciado por multiples `study_personalization_profiles` y `study_plan_profiles` historicos;
- una misma `study_plan_event_instance` podria terminar asociada a 0..N despachos y 0..N check-ins;
- el ownership por `student_id` se duplica a proposito en varias tablas para reforzar aislamiento y para soportar FKs compuestas.

## 6. Coherencia del modelo con los casos de uso

| Caso de uso | Soporte actual | Evidencia | Lectura |
| --- | --- | --- | --- |
| Onboarding | Alto | `students`, `email_verification_challenges`, `src/services/onboarding/service.py` | Bien soportado |
| Perfil del estudiante | Alto | `students` | Suficiente para MVP |
| Horarios fijos | Alto | `schedule_profiles`, `recurring_schedule_blocks`, `schedule_conflicts` | Bien soportado |
| Actividades extracurriculares | Medio-Alto | `recurring_schedule_blocks.block_type = extracurricular` | Funciona sin tabla separada |
| Personalizacion | Alto | `study_personalization_*` | Bien soportado |
| Scoring | Alto | `study_personalization_scores.max_score`, `normalized_score` | Bien soportado |
| Top tecnicas | Alto | `study_personalization_profiles.top_techniques` y tabla de scores | Bien soportado |
| Planes de estudio | Alto | `study_priority_*`, `study_plan_*`, `study_plan_event_instances` | Bien soportado |
| Integraciones calendario/correo | Medio | `microsoft_graph_*` y links externos | Estructura lista, uso real aun nulo |
| Recordatorios | Alto | `reminder_policies`, `reminder_dispatches` | Ya usado en datos reales |
| Replanificacion | Medio-Bajo | `study_replan_*` | Bien modelado, aun no usado |
| Trazabilidad conversacional | Medio | `langgraph_thread_*` | Trazabilidad tecnica, no de negocio |
| WhatsApp | Bajo | solo `reminder_policies.channel = whatsapp` y placeholder de integracion | No operativo aun |
| RAG | Nulo en BD | sin `pgvector`, sin tablas vectoriales | No implementado aun |

Conclusiones de soporte:

- onboarding, horario, personalizacion, scoring, top tecnicas, plan semanal e instancias estan bien cubiertos para el MVP;
- la base ya soporta reminders de forma real;
- el modelo sugiere replanificacion e integraciones Microsoft, pero hoy no hay evidencia de uso real en la base auditada;
- no existe modelado de persistencia vectorial ni soporte real para RAG.

## 7. Problemas de diseño

### 7.1 Credenciales Microsoft almacenadas en texto en `microsoft_graph_connections`

Hechos observados:

- `migrations/0013_microsoft_graph_connections_and_sync.sql` define `access_token TEXT NOT NULL` y `refresh_token TEXT NULL`.
- `src/repositories/microsoft_graph/state_repository.py` inserta y actualiza esos campos sin capa visible de cifrado.

Problema detectado:

- la tabla mezcla identidad de proveedor, defaults operativos y credenciales sensibles sin proteccion adicional observable desde el codigo auditado.

Riesgos:

- exposicion de credenciales si hay acceso de lectura a base;
- rotacion y auditoria de secretos mas compleja;
- mayor impacto ante un incidente de seguridad.

Recomendacion:

- mover `refresh_token` y, si es posible, `access_token` a un secret store o cifrarlos a nivel aplicativo/KMS;
- dejar en la tabla solo referencias, metadata minima y expiracion.

### 7.2 Redundancia alta entre columnas normalizadas y snapshots JSONB

Hechos observados:

- `recurring_schedule_blocks.normalized_payload` duplica informacion de columnas del bloque.
- `study_personalization_profiles.result_payload` convive con answers y scores normalizados.
- `study_priority_profiles.result_payload` convive con `study_priority_subjects`.
- `study_plan_profiles.result_payload` convive con `study_plan_events`.
- `study_plan_events.event_payload` y `study_plan_event_instances.instance_payload` duplican atributos del evento.

Problema detectado:

- hay varias capas de snapshot que aumentan trazabilidad, pero tambien riesgo de drift entre el dato relacional y el JSONB si un proceso actualiza solo una de las dos representaciones.

Riesgos:

- inconsistencias sutiles en reporting o debugging;
- mayor costo de evolucion de schema;
- ambiguedad sobre cual representacion es la canonica.

Recomendacion:

- documentar por tabla cual version es canonica y cual es snapshot;
- restringir las actualizaciones para que siempre se escriban ambas representaciones desde un solo servicio;
- si el patron se mantiene, agregar tests de consistencia por dominio.

### 7.3 Trazabilidad conversacional separada del dominio de negocio

Hechos observados:

- `langgraph_thread_checkpoints` y `langgraph_checkpoint_writes` se indexan por `thread_id`, `checkpoint_ns` y `checkpoint_id`.
- no existe una FK o tabla puente entre `thread_id` y `students.id`.
- en la base auditada ambas tablas estan vacias.

Problema detectado:

- la persistencia conversacional existe como infraestructura, pero no queda vinculada formalmente al estudiante ni al plan generado.

Riesgos:

- dificil auditar que conversacion produjo un horario o un plan concreto;
- mas costoso depurar regresiones de negocio;
- limita analitica de producto y trazabilidad funcional.

Recomendacion:

- agregar una tabla o metadata durable que vincule `thread_id` con `student_id` y, cuando aplique, con `schedule_profile_id` o `study_plan_profile_id`.

### 7.4 `email_verification_challenges` usa email como PK unica

Hechos observados:

- la tabla se identifica solo por `institutional_email`.
- no guarda historial de retos previos, solo el reto activo.

Problema detectado:

- el modelo esta optimizado para el reto vigente, no para auditoria historica o analitica de fraudes/reenvios.

Riesgos:

- perdida de historial operativo;
- poca capacidad para detectar abuso o patrones de reenvio.

Recomendacion:

- si el producto necesita auditoria o seguridad mas fuerte, separar `challenge_id` como PK y dejar el reto activo como vista o indice funcional.

### 7.5 Solapamiento entre sync de bloques recurrentes y sync de instancias materializadas

Hechos observados:

- `recurring_schedule_blocks` ya tiene campos `external_provider`, `external_event_id`, `external_sync_status`.
- ademas existen `outlook_calendar_event_links` y `microsoft_todo_task_links` para instancias del plan de estudio.

Problema detectado:

- hay dos niveles de integracion externa: horario recurrente y ocurrencias materializadas. La separacion es razonable, pero la frontera no esta plenamente documentada.

Riesgos:

- confundir que se sincroniza como evento de agenda base y que se sincroniza como sesion de estudio;
- duplicar logica o estado de sync en el futuro.

Recomendacion:

- explicitar que `recurring_schedule_blocks` representa agenda base del estudiante y que `*_event_links` representa solo sesiones de estudio materializadas.

### 7.6 Capacidad estructural adelantada respecto al uso real

Hechos observados:

- `study_replan_*`, `study_session_checkins`, `microsoft_graph_*` y `langgraph_thread_*` no tienen datos en la muestra auditada.

Problema detectado:

- la base ya modela varias capacidades futuras, pero el runtime actual no las usa de manera visible o estable.

Riesgos:

- deuda de esquema adelantado que luego diverja del flujo real;
- complejidad conceptual innecesaria para nuevos mantenedores.

Recomendacion:

- mantener estas tablas, pero documentarlas como `preparadas, no activas` hasta que el flujo real las use.

## 8. Riesgos de integridad y consistencia

Riesgos principales:

- Riesgo de seguridad en `microsoft_graph_connections` por tokens en claro.
- Riesgo de drift entre columnas relacionales y `JSONB`.
- Riesgo de trazabilidad incompleta entre conversacion y entidades de negocio.
- Riesgo de duplicidad conceptual entre sync de horario base y sync de instancias.
- Riesgo de sobre-modelado en capacidades aun no activas.

Riesgos mitigados por el diseño actual:

- ownership fuerte por `student_id` en casi todos los dominios;
- versionado con `is_current` e indices parciales;
- checks de estado bastante buenos en instancias, check-ins, replanes y dispatches;
- FKs compuestas que previenen cruces indebidos entre estudiantes;
- `ON CONFLICT`, dedup y `SKIP LOCKED` correctos para reminders e instancias.

## 9. Oportunidades de mejora

- Formalizar la regla de "dato canonico vs snapshot" por tabla.
- Vincular `thread_id` de LangGraph con `student_id` y perfiles persistidos.
- Endurecer seguridad de credenciales Microsoft.
- Documentar explicitamente las capacidades que existen solo a nivel schema.
- Preparar una futura persistencia vectorial separada del modelo operacional.

## 10. Recomendaciones de evolucion

### 10.1 Mantener el nucleo actual

La base actual esta bien para un MVP serio. No hay evidencia de que haya que rehacer el modelo desde cero. El corazon del negocio esta bien resuelto alrededor de:

- `students`
- `schedule_profiles`
- `study_personalization_profiles`
- `study_priority_profiles`
- `study_plan_profiles`
- `study_plan_event_instances`
- `reminder_dispatches`

### 10.2 Mejoras de alto valor

1. Endurecer seguridad de `microsoft_graph_connections`.
2. Agregar trazabilidad de negocio entre thread conversacional y estudiante.
3. Definir canonicidad de snapshots JSONB para evitar drift.
4. Documentar el uso de capacidades no activas: replan, check-ins, Microsoft sync y checkpointer.
5. Si se abre RAG, crear persistencia vectorial separada y no mezclarla con tablas operacionales.

### 10.3 Separacion entre persistencia estructurada y vectorial

Hechos observados:

- No existe `pgvector` en la base auditada.
- No hay tablas ni columnas vectoriales en `migrations/`.
- `src/rag/` existe solo como estructura reservada.

Conclusion:

- hoy toda la persistencia es estructurada o semi-estructurada en PostgreSQL relacional;
- no existe mezcla real entre persistencia operacional y vectorial porque la parte vectorial todavia no esta implementada;
- cuando se introduzca RAG, conviene separar claramente:
  - tablas operacionales del agente;
  - tablas de conocimiento y embeddings;
  - politicas de versionado y refresh de conocimiento.

## 11. Dictamen final de esta fase

Hechos observados:

- El modelo de datos actual ya soporta con coherencia el flujo implementado del agente.
- La arquitectura reciente mejoro la relacion entre servicios, repositorios y schema.
- El diseño de base de datos esta mas cerca de un modelo operacional versionado que de un CRUD simple, y eso es adecuado para este producto.

Problemas detectados:

- Persistencia de secretos sensibles en tablas.
- Redundancia fuerte en snapshots JSONB.
- Trazabilidad conversacional aun separada del negocio.
- Varias capacidades adelantadas en schema pero no activas en runtime.

Riesgos:

- seguridad;
- drift entre representaciones;
- dificultad de auditoria funcional end-to-end.

Recomendacion:

- No rehacer el modelo.
- Fortalecer seguridad, trazabilidad y documentacion del schema.
- Mantener el enfoque actual de versionado por perfiles e instancias, que es el tramo mejor resuelto del diseño.
