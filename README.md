<div align="center">

<img src="assets/agent/Logo_lara_ai.png" alt="Lara AI Logo" width="180"/>

# Lara — Agente de IA para la Gestión Académica

**Asistente conversacional inteligente para estudiantes universitarios**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0.8-FF6B35?style=flat-square&logo=graph&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-336791?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Azure](https://img.shields.io/badge/Azure-OpenAI-0078D4?style=flat-square&logo=microsoft-azure&logoColor=white)](https://azure.microsoft.com)
[![WhatsApp](https://img.shields.io/badge/WhatsApp-Cloud%20API-25D366?style=flat-square&logo=whatsapp&logoColor=white)](https://developers.facebook.com/docs/whatsapp)
[![License](https://img.shields.io/badge/Licencia-Académica-lightgrey?style=flat-square)](LICENSE)

---

*Lara es un agente conversacional de inteligencia artificial que acompaña al estudiante universitario en todo su proceso de organización académica: desde capturar su horario semanal hasta planificar sesiones de estudio, sincronizarlas con su calendario de Microsoft 365 y recomendarle técnicas de aprendizaje personalizadas.*

</div>

---

## Tabla de Contenidos

- [Descripción del Proyecto](#-descripción-del-proyecto)
- [Características Principales](#-características-principales)
- [Arquitectura del Sistema](#-arquitectura-del-sistema)
- [Flujo Conversacional](#-flujo-conversacional)
- [Módulos del Agente](#-módulos-del-agente)
- [Pipeline RAG de Recomendaciones](#-pipeline-rag-de-recomendaciones)
- [Integración con Microsoft 365](#-integración-con-microsoft-365)
- [Stack Tecnológico](#-stack-tecnológico)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Variables de Entorno](#-variables-de-entorno)
- [Migraciones de Base de Datos](#-migraciones-de-base-de-datos)
- [Ejecución de Tests](#-ejecución-de-tests)
- [Despliegue en Azure](#-despliegue-en-azure)
- [API Reference](#-api-reference)
- [Equipo](#-equipo)

---

## Descripción del Proyecto

**Lara** es el resultado de un proyecto de grado que aborda una problemática central en la vida universitaria: **la dificultad de organizar el tiempo de estudio de manera efectiva**. Muchos estudiantes carecen de herramientas accesibles que les permitan planificar sus actividades académicas, gestionar sus tiempos libres y adoptar métodos de estudio comprobados —todo ello integrado en un canal que ya usan a diario: **WhatsApp**.

El agente opera como un asistente personal académico que:

1. **Aprende el contexto del estudiante** mediante una conversación guiada (onboarding) en la que recoge su perfil, horario semanal y actividades extracurriculares.
2. **Genera un plan de estudio personalizado** con bloques de tiempo asignados para cada materia, respetando la carga académica y las preferencias del estudiante.
3. **Sincroniza el plan** automáticamente con Outlook Calendar y Microsoft To Do.
4. **Envía recordatorios proactivos** vía WhatsApp para mantener al estudiante en el camino correcto.
5. **Recomienda técnicas y métodos de estudio** pertinentes usando un motor de búsqueda semántica (RAG) sobre una base de conocimiento curada.
6. **Replantea el plan** de forma dinámica cuando el estudiante lo solicita o cuando sus actividades cambian.

---

## Características Principales

### Gestión del Tiempo Académico

| Funcionalidad | Descripción |
|---|---|
| **Captura de horario** | Ingesta el horario universitario semanal (texto o imagen) con extracción automática de eventos académicos |
| **Actividades extracurriculares** | Registra trabajo, deporte, compromisos y bloques de disponibilidad |
| **Plan de estudio personalizado** | Genera sesiones de estudio distribuidas según prioridades, dificultad y fechas de evaluación |
| **Replanificación dinámica** | Ajusta el plan ante cambios de agenda, entregas nuevas o sesiones perdidas |
| **Recordatorios WhatsApp** | Notificaciones proactivas antes de cada bloque de estudio o entrega importante |

### Sincronización con Microsoft 365

| Funcionalidad | Descripción |
|---|---|
| **Outlook Calendar** | Sincroniza el horario fijo y el plan de estudio como eventos en el calendario |
| **Microsoft To Do** | Refleja las actividades académicas como tareas con fechas de vencimiento |
| **OAuth Microsoft** | Autenticación con cuentas personales de Microsoft para el piloto estudiantil |
| **Reparación automática** | Detecta y corrige divergencias entre el plan y el estado del calendario |

### Recomendaciones de Estudio con IA

| Funcionalidad | Descripción |
|---|---|
| **Motor RAG híbrido** | Recuperación semántica (vectorial) + léxica sobre corpus curado de técnicas de estudio |
| **Personalización Radar** | Cuestionario de perfil cognitivo (8 dimensiones) para ajustar recomendaciones |
| **Soporte socrático** | Modo de acompañamiento que guía al estudiante con preguntas en lugar de respuestas directas |
| **Base de conocimiento** | 15 documentos sobre técnicas (Pomodoro, Feynman, Cornell, repetición espaciada) y métodos |

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WhatsApp Cloud API                           │
│                    (Canal de entrada/salida)                        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ Webhook HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                              │
│         /webhook  │  /oauth/callback  │  /tasks/reminders/run       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LangGraph State Machine                        │
│                                                                     │
│   __entry__                                                         │
│       │                                                             │
│       ├──► welcome_consent ──► collect_profile                      │
│       │                              │                              │
│       │                    request_microsoft_oauth                  │
│       │                              │                              │
│       ├──► collect_schedule ◄────────┘                              │
│       │         │                                                   │
│       ├──► collect_study_profile                                     │
│       │         │                                                   │
│       ├──► collect_priorities                                        │
│       │         │                                                   │
│       └──► academic_agent (running)                                 │
│                 ├── replan          ├── academic_update             │
│                 ├── recommendation  └── scope_boundary              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   PostgreSQL    │  │  Azure OpenAI    │  │  Microsoft Graph  │
│  (Checkpointer  │  │  GPT-4.1-mini   │  │  Outlook + To Do  │
│   + 23 tablas)  │  │  Embeddings 3-S  │  │  OAuth 2.0        │
└─────────────────┘  └──────────────────┘  └──────────────────┘
```

### Principios de Diseño

El agente sigue una arquitectura en capas con separación estricta de responsabilidades:

- **Nodos** — orquestan el flujo; llaman servicios y actualizan estado. Sin lógica de negocio.
- **Servicios** — contienen toda la lógica de negocio del dominio.
- **Repositorios** — capa de acceso a datos (Protocol + PostgreSQL + in-memory para tests).
- **AppContainer** — contenedor de inyección de dependencias, lazy-init de todos los servicios.
- **Integraciones** — clientes externos (Azure OpenAI, WhatsApp, Microsoft Graph).

---

## Flujo Conversacional

El agente avanza de forma lineal a través de fases de **onboarding** y luego opera en modo continuo:

```
consent
  └─► profile
        └─► email_verification
              └─► microsoft_oauth          ← bloqueante (configurable)
                    └─► schedules
                          └─► extras
                                └─► draft
                                      └─► validate
                                            └─► schedule_persist
                                                  └─► schedule_sync
                                                        └─► study_profile  (Radar)
                                                              └─► priorities
                                                                    └─► running
                                                                          ├─► replan
                                                                          ├─► academic_update
                                                                          ├─► answer_recommendation
                                                                          └─► scope_boundary
```

Cada fase corresponde a un **nodo LangGraph** con routing condicional. El flag `awaiting_user_input` controla si el grafo se detiene a esperar respuesta del usuario o avanza automáticamente.

---

## Módulos del Agente

### Nodos del Grafo (`src/agents/support/nodes/`)

| Nodo | Fase | Responsabilidad |
|---|---|---|
| `__entry__` | — | Enrutador de entrada; detecta fase actual y nuevo input |
| `welcome_consent` | `consent` | Presenta la política de datos y solicita consentimiento |
| `collect_profile` | `profile` | Extrae nombre, código estudiantil, email y edad |
| `request_microsoft_oauth` | `microsoft_oauth` | Bloqueo hasta que el estudiante autoriza Microsoft Entra |
| `collect_schedule` | `schedules → schedule_persist` | Orquesta captura, validación y persistencia del horario |
| `collect_study_profile` | `study_profile` | Aplica cuestionario Radar de 8 dimensiones cognitivas |
| `collect_priorities` | `priorities` | Captura prioridades semanales de materias |
| `academic_agent` | `running` | Agente operativo: replan, recomendaciones, actualizaciones |

### Flujos Multi-turno (`src/agents/support/flows/`)

| Flujo | Descripción |
|---|---|
| `scheduling/` | Captura de horario (texto/imagen), validación, draft, confirmación por sección, persistencia |
| `replanning/` | Análisis de modificaciones solicitadas, propuesta y aplicación de cambios |
| `planning/` | Orquestación de la materialización del plan de estudio |
| `academic_update/` | Registro y actualización de actividades puntuales (parciales, entregas, talleres) |
| `priorities/` | Captura semanal de prioridades por materia |
| `onboarding/` | Dispatcher y recolección de perfil base |
| `sync/` | Sincronización con Outlook Calendar y Microsoft To Do |

### Servicios de Dominio (`src/services/`)

| Servicio | Responsabilidad |
|---|---|
| `OnboardingService` | Validación de perfil, extracción de slots conversacionales |
| `ScheduleService` | Parsing de horarios en lenguaje natural e imágenes |
| `PersonalizationService` | Cuestionario Radar, scoring por dimensión |
| `StudyPlanMaterializationService` | Cálculo y distribución de bloques de estudio |
| `StudyReplanningService` | Replanificación automática ante cambios |
| `StudyPlanRemindersService` | Dispatching de recordatorios con políticas de reenvío |
| `StudySessionTrackingService` | Registro de sesiones completadas y perdidas |
| `StudyRecommendationService` | Recuperación RAG de técnicas y métodos |
| `OutlookCalendarSyncService` | Proyección del plan en Outlook |
| `MicrosoftTodoSyncService` | Sincronización de tareas en Microsoft To Do |

---

## Pipeline RAG de Recomendaciones

El motor de recomendaciones utiliza **Retrieval-Augmented Generation** sobre una base de conocimiento curada de técnicas y métodos de estudio:

```
Pregunta del estudiante
        │
        ▼
┌───────────────────────┐
│   Query Embedding     │  Azure text-embedding-3-small (1536 dims)
└──────────┬────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌─────────┐  ┌──────────┐
│ Vector  │  │ Lexical  │   top-k=8 cada canal
│ Search  │  │ Search   │
└────┬────┘  └────┬─────┘
     │             │
     └──────┬──────┘
            ▼
     ┌────────────┐
     │  Reranking │  Fusión y selección final (top-5)
     └─────┬──────┘
           ▼
     ┌────────────┐
     │ GPT-4.1-m  │  Generación de respuesta contextualizada
     └────────────┘
```

### Base de Conocimiento (`knowledge_base/study_recommendations/`)

**Técnicas de Estudio (8 documentos):**
- Técnica Pomodoro, Técnica Feynman, Notas Cornell
- Repetición Espaciada, Interleaving, Mapas Conceptuales
- Mnemotecnia, Recuperación Activa

**Métodos de Evaluación (4 documentos):**
- Lectura y síntesis, Parcial teórico, Repaso semanal, Evaluación numérica

**Marcos Conceptuales (2 documentos):**
- Diferencia técnica vs. método de estudio
- Árbol de decisión para selección de técnica

---

## Integración con Microsoft 365

> **Estado actual del piloto:** la integración con Outlook Calendar y Microsoft To Do está orientada a **cuentas personales de Microsoft** de los estudiantes. Inicialmente se intentó operar con las cuentas Outlook institucionales de la universidad, pero no fue posible completar esa implementación por gestión de permisos y aprobación administrativa sobre Microsoft Entra ID. Una vez la universidad tramite y apruebe los permisos necesarios, el mismo flujo OAuth podrá habilitarse para el correo universitario/institucional.

### Flujo de Autorización OAuth

```
Estudiante                   Lara (API)              Microsoft Entra
     │                           │                         │
     │  1. Inicia onboarding     │                         │
     │──────────────────────────►│                         │
     │                           │  2. Genera auth URL     │
     │                           │────────────────────────►│
     │  3. Recibe enlace OAuth   │                         │
     │◄──────────────────────────│                         │
     │  4. Autoriza en browser   │                         │
     │────────────────────────────────────────────────────►│
     │                           │  5. Callback + code     │
     │                           │◄────────────────────────│
     │                           │  6. Intercambia tokens  │
     │                           │────────────────────────►│
     │  7. Continúa onboarding   │                         │
     │◄──────────────────────────│                         │
```

### Sincronización de Calendario

Una vez autorizado, el agente mantiene sincronización bidireccional:

- **Horario fijo** → Eventos recurrentes en Outlook Calendar
- **Plan de estudio** → Bloques de tiempo en el calendario de la semana actual
- **Actividades académicas** → Tareas con fecha de vencimiento en Microsoft To Do
- **Reparación automática** → Detecta y corrige eventos faltantes o erróneos

---

## Stack Tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ |
| Agente / Orquestación | LangGraph (Pregel state machine) | 1.0.8 |
| LLM | Azure OpenAI GPT-4.1-mini | 2024-12-01-preview |
| Embeddings | Azure OpenAI text-embedding-3-small | 1536 dims |
| Base de Datos | PostgreSQL + psycopg3 | 13+ |
| Validación de Esquemas | Pydantic | 2.x |
| API HTTP | FastAPI + Uvicorn | 0.115+ |
| Canal de Mensajería | WhatsApp Cloud API | v21 |
| Calendario / Tareas | Microsoft Graph API | v1.0 |
| Autenticación | Microsoft Entra ID (OAuth 2.0) | — |
| Gestión de Paquetes | uv | — |
| Contenedorización | Docker (multi-stage) | — |
| Plataforma Cloud | Azure Container Apps | — |

---

## Estructura del Proyecto

```
academic_agentAI/
│
├── src/
│   ├── agents/support/             # Motor LangGraph del agente
│   │   ├── nodes/                  # 36 nodos (node.py + prompt.py por nodo)
│   │   ├── flows/                  # 7 flujos multi-turno
│   │   ├── agent.py                # Grafo: nodos + aristas condicionales
│   │   ├── state.py                # AgentState + particiones tipadas
│   │   └── dependencies.py         # Acceso a servicios desde nodos
│   │
│   ├── bootstrap/
│   │   └── container.py            # AppContainer — DI singleton (30+ servicios)
│   │
│   ├── integrations/
│   │   ├── ai/                     # Azure OpenAI: LLM, embeddings, audio
│   │   ├── microsoft_graph/        # OAuth, Outlook, Microsoft Graph client
│   │   ├── whatsapp/               # Cloud API, webhook parsing
│   │   ├── embeddings/             # Cliente de embeddings
│   │   └── langgraph/              # PostgreSQL checkpointer
│   │
│   ├── repositories/               # Capa de datos (Protocol + PostgreSQL + mock)
│   ├── services/                   # Lógica de negocio por dominio (13 módulos)
│   ├── schemas/                    # Modelos Pydantic del dominio
│   ├── rag/                        # Pipeline RAG (ingestion, retrieval, prompting)
│   └── api/
│       ├── app.py                  # FastAPI application
│       └── agent_runner.py         # Orquestador del grafo LangGraph
│
├── migrations/                     # 23 scripts DDL SQL numerados
├── knowledge_base/
│   └── study_recommendations/      # Corpus RAG (técnicas y métodos de estudio)
├── tests/                          # 98 archivos de tests (pytest)
├── scripts/                        # Workers, sync jobs, utilidades
│   └── deploy/                     # Scripts de despliegue Azure
├── assets/
│   ├── agent/                      # Logo y recursos del agente
│   └── whatsapp/                   # Imágenes de respuestas WhatsApp
├── docs/                           # Documentación de arquitectura y análisis
│
├── pyproject.toml                  # Dependencias (uv)
├── Dockerfile                      # Multi-stage build
├── langgraph.json                  # Configuración LangGraph API
└── main.py                         # Punto de entrada Uvicorn
```

---

## Instalación y Configuración

### Prerrequisitos

- Python 3.11+
- PostgreSQL 13+
- [uv](https://docs.astral.sh/uv/) — gestor de paquetes
- Cuenta Azure con Azure OpenAI habilitado
- Cuenta de desarrollador de Meta (WhatsApp Cloud API)
- Aplicación registrada en Microsoft Entra ID

### 1. Clonar el Repositorio

```bash
git clone https://github.com/tu-usuario/academic-agentAI.git
cd academic-agentAI
```

### 2. Instalar Dependencias

```bash
uv sync
```

### 3. Configurar Variables de Entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales (ver sección Variables de Entorno)
```

### 4. Aplicar Migraciones

```bash
# Aplicar en orden numérico
psql $DATABASE_URL -f migrations/0001_onboarding_students.sql
psql $DATABASE_URL -f migrations/0002_recurring_schedule_profiles.sql
# ... continuar hasta 0023
```

### 5. Construir el Corpus RAG

```bash
PYTHONPATH=src python scripts/build_rag_corpus.py
```

### 6. Levantar el Servidor

```bash
uvicorn src.api.main:app --reload
```

El servidor queda disponible en `http://localhost:8000`.

---

## Variables de Entorno

```ini
# ─── Azure OpenAI ─────────────────────────────────────────
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://<tu-recurso>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS=embeddings-3-small
OPENAI_API_VERSION=2024-12-01-preview

# ─── PostgreSQL ───────────────────────────────────────────
PGHOST=
PGPORT=5432
PGDATABASE=academic_agent
PGUSER=
PGPASSWORD=

# ─── WhatsApp Cloud API ───────────────────────────────────
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=

# ─── Microsoft Graph / OAuth ──────────────────────────────
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_TENANT_ID=
MICROSOFT_REDIRECT_URI=https://<tu-dominio>/oauth/callback
ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=true

# ─── RAG ──────────────────────────────────────────────────
RAG_ENABLED=true
RAG_CORPUS_ROOT=knowledge_base/study_recommendations
RAG_EMBEDDING_PROVIDER=azure_openai
RAG_EMBEDDING_MODEL=embeddings-3-small
RAG_TOP_K_VECTOR=8
RAG_TOP_K_LEXICAL=8
RAG_TOP_K_FINAL=5

# ─── Servidor HTTP ────────────────────────────────────────
PORT=8000
LOG_LEVEL=INFO
RELOAD=false
```

---

## Migraciones de Base de Datos

El esquema de la base de datos se construye mediante 23 migraciones SQL aplicadas en orden numérico:

| Migración | Propósito |
|---|---|
| `0001` | Tabla `students` — perfiles de estudiantes |
| `0002` | `recurring_schedule_profiles` — horarios fijos semanales |
| `0003` | Checkpointer LangGraph — persistencia de threads |
| `0004` | `personalization_profiles` — perfiles Radar |
| `0007` | `study_planning_profiles` — planes de estudio |
| `0009` | `study_plan_instances` + tracking de sesiones |
| `0010` | `reminder_policies` + historial de despachos |
| `0011` | `replan_requests` + propuestas de replanificación |
| `0013` | `microsoft_graph_connections` + metadatos de sync |
| `0016` | `rag_study_recommendations` — embeddings del corpus |
| `0019` | `academic_activities` — actividades puntuales |
| `0020` | `reminder_dispatch_retry` — reintentos de recordatorio |

---

## Ejecución de Tests

```bash
# Todos los tests (sin DB real)
PYTHONPATH=src python -m pytest tests/ -v

# Tests de un módulo específico
PYTHONPATH=src python -m pytest tests/test_schedule_parser.py -v

# Tests de integración (requieren PostgreSQL activo)
PYTHONPATH=src python -m pytest tests/integration/ -v
```

El proyecto cuenta con **98 archivos de tests** organizados por dominio:

| Suite | Archivos | Cobertura |
|---|---|---|
| Agent / Routing | 12 | State machine, routing condicional, particiones de estado |
| Scheduling | 9 | Parser de horarios, validación, gestión horario fijo |
| Planning | 11 | Materialización, tracking, replanificación |
| RAG | 9 | Retrieval, chunking, ranking, evaluación |
| Microsoft / Sync | 12 | OAuth, Outlook, Microsoft To Do |
| Onboarding | 6 | Extracción de slots, validación de perfil |
| Recordatorios | 4 | Dispatching, políticas, reintentos |
| Servicios / Bootstrap | 9 | AppContainer, Azure OpenAI config |
| Utilidades | 12 | Procesamiento de imágenes, rendering |

---

## Despliegue en Azure

El agente está optimizado para ejecutarse como un **Azure Container App**:

```bash
# 1. Preflight — verificar recursos Azure
bash scripts/deploy/01_preflight_azure_pilot.sh

# 2. Build y deploy de la imagen Docker
bash scripts/deploy/02_build_and_deploy_containerapp.sh

# 3. Deploy del job de recordatorios (Azure Container Job)
bash scripts/deploy/03_deploy_reminder_job.sh
```

### Arquitectura de Despliegue

```
Azure Container Apps
├── academic-agent-app          # API FastAPI + LangGraph
│   └── Dockerfile (multi-stage, python:3.11-slim)
│
├── academic-agent-reminders    # Azure Container Job (cron)
│   └── scripts/run_due_reminders.py
│
└── azure-pilot.env             # Variables de entorno de producción

Azure PostgreSQL Flexible Server
└── academic_agent DB (23 tablas)

Azure OpenAI
├── gpt-4.1-mini deployment
└── text-embedding-3-small deployment
```

---

## API Reference

| Endpoint | Método | Autenticación | Descripción |
|---|---|---|---|
| `/health` | `GET` | — | Health check para Azure Load Balancer |
| `/webhook` | `POST` | HMAC-SHA256 | Ingesta de mensajes WhatsApp Cloud API |
| `/webhook` | `GET` | Verify Token | Verificación de webhook Meta |
| `/oauth/callback` | `GET` | — | Callback OAuth Microsoft Entra ID |
| `/tasks/reminders/run` | `POST` | Worker Token | Trigger del worker de recordatorios |
| `/legal/privacy-policy` | `GET` | — | Política de privacidad (Habeas Data) |

### Seguridad

- Los webhooks de WhatsApp se validan con `X-Hub-Signature-256` (HMAC-SHA256 sobre el body).
- El endpoint de recordatorios requiere un token de worker en el header `x-reminder-worker-token`.
- El flujo OAuth sigue el estándar Authorization Code Flow de Microsoft Entra ID.

---

## Equipo

Este proyecto fue desarrollado como trabajo de grado en **Ingeniería de Sistemas**, con el objetivo de aportar una solución tecnológica real al reto de la gestión del tiempo en el entorno universitario colombiano.

---

<div align="center">

**Lara — Tu compañera de estudio inteligente**

*Construido con LangGraph · Azure OpenAI · WhatsApp · Microsoft 365*

</div>
