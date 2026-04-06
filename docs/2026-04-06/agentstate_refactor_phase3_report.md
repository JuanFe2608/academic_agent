# AgentState Refactor Phase 3

Fecha: 2026-04-06

Estado: implementado y validado

## 1. Objetivo de esta fase

Avanzar la siguiente ola incremental del refactor de `AgentState` sin cambiar la arquitectura base del proyecto ni romper el flujo actual del agente.

Objetivos ejecutados:

1. identificar qué partes de `schedule_review_service` y `collect_extracurricular_details` pueden salir después a `services/`;
2. estabilizar la semántica de `events` frente a `schedule.blocks`;
3. iniciar una migración progresiva y de bajo riesgo de lógica pura desde `agents/support/flows` hacia `services/`.

## 2. Diagnóstico que motivó esta fase

El mayor problema abierto después de la fase 2 era este:

- `events` seguía existiendo como campo legacy útil para compatibilidad, pero su slice derivada desde el horario recurrente no tenía una semántica estable;
- `agents.support.scheduling.render.blocks_to_events()` reconstruía eventos de `schedule.blocks` con `new_event_id()`, lo que generaba IDs nuevos aunque los bloques no hubieran cambiado;
- parte de la lógica estructural de corrección y combinación de bloques seguía embebida en flows concretos, especialmente en:
  - `src/agents/support/flows/scheduling/schedule_review_service.py`
  - `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`

Conclusión:

- antes de mover más lógica a `services/`, había que fijar primero el contrato `schedule.blocks -> events`;
- después de eso sí era seguro empezar a sacar transformaciones puras de bloques fuera de los flows.

## 3. Qué partes se identificaron para salir después a `services/`

### 3.1 `schedule_review_service`

Se separó conceptualmente el archivo en dos tipos de lógica:

Lógica que debe seguir en `agents/support` por ahora:

- manejo de `phase`, `awaiting_user_input`, `messages` y prompts;
- parsing de intención conversacional (`sí/no`, menú de corrección, target de corrección);
- secuencia turn-based de revisión.

Lógica que pertenece al dominio de scheduling y puede migrar gradualmente:

- combinación y reemplazo de bloques por sección;
- sincronización de la sección corregida con `raw_inputs`;
- convergencia de `events` derivados desde `schedule.blocks`;
- composición de resultados de corrección sobre bloques ya normalizados.

### 3.2 `collect_extracurricular_details`

Lógica que debe seguir en `agents/support` por ahora:

- detección de nuevo turno del usuario;
- prompts de aclaración y de continuación;
- manejo conversacional de `extras_collect_stage`.

Lógica que pertenece al dominio de scheduling y puede migrar gradualmente:

- combinación de bloques extracurriculares normalizados con el horario actual;
- sincronización consistente de la sección extracurricular dentro de `schedule.blocks`;
- convergencia posterior entre `extracurricular`, `extras_has_any` y la proyección sobre bloques.

Dictamen:

- la frontera correcta no es “mover el flow completo”;
- la frontera correcta es sacar primero las mutaciones puras de bloques y dejar la conversación en `agents/support`.

## 4. Qué se implementó

### 4.1 Proyección estable `schedule.blocks -> events`

Archivo creado:

- `src/services/scheduling/event_projection.py`

Se añadieron:

- `schedule_block_event_id()`
- `build_schedule_block_event()`
- `blocks_to_schedule_events()`
- `sync_schedule_block_events()`

Decisión clave:

- los eventos con `origen="schedule_block"` ahora usan IDs determinísticos basados en `block_id`, con formato `schedule-block:<block_id>`.

Resultado:

- la proyección desde bloques recurrentes dejó de regenerar IDs aleatorios;
- `events` sigue existiendo por compatibilidad, pero su slice derivada desde el horario ahora es estable;
- la resincronización preserva eventos de otros dominios, por ejemplo `study_planner` o cambios directos de replanning.

### 4.2 Resincronización automática desde `update_scheduling_state()`

Archivo actualizado:

- `src/agents/support/scheduling/state_helpers.py`

Cambio aplicado:

- si cambia `schedule.blocks` y el caller no pasa `events` explícitos, `update_scheduling_state()` ahora resincroniza solo los eventos derivados desde bloques.

Importante:

- no sobrescribe todos los eventos;
- reemplaza únicamente los de `origen="schedule_block"` y preserva el resto.

Esto cierra la inconsistencia principal entre `AgentState.schedule` y `AgentState.events` sin romper compatibilidad con replanning.

### 4.3 Extracción de mutaciones puras a `services/`

Archivos creados:

- `src/services/scheduling/block_operations.py`
- `src/services/scheduling/section_mutations.py`

Se movió a `services/` la lógica pura de:

- `current_section_blocks()`
- `merge_section_blocks()`
- `replace_section_blocks()`
- `append_section_blocks()`
- `merge_completed_section_blocks()`

Propósito:

- centralizar mutaciones estructurales sobre `WeeklyScheduleBlock`;
- reducir duplicación de lógica de sección entre flows;
- dejar una base para seguir sacando lógica desde `agents/support/flows`.

### 4.4 Integración progresiva en los flows objetivo

Archivos actualizados:

- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`

Cambios aplicados:

- `schedule_review_service.py` ya usa `merge_completed_section_blocks()` para la corrección incremental de secciones fijas;
- `collect_extracurricular_details.py` ya usa `append_section_blocks()` para sincronizar nuevos bloques extracurriculares sobre el horario actual.

Resultado:

- comenzó la migración real de lógica pura a `services/`;
- la capa de flow mantiene la conversación y el routing;
- la capa de services empieza a concentrar las transformaciones canónicas del horario.

### 4.5 Adaptadores de compatibilidad preservados

Archivos actualizados:

- `src/agents/support/scheduling/render.py`
- `src/agents/support/scheduling/normalizer.py`
- `src/agents/support/scheduling/__init__.py`
- `src/services/scheduling/__init__.py`

Rol de estos cambios:

- `render.blocks_to_events()` quedó como adapter y delega en `services.scheduling.event_projection`;
- `merge_section_blocks` y `replace_section_blocks` pasan a resolverse desde `services/`, manteniendo compatibilidad con imports existentes en `agents/support`.

Esto evita una reescritura grande y mantiene el contrato actual del proyecto.

## 5. Qué no se movió todavía y por qué

No se movió todavía:

- `normalize_schedule_section()`
- `parse_fixed_schedule_section()`
- `parse_extracurricular_section()`
- `parse_extracurricular_items_with_context()`
- la construcción de prompts y decisiones conversacionales de revisión/captura

Razón:

- todavía están acoplados a decisiones de UX conversacional y a dependencias que no conviene mover en bloque en esta ola;
- hacerlo ahora aumentaría el riesgo y mezclaría el refactor de estado con un refactor mayor de aplicación.

Dictamen:

- esta fase sí inició la migración a `services/`, pero solo en la frontera segura y puramente estructural.

## 6. Archivos modificados

- `src/services/scheduling/block_operations.py`
- `src/services/scheduling/section_mutations.py`
- `src/services/scheduling/event_projection.py`
- `src/services/scheduling/__init__.py`
- `src/agents/support/scheduling/__init__.py`
- `src/agents/support/scheduling/normalizer.py`
- `src/agents/support/scheduling/render.py`
- `src/agents/support/scheduling/state_helpers.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `tests/test_scheduling_state_helpers.py`
- `tests/test_schedule_draft_service.py`

## 7. Verificación ejecutada

Primera validación focalizada:

```bash
.venv/bin/python -m pytest \
  tests/test_scheduling_state_helpers.py \
  tests/test_schedule_draft_service.py \
  tests/test_extracurricular_flow.py \
  tests/test_schedule_modifications.py \
  tests/test_schedule_parsing_service.py \
  tests/test_refactor_guardrails.py
```

Resultado:

- `48 passed in 5.84s`

Validación amplia posterior:

```bash
.venv/bin/python -m pytest \
  tests/test_agent_state_partitioning.py \
  tests/test_scheduling_state_helpers.py \
  tests/test_message_image_utils.py \
  tests/test_out_of_scope_restart.py \
  tests/test_agent_wait_routing.py \
  tests/test_schedule_request_flow.py \
  tests/test_extracurricular_flow.py \
  tests/test_collect_profile_validation.py \
  tests/test_personalization_flow.py \
  tests/test_priorities_flow.py \
  tests/test_study_planning_persistence.py \
  tests/test_refactor_guardrails.py \
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

- `123 passed in 14.51s`

## 8. Impacto conceptual del cambio

Antes:

- `events` era parcialmente derivado pero con identidad inestable;
- la mutación estructural de bloques estaba repartida entre `normalizer`, `render` y flows concretos;
- no había una frontera limpia para seguir sacando lógica de scheduling hacia `services/`.

Ahora:

- la slice `schedule_block` dentro de `events` tiene identidad estable;
- `update_scheduling_state()` puede resincronizar esa slice sin tocar eventos ajenos;
- las mutaciones puras de secciones ya tienen una casa clara en `services/scheduling`;
- `schedule_review_service` y `collect_extracurricular_details` quedaron un poco más enfocados en orquestación conversacional.

## 9. Riesgos restantes

- `events` sigue siendo un campo mixto, no exclusivamente de scheduling;
- `extras_has_any` y `events_validated` siguen siendo campos legacy no derivados;
- parte del parsing y de la normalización aún vive en `agents/support`, aunque ya quedó mejor delimitado qué debe salir después.

## 10. Siguiente paso recomendado

El siguiente paso correcto ya no es tocar `AgentState` directamente.

Conviene:

1. seguir sacando de `schedule_review_service` la lógica de sincronización entre secciones corregidas, `raw_inputs` y bloques;
2. evaluar si `merge_extracurricular_items()` y la serialización estable de actividades completas deben pasar a `services/scheduling`;
3. solo después comenzar la migración gradual de parsing y composición de resultados desde `agents/support/flows` hacia `services/`.

Dictamen final de la fase:

- la semántica de `events` quedó estabilizada respecto a `schedule.blocks`;
- se inició una migración real y segura de lógica pura hacia `services/`;
- el flujo visible del agente no cambió;
- la base quedó mejor preparada para la siguiente ola de refactor sin abrir una reescritura grande.
