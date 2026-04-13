# Detalles Arquitectonicos Pendientes Post AgentState

Fecha: 2026-04-07

Estado: definicion arquitectonica para siguientes olas de implementacion

Documentos base:

- `docs/2026-04-05/08_informe_final_consolidado.md`
- `docs/2026-04-06/agentstate_refactor_report.md`
- `docs/2026-04-06/agentstate_refactor_phase3_report.md`
- `docs/2026-04-06/agentstate_refactor_phase4_report.md`
- `docs/2026-04-06/agentstate_refactor_phase5_report.md`

## 1. Objetivo

Dejar claro que falta de arquitectura despues del refactor de `AgentState` para poder seguir con nuevas features sin reabrir deuda estructural en:

- replanificacion;
- tracking y feedback adaptativo;
- reminders y jobs operativos;
- sync Microsoft;
- nuevos canales;
- RAG y recomendaciones de metodo de estudio.

Este documento no propone una reescritura ni un nuevo estilo arquitectonico. La recomendacion sigue siendo conservar el monolito modular orientado por grafo y cerrar las fronteras que aun siguen incompletas.

## 2. Que ya puede considerarse resuelto

La deuda principal sobre `AgentState` bajo de nivel de riesgo y ya no es el cuello de botella dominante.

Se considera resuelto para esta ola:

- ownership formal de campos en `src/agents/support/state.py`;
- vistas tipadas por dominio (`conversation_state`, `onboarding_state`, `scheduling_state`, `planning_state`, `integration_state`);
- helpers de update y reinicio menos fragiles;
- convergencia parcial entre `schedule.blocks` y `events`;
- salida de parsing contextual puro hacia `src/services/scheduling/`.

Conclusión:

- el problema ya no es "el estado no tiene forma";
- el problema ahora es "la topologia de ejecucion y de side-effects todavia no esta cerrada para crecer bien".

## 3. Diagnostico central post AgentState

Despues del trabajo del 2026-04-06, los pendientes importantes ya no estan concentrados en `state.py`. Quedaron repartidos en cuatro fronteras:

1. el grafo principal sigue demasiado centralizado en `src/agents/support/agent.py`;
2. scheduling conversacional todavia conserva parsing y normalizacion canonica fuera de `services/`;
3. el commit post-plan sigue mezclando persistencia, materializacion y reminders desde `agents/support/flows/planning/persistence_support.py`;
4. integraciones, jobs, observabilidad y seguridad todavia no tienen una frontera operativa suficientemente estable para abrir features nuevas con poco riesgo.

## 4. Hotspots que siguen condicionando el crecimiento

Medicion observada en el repo actual:

| Modulo | Lineas aprox. | Riesgo arquitectonico |
| --- | ---: | --- |
| `src/agents/support/flows/replanning/_update_flow.py` | 920 | replanificacion aun demasiado grande y con mucha logica acoplada |
| `src/integrations/microsoft_graph/auth_client.py` | 737 | OAuth, refresh, perfil y store en una sola pieza |
| `src/agents/support/flows/scheduling/schedule_review_service.py` | 707 | revision conversacional aun mezcla parte de composicion de dominio |
| `src/agents/support/agent.py` | 632 | routing, registro de nodos y politicas de espera en un solo archivo |
| `src/agents/support/flows/scheduling/schedule_capture_service.py` | 568 | subflujo de captura aun demasiado cargado |
| `src/agents/support/scheduling/normalizer.py` | 559 | normalizacion canonica todavia fuera de `services/` |

Lectura arquitectonica:

- estos hotspots no obligan a rehacer nada;
- si obligan a decidir bien donde vive cada feature nueva antes de implementarla.

## 5. Detalles de arquitectura que faltan cerrar

## 5.1 Grafo principal y politica de fases

### Problema actual

`src/agents/support/agent.py` sigue concentrando:

- registro de nodos;
- reglas de espera;
- routing por `phase`;
- decisiones transversales entre onboarding, scheduling, personalization y planning.

Ademas:

- `phase="sync"` hoy es un punto de transicion logico, no un nodo real;
- `phase="replan"` existe en el estado, pero no esta conectado al grafo principal.

### Que falta definir

Faltan reglas explicitas para decidir:

1. que merece una `phase` top-level;
2. que debe vivir como `substage` dentro de un dominio;
3. como se agrega una nueva feature sin agrandar `agent.py` en otro bloque monolitico.

### Recomendacion

Conservar `src/agents/support/agent.py` como entrypoint estable, pero partir internamente la orquestacion en modulos como:

```text
src/agents/support/graph/
  build.py
  routing.py
  phase_registry.py
  wait_policy.py
  transitions/
    onboarding.py
    scheduling.py
    planning.py
    replanning.py
```

Regla recomendada:

- `phase` solo para macro-etapas del agente;
- los detalles internos deben ir en subestados, por ejemplo `schedule.review_stage`, `schedule.capture_stage`, `replan.stage`, `onboarding.*`.

Decisiones concretas:

- eliminar la idea de usar `phase="sync"` como placeholder funcional;
- si hay side-effects post-plan, deben salir de un pipeline de aplicacion y no de una fase ficticia;
- cuando se conecte replanificacion, usar `phase="replan"` mas `replan.stage`, no una explosion de fases top-level.

## 5.2 Cierre canonico del dominio de scheduling

### Problema actual

El trabajo del 2026-04-06 movio parsing contextual y sincronizacion de varias piezas a `services/scheduling`, pero siguen vivas fuera de la capa de servicios:

- `normalize_schedule_section()` en `src/agents/support/scheduling/normalizer.py`;
- `parse_fixed_schedule_section()` y `parse_extracurricular_section()` en `src/agents/support/scheduling/pipeline.py`.

Ademas siguen pendientes tres campos legacy en `AgentState`:

- `events`
- `events_validated`
- `extras_has_any`

### Que falta definir

Falta cerrar cual es el modelo canonico del horario y cual es solo una proyeccion de compatibilidad.

### Recomendacion

Tomar estas decisiones como definitivas:

1. `schedule.blocks` es la fuente canonica del horario recurrente.
2. `events` se mantiene solo como proyeccion de compatibilidad para replanning y pruebas mientras se migra el resto.
3. `events_validated` debe tender a derivarse desde `phase + schedule.review_stage`.
4. `extras_has_any` debe tender a derivarse desde `extracurricular + extras_collect_stage`.

Siguiente paso tecnico recomendado:

- mover `normalize_schedule_section()` a `src/services/scheduling/`;
- mover el pipeline comun de secciones a `src/services/scheduling/`;
- dejar `agents/support/scheduling/*` solo como adapters temporales o utilidades conversacionales;
- hacer que `flows/scheduling/*` consuman solo servicios de dominio, prompts y helpers de estado.

Esto es importante porque manual replanning, cambios de horario base y syncs externos no deberian depender de parsing canonico alojado en la capa del agente.

## 5.3 Pipeline de commit academico post-plan

### Problema actual

`src/agents/support/flows/planning/persistence_support.py` sigue encadenando desde el agente:

- persistencia de priorities y study plan;
- materializacion de instancias;
- sincronizacion de reminders.

Hoy funciona, pero arquitectonicamente sigue siendo una frontera incompleta.

### Que falta definir

Falta una fachada de aplicacion unica para el cierre del plan academico.

Esa fachada debe declarar:

- que entra;
- que etapas ejecuta;
- como reporta fallas parciales;
- que resultados quedan listos para jobs futuros;
- como se extiende luego a tracking, sync externo y triggers de replan.

### Recomendacion

Crear un pipeline explicito en `src/services/planning/`, por ejemplo:

```text
src/services/planning/
  commit_pipeline.py
  commit_models.py
```

Contrato minimo sugerido:

- `StudyPlanCommitRequest`
- `StudyPlanCommitStageResult`
- `StudyPlanCommitResult`

Etapas del pipeline:

1. persistir snapshot academico;
2. materializar instancias;
3. sembrar/sincronizar reminders;
4. devolver estado consolidado para el nodo y para jobs posteriores.

Regla recomendada:

- el nodo LangGraph no debe coordinar side-effects de negocio en cadena;
- el nodo solo debe invocar el pipeline y mapear el resultado al estado conversacional.

Esta es la pieza que mas conviene cerrar antes de abrir replanificacion real, tracking reactivo o sync automatico.

## 5.4 Replanificacion como dominio de primera clase

### Problema actual

El repo ya tiene:

- `replan` en `AgentState`;
- flujos bajo `src/agents/support/flows/replanning/`;
- tablas `study_replan_requests` y `study_replan_proposals`.

Pero no existe aun una frontera completa entre:

- correccion conversacional del horario durante onboarding;
- replanificacion durable del plan ya persistido.

### Que falta definir

Falta separar dos conceptos distintos:

1. correccion del horario base antes de cerrar onboarding;
2. replanificacion del plan de estudio despues de que ya existen instancias, reminders y potencialmente tracking.

### Recomendacion

Cuando se conecte esta capability al grafo, introducir `src/services/replanning/` como slice propia.

Distribucion sugerida:

```text
src/services/replanning/
  request_service.py
  proposal_service.py
  application_service.py
  trigger_service.py
  models.py
```

Reglas de negocio recomendadas:

- una solicitud manual del usuario crea `study_replan_requests`;
- una sesion perdida, un cambio de horario base o un conflicto detectado pueden crear triggers automaticos;
- una propuesta aceptada debe generar un nuevo `study_plan_profile`, superseder el anterior, rematerializar instancias futuras y resincronizar reminders;
- cambios menores sobre captura inicial de horario no deben pasar por este pipeline: siguen siendo scheduling, no replanning.

Decisiones de estado recomendadas:

- usar `phase="replan"` cuando el usuario entre en ese subflujo;
- usar `replan.stage` para detalle interno;
- no agregar una fase top-level por cada subtarea de replan.

## 5.5 Feedback loop entre tracking y personalizacion

### Problema actual

El proyecto ya tiene `src/services/planning/tracking_service.py`, pero `src/services/personalization/` sigue siendo cuestionario inicial, no adaptacion.

### Que falta definir

Falta un contrato intermedio entre:

- datos crudos de `study_session_checkins`;
- recomendacion adaptativa de tecnicas;
- ajustes del planner.

### Recomendacion

No conectar `study_session_checkins` directamente al scoring actual.

Primero crear una capa de agregacion de señales, por ejemplo:

```text
src/services/personalization/
  learning_signals.py
  adaptive_recommendation.py
```

O, si la recomendacion de metodos va a crecer con contenido y RAG:

```text
src/services/study_methods/
  signals.py
  recommendation_service.py
  models.py
```

Contrato sugerido:

- `LearningSignalSnapshot`
- `TechniqueEffectivenessSnapshot`
- `StudyMethodRecommendationResult`

Regla recomendada:

- tracking alimenta señales agregadas;
- las señales ajustan recomendacion y planning;
- el cuestionario inicial sigue siendo baseline, no fuente unica.

Esto conviene hacerlo solo despues de que tracking y commit pipeline esten estables.

## 5.6 Sync Microsoft y desacople vendor-specific

### Problema actual

`src/integrations/microsoft_graph/auth_client.py` sigue mezclando:

- configuracion OAuth;
- transporte HTTP;
- exchange/refresh de tokens;
- obtencion de perfil;
- adaptacion al repositorio durable.

Ademas `src/services/sync/outlook_calendar_sync_service.py` y `src/services/sync/microsoft_todo_sync_service.py` estan muy modelados alrededor de Microsoft concreto.

### Que falta definir

Faltan dos fronteras:

1. una frontera interna entre OAuth y persistencia durable;
2. una frontera de servicios de sync que no queden casados a un solo proveedor.

### Recomendacion

Partir la integracion Microsoft en piezas menores, por ejemplo:

```text
src/integrations/microsoft_graph/
  oauth_config.py
  oauth_transport.py
  token_service.py
  profile_client.py
  auth_client.py        # wrapper/entrypoint estable
```

Y definir contratos en `src/services/sync/`:

- `CalendarSyncProvider`
- `TaskSyncProvider`
- `ConnectionResolver`

Regla recomendada:

- `services/sync/*` coordinan instancias, links y politicas de sync;
- `integrations/microsoft_graph/*` solo hablan el protocolo del proveedor;
- el binding con repositorios y settings debe salir del `AppContainer`, no quedar escondido en los clientes de integracion.

Adicional obligatorio antes de produccion:

- proteger tokens OAuth en repositorio o moverlos a un mecanismo de secreto/cifrado;
- unificar trazabilidad entre `student_id`, sync jobs y `thread_id` del checkpointer.

## 5.7 Canales nuevos: WhatsApp y Telegram

### Problema actual

La arquitectura ya reserva `src/integrations/whatsapp/`, pero hoy:

- no hay canal conversacional operativo;
- `whatsapp` existe como canal permitido para reminders, pero el dispatcher cae en `UnsupportedReminderSender("whatsapp")`;
- no existe aun una ruta equivalente para Telegram.

### Que falta definir

Falta separar claramente:

1. entrada conversacional de un canal;
2. salida conversacional del agente;
3. salida operacional de reminders;
4. resolucion de identidad del usuario por canal.

### Recomendacion

Normalizar el contrato de canal antes de implementar adapters concretos.

Distribucion sugerida:

```text
src/integrations/whatsapp/
  webhook.py
  sender.py
  models.py

src/integrations/telegram/
  webhook.py
  sender.py
  models.py
```

Y un contrato comun en `schemas/` o `services/` para:

- `InboundChannelMessage`
- `OutboundChannelMessage`
- `ChannelUserRef`

Regla recomendada:

- nodos y flujos del agente no deben preguntar por "si el canal es WhatsApp";
- los adapters convierten hacia un formato de mensaje normalizado;
- reminders y conversacion pueden reutilizar el mismo sender, pero con entrypoints de servicio distintos.

## 5.8 RAG y recomendacion de metodos de estudio

### Problema actual

`src/rag/` esta correctamente reservado, pero todavia no existe el contrato entre conocimiento recuperado y dominio academico.

### Que falta definir

Falta definir para que entra RAG y para que no.

### Recomendacion

Usar RAG solo para:

- enriquecer explicaciones de metodos de estudio;
- justificar recomendaciones;
- recuperar contenido o guias separadas del dato operativo.

No usar RAG para:

- persistencia del flujo;
- parseo canonico de horarios;
- reemplazar reglas de planning;
- resolver estado del usuario.

Frontera recomendada:

```text
src/rag/
  ingestion/
  retrieval/
  prompting/

src/services/study_methods/
  recommendation_service.py
  advisor.py
```

Regla recomendada:

- `services/study_methods/` consume RAG como dependencia de conocimiento;
- planning y personalization consumen resultados del servicio, no el retriever directamente.

## 5.9 Observabilidad, configuracion y jobs

### Problema actual

El repo sigue con tres debilidades operativas:

1. casi no hay logging estructurado visible;
2. la configuracion sigue fragmentada entre `bootstrap`, `services`, `integrations` y `agents/support/priorities/config.py`;
3. varios scripts todavia dependen de rutas legacy.

Hallazgos concretos en `scripts/`:

- `scripts/run_due_reminders.py` importa `agents.support.reminders_dispatcher`;
- `scripts/mark_missed_sessions.py` y `scripts/record_session_completion.py` importan `agents.support.planning.tracking_service`;
- `scripts/sync_outlook_calendar.py` y `scripts/sync_microsoft_todo.py` importan `agents.support.tools.db`;
- `scripts/microsoft_oauth_exchange_code.py` sigue usando `agents.support.tools.db_config` y repositorios legacy;
- `scripts/backfill_study_plan_instances.py` todavia importa contratos removidos desde `agents.support.state`.

### Que falta definir

Falta una politica operativa minima comun para:

- logs;
- settings;
- jobs;
- scripts de mantenimiento.

### Recomendacion

Agregar una base minima de observabilidad con campos estables:

- `trace_id`
- `thread_id`
- `student_id`
- `phase`
- `node`
- `service`
- `result`
- `error_code`

Y consolidar settings por dataclasses de dominio, no por lecturas directas dispersas de `os.getenv`.

Politica recomendada para scripts:

- los scripts deben depender de `bootstrap.container` o de builders oficiales en `services/`;
- no deben importar wrappers legacy ni contratos removidos;
- reminders, tracking y sync externo deben alinearse con la misma arquitectura que usa el runtime principal.

## 6. Arquitectura objetivo por feature

| Feature | Prerrequisitos arquitectonicos | Ownership recomendado |
| --- | --- | --- |
| Replanificacion manual | modularizar routing, cerrar scheduling canonico, crear commit pipeline | `agents/support/flows/replanning` + `services/replanning` + `repositories/planning/*` |
| Replanificacion automatica por sesion perdida | tracking estable, triggers de replan, commit pipeline | `services/planning/tracking_service.py` + `services/replanning/trigger_service.py` |
| Personalizacion adaptativa | tracking estable, agregacion de señales, contratos de recomendacion | `services/personalization/*` o `services/study_methods/*` |
| Sync Outlook Calendar / To Do | split de auth Microsoft, contratos de sync provider, jobs alineados | `services/sync/*` + `integrations/microsoft_graph/*` |
| WhatsApp / Telegram | contrato comun de mensajes/canales, senderes externos, observabilidad | `integrations/<canal>/*` + contrato comun en `schemas/` |
| RAG para metodos de estudio | frontera `study_methods`, separacion de dato operativo, versionado de corpus | `rag/*` + `services/study_methods/*` |

## 7. Orden recomendado de ejecucion

Para no mezclar demasiados frentes, conviene trabajar en bloques post-AgentState en este orden:

### Bloque A. Cierre de scheduling y modularizacion del grafo

- mover `normalize_schedule_section()` y el pipeline de secciones a `services/scheduling`;
- definir oficialmente `schedule.blocks` como fuente canonica;
- reducir `agent.py` a entrypoint + delegacion a registries/transitions;
- eliminar la semantica engañosa de `phase="sync"`.

### Bloque B. Pipeline de commit academico y alineacion operativa

- crear `services/planning/commit_pipeline.py`;
- dejar `persistence_support.py` como wrapper fino o retirarlo;
- alinear scripts de reminders, tracking y sync a servicios actuales;
- agregar guardrails para impedir imports legacy desde `scripts/`.

### Bloque C. Endurecimiento operativo

- logging estructurado minimo;
- settings centralizados por dominio;
- endurecimiento de tokens Microsoft;
- trazabilidad entre student, thread, jobs y sync.

### Bloque D. Features de negocio

- conectar replanificacion manual al grafo;
- despues conectar triggers automaticos desde tracking;
- luego abrir personalizacion adaptativa;
- despues abrir canales nuevos;
- RAG al final, cuando `study_methods/` ya exista como frontera real.

## 8. Decisiones explicitas que conviene tomar ya

1. No usar una reescritura del grafo como solucion.
2. No abrir RAG antes de tener `study_methods/` o una frontera equivalente.
3. No meter sync Microsoft dentro del grafo principal como nodos obligatorios en esta etapa.
4. No conectar personalizacion adaptativa directamente a check-ins crudos.
5. No seguir ampliando `agent.py` y `auth_client.py` como puntos de crecimiento por defecto.
6. No permitir que nuevos scripts usen rutas legacy fuera de `services/`, `repositories/`, `integrations/` y `bootstrap/`.

## 9. Conclusión

Despues de cerrar `AgentState`, lo que falta ya no es otra ola de particion del estado. Lo que falta es cerrar la arquitectura de ejecucion alrededor de:

- routing del grafo;
- scheduling como dominio canonico;
- commit post-plan;
- replanificacion como capability durable;
- adaptadores externos y operacion.

La mejor secuencia para continuar features del agente es:

1. cerrar esas fronteras;
2. endurecer operacion;
3. solo despues conectar replanificacion, adaptacion, nuevos canales y RAG.

Ese orden permite crecer sin volver a meter logica de negocio en `agents/support` ni reabrir la deuda que ya se empezo a resolver.
