# Arquitectura Actual Real Del Proyecto

Fecha: 2026-04-05

Estado: auditoria tecnica en progreso

## 1. Resumen ejecutivo de la arquitectura actual

La arquitectura real del proyecto hoy no es una arquitectura idealizada ni una hexagonal pura. Lo que existe en el codigo es un monolito modular en capas, orientado por grafo LangGraph, con suborganizacion por dominio dentro de cada capa y con rasgos hexagonales parciales en algunas fronteras.

En terminos practicos:

- el runtime del producto gira alrededor de un `StateGraph` central en `src/agents/support/agent.py`;
- el estado compartido entre fases y dominios se concentra en `src/agents/support/state.py`;
- la orquestacion conversacional vive en `src/agents/support/`;
- la mayor parte de la logica de aplicacion y negocio vive en `src/services/`;
- la persistencia durable vive en `src/repositories/`;
- las integraciones externas viven en `src/integrations/`;
- el wiring compartido vive en `src/bootstrap/container.py`.

La refactorizacion reciente si mejoro la arquitectura. El sistema actual es bastante mas claro y modular que un monolito desordenado. Sin embargo, todavia conserva deuda de transicion: parte de la logica de aplicacion sigue en `agents/support/flows/`, varios builders de servicios crean infraestructura concreta dentro de la capa de servicio, y aun existen superficies legacy como `src/agents/support/tools/db.py`.

## 2. Estilo arquitectonico identificado

### Arquitectura identificada

`Monolito modular en capas, orientado por grafo, con rasgos hexagonales parciales y suborganizacion por dominio`

### Por que esa clasificacion es la mas precisa

No es una arquitectura orientada primariamente por features porque el primer corte del arbol es tecnico:

- `src/agents/`
- `src/services/`
- `src/repositories/`
- `src/integrations/`
- `src/schemas/`
- `src/bootstrap/`

No es una arquitectura en capas pura y estricta porque:

- dentro de `agents/support/flows/` hay modulos que ya funcionan como servicios de aplicacion conversacional;
- existen algunos acoplamientos que atraviesan la direccion ideal de dependencias;
- el estado del agente atraviesa casi todos los dominios.

No es hexagonal pura porque:

- muchos servicios conocen builders concretos de repositorios e infraestructura;
- `bootstrap.container` y varios `build_*service()` terminan resolviendo implementaciones concretas;
- hay acoplamientos como:
  - `src/repositories/planning/repository.py` importando `services.scheduling.validation.validate_event`;
  - `src/integrations/microsoft_graph/auth_client.py` importando `repositories.microsoft_graph.state_repository`.

Si tiene rasgos hexagonales parciales porque:

- varios repositorios se exponen como `Protocol`, por ejemplo `OnboardingRepository` en `src/repositories/onboarding/repository.py`;
- varios clientes externos tambien se exponen como `Protocol`, por ejemplo `OutlookCalendarClient`, `MicrosoftTodoClient` y `MicrosoftMailClient` en `src/integrations/microsoft_graph/_clients_impl.py`;
- existen implementaciones `InMemory*` y `Postgres*` o clientes reales/disabled, lo que introduce puertos y adaptadores reales, aunque no de forma completamente sistematica.

## 3. Justificacion tecnica basada en evidencia del codigo

### 3.1 El centro del sistema es un grafo conversacional

Evidencia:

- `src/agents/support/agent.py` crea `StateGraph(AgentState)` en `build_agent()`;
- el mismo archivo registra nodos con `graph.add_node(...)` y compila con `graph.compile()`;
- `langgraph.json` define el entrypoint del runtime como `./src/agents/support/agent.py:agent`.

Interpretacion:

- el proyecto esta organizado alrededor de una maquina de estados conversacional controlada por fases;
- la arquitectura real esta fuertemente orientada por orquestacion de grafo, no por request/response clasico ni por eventos desacoplados.

### 3.2 El estado global es compartido y transversal

Evidencia:

- `src/agents/support/state.py` define un `AgentState` que contiene:
  - onboarding
  - scheduling
  - extracurricular
  - calendar
  - study profile
  - priorities
  - study plan
  - reminders
  - constraints
  - replan

Interpretacion:

- la arquitectura actual usa un gran estado compartido como backbone del flujo;
- esto simplifica la orquestacion del MVP;
- tambien aumenta el acoplamiento semantico entre dominios.

### 3.3 Los nodos son, en general, coordinadores finos

Evidencia:

- `src/agents/support/nodes/collect_profile/node.py` reexporta la logica desde `flows/onboarding/collect_profile.py`;
- `src/agents/support/nodes/parse_schedules_to_events/node.py` delega en `handle_schedule_parsing_turn(...)`;
- `src/agents/support/nodes/build_study_plan/node.py` llama `services.planning.sync_subjects_and_study_plan(...)` y luego `persist_planning_snapshot_for_update(...)`;
- `tests/test_refactor_guardrails.py` contiene `test_hotspot_nodes_are_now_thin_wrappers()`.

Interpretacion:

- la refactorizacion si movio logica fuera de varios nodos;
- la direccion general de la arquitectura es intencional y ya tiene enforcement.

### 3.4 Los servicios concentran la mayor parte de la aplicacion

Evidencia:

- `src/services/onboarding/service.py` orquesta verificacion y persistencia;
- `src/services/scheduling/service.py` persiste horarios recurrentes;
- `src/services/personalization/service.py` evalua y persiste el Radar;
- `src/services/planning/study_plan_sync_service.py` sincroniza materias y plan;
- `src/services/planning/materialization_service.py` materializa instancias;
- `src/services/reminders/service.py` sincroniza politicas y dispatches;
- `src/services/sync/outlook_calendar_sync_service.py` y `src/services/sync/microsoft_todo_sync_service.py` proyectan el plan hacia Microsoft Graph.

Interpretacion:

- el proyecto hoy se comporta principalmente como una arquitectura en capas donde `services/` es la capa de aplicacion dominante.

### 3.5 Existen puertos/adaptadores, pero no de forma total

Evidencia:

- repositorios como `OnboardingRepository`, `ScheduleRepository`, `StudyPlanningRepository`, `RemindersRepository` se definen como `Protocol`;
- clientes externos como `OutlookCalendarClient`, `MicrosoftTodoClient`, `MicrosoftMailClient` tambien se definen como `Protocol`;
- hay implementaciones `InMemory*`, `Postgres*`, `Disabled*` y `Graph*`.

Interpretacion:

- hay una intencion clara de inversion de dependencias;
- la implementacion real es parcial porque los servicios aun conocen builders concretos y configuracion de entorno.

## 4. Componentes principales

### 4.1 Orquestacion del agente

- `src/agents/support/agent.py`
  Grafo principal, nodos, transiciones y routing por `phase`.
- `src/agents/support/state.py`
  Contrato de estado unificado del runtime.
- `src/agents/support/nodes/`
  Nodos LangGraph.
- `src/agents/support/flows/`
  Logica conversacional y de coordinacion intermedia.
- `src/agents/support/dependencies.py`
  Frontera del agente hacia el container.

### 4.2 Aplicacion y dominio

- `src/services/onboarding/`
- `src/services/scheduling/`
- `src/services/personalization/`
- `src/services/priorities/`
- `src/services/planning/`
- `src/services/reminders/`
- `src/services/sync/`

### 4.3 Persistencia

- `src/repositories/onboarding/`
- `src/repositories/scheduling/`
- `src/repositories/personalization/`
- `src/repositories/planning/`
- `src/repositories/reminders/`
- `src/repositories/microsoft_graph/`
- `migrations/`

### 4.4 Integraciones externas

- `src/integrations/ai/`
- `src/integrations/microsoft_graph/`
- `src/integrations/langgraph/`
- `src/integrations/whatsapp/` como placeholder

### 4.5 Contratos compartidos

- `src/schemas/`

### 4.6 Wiring y entorno

- `src/bootstrap/container.py`
- `src/bootstrap/settings.py`
- `src/bootstrap/errors.py`
- `src/project_env.py`

## 5. Relaciones entre componentes

### 5.1 Relacion principal del runtime

```text
LangGraph Runtime
    |
    v
langgraph.json
    |
    v
agents/support/agent.py
    |
    v
AgentState + Nodes
    |
    v
agents/support/flows/*
    |
    v
agents/support/dependencies.py
    |
    v
bootstrap/container.py
    |
    v
services/*
    |
    +------------------> repositories/* --------------> PostgreSQL
    |
    +------------------> integrations/ai -------------> Azure/OpenAI
    |
    +------------------> integrations/microsoft_graph -> Microsoft Graph
    |
    \------------------> integrations/langgraph ------> Checkpointer PostgreSQL
```

### 5.2 Ejemplo real: onboarding

Ruta observada:

- `src/agents/support/nodes/persist_profile/node.py`
- `src/agents/support/dependencies.py:get_onboarding_service()`
- `src/bootstrap/container.py:get_onboarding_service()`
- `src/services/onboarding/service.py`
- `src/repositories/onboarding/repository.py`
- PostgreSQL

Lectura:

- es un flujo claro de nodo -> dependencia -> servicio -> repositorio.

### 5.3 Ejemplo real: scheduling

Ruta observada:

- `src/agents/support/nodes/request_schedules/node.py`
- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/flows/scheduling/schedule_parsing_service.py`
- `src/agents/support/flows/scheduling/schedule_draft_service.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/nodes/persist_schedule/node.py`
- `src/services/scheduling/service.py`
- `src/repositories/scheduling/repository.py`

Lectura:

- la captura y revision del horario estan muy orquestadas desde la capa del agente;
- la persistencia final si cae de forma limpia en `services/` y `repositories/`.

### 5.4 Ejemplo real: planning + materializacion + reminders

Ruta observada:

- `src/agents/support/nodes/build_study_plan/node.py`
- `src/services/planning/study_plan_sync_service.py`
- `src/services/priorities/subject_prioritization_service.py`
- `src/services/planning/study_planning_service.py`
- `src/agents/support/flows/planning/persistence_support.py`
- `src/services/planning/persistence_service.py`
- `src/repositories/planning/repository.py`
- `src/services/planning/materialization_service.py`
- `src/repositories/planning/instances_repository.py`
- `src/services/reminders/service.py`
- `src/repositories/reminders/repository.py`

Lectura:

- aqui se ve una cadena de aplicacion bastante rica;
- la persistencia y post-procesamiento del plan no estan totalmente encerrados en `services/`, porque `persistence_support.py` sigue en `agents/`.

### 5.5 Ejemplo real: sync con Microsoft

Ruta observada:

- `src/services/sync/outlook_calendar_sync_service.py`
- `src/repositories/microsoft_graph/sync_repository.py`
- `src/repositories/microsoft_graph/state_repository.py`
- `src/integrations/microsoft_graph/auth_client.py`
- `src/integrations/microsoft_graph/calendar_client.py`
- Microsoft Graph

Lectura:

- este es uno de los sectores mas cercanos a puertos/adaptadores parciales;
- el servicio de sync coordina repositorios y clientes externos claramente.

## 6. Flujo de dependencias

## 6.1 Direccion principal observada

La direccion de dependencias dominante en codigo es:

`agents -> services -> repositories / integrations -> PostgreSQL / APIs externas`

con `schemas` y `bootstrap` como piezas transversales.

## 6.2 Donde si se cumple bien

Señales positivas:

- `src/agents/` no importa repositorios directamente;
- `src/agents/` no importa integraciones directamente;
- `src/services/` no importa `agents.support`;
- `tests/test_refactor_guardrails.py` hace enforcement de esos limites.

## 6.3 Donde no es totalmente limpio

Excepciones relevantes:

- `src/repositories/planning/repository.py` importa `services.scheduling.validation.validate_event`;
- `src/integrations/microsoft_graph/auth_client.py` importa `repositories.microsoft_graph.state_repository`;
- `src/agents/support/flows/planning/persistence_support.py` coordina persistencia, materializacion y reminders desde la capa del agente;
- muchos `build_*service()` resuelven repositorios concretos desde entorno dentro de la propia capa de servicio.

## 6.4 Naturaleza del acoplamiento

Evaluacion:

- acoplamiento bajo a medio entre `agents` y `repositories` o `integrations`;
- acoplamiento medio dentro del eje `agents -> services`;
- acoplamiento medio a alto alrededor del estado compartido y de ciertos helpers de flujo;
- acoplamiento pragmatico entre servicios y builders de infraestructura.

## 7. Puntos fuertes de la arquitectura actual

- La arquitectura real es entendible y trazable.
- El primer corte por capas esta bien definido en `src/`.
- Hay una separacion clara entre runtime conversacional, logica de aplicacion, persistencia e integraciones.
- Los nodos del grafo son hoy bastante mas delgados que en una version pre-refactor.
- `bootstrap.container` centraliza wiring y pruebas pueden inyectar overrides.
- Los repositorios y varios clientes externos usan `Protocol`, lo que facilita pruebas y reemplazos.
- Hay implementaciones `InMemory*` y `Postgres*`, utiles para MVP y para evolucion segura.
- La persistencia no es improvisada: hay migraciones por dominio y guardrails de arquitectura automatizados.
- `langgraph.json` y `src/integrations/langgraph/checkpointer.py` separan bien el runtime del agente de la persistencia de hilos.
- La arquitectura soporta crecimiento incremental sin reescritura total.

## 8. Debilidades de la arquitectura actual

- La arquitectura no esta completamente cerrada; sigue en transicion.
- `AgentState` concentra demasiados subdominios y actua como bus de estado global.
- Parte de la logica de aplicacion sigue en `agents/support/flows/`, no solo en `services/`.
- La frontera entre “flow conversacional” y “application service” aun es borrosa en scheduling, priorities y planning.
- Los builders de servicios resuelven infraestructura concreta desde entorno, lo que reduce pureza de inversion de dependencias.
- `src/agents/support/dependencies.py` y el singleton `AppContainer` son un service locator controlado; pragmatico, pero no idealmente explicito.
- Existen acoplamientos cruzados no deseables:
  - repositorio -> servicio
  - integracion -> repositorio
- El subflujo de replanificacion existe en codigo y pruebas, pero no esta conectado al grafo principal.
- Las superficies legacy no han desaparecido del todo, por ejemplo `src/agents/support/tools/db.py` y varios scripts.

## 9. Que decisiones parecen intencionales y cuales parecen accidentales

### 9.1 Decisiones que parecen intencionales

- Separar el repo por capas top-level.
- Mantener el runtime alrededor de un `StateGraph`.
- Adelgazar nodos y mover logica fuera de ellos.
- Introducir `bootstrap/container.py` como composition root.
- Definir contratos `Protocol` para repositorios y varios clientes externos.
- Mantener implementaciones `InMemory` para pruebas y `Postgres` para produccion.
- Separar `integrations/langgraph/` del resto del runtime.
- Reservar `src/rag/` y `src/integrations/whatsapp/` como extensiones futuras sin contaminar el core.
- Añadir guardrails en `tests/test_refactor_guardrails.py`.

### 9.2 Decisiones que parecen accidentales o transicionales

- Mantener `src/agents/support/tools/db.py` como shim legacy.
- Dejar scripts operativos apuntando a rutas legacy que ya no existen como fuente activa.
- Permitir que `src/repositories/planning/repository.py` dependa de validacion en `services/`.
- Acoplar `src/integrations/microsoft_graph/auth_client.py` al repositorio durable concreto.
- Dejar `replan` dentro de `AgentState` sin conexion efectiva en `src/agents/support/agent.py`.
- Mantener `main.py` como placeholder que no representa el entrypoint real del sistema.

## 10. Evaluacion de soporte por capacidad del sistema

### 10.1 Onboarding

Evaluacion: `soporte fuerte`

Evidencia:

- subflujo claro en `src/agents/support/agent.py`;
- captura de perfil en `src/agents/support/flows/onboarding/collect_profile.py`;
- verificacion y persistencia en `src/services/onboarding/service.py`;
- repositorio dedicado en `src/repositories/onboarding/repository.py`.

Matiz:

- el sender real de correo para onboarding no esta implementado; `DisabledEmailSender` es el default en `src/services/onboarding/email_sender.py`.

### 10.2 Captura de horarios

Evaluacion: `soporte fuerte`

Evidencia:

- request, parsing, draft, review y persistencia existen y estan conectados al grafo;
- la persistencia esta resuelta en `src/services/scheduling/service.py` y `src/repositories/scheduling/repository.py`.

Matiz:

- la orquestacion esta muy repartida entre nodos, flows y helpers.

### 10.3 Actividades

Evaluacion: `soporte medio a fuerte`

Evidencia:

- extras y extracurricular estan presentes en `AgentState`;
- existen flujos y parsing en `src/agents/support/flows/extracurricular/` y `src/agents/support/flows/replanning/`;
- scheduling tiene soporte para actividades fijas y tentativas.

Matiz:

- la replanificacion de actividades no esta integrada al grafo principal;
- la funcionalidad existe, pero la arquitectura de ejecucion aun no la expone de forma completa.

### 10.4 Personalizacion

Evaluacion: `soporte fuerte`

Evidencia:

- dominio claro en `src/services/personalization/`;
- persistencia dedicada en `src/repositories/personalization/repository.py`;
- nodos y prompts dedicados en `src/agents/support/nodes/collect_study_profile*`.

### 10.5 RAG

Evaluacion: `soporte estructural, no funcional`

Evidencia:

- `src/rag/` existe con subcapas reservadas;
- `src/rag/README.md` define la intencion arquitectonica.

Conclusion:

- la arquitectura lo preve, pero hoy no hay modulo RAG operativo.

### 10.6 Integraciones con calendario y correo

Evaluacion: `soporte parcial a fuerte`

Calendario:

- Outlook Calendar esta bien encaminado y tiene servicio, repositorios, OAuth y cliente Graph reales.

Correo:

- reminders por email si tienen soporte real mediante Microsoft Graph en `src/services/reminders/dispatcher.py`;
- onboarding por correo esta solo parcialmente soportado porque el sender default esta deshabilitado.

### 10.7 WhatsApp

Evaluacion: `soporte solo estructural`

Evidencia:

- `src/integrations/whatsapp/__init__.py` es solo placeholder;
- `src/integrations/whatsapp/README.md` fija la regla arquitectonica de entrada por adaptador;
- no existe implementacion funcional del canal.

Conclusion:

- la arquitectura actual si deja un lugar limpio para WhatsApp;
- hoy no lo soporta funcionalmente.

## 11. Diagrama logico inferido en ASCII

```text
                            +----------------------+
                            |    LangGraph Runtime |
                            +----------+-----------+
                                       |
                                       v
                            +----------------------+
                            | langgraph.json       |
                            | graph + checkpointer |
                            +----------+-----------+
                                       |
                                       v
                 +----------------------------------------------+
                 | agents/support/agent.py                      |
                 | StateGraph + routes by AgentState.phase      |
                 +-------------------+--------------------------+
                                     |
                                     v
                 +----------------------------------------------+
                 | AgentState                                   |
                 | onboarding, schedule, study_profile, plan... |
                 +-------------------+--------------------------+
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
      +-----------------------------+    +------------------------------+
      | nodes/*                     |    | flows/*                      |
      | thin coordinators           |    | conversational app logic     |
      +-------------+---------------+    +--------------+---------------+
                    |                                   |
                    +----------------+------------------+
                                     |
                                     v
                    +-----------------------------------+
                    | agents/support/dependencies.py    |
                    | semantic access to AppContainer   |
                    +----------------+------------------+
                                     |
                                     v
                    +-----------------------------------+
                    | bootstrap/container.py            |
                    | runtime composition root          |
                    +----------------+------------------+
                                     |
                                     v
                    +-----------------------------------+
                    | services/*                        |
                    | application + business orchestration |
                    +---------+---------------+---------+
                              |               |
                              v               v
                +---------------------+   +-----------------------+
                | repositories/*      |   | integrations/*        |
                | Postgres/InMemory   |   | AI, Graph, LangGraph  |
                +----------+----------+   +-----------+-----------+
                           |                          |
                           v                          v
                     PostgreSQL                External APIs/Providers
```

## 12. Conclusión de esta fase

La arquitectura actual real del proyecto es coherente para un MVP y mejora claramente el estado historico previo al refactor. La forma efectiva en que funciona hoy es:

- grafo central LangGraph;
- estado compartido transversal;
- agentes y flows como capa conversacional;
- servicios como capa principal de aplicacion;
- repositorios e integraciones separados;
- container explicito para wiring;
- algunos puertos/adaptadores parciales en persistencia e integraciones.

La mejor descripcion no es “arquitectura limpia completa”, sino:

`monolito modular en capas, orientado por grafo, con rasgos hexagonales parciales y deuda de transicion controlada`
