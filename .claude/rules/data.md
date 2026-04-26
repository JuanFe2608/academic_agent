---
paths:
  - "src/repositories/**/*.py"
  - "src/services/**/*.py"
  - "migrations/**/*.sql"
---

# Reglas para la capa de datos

## Patrón de repositorio

Estructura obligatoria al crear un repositorio nuevo:

```
src/repositories/{dominio}/
├── repository.py    # Protocol (interfaz abstracta)
├── pg_repository.py # Implementación PostgreSQL
└── mock_repository.py # Implementación in-memory (para tests)
```

El servicio recibe el repositorio por inyección. Nunca instanciarlo directamente.

## Patrón de versionado (is_current + version_number)

Aplica en: `schedule_profiles`, `study_personalization_profiles`,
`study_priority_profiles`, `study_plan_profiles`.

Al guardar una nueva versión:
1. `UPDATE ... SET is_current = FALSE WHERE student_id = %s AND is_current = TRUE`
2. `INSERT ... SET is_current = TRUE, version_number = anterior + 1`

Hay un índice único parcial: `UNIQUE (student_id) WHERE is_current = TRUE`.
Nunca insertar dos filas con `is_current = TRUE` para el mismo estudiante.

## Tablas reales en DB

| Tabla real | Dominio |
|---|---|
| `students` | Perfil del estudiante |
| `academic_programs` | Programas académicos (lookup) |
| `email_verification_challenges` | Códigos de verificación (TTL) |
| `schedule_profiles` | Versiones del horario fijo |
| `recurring_schedule_blocks` | Bloques individuales del horario |
| `schedule_conflicts` | Conflictos detectados |
| `study_personalization_profiles` | Resultados del Radar de estudio |
| `study_personalization_answers` | Respuestas por pregunta |
| `study_personalization_scores` | Scores normalizados por técnica |
| `study_priority_profiles` | Snapshots de prioridades |
| `study_priority_subjects` | Materias por snapshot |
| `study_plan_profiles` | Planes de estudio generados |
| `study_plan_events` | Eventos del plan (abstractos) |
| `study_plan_event_instances` | Sesiones materializadas (concretas) |
| `study_session_checkins` | Registro de sesiones completadas |
| `study_replan_requests` | Solicitudes de replanning |
| `study_replan_proposals` | Propuestas generadas |
| `reminder_policies` | Preferencias de notificaciones |
| `reminder_dispatches` | Cola de envío de recordatorios |
| `microsoft_graph_connections` | Tokens OAuth Microsoft (1:1 por estudiante) |
| `outlook_calendar_event_links` | Links Outlook ↔ sesiones del plan |
| `microsoft_todo_task_links` | Links To Do ↔ sesiones del plan |
| `microsoft_oauth_pending_states` | State tokens durante flujo OAuth |
| `academic_activities` | Actividades académicas puntuales |
| `langgraph_thread_checkpoints` | Estado completo de conversación |
| `langgraph_checkpoint_writes` | Mutaciones incrementales de estado |
| `rag.documents` / `rag.chunks` / `rag.relations` | Corpus RAG (schema separado) |

## Constraints importantes a respetar en código

- `students.average_grade`: `NUMERIC(5,2)`, valor entero (0-100), se guarda como `int`
- `schedule_profiles.occupation`: `CHECK IN ('solo_estudio', 'ambos', 'ninguna')`
- `recurring_schedule_blocks.block_type`: `CHECK IN ('academic', 'work', 'extracurricular')`
- `study_plan_event_instances.source_instance_key`: UNIQUE — clave de deduplicación
- `study_personalization_scores.normalized_score`: `NUMERIC(6,4)`, rango `[0.0, 1.0]`

## Migraciones

Las migraciones son archivos SQL numerados en `migrations/`. Se aplican manualmente
en orden numérico con `psql $DATABASE_URL -f migrations/XXXX_nombre.sql`.
No hay runner automático — verificar siempre que la migración esté aplicada
antes de asumir que una columna/tabla existe.

## Acceso a datos en tests

Usar la implementación in-memory del repositorio cuando el test no necesita DB real.
Los tests de integración que sí necesitan DB deben estar marcados claramente
y asumir que las migraciones ya están aplicadas.
