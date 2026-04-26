Q# Arquitectura del Sistema Academic AgentAI - Lara AI

**Proyecto:** Lara AI — Asistente Académico Conversacional

---

## 1. Qué es el sistema

Lara AI es un asistente académico conversacional multi-fase diseñado para estudiantes universitarias. El estudiante interactúa exclusivamente vía **WhatsApp**. El agente guía al estudiante a través de un proceso de onboarding (registro, horarios, perfil de aprendizaje), genera un plan de estudio semanal personalizado, lo sincroniza con **Microsoft Outlook Calendar** y **Microsoft To Do**, y permanece disponible de forma reactiva para registrar nuevas actividades, replantificar y recomendar estrategias de estudio.

---

## 2. Estilo Arquitectónico

El sistema sigue una arquitectura de **Agente Conversacional Orientado a Fases** implementada sobre un **grafo de estados finitos deterministico** (LangGraph / Pregel state machine), desplegado como servicio HTTP en **Azure** y conectado a WhatsApp mediante Webhooks.

Los patrones principales son:

| Patrón                                   | Aplicación                                                 |
| ---------------------------------------- | ---------------------------------------------------------- |
| **State Machine**                        | LangGraph orquesta 29 fases con transiciones deterministas |
| **Layered Architecture**                 | API → Agent → Services → Repositories → DB                 |
| **Protocol-Based Repositories**          | Interfaces abstractas → PostgreSQL / Mock                  |
| **Dependency Injection**                 | AppContainer singleton con lazy init                       |
| **Event-Driven (Webhooks)**              | WhatsApp POST → background task → agente                   |
| **RAG (Retrieval-Augmented Generation)** | Conocimiento externo enriquece respuestas del LLM          |
| **Stateful Conversation**                | Checkpointing por thread_id en PostgreSQL                  |

---

## 3. Diagrama de Arquitectura General

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         ESTUDIANTE — WHATSAPP                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                      │  POST /webhook (text, image, audio)
                                      ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                         API LAYER  (FastAPI / Azure)                         ║
║  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐   ║
║  │ GET /webhook   │  │  POST /webhook   │  │  GET /oauth/callback       │   ║
║  │ (verificación  │  │  (mensajes de    │  │  (Microsoft OAuth retorno) │   ║
║  │  WhatsApp)     │  │   WhatsApp)      │  │                            │   ║
║  └────────────────┘  └────────┬─────────┘  └────────────────────────────┘   ║
╚═════════════════════════════════╪════════════════════════════════════════════╝
                                  │ background_task
                                  ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                          AGENT RUNNER                                        ║
║  AgentRunner.process_message(WhatsAppInboundMessage)                         ║
║  ├─ thread_id = from_phone_number  (identidad de conversación)               ║
║  ├─ _build_human_message()  (texto + imágenes base64)                        ║
║  ├─ agent.invoke(input, config={thread_id})                                  ║
║  ├─ [checkpointer carga estado previo desde PostgreSQL]                      ║
║  ├─ _extract_new_ai_messages()                                               ║
║  └─ whatsapp_service.send_agent_messages()                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                  │
                                  ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║              LANGGRAPH STATE MACHINE  (src/agents/support/)                  ║
║                                                                              ║
║   AgentState  ──────────────────────────────────────────────────────────────►║
║   (estado plano con particiones tipadas)                                     ║
║                                                                              ║
║   conversation_state  │ phase, messages, timezone, awaiting_user_input       ║
║   onboarding_state    │ consent, student_profile, email_verification, oauth  ║
║   scheduling_state    │ raw_inputs, events, schedule                         ║
║   planning_state      │ subjects, activities, study_profile, priorities      ║
║   interaction_state   │ active_intent, domain, missing_fields                ║
║   integration_state   │ calendar (Outlook sync metadata)                     ║
║                                                                              ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │                         NODOS (38 total)                             │   ║
║   │                                                                      │   ║
║   │  welcome_consent → collect_profile → send_email_verification        │   ║
║   │     → verify_email_code → request_microsoft_oauth                   │   ║
║   │     → persist_profile                                                │   ║
║   │     → request_schedules → parse_schedules_to_events                 │   ║
║   │     → ask_extracurricular → collect_extracurricular_details         │   ║
║   │     → build_draft_schedule → validate_schedule                      │   ║
║   │     → persist_schedule → sync_fixed_schedule                        │   ║
║   │     → collect_study_profile → collect_priorities                    │   ║
║   │     → build_study_plan                                               │   ║
║   │     → running  ────────────────────────────────────────────────┐    │   ║
║   │                                                                 │    │   ║
║   │             ┌─── handle_academic_update                         │    │   ║
║   │             ├─── request_replan                                 │    │   ║
║   │             ├─── answer_study_recommendation (RAG)              │    │   ║
║   │             └─── answer_scope_boundary                          │    │   ║
║   │                                                        ◄────────┘    │   ║
║   │                                                                      │   ║
║   │  Cada nodo: fn(AgentState) → dict  (solo campos modificados)        │   ║
║   │  Routing: _route_*() functions + conditional edges                   │   ║
║   │  Blocking: awaiting_user_input = True → graph suspende ejecución    │   ║
║   └─────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════╝
         │                       │                        │
         ▼                       ▼                        ▼
╔═══════════════╗     ╔══════════════════╗     ╔═════════════════════════╗
║   SERVICES    ║     ║  INTEGRATIONS    ║     ║    REPOSITORIES         ║
║               ║     ║                  ║     ║                         ║
║ Onboarding    ║     ║ Azure OpenAI     ║     ║  PostgreSQL             ║
║ Schedule      ║     ║   GPT-4.1-mini   ║     ║  (psycopg async)        ║
║ StudyPlan     ║     ║   embeddings-3sm ║     ║                         ║
║ Personali-    ║     ║                  ║     ║  students               ║
║  zation       ║     ║ WhatsApp Cloud   ║     ║  schedule_blocks        ║
║ StudyRecom-   ║     ║   API            ║     ║  academic_activities    ║
║  mendation    ║     ║                  ║     ║  study_plans            ║
║ Replanning    ║     ║ Microsoft Graph  ║     ║  study_profiles         ║
║ OAuthFlow     ║     ║   Outlook Cal.   ║     ║  priorities             ║
║ OutlookSync   ║     ║   To Do          ║     ║  rag_corpus             ║
║ TodoSync      ║     ║   Mail           ║     ║  microsoft_oauth_tokens ║
║ Reminders     ║     ║   OAuth 2.0/MSAL ║     ║  langgraph_checkpoints  ║
║ Tracking      ║     ║                  ║     ║                         ║
╚═══════════════╝     ╚══════════════════╝     ╚═════════════════════════╝
                                                         │
                                                         ▼
                                              ╔══════════════════╗
                                              ║   PostgreSQL DB  ║
                                              ║   (Azure PaaS)   ║
                                              ╚══════════════════╝
```

---

## 4. Flujo de Datos End-to-End

### 4.1 Un Mensaje de WhatsApp

```
1. RECEPCIÓN
   ─────────
   Estudiante envía mensaje (texto, imagen, audio)
       → WhatsApp Cloud API → POST /webhook (JSON payload)
       → FastAPI extrae mensaje con extract_inbound_messages()
       → Dispara background_task → no bloquea HTTP response

2. PREPARACIÓN
   ────────────
   AgentRunner.process_message(WhatsAppInboundMessage)
       → thread_id = número de teléfono (identidad única)
       → _build_human_message():
           si texto → HumanMessage(content=texto)
           si imagen → HumanMessage(content=[{type:image_url, base64}])
       → Cargar checkpoint desde PostgreSQL por thread_id
           → AgentState previo restaurado completamente

3. CLASIFICACIÓN Y ROUTING
   ────────────────────────
   agent.invoke({"messages": [human_message]}, config)
       → welcome_consent (entry point del grafo)
       → _route_welcome(state):
           classify_input(texto) → InputClassification(tipo, entidad)
           route_conversation_input(texto, interaction, phase)
               decide_scope(texto) → ScopeDecision(in_scope/out_scope)
               Routing condicional según phase actual
           Devuelve nombre del siguiente nodo

4. EJECUCIÓN DE NODO
   ──────────────────
   Cada nodo (ej: collect_profile):
       a. Lee estado via state.get("campo") o state.{dominio}_state
       b. Llama servicios via get_*_service() [dependencies.py]
       c. Llama LLM (Azure OpenAI) si necesita extracción/conversación
       d. Llama repositorio via servicio → PostgreSQL si necesita persistir
       e. Retorna dict con solo campos modificados (merge parcial LangGraph)

5. PERSISTENCIA DE ESTADO
   ───────────────────────
   Después de cada nodo:
       PostgresLangGraphCheckpointer.put(config, state)
       → INSERT INTO langgraph_thread_checkpoints (serialized AgentState)
       → INSERT INTO langgraph_checkpoint_writes (deltas incrementales)

6. SUSPENSIÓN / CONTINUACIÓN
   ──────────────────────────
   Si nodo setea awaiting_user_input=True:
       → Grafo suspende ejecución
       → Retorna al AgentRunner
   Si nodo setea awaiting_user_input=False:
       → Grafo continúa al siguiente nodo automáticamente
       → El flujo puede ejecutar múltiples nodos sin interacción del usuario

7. RESPUESTA
   ──────────
   AgentRunner extrae AIMessages nuevos (post-último HumanMessage)
       → whatsapp_service.send_agent_messages(recipient_id, messages)
           agent_message_to_channel_messages():
               texto → ChannelOutboundMessage(kind="text")
               imagen → ChannelOutboundMessage(kind="image")
               documento → ChannelOutboundMessage(kind="document")
       → WhatsAppCloudClient.send_text/send_image() → WhatsApp Cloud API
       → Estudiante recibe mensaje
```

---

## 5. Fases del Agente (State Machine)

Las 29 fases son los valores del enum `Phase`. Se organizan en bloques funcionales:

```
BLOQUE 1: ONBOARDING
──────────────────────────────────────────────────────────────
  consent ──► profile ──► email_verification ──► microsoft_oauth
                                                       │
                                         (OAuth requerido o no)
                                                       ▼

BLOQUE 2: CAPTURA DE HORARIO
──────────────────────────────────────────────────────────────
  schedules ──► extras ──► draft ──► validate ──► schedule_persist
                                                       │
                                             schedule_sync (Outlook)
                                                       │
                                                       ▼

BLOQUE 3: PERFIL DE ESTUDIO
──────────────────────────────────────────────────────────────
  study_profile ──► priorities ──► study_plan
                                       │
                                       ▼

ESTADO RUNNING (Idle Reactivo)
──────────────────────────────────────────────────────────────
  running ─┬─► replan              (solicita replanning del plan)
            ├─► academic_update    (registra parcial, tarea, examen)
            ├─► answer_recommendation (consulta estrategia via RAG)
            └─► scope_boundary     (consulta fuera de alcance)
```

**Regla fundamental:** las transiciones son deterministas. El campo `phase` en el estado más el contenido del último mensaje determinan el siguiente nodo. No existe lógica de routing ambigua.

---

## 6. Capas del Sistema

### 6.1 API Layer (`src/api/`)

- **FastAPI** como servidor HTTP
- 3 endpoints públicos: `/health`, `GET /webhook`, `POST /webhook`
- 1 endpoint OAuth: `GET /oauth/callback`
- **AgentRunner** encapsula el pipeline completo
- ThreadPoolExecutor para procesamiento concurrente de mensajes

### 6.2 Agent Layer (`src/agents/support/`)

| Archivo           | Rol                                                             |
| ----------------- | --------------------------------------------------------------- |
| `agent.py`        | Definición completa del grafo LangGraph (38 nodos, 25+ aristas) |
| `state.py`        | AgentState — dataclass plano con particiones tipadas            |
| `dependencies.py` | Facade público de inyección de dependencias                     |
| `nodes/*/node.py` | Implementación de cada nodo (thin orchestrators)                |
| `flows/*/`        | Servicios de flujo (lógica multi-turno compleja)                |
| `priorities/`     | Formatters y lógica del radar semanal                           |

**Separación de responsabilidades:**

- Los **nodos** orquestan: leen estado, invocan servicios, retornan delta
- Los **flows** contienen diálogos multi-turno complejos
- La **lógica de negocio** vive en `services/`

### 6.3 Services Layer (`src/services/`)

Servicios stateless organizados por dominio:

| Servicio                             | Dominio                                             |
| ------------------------------------ | --------------------------------------------------- |
| `OnboardingService`                  | Registro, verificación de email, deduplicación      |
| `ScheduleService`                    | CRUD horario semanal fijo + validación              |
| `PersonalizationService`             | Cuestionario Likert → estilo de aprendizaje         |
| `StudyPlanningPersistenceService`    | Planes de estudio: guardar/cargar                   |
| `StudyPlanMaterializationService`    | Instanciar sesiones concretas del plan              |
| `StudyReplanningService`             | Replanning reactivo ante cambios                    |
| `AcademicActivityPersistenceService` | Actividades académicas (parciales, tareas)          |
| `StudyRecommendationService`         | RAG → respuestas de estrategia de estudio           |
| `OutlookCalendarSyncService`         | Sesiones de estudio → Outlook Calendar              |
| `OutlookFixedScheduleSyncService`    | Horario fijo → Outlook Calendar                     |
| `MicrosoftTodoSyncService`           | Actividades → Microsoft To Do                       |
| `MicrosoftOAuthFlowService`          | OAuth 2.0 completo (state token, callback, refresh) |
| `WhatsAppChannelService`             | Buffer de mensajes, normalización canal             |
| `StudyPlanRemindersService`          | Recordatorios programados de sesiones               |
| `StudySessionTrackingService`        | Tracking de sesiones completadas/perdidas           |

### 6.4 Integrations Layer (`src/integrations/`)

```
integrations/
├── ai/
│   ├── chat_client.py           LLM conversacional (Azure OpenAI GPT-4.1-mini)
│   ├── extraction_client.py     Extracción estructurada JSON (function calling)
│   └── multimodal_client.py     Análisis de imágenes (horarios fotográficos)
│
├── microsoft_graph/
│   ├── auth_client.py           OAuth 2.0 + MSAL + refresh token
│   ├── calendar_client.py       Outlook Calendar CRUD
│   ├── todo_client.py           Microsoft To Do CRUD
│   └── mail_client.py           Envío de emails (verificación)
│
├── whatsapp/
│   ├── client.py                WhatsApp Cloud API (send/receive/upload/download)
│   ├── message_mapper.py        Webhook JSON → WhatsAppInboundMessage typed
│   └── transport.py             HTTP transport abstraction (urllib)
│
└── langgraph/
    └── checkpointer.py          PostgresLangGraphCheckpointer (custom)
                                 Extiende BaseCheckpointSaver de LangGraph
```

### 6.5 Repositories Layer (`src/repositories/`)

Patrón **Protocol-based**: cada dominio tiene interface abstracta + implementación PostgreSQL + implementación in-memory para tests.

```
repositories/
├── onboarding/      students, student_profiles, verification_challenges
├── scheduling/      schedule_profiles, schedule_blocks
├── planning/        study_plans, study_plan_instances, academic_activities
├── personalization/ study_profiles, questionnaire_configs
├── microsoft_graph/ oauth_tokens, oauth_pending_states, calendar_sync, todo_sync
├── rag/             rag_corpus (chunks + embeddings)
├── reminders/       reminders programados
└── common/          tipos base, queries compartidos
```

### 6.6 Bootstrap / DI (`src/bootstrap/`)

```python
# Singleton global
container = AppContainer()

# Lazy init: primer get_*() construye la dependencia
container.get_onboarding_service()
    → build_onboarding_service()
        → PostgresStudentRepository(db_pool)
        → PostgresVerificationRepository(db_pool)
        → OnboardingService(student_repo, verification_repo, mail_client)

# Overrides para testing
container.set_onboarding_service(MockOnboardingService())
```

---

## 7. Pipeline RAG (Recomendación de Estrategias)

```
FASE A — INGESTION (offline, script build_rag_corpus.py)
────────────────────────────────────────────────────────
  knowledge_base/*.md  (estrategias de estudio en markdown)
        ↓ Chunking (por sección, ~500 tokens)
        ↓ Azure text-embedding-3-small (1536 dimensiones)
        ↓ INSERT INTO rag_corpus (chunk_id, content, embedding, metadata)

FASE B — RETRIEVAL (runtime, por consulta del estudiante)
─────────────────────────────────────────────────────────
  Consulta del estudiante
        ↓ QueryUnderstanding (intent, detected_techniques, filters)
        ↓ Vector Search (pgvector cosine similarity, top_k=8)
        ↓ BM25 Lexical Search (PostgreSQL full-text, top_k=8)
        ↓ Reranking (reciprocal rank fusion, top_k=5)
        ↓ GroundedContextPackage (chunks + citas)

FASE C — GENERATION
────────────────────
  GroundedContextPackage + consulta
        ↓ Prompt: "Usando estas estrategias, responde al estudiante..."
        ↓ Azure OpenAI GPT-4.1-mini (temperature=0.2)
        ↓ Respuesta grounded con citas
```

El RAG se activa únicamente en el nodo `answer_study_recommendation`. El LLM es siempre quien genera la respuesta final; el RAG provee contexto de apoyo.

---

## 8. Integración Microsoft 365

### Flujo OAuth 2.0

```
Agente: "¿Vinculas tu cuenta de Outlook?"
       ↓
MicrosoftOAuthFlowService.generate_auth_url()
  → state_token = UUID (almacenado en oauth_pending_states)
  → URL = https://login.microsoftonline.com/…?state=token&redirect_uri=…

Estudiante: clic en URL → autoriza en Microsoft
       ↓
Microsoft redirige → GET /oauth/callback?code=…&state=…
  → MicrosoftOAuthFlowService.handle_callback(code, state)
      → Validar state_token
      → Intercambiar code → access_token + refresh_token
      → Guardar en microsoft_oauth_tokens (PostgreSQL)
       ↓
Agente: "Cuenta vinculada exitosamente"
```

### Sincronización de Calendarios

```
OutlookFixedScheduleSyncService.sync(student_id, events):
  → calendar_client.get_or_create_calendar("Lara AI — Horario Fijo")
  → Para cada Event:
      calendar_client.create_event({
          subject: evento.titulo,
          start: {dateTime: iso_datetime, timeZone: America/Bogota},
          end: {dateTime: iso_datetime, timeZone: America/Bogota},
          recurrence: {pattern: weekly, daysOfWeek: [evento.dia]}
      })
  → Guardar event_ids en calendar_sync_state (para updates futuros)
```

---

## 9. Persistencia de Conversaciones

```
thread_id = número de teléfono WhatsApp (ej: "573001234567")

PostgresLangGraphCheckpointer:
  ┌─────────────────────────────────────────────────┐
  │ langgraph_thread_checkpoints                    │
  │   thread_id | checkpoint_id | state_json | ts   │
  ├─────────────────────────────────────────────────┤
  │ langgraph_checkpoint_writes                     │
  │   thread_id | checkpoint_id | key | value_json  │
  └─────────────────────────────────────────────────┘

Cada invocación del agente:
  1. GET checkpoint WHERE thread_id = ?   → restaura AgentState completo
  2. Ejecuta nodos (modifica estado en memoria)
  3. PUT checkpoint (AgentState completo + deltas)

Resultado: el agente "recuerda" todo el historial de la conversación,
la fase actual, el perfil y el plan de estudio entre sesiones de WhatsApp.
```

---

## 10. Tablas Principales de Base de Datos

| Tabla                            | Propósito                              | Capa                        |
| -------------------------------- | -------------------------------------- | --------------------------- |
| `students`                       | Identidad del estudiante               | Repository: onboarding      |
| `student_profiles`               | Perfil académico completo              | Repository: onboarding      |
| `verification_challenges`        | Códigos de email (hash + TTL)          | Repository: onboarding      |
| `schedule_profiles`              | Metadata del horario fijo              | Repository: scheduling      |
| `schedule_blocks`                | Bloques individuales del horario       | Repository: scheduling      |
| `academic_activities`            | Parciales, tareas, entregas            | Repository: planning        |
| `study_plans`                    | Planes de estudio generados            | Repository: planning        |
| `study_plan_instances`           | Sesiones concretas materializadas      | Repository: planning        |
| `study_profiles`                 | Resultado del radar de aprendizaje     | Repository: personalization |
| `priorities`                     | Snapshots semanales de prioridades     | Repository: planning        |
| `replans`                        | Historial de replanning                | Repository: planning        |
| `microsoft_oauth_tokens`         | Access + refresh tokens                | Repository: microsoft_graph |
| `microsoft_oauth_pending_states` | State tokens durante OAuth             | Repository: microsoft_graph |
| `calendar_sync_state`            | Event IDs sincronizados en Outlook     | Repository: microsoft_graph |
| `todo_sync_state`                | Task IDs sincronizados en To Do        | Repository: microsoft_graph |
| `reminders`                      | Recordatorios programados              | Repository: reminders       |
| `rag_corpus`                     | Chunks + embeddings del knowledge base | Repository: rag             |
| `langgraph_thread_checkpoints`   | Estado completo por conversación       | Checkpointer                |
| `langgraph_checkpoint_writes`    | Deltas incrementales                   | Checkpointer                |

---

## 11. Feature Flags

El sistema tiene comportamiento condicional controlado por flags en la configuración:

| Flag                                  | Efecto si está deshabilitado                                           |
| ------------------------------------- | ---------------------------------------------------------------------- |
| `is_personalization_enabled()`        | Omite el cuestionario de estilo de aprendizaje (collect_study_profile) |
| `is_microsoft_oauth_required()`       | No obliga la vinculación con Outlook                                   |
| `is_post_radar_flow_enabled()`        | Omite el radar semanal de prioridades                                  |
| `is_study_session_tracking_enabled()` | No rastrea sesiones completadas/perdidas                               |
| `RAG_ENABLED`                         | El nodo answer_study_recommendation retorna respuesta sin retrieval    |

---

## 12. Principios de Diseño Observados

### Invariantes arquitectónicas

1. **Sin lógica de negocio en nodos.** Los nodos son coordinadores delgados. La lógica vive en services y flows.
2. **Sin acceso directo a DB desde servicios.** Siempre a través de repositories.
3. **AppContainer como único punto de DI.** Los nodos acceden a servicios exclusivamente via `dependencies.py`.
4. **Estado vía particiones tipadas.** Nunca acceder a campos planos de `AgentState` desde lógica de negocio; usar `state.{domain}_state`.
5. **Checkpointing como fuente de verdad.** La conversación es el estado; la DB es derivada.
6. **RAG como apoyo, no reemplazo.** El LLM siempre genera la respuesta; el RAG provee contexto.
7. **Multimodal lazy.** Las imágenes se descargan solo cuando el nodo que las necesita ejecuta.

### Trade-offs identificados

| Decisión                                | Ventaja                                       | Costo                                           |
| --------------------------------------- | --------------------------------------------- | ----------------------------------------------- |
| LangGraph como orquestador              | Checkpointing nativo, trazabilidad            | Curva de aprendizaje, overhead de serialización |
| PostgreSQL para checkpoints             | Un solo sistema de datos                      | Volumen de snapshots JSON puede crecer rápido   |
| thread_id = teléfono                    | Correlación directa estudiante ↔ conversación | Un estudiante = un número (no multi-device)     |
| Nodos sincrónicos en ThreadPoolExecutor | Simplicidad, compatibilidad con código sync   | Max workers limita concurrencia simultánea      |
| Español en campos de dominio            | Legibilidad del dominio                       | Prompts LLM deben ser en español o bilingüe     |

---

## 13. Mapa de Componentes por Responsabilidad

```
CANAL DE ENTRADA
  WhatsApp Cloud API ──► src/integrations/whatsapp/
                     ──► src/api/app.py (FastAPI)

ORQUESTACIÓN
  src/api/agent_runner.py ──► src/agents/support/agent.py (grafo LangGraph)
                          ──► src/integrations/langgraph/checkpointer.py

CONVERSACIÓN
  src/agents/support/nodes/  ──► Lógica por fase
  src/agents/support/flows/  ──► Diálogos multi-turno complejos

INTELIGENCIA ARTIFICIAL
  src/integrations/ai/       ──► Azure OpenAI (chat, extracción, multimodal)
  src/rag/                   ──► Pipeline RAG (vector search + LLM)

LÓGICA DE NEGOCIO
  src/services/              ──► Stateless, inyectados via AppContainer

DATOS
  src/repositories/          ──► Protocol + PostgreSQL + Mock
  src/schemas/               ──► Modelos Pydantic del dominio

INTEGRACIÓN EXTERNA
  src/integrations/microsoft_graph/ ──► Outlook Calendar, To Do, OAuth
  src/integrations/whatsapp/        ──► Canal de mensajería

CONFIGURACIÓN
  src/bootstrap/             ──► AppContainer (DI) + settings
```

---

## 14. Clasificación Arquitectónica Formal

### 14.1 Arquitectura del Sistema: Monolito Modular

El sistema es un **Monolito Modular** (Modular Monolith), no microservicios ni monolito tradicional.

```
UN SOLO proceso / deployable (FastAPI en Azure)
         │
         ├── Módulos internos con fronteras semánticas claras
         ├── Capas con responsabilidades sin solapamiento
         └── Toda comunicación en memoria (sin HTTP interno)
```

**¿Por qué NO es Microservicios?**

| Criterio microservicios                | Este proyecto                    |
| -------------------------------------- | -------------------------------- |
| Servicios desplegados por separado     | ✗ Un solo proceso FastAPI        |
| Comunicación HTTP/gRPC entre servicios | ✗ Llamadas directas en memoria   |
| Bases de datos aisladas por servicio   | ✗ Una sola PostgreSQL compartida |
| Escalado independiente por dominio     | ✗ Escala el proceso completo     |
| Equipos independientes por servicio    | ✗ Proyecto unipersonal / tesis   |

**¿Por qué NO es Monolito Tradicional (spaghetti)?**

| Criterio monolito clásico                 | Este proyecto                                               |
| ----------------------------------------- | ----------------------------------------------------------- |
| Acoplamiento entre capas                  | ✗ Repositories via Protocol, DI via AppContainer            |
| Lógica mezclada en cualquier capa         | ✗ Nodos solo orquestan, servicios tienen el dominio         |
| Acceso directo a DB desde cualquier punto | ✗ Solo via repositories                                     |
| Sin interfaces abstractas                 | ✗ Todos los repositorios tienen Protocol + implementaciones |
| Sin inyección de dependencias             | ✗ AppContainer singleton con lazy init                      |

**¿Por qué SÍ es Monolito Modular?**

1. **Módulos con fronteras claras:** cada subdirectorio de `src/` es un módulo con responsabilidad única y solo expone lo necesario.
2. **Dependencias unidireccionales:** `api → agents → services → repositories → db`. Ninguna capa importa de la capa superior.
3. **Contratos explícitos:** los repositorios se definen como `Protocol` (interface), haciendo que las capas superiores dependan de abstracciones, no de implementaciones.
4. **DI centralizada:** el `AppContainer` es el único lugar donde los módulos se ensamblan. Nadie instancia sus propias dependencias.
5. **Testabilidad:** cada módulo puede testearse en aislamiento con mocks inyectados via `set_*_service()`.

Adicionalmente el sistema aplica dos patrones secundarios complementarios:

| Patrón secundario         | Dónde                                                                              |
| ------------------------- | ---------------------------------------------------------------------------------- |
| **Event-Driven**          | WhatsApp webhook → background task → agente (desacopla recepción de procesamiento) |
| **Pipeline Architecture** | RAG: ingestion → retrieval → reranking → generation                                |

---

### 14.2 Arquitectura del Agente: FSM Agent (ReAct sobre State Machine)

El agente sigue el patrón **Stateful FSM Agent**, una variante controlada del paradigma ReAct, donde el LLM opera dentro de nodos predefinidos en lugar de decidir libremente qué acción tomar.

#### Los tres paradigmas de agentes IA comparados

```
1. ReAct PURO (libre)
   ─────────────────────────────────────────────────────
   LLM: "pienso → elijo herramienta → observo → repito"
   El LLM decide en cada paso qué hacer y con qué herramienta.
   Ejemplo: LangChain AgentExecutor, OpenAI Assistants.

   Riesgo: impredecible, difícil de auditar, puede ciclar.

2. Plan-and-Execute
   ─────────────────────────────────────────────────────
   LLM genera un plan completo → executor lo ejecuta paso a paso.
   Ejemplo: BabyAGI, OpenAI o1 reasoning.

   Riesgo: el plan puede quedar desactualizado si el entorno cambia.

3. FSM Agent / Orchestration Agent  ← ESTE PROYECTO
   ─────────────────────────────────────────────────────
   El desarrollador define el grafo de estados y las transiciones.
   El LLM opera DENTRO de cada nodo de forma controlada.
   Ejemplo: LangGraph, AWS Step Functions con LLM.

   Ventaja: predecible, auditable, recuperable ante fallos.
```

#### Cómo se combina ReAct con FSM en este proyecto

```
NIVEL MACRO (FSM — deterministico, controlado por el desarrollador)
──────────────────────────────────────────────────────────────────
  welcome_consent
       │  _route_welcome(state) → routing deterministico
       ▼
  collect_profile
       │  _route_collect_profile(state)
       ▼
  ...  (29 fases, transiciones fijas)
       ▼
  running ──► [replan | academic_update | RAG | scope_boundary]

NIVEL MICRO (ReAct parcial — dentro de cada nodo)
──────────────────────────────────────────────────────────────────
  Nodo collect_profile:
    Razona: "¿Qué datos faltan del perfil?"
    Actúa: llm.with_structured_output(StudentProfile).invoke(prompt)
    Observa: resultado → actualiza state.student_profile
    Siguiente nodo: deterministico (no lo decide el LLM)
```

**El LLM nunca decide a qué nodo ir.** Las funciones `_route_*()` en [agent.py](src/agents/support/agent.py) son código Python puro que leen el estado y retornan el nombre del siguiente nodo. El LLM solo participa en la lógica de _contenido_ dentro del nodo, nunca en la lógica de _navegación_ del grafo.

#### Justificación de esta elección para el dominio académico

| Requisito del sistema                           | Por qué FSM Agent es la respuesta                                   |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| Onboarding multi-paso obligatorio               | El grafo garantiza que cada fase se complete antes de avanzar       |
| No se puede saltar pasos (ej: plan sin horario) | Las aristas condicionales bloquean transiciones inválidas           |
| Recuperación entre sesiones (días después)      | El checkpointing restaura exactamente la fase donde quedó           |
| Auditable para tesis académica                  | El grafo es un diagrama explícito de todo el comportamiento posible |
| Flujos opcionales (OAuth, personalization)      | Feature flags en los `_route_*()` sin modificar el grafo base       |

---

## 15. Cómo se Conectan las APIs Externas

El sistema interactúa con tres APIs externas. Ninguna se llama directamente desde nodos o servicios — siempre a través de la capa `src/integrations/`.

### 15.1 WhatsApp Cloud API

```
RECEPCIÓN (entrada al sistema)
──────────────────────────────────────────────────────────────
WhatsApp Cloud API
  │  POST /webhook  (JSON con entry→changes→messages)
  ▼
FastAPI  app.py:receive_webhook()
  → extract_inbound_messages(payload)     [message_mapper.py]
      itera entry → changes → messages
      retorna List[WhatsAppInboundMessage]  (tipo conocido, no dict crudo)
  → background_tasks.add_task(runner.process_message, msg)
      ↑ desacopla recepción de procesamiento (no bloquea HTTP response)

ENVÍO (salida del sistema)
──────────────────────────────────────────────────────────────
AgentRunner
  → whatsapp_service.send_agent_messages(recipient_id, ai_messages)
      agent_message_to_channel_messages(msg):
          texto    → ChannelOutboundMessage(kind="text")
          imagen   → ChannelOutboundMessage(kind="image")
          doc      → ChannelOutboundMessage(kind="document")
  → WhatsAppCloudClient.send_text(to, text)
      POST https://graph.facebook.com/v18.0/{phone_id}/messages
      Headers: Authorization: Bearer {WHATSAPP_ACCESS_TOKEN}
      Transport: urllib (sin dependencia httpx/requests)

MEDIA (imágenes del estudiante)
──────────────────────────────────────────────────────────────
Nodo request_schedules detecta imagen en el mensaje
  → WhatsAppCloudClient.download_media(media_id)
      GET https://graph.facebook.com/v18.0/{media_id}  → URL firmada
      GET {url_firmada}  → bytes de la imagen
      Guarda en /tmp/  → retorna ruta local
  → Imagen se convierte a base64 → HumanMessage multimodal → LLM
```

### 15.2 Azure OpenAI (LLM + Embeddings)

```
ACCESO VIA SDK DE LANGCHAIN (no HTTP directo)
──────────────────────────────────────────────────────────────
AzureChatOpenAI(
    azure_endpoint   = AZURE_OPENAI_ENDPOINT,
    azure_deployment = AZURE_OPENAI_DEPLOYMENT_NAME,   # gpt-4.1-mini
    api_key          = AZURE_OPENAI_API_KEY,
    api_version      = OPENAI_API_VERSION
)

TRES MODOS DE USO desde los nodos:

1. Conversacional (respuesta libre)
   llm.invoke([HumanMessage(content=prompt)])
   → AIMessage(content="Hola, soy Lara...")
   Usado en: welcome_consent, answer_scope_boundary, guided_academic_support

2. Extracción estructurada (JSON garantizado)
   llm.with_structured_output(StudentProfile).invoke([HumanMessage(...)])
   → StudentProfile(full_name="Ana", semester=4, ...)
   Usado en: collect_profile, parse_schedules_to_events, collect_priorities

3. Multimodal (imagen + texto)
   llm.invoke([HumanMessage(content=[
       {"type": "text", "text": "Extrae el horario de esta imagen"},
       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
   ])])
   → List[Event] extraídos de la foto
   Usado en: parse_schedules_to_events cuando el estudiante envía foto

EMBEDDINGS para RAG:
   AzureOpenAIEmbeddings(model="text-embedding-3-small")
   → embed_query(texto_consulta)  → vector float[1536]
   → pgvector cosine similarity search en rag_corpus
```

### 15.3 Microsoft Graph API (OAuth 2.0)

```
AUTENTICACIÓN: Authorization Code Flow + MSAL
──────────────────────────────────────────────────────────────
1. Agente genera URL de autorización:
   MicrosoftOAuthFlowService.generate_auth_url(student_id)
     → state_token = UUID  →  INSERT INTO microsoft_oauth_pending_states
     → msal.ConfidentialClientApplication.get_authorization_request_url(
           scopes=["Calendars.ReadWrite", "Tasks.ReadWrite", "Mail.Send"],
           state=state_token,
           redirect_uri=MICROSOFT_REDIRECT_URI
       )
     → Retorna URL → se envía al estudiante por WhatsApp

2. Estudiante autoriza en Microsoft → redirige a:
   GET /oauth/callback?code=AUTH_CODE&state=STATE_TOKEN
     → Validar state_token (EXISTS en pending_states)
     → app.acquire_token_by_authorization_code(code, scopes, redirect_uri)
     → Obtiene: access_token (1h) + refresh_token (90d)
     → INSERT INTO microsoft_oauth_tokens (student_id, tokens)
     → DELETE FROM microsoft_oauth_pending_states

3. Cada llamada a Graph API:
   → auth_client.get_valid_token(student_id)
       Si token no expirado → retorna access_token
       Si expirado → app.acquire_token_by_refresh_token(refresh_token, scopes)
                   → actualiza tokens en DB → retorna nuevo access_token

CALENDARIO (Outlook)
──────────────────────────────────────────────────────────────
OutlookCalendarClient.create_event(access_token, calendar_id, event_data)
  POST https://graph.microsoft.com/v1.0/me/calendars/{id}/events
  Headers: Authorization: Bearer {access_token}
  Body: {
    "subject": "Cálculo I",
    "start": {"dateTime": "2026-04-21T08:30:00", "timeZone": "America/Bogota"},
    "end":   {"dateTime": "2026-04-21T11:50:00", "timeZone": "America/Bogota"},
    "recurrence": {"pattern": {"type": "weekly", "daysOfWeek": ["monday"]}}
  }
  → event_id guardado en calendar_sync_state para updates futuros

MICROSOFT TO DO
──────────────────────────────────────────────────────────────
MicrosoftTodoClient.create_task(access_token, list_id, task_data)
  POST https://graph.microsoft.com/v1.0/me/todo/lists/{id}/tasks
  Body: {
    "title": "Parcial Cálculo I",
    "dueDateTime": {"dateTime": "2026-04-25T00:00:00", "timeZone": "America/Bogota"},
    "importance": "high"
  }
```

---

## 16. Cómo se Conectan los Módulos Internos

La conexión entre módulos sigue un **grafo de dependencias unidireccional estricto**. Ninguna capa importa de la capa que está encima de ella.

### 16.1 Dirección de Dependencias

```
src/api/
  └── imports → src/agents/support/agent.py
             → src/integrations/whatsapp/
             → src/services/channels/
             → src/integrations/langgraph/

src/agents/support/  (nodos y flows)
  └── imports → src/agents/support/dependencies.py  (único punto de entrada)
             → src/integrations/ai/  (LLM directo desde nodos que lo necesitan)
             → src/schemas/

src/agents/support/dependencies.py
  └── imports → src/bootstrap/container.py  (única conexión permitida)

src/bootstrap/container.py
  └── imports → src/services/  (factory functions de cada servicio)
             → src/integrations/  (clientes externos)
             → src/repositories/  (implementaciones DB)

src/services/
  └── imports → src/repositories/  (via inyección en constructor)
             → src/integrations/  (via inyección en constructor)
             → src/schemas/

src/repositories/
  └── imports → src/schemas/
             → psycopg (pool de conexiones PostgreSQL)

src/schemas/
  └── imports → pydantic  (no importa nada del proyecto → hoja del grafo)
```

### 16.2 El Mecanismo de Conexión Concreto

```python
# PASO 1 — Bootstrap ensambla la cadena completa al primer acceso
container.get_onboarding_service()
  → build_onboarding_service()
      db_pool      = get_db_pool()                    # psycopg pool
      student_repo = PostgresStudentRepository(db_pool)
      verif_repo   = PostgresVerificationRepository(db_pool)
      mail_client  = MicrosoftMailClient.from_env()
      return OnboardingService(student_repo, verif_repo, mail_client)
                              # inyección por constructor ↑

# PASO 2 — Los nodos piden servicios al facade (nunca al container directamente)
# src/agents/support/nodes/persist_profile/node.py
from agents.support.dependencies import get_onboarding_service

def persist_profile(state: AgentState) -> dict:
    service = get_onboarding_service()   # → container → singleton ya construido
    result  = service.persist_student(profile)
    return {"phase": "schedules", "student_profile": profile}

# PASO 3 — LangGraph conecta nodos vía el grafo compilado
graph = StateGraph(AgentState)
graph.add_node("persist_profile", persist_profile)
graph.add_node("request_schedules", request_schedules)
graph.add_conditional_edges(
    "persist_profile",
    _route_persist_profile,       # función Python pura
    {"schedules": "request_schedules", "profile": "collect_profile"}
)
agent = graph.compile(checkpointer=PostgresLangGraphCheckpointer(db_url))
```

### 16.3 Visualización Completa del Flujo de Conexiones

```
WhatsApp Cloud API
        │ POST /webhook
        ▼
FastAPI (src/api/app.py)
        │ background_task
        ▼
AgentRunner (src/api/agent_runner.py)
        │
        ├─── agent.invoke(input, {thread_id})
        │         │
        │    PostgresLangGraphCheckpointer
        │    ├── GET checkpoint → restaura AgentState
        │    │
        │    LangGraph StateGraph
        │    ├── _route_*(state) → nombre del siguiente nodo
        │    └── nodo_actual(state) → dict con campos actualizados
        │              │
        │              ├── dependencies.get_*_service()
        │              │         │
        │              │    AppContainer (singleton)
        │              │         │
        │              │    Service.__init__(repo, integration_client)
        │              │         │
        │              │    Repository.method() → psycopg → PostgreSQL
        │              │    Integration.method() → HTTP → API externa
        │              │
        │              └── llm.invoke(prompt) → Azure OpenAI
        │
        ├─── checkpointer.put(state) → PostgreSQL
        │
        └─── whatsapp_service.send_agent_messages()
                  └── WhatsAppCloudClient.send_text() → WhatsApp Cloud API

Estudiante recibe mensaje
```

### 16.4 Por Qué Este Diseño de Conexión es Robusto

| Decisión                                                               | Beneficio concreto                                                                   |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `dependencies.py` como única puerta de entrada a servicios desde nodos | Un nodo nunca necesita saber cómo se construye un servicio                           |
| Repositorios como `Protocol`                                           | Un servicio puede testearse con `MockRepository` sin tocar la DB                     |
| `AppContainer` con `set_*()` para testing                              | Se puede inyectar cualquier mock en cualquier test sin monkey-patching               |
| Ningún módulo instancia sus dependencias internamente                  | Cero acoplamiento oculto; todo el grafo de dependencias es legible en `container.py` |
| LangGraph como bus de estado                                           | Los nodos se comunican solo a través del estado, nunca llamándose entre sí           |

---

## 18. Resumen Ejecutivo

Lara AI es un **agente académico orientado a fases** donde cada turno de conversación del estudiante vía WhatsApp dispara la reanudación de una máquina de estados persistida en PostgreSQL. El grafo LangGraph garantiza que el agente siempre sabe en qué fase está la estudiante, qué información falta recolectar y qué acción realizar a continuación.

La arquitectura está bien separada en capas con responsabilidades claras:

- **API** recibe y despacha eventos de WhatsApp
- **AgentRunner** conecta el canal con el grafo
- **Nodos** orquestan sin contener lógica
- **Services** contienen el dominio académico
- **Repositories** abstraen el acceso a datos
- **Integrations** encapsulan APIs externas (WhatsApp, Azure OpenAI, Microsoft Graph)

La fortaleza principal del sistema es la **trazabilidad completa de la conversación** mediante checkpointing por thread_id, que permite al agente retomar cualquier conversación exactamente donde quedó, incluso días después, sin pérdida de contexto.
