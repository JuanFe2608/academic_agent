# Recomendaciones Y Refactor Roadmap

Fecha: 2026-04-05

Estado: propuesta de mejora incremental basada en auditoria

## 1. Principios de mejora

Las recomendaciones de esta fase parten de los hallazgos reales documentados en:

- `docs/2026-04-05/02_arquitectura_actual.md`
- `docs/2026-04-05/03_flujo_agente_actual.md`
- `docs/2026-04-05/04_analisis_modular.md`
- `docs/2026-04-05/05_auditoria_base_datos.md`
- `docs/2026-04-05/06_debilidades_y_riesgos.md`

Principios rectores:

1. Mantener el proyecto como monolito modular.
   No se recomienda microservicios ni una reescritura total.

2. Mejorar límites, no multiplicar capas.
   La arquitectura actual ya tiene capas útiles (`agents`, `services`, `repositories`, `integrations`, `schemas`, `bootstrap`). La mejora debe reforzar esas fronteras, no crear taxonomías nuevas innecesarias.

3. Preservar comportamiento antes de mover estructura.
   Cualquier refactor debe empezar por aislar lógica y agregar pruebas, no por renombrar carpetas masivamente.

4. Priorizar hotspots y deuda transicional.
   Los mayores beneficios están en reducir complejidad de `agents/support`, alinear scripts y endurecer observabilidad/errores/configuración.

5. Preparar extensibilidad sólo donde el producto ya la sugiere.
   Outlook, correo, WhatsApp, Telegram, personalización avanzada y RAG deben entrar como extensiones de la arquitectura actual, no como líneas paralelas improvisadas.

6. Favorecer una arquitectura explicable para un proyecto de grado.
   La solución recomendada debe poder explicarse como:
   un monolito modular por capas, con orquestación LangGraph, servicios de aplicación claros, repositorios explícitos e integraciones encapsuladas.

## 2. Arquitectura objetivo recomendada

### 2.1 Recomendación principal

La arquitectura objetivo recomendada es:

`monolito modular por capas, orientado por grafo, con puertos/adaptadores parciales reforzados`

Justificación:

- Encaja con el estado actual del repositorio.
- Aprovecha la refactorización ya hecha.
- Evita sobreingeniería.
- Permite crecer hacia más integraciones y capacidades sin romper el corazón del MVP.

No se recomienda:

- migrar a microservicios;
- reestructurar todo a hexagonal pura;
- cambiar el primer corte del repo a “features” únicamente;
- reemplazar LangGraph o rehacer el flujo desde cero.

### 2.2 Forma objetivo de interacción entre capas

```text
LangGraph / Agent Runtime
    |
    v
agents/support
  - grafo
  - rutas
  - nodos finos
  - mapeo AgentState <-> comandos/resultados
    |
    v
services/*
  - casos de uso
  - orquestación de negocio
  - validación de aplicación
    |
    +--------------------+
    |                    |
    v                    v
repositories/*      integrations/*
  - PostgreSQL         - AI
  - durable state      - Microsoft Graph
  - snapshots          - WhatsApp / Telegram futuro
                        - correo / calendario
    |
    v
schemas/* + utils/*
```

### 2.3 Regla objetivo de responsabilidades

- `agents/`
  Debe saber de fases, prompts, LangGraph, `AgentState` y coordinación conversacional.
- `services/`
  Debe saber de reglas de negocio, coordinación de casos de uso, pipelines de aplicación y decisiones de dominio.
- `repositories/`
  Debe saber de SQL, persistencia durable, materialización, deduplicación y mapping fila-objeto.
- `integrations/`
  Debe saber de proveedores externos, transporte, autenticación y contratos de I/O externo.
- `schemas/`
  Debe contener contratos estables y DTOs compartidos.
- `bootstrap/`
  Debe ser el punto único de wiring y de configuración base.

## 3. Qué conservar del diseño actual

No conviene desmontar estas decisiones, porque hoy son de las partes más sanas del proyecto:

- El corte top-level actual del repo:
  - `src/agents/`
  - `src/services/`
  - `src/repositories/`
  - `src/integrations/`
  - `src/schemas/`
  - `src/bootstrap/`
- El uso de `Protocol + InMemory + Postgres` en repositorios.
- El `AppContainer` en `src/bootstrap/container.py` como composition root central.
- La organización de `integrations/` por proveedor.
- El checkpointer de LangGraph separado en `src/integrations/langgraph/checkpointer.py`.
- El modelo de persistencia versionada:
  - `schedule_profiles`
  - `study_personalization_profiles`
  - `study_priority_profiles`
  - `study_plan_profiles`
  - `study_plan_event_instances`
- Los guardrails arquitectónicos ya presentes en `tests/test_refactor_guardrails.py`.
- La decisión de dejar `src/rag/` y `src/integrations/whatsapp/` como extensiones reservadas en vez de mezclarlas ya con el core.

## 4. Qué reorganizar primero

Orden recomendado de reorganización:

1. Orquestación de persistencia posterior al plan.
   Evidencia: `src/agents/support/flows/planning/persistence_support.py`.
   Motivo: hoy mezcla responsabilidades que ya pertenecen a aplicación.

2. Routing y composición del grafo.
   Evidencia: `src/agents/support/agent.py`.
   Motivo: es el archivo más central y uno de los más densos.

3. Scheduling conversacional.
   Evidencia:
   - `src/agents/support/flows/scheduling/schedule_capture_service.py`
   - `src/agents/support/flows/scheduling/schedule_review_service.py`
   Motivo: son hotspots reales del MVP.

4. OAuth Microsoft y scripts operativos.
   Evidencia:
   - `src/integrations/microsoft_graph/auth_client.py`
   - `scripts/run_due_reminders.py`
   - `scripts/backfill_study_plan_instances.py`
   - `scripts/microsoft_oauth_exchange_code.py`

5. Observabilidad, configuración y seguridad.
   Motivo: no cambian la arquitectura visible, pero sí mejoran operación y crecimiento.

## 5. Refactors de bajo riesgo

Estos cambios deberían poder hacerse sin alterar comportamiento funcional del agente.

### 5.1 Dividir `agent.py` sin cambiar el entrypoint

Evidencia:

- `src/agents/support/agent.py` concentra definición de grafo, routers y lógica de espera.

Recomendación:

- conservar `src/agents/support/agent.py` como entrypoint estable del runtime;
- extraer a módulos auxiliares:
  - `src/agents/support/routing.py`
  - `src/agents/support/waiting.py`
  - `src/agents/support/graph_builder.py`

Beneficio:

- menor densidad del archivo central;
- menos riesgo de edición concurrente;
- más legible para mantenimiento.

### 5.2 Convertir `persistence_support.py` en un wrapper fino

Evidencia:

- `src/agents/support/flows/planning/persistence_support.py` hoy coordina:
  - persistencia de planning,
  - materialización,
  - reminders.

Recomendación:

- crear en `src/services/planning/` un servicio/fachada de pipeline, por ejemplo:
  - `study_plan_pipeline_service.py`
  o
  - `planning_pipeline_service.py`
- dejar `persistence_support.py` solo como adaptador temporal de `AgentState -> service call`.

Beneficio:

- limpia la frontera `agents -> services`;
- da mucho valor con poco riesgo porque mueve coordinación, no lógica de dominio nueva.

### 5.3 Alinear scripts a `bootstrap` y `services`

Evidencia:

- varios scripts siguen usando imports legacy desde `agents.support`.

Recomendación:

- hacer que cada script importe solo desde:
  - `bootstrap`
  - `services`
  - `repositories`
  - `integrations`
- prohibir nuevos imports a `agents.support.tools.*` o rutas legacy.

Beneficio:

- reduce deuda transicional sin tocar el flujo conversacional.

### 5.4 Agregar observabilidad mínima

Evidencia:

- no hay `logging` visible en `src/`.

Recomendación:

- introducir logging estructurado simple en:
  - servicios de persistencia,
  - workers de reminders,
  - syncs Microsoft,
  - llamadas LLM.
- no hace falta una plataforma compleja; basta con un contrato consistente de eventos y errores.

Beneficio:

- enorme mejora operativa con riesgo bajo.

### 5.5 Unificar errores públicos por servicio

Evidencia:

- muchos servicios devuelven `error_code`, pero algunos nodos degradan con `except Exception` genérico.

Recomendación:

- estandarizar resultados tipo:
  - `ok/persisted/synced/tracked`
  - `error_code`
  - `detail`
  - `context` mínimo opcional

Beneficio:

- mejor depuración;
- menos acoplamiento entre flujo conversacional y excepciones internas.

### 5.6 Endurecer guardrails y agregar CI básico

Evidencia:

- hay guardrails buenos en `tests/test_refactor_guardrails.py`;
- no hay workflow CI visible.

Recomendación:

- mantener los guardrails actuales;
- agregar pruebas equivalentes para `scripts/`;
- crear un pipeline mínimo que ejecute:
  - `pytest`
  - smoke de imports del runtime

Beneficio:

- reduce regresiones sin rediseño.

## 6. Refactors de riesgo medio

Estos cambios tienen mucho valor, pero tocan fronteras sensibles del sistema.

### 6.1 Adelgazar semánticamente `AgentState`

Evidencia:

- `AgentState` concentra demasiados subdominios.

Recomendación:

- no cambiar de golpe el contrato global;
- sí separar mejor:
  - estado conversacional puro,
  - estado durable referenciado por IDs persistidos,
  - estado efímero de captura.

Estrategia:

- comenzar por modularizar el archivo y documentar ownership de cada subestado;
- después reducir qué llaves top-level pueden agregarse.

### 6.2 Mover lógica pura de scheduling desde `agents/support/flows` a `services/scheduling`

Evidencia:

- `schedule_capture_service.py` y `schedule_review_service.py` concentran parsing, mutación, prompts y lógica de reconstrucción.

Recomendación:

- dejar en `agents/` solamente prompts, routing y adaptación a `AgentState`;
- mover a `services/scheduling/` la lógica reutilizable de:
  - resolución de bloques pendientes,
  - composición de borradores,
  - reglas de confirmación/corrección.

Riesgo:

- toca el tramo más vivo del flujo.

### 6.3 Reorganizar `auth_client.py` por submódulos internos

Evidencia:

- `src/integrations/microsoft_graph/auth_client.py` mezcla config, transporte, token store, DTOs y cliente OAuth.

Recomendación:

- conservar una fachada pública estable;
- dividir internamente en:
  - `config.py`
  - `transport.py`
  - `token_store.py`
  - `oauth_client.py`

Beneficio:

- misma funcionalidad, frontera más limpia.

### 6.4 Reducir duplicación entre sync Outlook y sync To Do

Evidencia:

- `src/services/sync/outlook_calendar_sync_service.py` y `src/services/sync/microsoft_todo_sync_service.py` comparten bastante esqueleto.

Recomendación:

- extraer helpers comunes de sync en `src/services/sync/common.py` o similar;
- no fusionar los servicios, solo compartir pasos repetidos.

### 6.5 Mejorar seguridad de tokens Microsoft

Evidencia:

- `microsoft_graph_connections` guarda `access_token` y `refresh_token`.

Recomendación:

- si el proyecto sigue creciendo con Microsoft:
  - cifrar tokens;
  - o mover refresh tokens a un secret store.

Riesgo:

- cambio delicado de persistencia, pero muy valioso.

## 7. Cambios delicados que deben posponerse

Estos cambios no deben ser la primera fase de intervención.

### 7.1 Reescribir el modelo de datos

No se recomienda:

- renombrar masivamente tablas o campos;
- eliminar snapshots JSONB de golpe;
- rehacer versionado de perfiles.

Razón:

- el modelo actual sí soporta el MVP;
- cambiarlo primero daría mucho riesgo con beneficio limitado.

### 7.2 Reemplazar el `AppContainer`

No se recomienda por ahora:

- eliminar el container;
- migrar todo a DI explícita profunda.

Razón:

- hoy funciona;
- está cubierto por pruebas;
- la deuda principal está en otros lados.

### 7.3 Cambiar de arquitectura base

No se recomienda:

- migrar a microservicios;
- rehacer el repo a arquitectura puramente feature-based;
- perseguir hexagonal pura.

Razón:

- sería más coste que valor para este MVP.

### 7.4 Abrir RAG antes de estabilizar el core

No se recomienda:

- implementar embeddings y retrieval antes de estabilizar scheduling/planning/reminders.

Razón:

- hoy RAG no es cuello de botella del producto;
- introducirlo antes aumentaría complejidad y mezcla conceptual.

### 7.5 Activar WhatsApp/Telegram antes de cerrar el patrón de canales

No se recomienda:

- conectar proveedores reales mientras el patrón de `ReminderChannelSender` y la operación de scripts/workers no esté estabilizada.

Razón:

- se multiplicaría la deuda operativa.

## 8. Roadmap por fases

### Fase 1. Estabilización estructural sin cambio funcional

Objetivo:

- bajar riesgo operativo y dejar el refactor reciente coherente.

Incluye:

- alinear scripts a imports actuales;
- dividir `agent.py` en routing/graph/wait sin cambiar entrypoint;
- introducir logging estructurado mínimo;
- unificar manejo de errores públicos por servicio;
- agregar guardrails para `scripts/`;
- agregar CI básico.

Resultado esperado:

- misma funcionalidad;
- mejor mantenimiento y operación.

### Fase 2. Limpieza de límites entre agente y aplicación

Objetivo:

- hacer que `agents/` vuelva a ser principalmente orquestación conversacional.

Incluye:

- crear una fachada/pipeline en `services/planning/` para persistencia + materialización + reminders;
- adelgazar `persistence_support.py`;
- empezar a mover lógica pura de scheduling desde `agents/support/flows` a `services/scheduling/`;
- documentar ownership claro de cada parte de `AgentState`.

Resultado esperado:

- menor acoplamiento del grafo;
- mejor separación de responsabilidades.

### Fase 3. Endurecimiento de infraestructura y trazabilidad

Objetivo:

- preparar crecimiento real con menor riesgo operativo.

Incluye:

- reorganizar internamente `auth_client.py`;
- reforzar seguridad de tokens Microsoft;
- definir política de canonicidad entre columnas y `JSONB`;
- agregar vínculo durable entre `thread_id` y `student_id`;
- sumar pruebas de integración con PostgreSQL real.

Resultado esperado:

- mejor seguridad;
- mejor auditabilidad;
- menor riesgo en integraciones.

### Fase 4. Extensiones controladas

Objetivo:

- abrir nuevas capacidades sin contaminar el core.

Incluye:

- activar replanificación real solo cuando el flujo principal esté estable;
- incorporar feedback de tracking a personalización;
- abrir `integrations/telegram/` y/o `integrations/whatsapp/` bajo el patrón de senderes;
- implementar RAG solo con persistencia y contratos separados del núcleo operacional.

Resultado esperado:

- extensibilidad real sin reintroducir caos.

## 9. Quick wins

Quick wins recomendados:

1. Corregir imports legacy en `scripts/`.
2. Extraer `routing.py` y `waiting.py` desde `src/agents/support/agent.py`.
3. Crear un servicio de pipeline para planning y dejar `persistence_support.py` delgado.
4. Agregar logging básico a:
   - LLM
   - reminders worker
   - sync Outlook
   - sync To Do
5. Agregar guardrail que prohíba imports legacy en `scripts/`.
6. Crear una hoja de variables de entorno efectiva del proyecto.
7. Documentar qué capacidades están:
   - activas,
   - estructuradas pero no operativas,
   - reservadas para más adelante.

## 10. Criterios de éxito

La estrategia será exitosa si al terminar las primeras fases se cumple lo siguiente:

1. `agents/support` queda claramente más delgado.
   Señal:
   - menos lógica de aplicación fuera de `services/`.

2. El grafo principal sigue estable.
   Señal:
   - `langgraph.json` no cambia;
   - el entrypoint `src/agents/support/agent.py:agent` sigue funcionando.

3. Los scripts dejan de depender de rutas legacy.
   Señal:
   - imports solo desde capas activas del refactor.

4. Se mejora operación real del MVP.
   Señal:
   - logging básico;
   - errores con `error_code` y detalle consistente;
   - mejor diagnóstico de fallos.

5. El proyecto queda listo para nuevas capacidades sin mezclar responsabilidades.
   Señal:
   - patrón de integraciones claro para Microsoft, correo, WhatsApp y Telegram;
   - RAG separado del core operacional.

6. Las pruebas protegen mejor la arquitectura y la operación.
   Señal:
   - guardrails ampliados;
   - integración mínima con PostgreSQL;
   - CI visible.

## 11. Propuesta de estructura de carpetas objetivo

La propuesta no implica una gran migración de carpetas, sino una limpieza incremental sobre el árbol actual.

```text
src/
├── agents/
│   └── support/
│       ├── agent.py                # entrypoint estable
│       ├── graph_builder.py        # compone StateGraph
│       ├── routing.py              # routers por phase
│       ├── waiting.py              # lógica de pausa/espera
│       ├── dependencies.py
│       ├── state.py                # o state/ si luego se fragmenta
│       ├── nodes/
│       ├── flows/
│       │   ├── onboarding/
│       │   ├── scheduling/
│       │   └── replanning/
│       └── prompts/                # opcional si prompts siguen creciendo
├── services/
│   ├── onboarding/
│   ├── scheduling/
│   ├── personalization/
│   ├── priorities/
│   ├── planning/
│   │   ├── persistence_service.py
│   │   ├── materialization_service.py
│   │   ├── tracking_service.py
│   │   ├── study_plan_sync_service.py
│   │   └── planning_pipeline_service.py
│   ├── reminders/
│   └── sync/
├── repositories/
│   ├── onboarding/
│   ├── scheduling/
│   ├── personalization/
│   ├── planning/
│   ├── reminders/
│   ├── microsoft_graph/
│   └── common/
├── integrations/
│   ├── ai/
│   ├── langgraph/
│   ├── microsoft_graph/
│   │   ├── auth_client.py         # fachada pública estable
│   │   ├── config.py
│   │   ├── transport.py
│   │   ├── token_store.py
│   │   └── clients/
│   ├── whatsapp/
│   └── telegram/                  # futuro, solo cuando haya caso real
├── schemas/
├── bootstrap/
└── utils/
```

## 12. Lista de refactors por prioridad

### Prioridad alta

- Adelgazar `src/agents/support/agent.py`.
- Sacar coordinación durable de `src/agents/support/flows/planning/persistence_support.py`.
- Corregir scripts con imports legacy.
- Introducir logging y manejo de errores consistente.
- Añadir guardrails y CI básico.

### Prioridad media

- Mover lógica reutilizable de scheduling a `services/scheduling/`.
- Reorganizar internamente `src/integrations/microsoft_graph/auth_client.py`.
- Estandarizar configuración y documentación de variables de entorno.
- Definir canonicidad de payloads `JSONB`.
- Agregar trazabilidad `thread_id -> student_id`.

### Prioridad baja o diferida

- Afinar terminología del dominio.
- Reducir gradualmente superficie de `AgentState`.
- Integrar personalización adaptativa.
- Abrir RAG.
- Abrir nuevos canales reales.

## 13. Qué se puede mejorar sin romper nada y qué requiere más cuidado

Se puede mejorar sin romper nada, si se hace con pruebas:

- división interna de `agent.py`;
- alineación de scripts;
- logging;
- normalización de errores;
- documentación y guardrails;
- creación de fachadas/pipelines de aplicación conservando APIs actuales.

Requiere cambios más delicados:

- mover lógica desde `agents/support/flows` a `services/`;
- adelgazar semánticamente `AgentState`;
- cambiar persistencia de tokens Microsoft;
- introducir trazabilidad durable de conversación;
- reducir redundancia entre snapshots y datos estructurados.

## 14. Dictamen final

La recomendación no es “refactorizar todo”, sino completar el refactor en los puntos donde ya hay evidencia de transición incompleta.

La mejor trayectoria para este proyecto es:

- conservar el monolito modular por capas;
- reforzar límites entre orquestación y aplicación;
- endurecer operación, seguridad y trazabilidad;
- y abrir nuevas capacidades sólo cuando el núcleo esté estable.

Eso encaja con un MVP académico robusto, explicable y mantenible, sin caer en sobreingeniería.
