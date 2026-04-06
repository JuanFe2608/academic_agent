# Refactor Incremental De AgentState

Fecha: 2026-04-06

Estado: implementado y verificado

## 1. Objetivo

Reducir el riesgo arquitectónico identificado en la auditoría sobre `AgentState` sin romper el flujo actual del agente ni cambiar el estilo arquitectónico del proyecto.

Objetivos concretos de esta sesión:

- documentar ownership del estado;
- particionar el estado por dominio;
- mantener compatibilidad con LangGraph y con el contrato plano actual;
- eliminar reseteos manuales dispersos;
- dejar una base clara para migrar lectores/escritores hacia subestados tipados.

## 2. Diagnóstico Inicial

### Hallazgo principal

`src/agents/support/state.py` ya reutilizaba DTOs de `schemas/`, pero seguía exponiendo un estado top-level muy ancho y transversal.

Problemas observados antes del cambio:

- `AgentState` mezclaba runtime conversacional, onboarding, scheduling, planificación, recordatorios e integración externa en un solo nivel.
- El ownership de varios campos no estaba declarado en código.
- Había campos operativos y derivables al mismo nivel que campos canónicos del flujo.
- El reinicio desde `out_of_scope` en `src/agents/support/nodes/welcome_consent/node.py` reconstruía manualmente un payload grande, frágil y propenso a divergencias.
- El router de `src/agents/support/agent.py` seguía leyendo el estado mayormente como bolsa plana con `state.get(...)`.

### Diagnóstico técnico

La situación no requería una reescritura. El contrato plano sigue siendo necesario porque:

- LangGraph hoy opera sobre claves top-level;
- muchos nodos devuelven updates planos;
- múltiples pruebas recrean el estado con `AgentState(**payload)` a partir de `model_dump()`.

Por eso la estrategia correcta era:

- conservar el contrato plano;
- introducir subestados tipados como vistas canónicas;
- centralizar el reset;
- migrar lectores críticos de forma incremental.

## 3. Ownership De Campos

Notas:

- La tabla lista escritores y lectores principales, no necesariamente exhaustivos.
- Las categorías `durable`, `transitorio`, `derivado` y `control de flujo` se usan en sentido conversacional/runtime, no exclusivamente de persistencia en base de datos.

| Campo | Tipo actual | Escritores principales | Lectores principales | Dominio | Categoría | Criticidad | Propuesta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `messages` | `list[BaseMessage]` | casi todos los nodos y flujos vía `append_message`; p.ej. `nodes/welcome_consent/node.py`, `flows/onboarding/collect_profile.py` | `detect_new_input` en onboarding, scheduling, personalization y routing | conversation/runtime | durable | alta | conservar en runtime tipado |
| `phase` | `Phase` | prácticamente todos los nodos; p.ej. `welcome_consent`, `collect_profile`, `persist_schedule`, `build_study_plan` | `src/agents/support/agent.py` | conversation/runtime | control de flujo | alta | conservar en runtime tipado |
| `errors` | `list[str]` | flujos de replanning y generación de extras; p.ej. `flows/replanning/_direct_changes.py`, `services/scheduling/extracurricular_events.py` | replanning y generación de eventos | conversation/runtime | transitorio | media | mover a runtime tipado |
| `timezone` | `str` | default en `make_initial_state`; puede inyectarse al crear `AgentState` | onboarding, scheduling, planning, personalization, reminders | conversation/runtime | durable | alta | conservar en runtime tipado |
| `user_status` | `Literal[start,valid,out_of_scope]` | `collect_profile`, `welcome_consent` | routing en `agent.py`, onboarding | onboarding + runtime | control de flujo | alta | mover a runtime tipado |
| `welcome_sent` | `bool` | `welcome_consent` | `welcome_consent` | conversation/runtime | control de flujo | media | mover a runtime tipado |
| `last_user_text` | `str \| None` | onboarding, scheduling, extras, personalization, priorities | `detect_new_input`, routing de espera | conversation/runtime | transitorio | alta | mover a runtime tipado |
| `last_user_images` | `list[str]` | reset en `welcome_consent`; tracking indirecto desde `detect_new_input` | `_should_wait`, `detect_new_input` | conversation/runtime | transitorio | media | mover a runtime tipado |
| `profile_edit_target` | `str \| None` | `nodes/confirm_profile/node.py` | `nodes/confirm_profile/node.py` | onboarding | control de flujo | media | mover a runtime tipado por compatibilidad temporal |
| `user_message_count` | `int` | onboarding, scheduling, extras, personalization, priorities | `detect_new_input`, routing | conversation/runtime | control de flujo | alta | mover a runtime tipado |
| `awaiting_user_input` | `bool` | prácticamente todos los nodos del flujo | `_should_wait`, routing global | conversation/runtime | control de flujo | alta | mover a runtime tipado |
| `consent` | `ConsentState` | `nodes/welcome_consent/node.py` | `agent.py`, `welcome_consent` | onboarding | durable | alta | mover a subestado onboarding |
| `student_profile` | `StudentProfile` | `flows/onboarding/collect_profile.py`, `nodes/confirm_profile/node.py`, `nodes/verify_email_code/node.py`, `nodes/persist_profile/node.py` | onboarding, scheduling, persistencia, planning | onboarding | durable | alta | mover a subestado onboarding |
| `onboarding` | `OnboardingState` | `collect_profile`, `send_email_verification`, `verify_email_code`, `persist_profile` | onboarding nodes y validators | onboarding | control de flujo | alta | mover a subestado onboarding |
| `raw_inputs` | `RawInputs` | `schedule_capture_service`, `schedule_review_service`, replanning directo | `schedule_parsing_service`, `agent.py`, correcciones | scheduling | durable | alta | mover a subestado scheduling |
| `extras_has_any` | `bool \| None` | `ask_extracurricular`, `schedule_review_service` | `_route_extras`, `ask_extracurricular` | scheduling | control de flujo | media | mover a subestado scheduling; convertir en derivado más adelante |
| `extras_collect_stage` | `Literal \| None` | `ask_extracurricular`, `collect_extracurricular_details` | `_route_collect_extracurricular`, flujo de extras | scheduling | control de flujo | alta | mover a subestado scheduling |
| `extras_pending_is_variable` | `bool \| None` | `ask_extracurricular`, `collect_extracurricular_details` | flujo de extras | scheduling | transitorio | media | mover a subestado scheduling |
| `extras_pending_items` | `list[PendingExtracurricularItem]` | `collect_extracurricular_details`, `schedule_review_service` | flujo de extras y corrección | scheduling | transitorio | alta | mover a subestado scheduling |
| `academic_pending_items` | `list[PendingScheduleItem]` | `schedule_parsing_service`, `schedule_review_service` | `agent.py`, `schedule_capture_service`, corrección | scheduling | transitorio | alta | mover a subestado scheduling |
| `work_pending_items` | `list[PendingScheduleItem]` | `schedule_parsing_service`, `schedule_review_service` | `agent.py`, `schedule_capture_service`, corrección | scheduling | transitorio | alta | mover a subestado scheduling |
| `extracurricular` | `list[ExtracurricularItem]` | `collect_extracurricular_details`, `schedule_review_service`, replanning | draft, review, replanning | scheduling | durable | media | mover a subestado scheduling |
| `events` | `list[Event]` | `schedule_parsing_service`, `schedule_draft_service`, replanning | replanning, generación de extras, pruebas de parsing | scheduling | derivado | media | mover a subestado scheduling; revisar convergencia con `schedule.blocks` en próxima ola |
| `events_validated` | `bool` | `schedule_draft_service`, `schedule_review_service` | pruebas y gating de revisión | scheduling | control de flujo | media | mover a subestado scheduling; candidato a derivado |
| `schedule_preview` | `SchedulePreview` | `schedule_draft_service`, `render_schedule_preview` | `agent.py`, `render_schedule_preview` | scheduling | derivado | media | mover a subestado scheduling |
| `schedule` | `ScheduleFlowState` | `schedule_capture_service`, `schedule_parsing_service`, `schedule_draft_service`, `schedule_review_service`, `persist_schedule` | routing, preview, persistencia, priorities | scheduling | durable | alta | mover a subestado scheduling |
| `calendar` | `CalendarState` | hoy principalmente inicialización/reset; sync Outlook lo consume fuera del grafo principal | servicios de sync Outlook y futuras integraciones | integración externa | durable | baja | mover a subestado integrations |
| `subjects` | `list[SubjectItem]` | `persist_study_profile`, `priority_capture_service`, `build_study_plan` | prioridades y planning | planning | durable | alta | mover a subestado planning |
| `study_profile` | `StudyProfile` | `collect_study_profile`, `collect_study_profile_tiebreaker`, `persist_study_profile` | routing post-schedule, priorities, planning, persistencia | personalization | durable | alta | mover a subestado planning |
| `priorities` | `PrioritiesState` | `priority_capture_service`, `persistence_support` | priorities y planning | planning | durable | alta | mover a subestado planning |
| `study_plan` | `StudyPlanState` | `build_study_plan`, `persist_study_profile`, `persistence_support` | planning, materialización, reminders | planning | durable | alta | mover a subestado planning |
| `replan` | `ReplanState` | `render_schedule_preview`, `flows/replanning/*` | replanning y preview | planning/runtime | control de flujo | media | mover a subestado planning |
| `reminders` | `RemindersState` | `persistence_support` | sync de reminders y persistencia | reminders | durable | media | mover a subestado planning en esta fase; aislar luego si crece |
| `constraints` | `Constraints` | default de estado; puede llegar por updates externos | `persist_study_profile`, `build_study_plan`, `services/planning/*` | planning | durable | media | mover a subestado planning |

## 4. Campos Más Problemáticos Antes Del Cambio

### Ambiguos o multiuso

- `events`: sirve como vista derivada del horario, pero también como base para replanning. No es claramente canónico frente a `schedule.blocks`.
- `extras_has_any`: expresa una decisión conversacional, pero también intenta resumir si existen actividades. Puede derivarse parcialmente de `extracurricular`.
- `events_validated`: es un flag de progreso, no un dato de negocio.
- `profile_edit_target`: es control de flujo de onboarding, no parte del perfil del estudiante.

### Ownership difuso

- El reset completo desde `out_of_scope` estaba disperso y manual.
- El router usaba muchas claves planas sin declarar la frontera entre runtime, onboarding y scheduling.

### Temporales tratados como canónicos

- `last_user_text`
- `last_user_images`
- `user_message_count`
- `awaiting_user_input`
- `extras_pending_items`
- `academic_pending_items`
- `work_pending_items`

## 5. Propuesta De Subestados

La partición adoptada en código fue:

- `conversation_state`
- `onboarding_state`
- `scheduling_state`
- `planning_state`
- `integration_state`
- `partitions`

### Responsabilidad de cada subestado

#### `conversation_state`

Ownership de metadata transversal y control de turno:

- `messages`
- `phase`
- `errors`
- `timezone`
- `user_status`
- `welcome_sent`
- `last_user_text`
- `last_user_images`
- `profile_edit_target`
- `user_message_count`
- `awaiting_user_input`

#### `onboarding_state`

Ownership del perfil y del subflujo de onboarding:

- `consent`
- `student_profile`
- `onboarding`

#### `scheduling_state`

Ownership del flujo de horarios y actividades:

- `raw_inputs`
- flags y pendientes de extras
- pendientes académicos/laborales
- `extracurricular`
- `events`
- `events_validated`
- `schedule_preview`
- `schedule`

#### `planning_state`

Ownership de personalización, prioridades, plan, replan, reminders y constraints:

- `subjects`
- `study_profile`
- `priorities`
- `study_plan`
- `replan`
- `reminders`
- `constraints`

#### `integration_state`

Ownership de metadatos de integración externa acoplados al grafo:

- `calendar`

## 6. Estrategia De Migración Incremental

### Etapa 1

Tipado y declaración de ownership sin romper el contrato plano.

Resultado:

- implementada en esta sesión.

### Etapa 2

Exponer composición tipada del estado desde `AgentState`.

Resultado:

- implementada en esta sesión con propiedades:
  - `conversation_state`
  - `onboarding_state`
  - `scheduling_state`
  - `planning_state`
  - `integration_state`
  - `partitions`

### Etapa 3

Migrar lectores de bajo riesgo a los subestados tipados.

Resultado:

- implementada parcialmente:
  - `_should_wait`
  - `_route_request_schedules`
  - `_route_extras`
  - `_route_collect_extracurricular`

### Etapa 4

Centralizar resets y payloads legacy.

Resultado:

- implementada con `restart_payload_for_new_attempt()`.

### Etapa 5

Migrar escritores hotspots y deprecar flags derivables.

Resultado:

- pendiente para próxima ola.

## 7. Implementación Realizada

### 7.1 Cambios en `src/agents/support/state.py`

Se añadieron vistas tipadas internas:

- `_ConversationState`
- `_OnboardingDomainState`
- `_SchedulingDomainState`
- `_PlanningDomainState`
- `_IntegrationState`
- `_PartitionedAgentState`

Se añadió un mapa formal de partición:

- `AgentState._FIELD_GROUPS`
- `AgentState.field_groups()`
- `AgentState.field_group_for()`

Se añadieron accesores tipados:

- `conversation_state`
- `onboarding_state`
- `scheduling_state`
- `planning_state`
- `integration_state`
- `partitions`

Se añadió compatibilidad explícita con el contrato actual:

- `legacy_group_payload()`
- `_group_payload()`
- `restart_payload_for_new_attempt()`

Se extendió `make_initial_state()` para aceptar `timezone` sin romper la firma actual de uso.

### 7.2 Cambios en `src/agents/support/nodes/welcome_consent/node.py`

Se eliminó el reset manual enorme de `_restart_after_out_of_scope()`.

Ahora el reinicio:

- usa `state.restart_payload_for_new_attempt(...)`;
- toma defaults desde un `AgentState` fresco;
- reduce el riesgo de divergencia si cambian defaults del estado.

### 7.3 Cambios en `src/agents/support/agent.py`

Se migraron lectores de bajo riesgo para usar las vistas tipadas:

- `_should_wait()` usa `conversation_state`;
- `_route_request_schedules()` usa `onboarding_state`, `scheduling_state` y `conversation_state`;
- `_route_extras()` usa `scheduling_state`;
- `_route_collect_extracurricular()` usa `scheduling_state`.

Esto no cambia comportamiento funcional; solo reduce acceso desestructurado al top-level.

## 8. Pruebas Añadidas Y Actualizadas

Se añadió:

- `tests/test_agent_state_partitioning.py`

Casos cubiertos:

- cobertura total y no solapada de los grupos de campos;
- acceso a particiones tipadas por dominio;
- reset consistente para reinicio de conversación;
- soporte de `timezone` en `make_initial_state()`.

## 9. Verificación Ejecutada

### Batería 1

Comando:

```bash
.venv/bin/python -m pytest \
  tests/test_agent_state_partitioning.py \
  tests/test_out_of_scope_restart.py \
  tests/test_agent_wait_routing.py \
  tests/test_schedule_request_flow.py \
  tests/test_extracurricular_flow.py \
  tests/test_collect_profile_validation.py \
  tests/test_personalization_flow.py \
  tests/test_priorities_flow.py \
  tests/test_study_planning_persistence.py \
  tests/test_refactor_guardrails.py
```

Resultado:

- `84 passed in 7.33s`

### Batería 2

Comando:

```bash
.venv/bin/python -m pytest \
  tests/test_email_verification_nodes.py \
  tests/test_schedule_modifications.py \
  tests/test_schedule_draft_service.py \
  tests/test_schedule_persistence.py \
  tests/test_schedule_preview.py \
  tests/test_schedule_parsing_service.py \
  tests/test_study_planning_service.py \
  tests/test_reminder_policy_persistence.py
```

Resultado:

- `26 passed in 2.47s`

### Resultado total validado

- `110 pruebas aprobadas`

## 10. Qué Cambió

- `AgentState` ahora tiene ownership formal por dominio.
- El proyecto ya cuenta con una composición tipada del estado sin romper LangGraph.
- El reset desde `out_of_scope` dejó de depender de un bloque manual largo y frágil.
- Parte del router crítico ya lee subestados tipados en vez de depender completamente de claves planas.
- Hay guardrails de pruebas para evitar que nuevos campos queden fuera de la partición.

## 11. Qué No Cambió

- No se reescribió la arquitectura.
- No se cambió `langgraph.json`.
- No se cambió el entrypoint principal.
- No se eliminó el contrato plano del grafo.
- No se movió masivamente lógica de `agents/support/flows` a `services/`.
- No se eliminaron campos legacy.
- No se modificó comportamiento visible del flujo.

## 12. Riesgos Restantes

### Riesgos aún presentes

- Los nodos siguen devolviendo updates planos; por eso el contrato legacy sigue vivo.
- `events`, `events_validated` y `extras_has_any` siguen existiendo como campos top-level y todavía no fueron deprecados.
- Replanning sigue operando fuertemente sobre `state.get("events")`.
- Hay muchos escritores del estado repartidos en `flows/scheduling`, `flows/extracurricular` y `flows/replanning`.

### Riesgo reducido

- El ownership del estado ya no depende solo de interpretación humana.
- El reset de conversación ya no puede quedarse desactualizado tan fácilmente.

## 13. Siguiente Ola De Refactor Recomendado

Orden sugerido:

1. introducir helpers de update por subestado para scheduling y runtime, análogos a `update_schedule_flow_state()`;
2. migrar hotspots de escritura en `schedule_capture_service`, `collect_extracurricular_details` y `schedule_review_service` para usar esos helpers;
3. marcar `events`, `events_validated` y `extras_has_any` como candidatos a derivación controlada;
4. encapsular todavía más el routing sobre `conversation_state`, `onboarding_state` y `scheduling_state`;
5. recién después abordar la migración progresiva de lógica desde `agents/support/flows` hacia `services/`.

## 14. Conclusión

El problema de `AgentState` no se resolvía con una reescritura. Se resolvía declarando límites sin romper el flujo existente.

Esta sesión deja:

- un `AgentState` formalmente particionado;
- compatibilidad total con el contrato actual del grafo;
- menor riesgo de seguir creciendo sobre un estado amorfo;
- una base concreta para el siguiente refactor incremental.

Para este MVP, la solución implementada es la correcta: menos riesgosa que una reestructuración total y suficientemente fuerte para sostener la siguiente ola de limpieza arquitectónica.
