# Academic AgentAI — CLAUDE.md

Guía de arquitectura y contexto de desarrollo para el proyecto. Léela antes de cualquier tarea.

---

## Propósito del Sistema

Asistente académico conversacional multi-fase para estudiantes universitarias.
Guía a la estudiante desde el onboarding hasta la generación de un plan de estudio semanal
personalizado, con sincronización a Microsoft 365 (Outlook Calendar, To Do, Mail) y soporte
reactivo continuo via WhatsApp.

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Orquestación del agente | LangGraph 1.0.8 (Pregel state machine) |
| LLM | Azure OpenAI GPT-4.1-mini |
| Embeddings | Azure text-embedding-3-small (RAG) |
| Base de datos | PostgreSQL 13+ via psycopg (async) |
| Validación de datos | Pydantic 2.x |
| Canal de mensajería | WhatsApp Cloud API |
| Integración calendario | Microsoft Graph API (Outlook, To Do, Mail) |
| Persistencia de estado | PostgreSQL Checkpointer (LangGraph custom) |
| Gestión de paquetes | uv + pyproject.toml |

---

## Estructura de Directorios

```
academic_agentAI/
├── src/
│   ├── agents/support/         # Agente principal: state machine, nodos, flujos
│   ├── bootstrap/              # AppContainer (DI singleton + inicialización)
│   ├── integrations/           # Clientes externos (AI, WhatsApp, MS Graph, LangGraph)
│   ├── repositories/           # Capa de datos (PostgreSQL + protocolo mock)
│   ├── schemas/                # Modelos Pydantic del dominio
│   ├── services/               # Lógica de negocio por dominio
│   ├── rag/                    # Pipeline RAG (ingestion, retrieval, generation)
│   ├── auth/                   # Utilidades de autenticación
│   └── utils/                  # Utilidades compartidas
├── scripts/                    # Scripts de automatización y mantenimiento
├── knowledge_base/             # Corpus RAG (markdowns de estrategias de estudio)
├── migrations/                 # Migraciones de base de datos
├── tests/                      # Tests unitarios e integración
└── docs/                       # Documentación adicional
```

---

## Arquitectura del Agente

### Estado Central — `AgentState`

Dataclass plano requerido por LangGraph, ubicado en `src/agents/support/state.py`.
Se accede a sus dominios via **particiones tipadas** (property accessors):

```python
state.conversation_state   # phase, messages, awaiting_user_input, timezone
state.onboarding_state     # consent, student_profile, email_verification, oauth
state.scheduling_state     # raw_inputs, events, schedule, extras
state.planning_state       # subjects, activities, study_profile, priorities, study_plan, replan
state.integration_state    # calendar (Outlook sync metadata)
state.partitions           # Vista completa _PartitionedAgentState
```

### Fases del Agente (`Phase` enum — 29 valores)

```
consent → profile → email_verification → microsoft_oauth
       → schedules → extras → draft → validate → schedule_persist → schedule_sync
       → study_profile → priorities → study_plan
       → running  (estado idle)
            ├→ replan
            ├→ academic_update
            ├→ answer_recommendation (RAG)
            └→ scope_boundary
```

### Nodos Principales (`src/agents/support/nodes/`)

Cada nodo es una función que recibe `AgentState` y retorna un `dict` con los campos actualizados.

| Nodo | Función |
|---|---|
| `welcome_consent` | Bienvenida y recolección de consentimiento |
| `collect_profile` | Recolección de perfil estudiantil |
| `send_email_verification` | Envío de código de verificación |
| `verify_email_code` | Validación del código |
| `request_microsoft_oauth` | Inicio de flujo OAuth con Outlook |
| `persist_profile` | Persistencia del perfil en DB |
| `request_schedules` | Captura de horarios (texto o imagen) |
| `parse_schedules_to_events` | LLM + multimodal → `List[Event]` |
| `collect_extracurricular_details` | Actividades extracurriculares |
| `build_draft_schedule` | Generación de horario optimizado |
| `validate_schedule` | Revisión y corrección del borrador |
| `persist_schedule` | Guardado en DB |
| `sync_fixed_schedule` | Sincronización a Outlook Calendar |
| `collect_study_profile` | Radar de estilo de aprendizaje |
| `collect_priorities` | Captura de prioridades semanales |
| `build_study_plan` | Generación del plan de estudio |
| `handle_academic_update` | Registro de nueva actividad académica |
| `request_replan` | Replanning reactivo |
| `answer_study_recommendation` | Respuesta con RAG de estrategias |
| `answer_scope_boundary` | Respuesta para consultas fuera de alcance |

### Sub-flujos (`src/agents/support/flows/`)

- `onboarding/` — orquestación de recolección de perfil
- `scheduling/` — captura, parseo, validación de horarios
- `extracurricular/` — actividades extracurriculares
- `planning/` — materialización del plan de estudio
- `priorities/` — radar semanal de prioridades
- `replanning/` — modificaciones reactivas al plan
- `sync/` — sincronización con Outlook y Teams

---

## Capas del Sistema

### Integrations (`src/integrations/`)

- `ai/` — OpenAI chat completion, extracción estructurada JSON, multimodal (imágenes)
- `microsoft_graph/` — OAuth 2.0, Calendar, To Do, Mail (auth_client, calendar_client, todo_client, mail_client)
- `whatsapp/` — Webhook parsing, send/receive mensajes, upload/download de media
- `langgraph/` — `PostgresLangGraphCheckpointer` custom (extiende `BaseCheckpointSaver`)
  - Tablas: `langgraph_thread_checkpoints`, `langgraph_checkpoint_writes`
  - Conversación identificada por `thread_id`

### Services (`src/services/`)

| Servicio | Responsabilidad |
|---|---|
| `OnboardingService` | Verificación de email, persistencia y deduplicación de perfil |
| `ScheduleService` | CRUD de horario semanal fijo |
| `StudyPlanningPersistenceService` | Guardar/cargar planes de estudio |
| `StudyPlanMaterializationService` | Instanciar sesiones concretas del plan abstracto |
| `StudySessionTrackingService` | Rastrear sesiones completadas o perdidas |
| `StudyReplanningService` | Adaptar plan ante cambios de prioridades |
| `AcademicActivityPersistenceService` | Persistir actividades académicas individuales |
| `OutlookCalendarSyncService` | Sincronizar eventos de estudio a Outlook |
| `OutlookFixedScheduleSyncService` | Sincronizar horario fijo a Outlook |
| `MicrosoftTodoSyncService` | Sincronizar actividades a Microsoft To Do |
| `MicrosoftOAuthFlowService` | Gestionar flujo OAuth completo (state token, callback, refresh) |
| `PersonalizationService` | Perfil de estudio personalizado (feature flag) |
| `StudyRecommendationService` | RAG — recomendaciones de estrategias de estudio |
| `WhatsAppChannelService` | Buffer de mensajes, manejo de webhook |
| `StudyPlanRemindersService` | Programar recordatorios de sesiones |

### Repositories (`src/repositories/`)

Patrón **Protocol-based**: interfaz abstracta → implementación PostgreSQL → implementación
in-memory para testing. Nunca acceder a DB directamente desde nodos o servicios sin pasar
por el repositorio.

Dominios: `onboarding/`, `scheduling/`, `planning/`, `personalization/`,
`microsoft_graph/`, `rag/`, `reminders/`, `common/`

### Bootstrap y DI (`src/bootstrap/`)

`AppContainer` es el registro central (singleton con lazy init). Todos los servicios se
obtienen via sus factory methods (`get_onboarding_service()`, etc.).

Los nodos del agente acceden a servicios exclusivamente via `src/agents/support/dependencies.py`
(facade público del container).

Secuencia de arranque:
```python
load_project_env()          # Carga .env
AppContainer (singleton)    # Lazy-init de servicios
build_agent()               # Construye grafo LangGraph
PostgresCheckpointer(db)    # Inicializa persistencia de threads
```

---

## Schemas del Dominio (`src/schemas/`)

Todos heredan de `BaseSchemaModel` (Pydantic).

### Enums clave

- `Phase` — 29 fases del agente
- `Prioridad` — `"baja"`, `"media"`, `"alta"`
- `Occupation` — `"academico"`, `"laboral"`, `"ambos"`, `"ninguna"`
- `EventCategory` — `"academico"`, `"laboral"`, `"extracurricular"`, `"estudio"`
- `AcademicActivityType` — `"parcial"`, `"quiz"`, `"tarea"`, `"taller"`, `"entrega"`, `"exposicion"`, `"proyecto"`, `"estudio_pendiente"`

### Modelos principales

- `StudentProfile` — full_name, student_code, age, institutional_email, academic_program, semester, average_grade, occupation
- `Event` — dia, inicio, fin, titulo, tipo, categoria, prioridad, dificultad
- `ExtracurricularItem` — nombre, es_variable, detalle, dias, frecuencia, horarios
- `AcademicActivity` — tipo, materia, fecha_entrega, prioridad, dificultad, duracion_min
- `SubjectItem` — nombre, prioridad, dificultad, urgencia, carga_semanal_min
- `StudyProfile` — estilos de aprendizaje, preferencias de sesión

### Modelos de estado operacional

- `ConsentState`, `EmailVerificationState`, `MicrosoftOAuthOnboardingState`, `OnboardingState`
- `ScheduleFlowState` (etapas de captura de horario)
- `PrioritiesState`, `StudyPlanState`, `ReplanState`
- `CalendarState`, `RemindersState`

---

## Pipeline RAG (`src/rag/`)

```
knowledge_base/ (archivos .md)
        ↓  ingestion/
  chunks + embeddings → PostgreSQL (tabla rag_corpus)
        ↓  retrieval/
  vector search (top_k=8) + BM25 lexical (top_k=8) → rerank (top_k=5)
        ↓  prompting/
  LLM con contexto recuperado → respuesta grounded
```

Configuración via `RagSettings`:
- `RAG_ENABLED` — feature flag
- `RAG_TOP_K_VECTOR=8`, `RAG_TOP_K_LEXICAL=8`, `RAG_TOP_K_FINAL=5`
- `RAG_EMBEDDING_MODEL` — Azure text-embedding-3-small (1536 dims)
- `answer_temperature=0.2`

Se activa en el nodo `answer_study_recommendation`.

---

## Flujo de un Mensaje (End-to-End)

```
WhatsApp Webhook POST
  → WhatsAppChannelService (normaliza, extrae media)
  → Cargar thread desde PostgreSQL Checkpointer (thread_id)
  → classify_input() → intent + scope
  → routing condicional LangGraph (phase + intent → node)
  → Ejecución del nodo:
      ├ LLM call (Azure OpenAI) — conversacional o extracción estructurada/multimodal
      ├ Service calls (OnboardingService, ScheduleService, etc.)
      └ Repository writes (PostgreSQL)
  → Generar respuesta → state.messages
  → Checkpoint → PostgreSQL
  → WhatsApp Cloud API → usuario
  → awaiting_user_input = True
```

---

## Tablas de Base de Datos

| Tabla | Propósito |
|---|---|
| `students` | Perfiles de estudiantes |
| `student_profiles` | Datos normalizados del perfil |
| `verification_challenges` | Códigos de verificación de email (hash + TTL) |
| `schedule_profiles` | Metadata del horario semanal fijo |
| `schedule_blocks` | Bloques individuales (día, inicio, fin, categoría) |
| `academic_activities` | Actividades académicas (tipo, fecha, prioridad) |
| `study_plans` | Planes de estudio generados |
| `study_plan_instances` | Sesiones materializadas del plan |
| `study_profiles` | Preferencias de estudio personalizadas |
| `priorities` | Snapshots de radar semanal de prioridades |
| `replans` | Historial de replanning |
| `microsoft_oauth_tokens` | Tokens de acceso y refresh (OAuth) |
| `microsoft_oauth_pending_states` | State tokens durante el flujo OAuth |
| `calendar_sync_state` | Último sync, calendar ID |
| `todo_sync_state` | Último sync, list ID |
| `reminders` | Recordatorios programados |
| `rag_corpus` | Embeddings + chunks del knowledge base |
| `langgraph_thread_checkpoints` | Snapshots completos de conversación |
| `langgraph_checkpoint_writes` | Mutaciones incrementales de estado |

---

## Variables de Entorno (`.env`)

```bash
# LLM
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT_NAME          # gpt-4.1-mini
AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS  # embeddings-3-small
OPENAI_API_VERSION

# Base de datos
PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD
DATABASE_URL                           # connection string completo
CHECKPOINT_DATABASE_URL                # opcional, por defecto = DATABASE_URL

# Microsoft Graph
MS_CLIENT_ID
MS_CLIENT_SECRET
MS_TENANT_ID
MICROSOFT_REDIRECT_URI

# WhatsApp
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_BUSINESS_ACCOUNT_ID
WHATSAPP_ACCESS_TOKEN

# RAG
RAG_ENABLED
RAG_CORPUS_ROOT
RAG_CORPUS_NAME
RAG_EMBEDDING_PROVIDER
RAG_EMBEDDING_MODEL
RAG_EMBEDDING_DIMENSIONS
RAG_TOP_K_VECTOR / RAG_TOP_K_LEXICAL / RAG_TOP_K_FINAL
```

---

## Scripts de Automatización (`scripts/`)

| Script | Propósito |
|---|---|
| `run_due_reminders.py` | Cron: enviar recordatorios de sesiones vencidas |
| `record_session_completion.py` | Marcar sesiones como completadas |
| `mark_missed_sessions.py` | Marcar sesiones vencidas como perdidas |
| `sync_microsoft_todo.py` | Sincronizar To Do manualmente |
| `sync_outlook_calendar.py` | Sincronizar calendario manualmente |
| `build_rag_corpus.py` | Ingestar knowledge base al vector store |
| `evaluate_rag.py` | Evaluar calidad del RAG (RAGAS) |
| `simulate_support_flow.py` | Simular flujos de conversación para testing |
| `backfill_study_plan_instances.py` | Backfill de sesiones materializadas |
| `check_student_microsoft_connection.py` | Verificar validez de token OAuth |

---

## Patrones Arquitectónicos a Respetar

1. **State Machine (LangGraph)** — las transiciones de fase son deterministas. No modificar el routing sin entender las aristas condicionales en `agent.py`.
2. **Typed Partitions** — usar siempre `state.{domain}_state` para acceder a subdominios, nunca acceder directo a campos del `AgentState` plano desde lógica de negocio.
3. **Protocol-Based Repositories** — nuevos servicios deben recibir el repositorio por inyección, nunca instanciarlo directamente.
4. **AppContainer como único punto de DI** — todos los servicios se registran y obtienen via `AppContainer`. Los nodos los obtienen via `dependencies.py`.
5. **Checkpointing** — el `thread_id` es el identificador canónico de una conversación. La persistencia de estado es responsabilidad del checkpointer, no de los nodos.
6. **Sin lógica de negocio en nodos** — los nodos orquestan (llaman servicios y actualizan estado). La lógica vive en `services/`.
7. **Sin acceso directo a DB desde servicios** — siempre via repositorios.
8. **Feature Flags** — respetar `is_personalization_enabled()`, `is_microsoft_oauth_required()`, etc. antes de activar flujos opcionales.
9. **Multimodal** — las imágenes se materializan lazy desde `state.media`; no cargar bytes hasta que el nodo los necesite.
10. **RAG como apoyo al LLM** — el RAG provee contexto, el LLM genera la respuesta final. No reemplazar uno con el otro.

---

## Feature Flags

```python
is_personalization_enabled()        # Habilita recolección de estilo de estudio
is_microsoft_oauth_required()       # Obliga sincronización con Outlook
is_post_radar_flow_enabled()        # Habilita radar semanal de prioridades
is_study_session_tracking_enabled() # Habilita tracking de sesiones
```

---

## Convenciones de Código

- Todos los modelos heredan de `BaseSchemaModel` (Pydantic, en `src/schemas/common.py`)
- Los nodos retornan `dict` con solo los campos que cambian (LangGraph merge parcial)
- Los servicios son stateless; el estado vive en `AgentState` o en DB
- Los nombres de campos de `Event` y entidades de dominio están en **español** (ej: `dia`, `titulo`, `prioridad`) — mantener esta convención
- Los mensajes al usuario se generan en español
