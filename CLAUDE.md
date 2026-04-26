# Academic AgentAI — CLAUDE.md

Asistente académico conversacional multi-fase (WhatsApp → LangGraph → PostgreSQL → Microsoft 365).

---

## Comandos

```bash
# Instalar dependencias
uv sync

# Correr todos los tests
PYTHONPATH=src python -m pytest tests/ -v

# Correr un test específico
PYTHONPATH=src python -m pytest tests/test_nombre.py -v

# Levantar el servidor local
uvicorn src.api.main:app --reload

# Ingestar corpus RAG
python scripts/build_rag_corpus.py

# Aplicar migraciones (orden numérico, manual)
psql $DATABASE_URL -f migrations/0001_onboarding_students.sql
```

> Los tests no requieren DB real si el repositorio usa la implementación in-memory (mock).
> Los tests de integración sí requieren PostgreSQL activo y migraciones aplicadas.

---

## Estructura de Directorios

```
src/
├── agents/support/         # State machine LangGraph: nodos, flujos, routing
│   ├── nodes/              # Un directorio por nodo (node.py + prompt.py)
│   ├── flows/              # Sub-flujos multi-turno (onboarding, scheduling, planning...)
│   └── agent.py            # Grafo LangGraph: nodos + aristas condicionales
├── bootstrap/              # AppContainer — DI singleton, lazy-init de servicios
├── integrations/           # Clientes externos (AI, WhatsApp, MS Graph, LangGraph)
├── repositories/           # Capa de datos por dominio (Protocol + PostgreSQL + mock)
├── schemas/                # Modelos Pydantic del dominio
├── services/               # Lógica de negocio por dominio
└── rag/                    # Pipeline RAG (ingestion, retrieval, prompting)

migrations/                 # DDL SQL numerados (0001…0020)
tests/                      # pytest — conftest.py añade src/ al PYTHONPATH
scripts/                    # Cron jobs y utilidades de mantenimiento
knowledge_base/             # Markdowns del corpus RAG (estrategias de estudio)
```

---

## Reglas de Arquitectura

**Estas reglas son no negociables. Romperlas introduce bugs difíciles de rastrear.**

1. **Sin lógica de negocio en nodos.** Los nodos orquestan: llaman servicios y actualizan estado. La lógica vive en `services/`.

2. **Sin acceso directo a DB desde servicios.** Siempre via repositorios (`src/repositories/`).

3. **DI exclusiva via AppContainer.** Los servicios se registran en `src/bootstrap/container.py`. Los nodos los obtienen únicamente via `src/agents/support/dependencies.py`.

4. **Los nodos retornan `dict` parcial.** LangGraph hace merge — solo incluir los campos que cambian. Nunca retornar el `AgentState` completo.

5. **Acceder al estado via particiones tipadas:**
   ```python
   state.conversation_state   # phase, messages, awaiting_user_input
   state.onboarding_state     # consent, student_profile, email_verification
   state.scheduling_state     # raw_inputs, events, schedule, extras
   state.planning_state       # subjects, priorities, study_plan, replan
   state.integration_state    # calendar sync metadata
   ```
   Nunca acceder directamente a campos del `AgentState` plano desde lógica de negocio.

6. **Feature flags antes de flujos opcionales:**
   ```python
   is_personalization_enabled()
   is_microsoft_oauth_required()
   is_post_radar_flow_enabled()
   is_study_session_tracking_enabled()
   ```

7. **Nuevos servicios:** registrar en `AppContainer` → exponer en `dependencies.py` → usar desde el nodo.

8. **Nuevos repositorios:** definir Protocol → implementación PostgreSQL → implementación in-memory para tests. Recibir por inyección, nunca instanciar directamente.

---

## Gotchas Críticos

> Estos son errores reales que ya ocurrieron en el proyecto.

### `ScheduleReviewStage` — registro doble obligatorio
Cuando se agrega un nuevo stage al flujo de revisión de horarios, hay que actualizar **dos lugares**:
1. `ScheduleReviewStage` Literal en `src/services/scheduling/constants.py`
2. `_SECTION_REVIEW_STAGES` set en `src/agents/support/flows/scheduling/section_confirmation_service.py`

Olvidar cualquiera de los dos → Pydantic lanza `literal_error` en runtime.

### Nuevas fases del agente — registro doble obligatorio
1. Agregar el valor al enum `Phase` en `src/agents/support/state.py`
2. Agregar la arista condicional en `src/agents/support/agent.py`

### `awaiting_user_input`
- Ponerlo en `True` cuando el nodo emite un mensaje y espera respuesta.
- Ponerlo en `False` cuando el nodo procesa la respuesta y avanza de fase.
- LangGraph usa este flag para decidir si el grafo se detiene a esperar input.

### Convenciones de nombres de campo
Los campos de entidades de dominio (`Event`, `ExtracurricularItem`, etc.) están en **español**: `dia`, `titulo`, `prioridad`, `dificultad`, `inicio`, `fin`. No cambiar a inglés.

---

## Enums y Tipos Clave

```python
# src/schemas/common.py
Occupation = Literal["solo_estudio", "ambos", "ninguna"]
Prioridad  = Literal["alta", "media", "baja"]

# src/schemas/scheduling.py
EventCategory        = Literal["academico", "laboral", "extracurricular", "estudio"]
ScheduleBlockType    = Literal["academic", "work", "extracurricular"]

# src/services/scheduling/constants.py
DayOfWeek            = Literal["monday", "tuesday", ..., "sunday"]

# src/schemas/planning.py
AcademicActivityType = Literal["parcial", "quiz", "tarea", "taller",
                                "entrega", "exposicion", "proyecto", "estudio_pendiente"]
```

---

## Fases del Agente

```
consent → profile → email_verification → microsoft_oauth
       → schedules → extras → draft → validate → schedule_persist → schedule_sync
       → study_profile → priorities → study_plan
       → running
            ├→ replan
            ├→ academic_update
            ├→ answer_recommendation
            └→ scope_boundary
```

Ver detalles de nodos y routing en `.claude/rules/agent.md`.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Agente | LangGraph 1.0.8 (Pregel state machine) |
| LLM | Azure OpenAI GPT-4.1-mini |
| Embeddings | Azure text-embedding-3-small (1536 dims) |
| Base de datos | PostgreSQL 13+ via psycopg |
| Validación | Pydantic 2.x |
| Canal | WhatsApp Cloud API |
| Calendario | Microsoft Graph API |
| Paquetes | uv + pyproject.toml |
| `thread_id` | Identificador canónico de conversación (LangGraph checkpointer) |
