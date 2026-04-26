# Plan de Refactorización — De Chatbot a Agente Autónomo

## 1. ¿ReAct o qué arquitectura?

**ReAct sí es la dirección correcta, pero necesitas entender qué es exactamente aquí.**

ReAct (Reasoning + Acting) en LLMs modernos = **Tool-Calling Agent**: el LLM recibe herramientas, razona sobre qué hacer, llama herramientas, observa resultados, vuelve a razonar, y eventualmente responde. LangGraph tiene `create_react_agent` que implementa exactamente este loop.

**Por qué ReAct puro no es suficiente solo:**
El onboarding (recoger perfil, horario, Radar) necesita ser estructurado. No puedes dejarle al LLM decidir si "preguntar el nombre antes o el horario" — necesitas esos datos en orden para que el agente tenga contexto suficiente para actuar. El LLM libre allí introduce errores, olvida preguntar campos, o inventa datos.

**Arquitectura recomendada: Onboarding FSM + Agent ReAct**

`┌─────────────────────────────────────────────────────────────┐
│  ONBOARDING (FSM estructurado — recolector de datos)        │
│                                                             │
│  consent → profile → schedule → radar → priorities         │
│                                                             │
│  Propósito: capturar datos limpios y validados              │
│  LLM rol: parsear texto libre, extraer estructuras          │
└───────────────────────┬─────────────────────────────────────┘
                        │ datos completos: perfil + horario + 
                        │ radar + prioridades + actividades
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  ACADEMIC AGENT (ReAct — agente autónomo)                   │
│                                                             │
│  ┌──────────────────────────────────────┐                   │
│  │  LLM con contexto completo del       │                   │
│  │  estudiante + herramientas           │                   │
│  │                                      │                   │
│  │  Razón → Tool → Observa → Razón...   │                   │
│  └──────────────────────────────────────┘                   │
│                                                             │
│  Herramientas:                                              │
│  • search_study_methods(query)  ← RAG                      │
│  • get_study_plan()                                         │
│  • update_study_plan(changes)                               │
│  • add_academic_activity(...)                               │
│  • get_schedule(week)                                       │
│  • get_priorities()                                         │
│  • sync_to_calendar()                                       │
└─────────────────────────────────────────────────────────────┘`

**La diferencia con el chatbot actual:** el chatbot tiene un árbol de decisión determinista — "si el usuario dice X, ir al nodo Y". El agente tiene el LLM como motor de decisión: recibe el mensaje del estudiante + todo su contexto + herramientas, y _él decide_ qué hacer, en qué orden, y qué combinar. Un estudiante que dice "mañana tengo parcial de Cálculo" no activa un handler específico — el agente razona, agrega la actividad, busca en RAG técnicas para parciales de Cálculo según el Radar del estudiante, revisa si hay conflicto con el horario, y responde integrando todo.

---

## 2. Los Bloqueantes — Lo que DEBES arreglar antes de tocar el agente

Estos son los 5 problemas que, si no se resuelven, van a hacer que la refactorización sea imposible o cree deuda nueva.

### BLOQUEANTE 1: `welcome_consent` como dispatcher universal

**Problema actual** en agent.py:647-684: un solo nodo tiene aristas condicionales hacia los 31 nodos del grafo. Cada nodo nuevo que añadas obliga a tocar `welcome_consent` y `_route_welcome`.

**Por qué bloquea el agente:** el nuevo agent node necesita ser un destino desde el entry point. Con la estructura actual, añadirlo significa agregar una arista #32 al mismo nodo dios.

**Fix:** separar el entry point del nodo de consentimiento. El entry point es solo un router sin lógica propia.

### BLOQUEANTE 2: `Phase` enum con 29 valores, 6+ son fantasmas

**Fases que no tienen nodo en el grafo actualmente:**

- `email_verification_send` / `email_verification` — los nodos `send_email_verification` y `verify_email_code` existen en filesystem pero no están registrados en `agent.py`
- `sync` — alias confuso que apunta a `collect_study_profile`
- `academic_activity_management` — aparece en el router pero sin nodo dedicado

**Por qué bloquea:** el checkpointer guarda la `phase` en DB. Si una conversación activa queda con `phase="email_verification"` y esa fase no existe en el nuevo grafo, la recuperación del estado falla silenciosamente.

**Fix:** decidir explícitamente — ¿va verificación OTP? Si sí: registrar los nodos. Si no: eliminar del enum y migrar estados existentes.

### BLOQUEANTE 3: Lógica de negocio en nodos

handle_academic_update/node.py tiene 617 líneas. build_study_plan/node.py tiene 254 con RAG embebido.

**Por qué bloquea:** los tools del nuevo agente van a necesitar llamar exactamente esa lógica. Si está dentro de nodos de LangGraph, no puedes reutilizarla como herramienta sin duplicar código o crear dependencias circulares.

**Fix:** extraer a servicios **antes** de diseñar los tools. Los tools del agente llaman servicios, no nodos.

### BLOQUEANTE 4: Estado plano con ~50 campos y campos duplicados

Los más críticos:

- `events` y `schedule.blocks` contienen lo mismo (lo dice el propio `_DERIVATION_CANDIDATES`)
- `events_validated` es un flag operativo que debería derivarse de la fase
- `extras_has_any` debería derivarse de `len(extracurricular) > 0`

**Por qué bloquea:** el system prompt del agente ReAct necesita recibir el contexto del estudiante de forma limpia. Si el estado tiene campos duplicados con valores potencialmente inconsistentes, el contexto que le pasas al LLM puede ser contradictorio.

**Fix:** consolidar antes de construir el context builder del agente.

### BLOQUEANTE 5: RAG desconectado del agente conversacional

El RAG existe y funciona, pero solo está conectado en `build_study_plan` como metadata silenciosa (el estudiante nunca ve la guía RAG directamente). En el agente nuevo, el RAG debe ser una herramienta de primera clase que el LLM puede invocar cuando lo decide.

**Por qué bloquea:** es el objetivo principal del agente. Si el RAG no está expuesto como tool, el agente nuevo no puede usarlo.

---

## 3. Plan de Refactorización — 6 Fases

### Fase 0: Limpieza Bloqueante

**Objetivo:** dejar el proyecto en estado donde sea posible hacer una refactorización sin romper lo que ya funciona.

**Tarea 0.1 — Resolver fases fantasma (1-2 días)**

`Decisión: ¿va verificación OTP por email?
SI → registrar send_email_verification y verify_email_code en agent.py
NO → eliminar del Phase enum, del router.py, del \_ACTIVE_PHASE_ROUTES dict + migración SQL: UPDATE students SET phase = 'profile'
WHERE phase IN ('email_verification_send', 'email_verification')

Eliminar fase "sync" → reemplazar por "study_profile" en el código donde se usa.
Eliminar "academic_activity_management" del router si no tiene nodo propio.`

**Tarea 0.2 — Extraer lógica de negocio de nodos (2-3 días)**

`handle_academic_update/node.py` → crear `AcademicUpdateOrchestrator` en `src/services/planning/`:

- `handle_activity_confirmation(state, payload)`
- `handle_session_tracking(state, text)`
- `handle_new_activity_request(state, text)`
- El nodo queda en ~60 líneas delegando al orquestador

`build_study_plan/node.py` → mover a `src/services/planning/`:

- `enrich_with_rag_guidance(study_plan, subjects, study_profile)` → `StudyPlanEnrichmentService`
- `enrich_with_applied_methods(study_plan, ...)` → `StudyPlanEnrichmentService`
- El nodo queda en ~40 líneas

**Tarea 0.3 — Separar entry point (1 día)**

Crear un nodo puro `__entry__` que solo hace routing sin lógica propia. `welcome_consent` se convierte en un nodo normal que solo maneja consentimiento. Esto elimina las 31 aristas del nodo dios.

**Tarea 0.4 — Consolidar estado (1-2 días)**

`# Eliminar redundancias:

# 1. events (usar schedule.blocks como fuente de verdad)

# 2. events_validated (derivar de scheduling_state.schedule.review_stage)

# 3. extras_has_any (derivar de len(extracurricular) > 0)

# Documentar explícitamente el contrato:

# flat fields = fuente de verdad (LangGraph persiste esto)

# typed partitions = views de solo lectura (nunca escribir desde aquí)`

---

### Fase 1: Rediseño del Estado del Agente

**Objetivo:** el estado del agente después del onboarding debe ser una representación limpia que se pueda pasar al LLM como contexto.

El estado nuevo tiene dos secciones claras:

`class AgentState: # --- CONVERSACIÓN (siempre en memoria) ---
messages: list[BaseMessage] # historial
phase: Phase # 8 valores, no 29
awaiting_user_input: bool
user_message_count: int
last_user_text: str | None

    # --- DATOS DEL ESTUDIANTE (el contexto del agente) ---
    student_profile: StudentProfile    # nombre, código, carrera, semestre
    schedule: ScheduleProfile          # horario fijo consolidado
    study_profile: StudyProfile        # Radar: top 3 técnicas, scores, señales
    priorities: PrioritiesState        # materias + prioridades semana actual
    academic_activities: list[AcademicActivity]  # actividades registradas
    study_plan: StudyPlanState         # plan generado

    # --- INTEGRACIÓN ---
    calendar: CalendarState
    interaction: InteractionState      # contexto de turno para el agente`

`Phase` se reduce a:

`Phase = Literal[
    "consent",
    "profile", 
    "schedule",    # captura + validación (todo el flujo actual de horarios)
    "radar",       # study_profile + tiebreaker + persist  
    "priorities",
    "running",     # el agente autónomo opera aquí
    "end",
]`

Los sub-estados de cada macro-fase (ej: capture_stage, review_stage) se mantienen dentro de los sub-schemas correspondientes, no como fases top-level del agente.

---

### Fase 2: Simplificación del Grafo de Onboarding

**Objetivo:** el grafo de onboarding queda limpio, con un nodo por macro-fase. Cada nodo maneja internamente sus sub-estados sin exponer fases internas al grafo principal.

`entry_router
    ↓
welcome_consent          (phase: consent)
    ↓
collect_profile          (phase: profile) — delega a flow service
    ↓  
collect_schedule         (phase: schedule) — integra capture + parse + validate + persist
    ↓
collect_study_profile    (phase: radar) — integra radar + tiebreaker + persist
    ↓
collect_priorities       (phase: priorities)
    ↓
academic_agent           (phase: running) ← NUEVO`

Esto es solo **7 nodos** en el grafo principal más el agente. Los subflujos complejos (horario, extracurriculares, sección-por-sección) viven en los flow services donde ya están, no en el grafo.

**Nodos que desaparecen del grafo principal:**`parse_schedules_to_events`, `ask_extracurricular`, `collect_extracurricular_details`, `build_draft_schedule`, `render_schedule_preview`, `validate_schedule`, `apply_schedule_correction`, `persist_schedule`, `sync_fixed_schedule`, `collect_study_profile_tiebreaker`, `persist_study_profile`, `build_study_plan`, `confirm_profile`, `persist_profile` — todos pasan a ser pasos internos de sus respectivos flow services.

**Nodos que desaparecen por completo (reemplazados por el agente):**`guided_academic_support`, `handle_academic_update`, `request_replan`, `view_weekly_agenda`, `view_tasks`, `answer_study_recommendation`, `answer_scope_boundary`, `manage_fixed_schedule`, `sync_study_calendar`, `sync_study_todo`, `renew_fixed_schedule`, `repair_fixed_schedule`

---

### Fase 3: Diseño del Agente Autónomo

**Objetivo:** definir las herramientas, el system prompt, y el context builder del agente.

**Context Builder** — lo que el agente recibe como contexto en el system prompt:

`def build_agent_context(state: AgentState) -> str:
"""Construye el contexto completo del estudiante para el system prompt."""
return f"""
Eres el asistente académico de {state.student_profile.full_name}.

PERFIL:

- Semestre: {state.student_profile.semester}
- Promedio: {state.student_profile.average_grade}
- Ocupación: {state.student_profile.occupation}

TÉCNICAS DE ESTUDIO PREFERIDAS (Radar):

- Top 1: {study_profile.top_techniques[0]}
- Top 2: {study_profile.top_techniques[1]}
- Top 3: {study_profile.top_techniques[2]}
- Señales de debilidad: {study_profile.weakness_tags}

HORARIO FIJO:
{format_schedule_blocks(state.schedule)}

MATERIAS CON PRIORIDAD ESTA SEMANA:
{format_priorities(state.priorities)}

ACTIVIDADES ACADÉMICAS PENDIENTES:
{format_activities(state.academic_activities)}

PLAN DE ESTUDIO ACTUAL:
{format_study_plan(state.study_plan)}

Fecha actual: {today} | Timezone: {state.timezone}
"""`

**Herramientas del agente:**

`# RAG - primera clase
@tool
def search_study_methods(query: str, technique_id: str = None, subject: str = None) -> str:
"""Busca métodos y estrategias de estudio en la base de conocimiento."""

@tool  
def get_technique_guide(technique_id: str, activity_type: str, available_minutes: int) -> str:
"""Obtiene guía específica de cómo aplicar una técnica para un tipo de actividad."""

# Planificación

@tool
def add_academic_activity(subject: str, activity_type: str, title: str, due_date: str,
priority: str = "media", difficulty: str = "media") -> dict:
"""Registra una actividad académica nueva (parcial, tarea, proyecto, etc.)."""

@tool
def update_study_plan(reason: str, modifications: list[dict]) -> dict:
"""Actualiza el plan semanal de estudio con los cambios solicitados."""

@tool  
def get_weekly_plan(week_offset: int = 0) -> dict:
"""Obtiene el plan de estudio de la semana (0=actual, 1=próxima)."""

@tool
def get_pending_activities(days_ahead: int = 7) -> list:
"""Lista actividades académicas pendientes en los próximos N días."""

@tool
def update_priorities(subjects_with_priorities: list[dict]) -> dict:
"""Actualiza las prioridades de materias para la semana."""

# Horario

@tool
def get_schedule(week_offset: int = 0) -> dict:
"""Obtiene el horario de clases y actividades fijas."""

@tool
def manage_schedule_change(change_type: str, details: dict) -> dict:
"""Gestiona cambios al horario fijo (renovar semestre, reparar conflictos)."""

# Integración externa

@tool
def sync_plan_to_calendar() -> dict:
"""Sincroniza el plan de estudio con Outlook Calendar."""

@tool
def sync_tasks_to_todo() -> dict:
"""Sincroniza actividades pendientes con Microsoft To Do."""`

**System prompt del agente:**

`Eres Lara, asistente académica autónoma de {nombre_estudiante}.

Tu objetivo es ayudar al estudiante a:

1. Planificar su tiempo de estudio de forma efectiva
2. Registrar y hacer seguimiento de actividades académicas
3. Recomendar técnicas de estudio adaptadas a su perfil (usa search_study_methods)
4. Mantener su plan semanal actualizado

CÓMO ACTUAR:

- Cuando el estudiante mencione un examen, tarea o entrega → usa add_academic_activity
- Cuando pida reorganizar su semana → usa update_study_plan + get_weekly_plan
- Cuando pregunte cómo estudiar algo → usa search_study_methods con sus técnicas top
- Cuando pida ver su agenda → usa get_weekly_plan + get_schedule
- Actúa proactivamente: si registras una actividad, sugiere una técnica inmediatamente

LÍMITES:

- Solo apoyas con planificación académica y técnicas de estudio
- No resuelves ejercicios ni tareas directamente
- Si el estudiante necesita apoyo emocional, reconócelo brevemente y redirige

{contexto_completo_del_estudiante}`

---

### Fase 4: Implementación del Nodo Agente

**El nodo `academic_agent`** reemplaza a los ~12 nodos del modo `running`:

`from langgraph.prebuilt import create_react_agent

def build_academic_agent_node(llm, tools):
"""Construye el subgrafo del agente ReAct."""
return create_react_agent(
model=llm,
tools=tools,
state_modifier=build_agent_context, # inyecta contexto en system prompt
)

def academic_agent(state: AgentState) -> dict:
"""Nodo único del agente autónomo en modo running."""
messages = state.get("messages", [])
has_new_input, last_text, current_count = detect_new_input(...)

    if not has_new_input:
        return {"awaiting_user_input": True}

    # El agente recibe el mensaje + contexto completo
    agent = get_academic_agent()  # via AppContainer
    result = agent.invoke({
        "messages": [HumanMessage(content=last_text)],
        "student_context": build_agent_context(state),
    })

    # Recoger cambios que hicieron las herramientas al estado
    tool_state_updates = extract_tool_state_updates(result)

    return {
        "messages": append_message(messages, "assistant", result["messages"][-1].content),
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "phase": "running",
        **tool_state_updates,   # actualizaciones del plan, actividades, etc.
    }`

El grafo final queda:

`graph.add_node("entry_router", entry_router)
graph.add_node("welcome_consent", welcome_consent)
graph.add_node("collect_profile", collect_profile)
graph.add_node("collect_schedule", collect_schedule) # flujo completo interno
graph.add_node("collect_study_profile", collect_study_profile) # radar completo interno
graph.add_node("collect_priorities", collect_priorities)
graph.add_node("academic_agent", academic_agent) # el agente ReAct

# 6 aristas simples, no 31

graph.set_entry_point("entry_router")

# edges simples siguiendo las fases`

---

### Fase 5: Integración RAG como Tool de Primera Clase

El RAG ya tiene toda la infraestructura. El cambio es exponer `search_study_methods` como tool que el agente puede invocar cuando lo decide:

`@tool
def search_study_methods(
    query: str, 
    technique_id: str | None = None,
    subject: str | None = None,
    activity_type: str | None = None,
) -> str:
    """
    Busca estrategias y métodos de estudio relevantes para la consulta.
    Retorna guía práctica con pasos concretos.
    """
    service = get_study_recommendation_service()
    result = service.recommend_for_session(
        technique_id=technique_id or _infer_technique(query),
        subject_name=subject,
        query_override=query,
        ...
    )
    return result.answer`

La diferencia con el RAG actual: antes el sistema _decide en código_ cuándo usar RAG (solo al generar el plan). Ahora el **LLM decide cuándo usarlo** durante la conversación. El estudiante que pregunta "¿cómo debería preparar mi parcial de Cálculo?" activa el tool de RAG porque el agente razona que esa pregunta requiere consultar la base de conocimiento.

---

## 4. Prioridad de Ejecución

`SEMANA 1 — Fase 0: Limpieza Bloqueante
Día 1-2: Resolver fases fantasma (OTP sí/no, eliminar sync, academic_activity_management)
Día 3-4: Extraer lógica de handle_academic_update y build_study_plan a servicios
Día 5: Separar entry_router de welcome_consent, consolidar estado

SEMANA 2 — Fase 1+2: Estado y Onboarding
Día 1-2: Rediseñar AgentState (8 campos < 50, eliminar duplicados)
Día 3-5: Consolidar flujo de onboarding en 5 nodos macro

SEMANA 3-4 — Fase 3+4: El Agente
Día 1-2: Diseñar y testear tools de planificación (add_activity, update_plan, etc.)
Día 3-4: Implementar academic_agent_node con create_react_agent
Día 5: Wiring en el grafo, tests end-to-end del modo running

SEMANA 5 — Fase 5: RAG como Tool
Día 1-3: Exponer search_study_methods como tool del agente
Día 4-5: Pruebas de integración RAG + agent`

---

## 5. Qué NO cambiar

La capa de servicios (`src/services/`), repositorios (`src/repositories/`), schemas (`src/schemas/`) y la integración con WhatsApp (`src/integrations/`) **están bien y no necesitan refactorización significativa**. Son la base sólida sobre la que construyes el agente. Los tools del agente van a llamar exactamente esos servicios — nada cambia ahí.

El checkpointer PostgreSQL tampoco cambia. El `thread_id = número_de_whatsapp` sigue siendo el mecanismo correcto para persistencia por usuario.

---

**El resultado:** un sistema donde el onboarding recoge datos estructurados limpiamente, y una vez que el estudiante tiene su perfil completo, hay un agente real con LLM + herramientas que **razona** sobre qué hacer en lugar de seguir un árbol de decisión codificado. La diferencia para el estudiante: se siente como hablar con alguien que conoce su situación completa, no como llenar un formulario.
