# AgentState Refactor Phase 4

Fecha: 2026-04-06

Estado: implementado y validado

## 1. Objetivo de esta fase

Continuar la estabilización alrededor de `AgentState` y de los flows de scheduling sin reescribir la arquitectura ni mover conversación fuera de `agents/support`.

Objetivos ejecutados:

1. terminar de sacar de `schedule_review_service` la lógica de sincronización entre secciones corregidas, `raw_inputs` y bloques;
2. evaluar y mover a `services/scheduling` las utilidades puras de `merge_extracurricular_items()` y la serialización estable de actividades completas;
3. iniciar una migración gradual del parsing y de la composición de resultados desde `agents/support/flows` hacia `services/`, sin romper el comportamiento actual.

## 2. Diagnóstico previo

Después de la fase 3 todavía quedaban tres tensiones:

- `schedule_review_service` seguía armando por sí mismo la sincronización entre bloques corregidos y `raw_inputs`;
- la lógica pura de extracurricular seguía alojada en `agents/support/scheduling/extracurricular_support.py`;
- el contrato `SectionPipelineResult` y parte de la composición alrededor del parsing aún vivían en `agents/support`, aunque conceptualmente pertenecen al dominio de scheduling.

Conclusión:

- la siguiente frontera segura no era mover más conversación;
- la siguiente frontera segura era completar la extracción de sincronización y contratos puros a `services/scheduling`.

## 3. Qué se implementó

### 3.1 Sincronización de secciones corregidas fuera de `schedule_review_service`

Archivos creados:

- `src/services/scheduling/raw_input_sync.py`
- `src/services/scheduling/correction_sync.py`

Se añadieron:

- `ensure_raw_inputs()`
- `serialize_blocks_for_schedule_type()`
- `sync_schedule_blocks_to_raw_inputs()`
- `FixedSectionSyncResult`
- `merge_completed_fixed_section()`
- `replace_fixed_section()`
- `sync_fixed_section_result()`

Propósito:

- encapsular toda la sincronización `bloques corregidos -> texto canónico de raw_inputs`;
- sacar de `schedule_review_service` la coordinación estructural entre bloques, texto crudo y sección objetivo;
- dejar una API reutilizable también por `schedule_pending_resolution_service`.

Archivos actualizados:

- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/scheduling/state_helpers.py`

Resultado:

- `schedule_review_service` dejó de recalcular manualmente `raw_inputs` para secciones académicas/laborales;
- `schedule_pending_resolution_service` ahora reutiliza la misma sincronización de dominio;
- `state_helpers.serialize_schedule_blocks_to_raw_inputs()` quedó como wrapper sobre la utilidad canónica de `services/scheduling`.

### 3.2 Evaluación de `merge_extracurricular_items()` y serialización de actividades

Dictamen de la evaluación:

- sí, estas funciones deben vivir en `services/scheduling`;
- no dependen de LangGraph, prompts ni estado conversacional;
- son lógica pura de dominio y además se reutilizan en más de un flow.

Implementación:

Archivo creado:

- `src/services/scheduling/extracurricular_state.py`

Funciones movidas:

- `coerce_extracurricular_pending_items()`
- `merge_extracurricular_items()`
- `build_extracurricular_item_source_text()`
- `build_extracurricular_items_source_text()`
- `build_extracurricular_reply_hint()`

Archivo convertido en adapter transitorio:

- `src/agents/support/scheduling/extracurricular_support.py`

Archivos consumidores actualizados:

- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`

Resultado:

- la lógica pura de extracurricular ya quedó centrada en `services/scheduling`;
- `agents/support/scheduling/extracurricular_support.py` ahora solo preserva compatibilidad temporal.

### 3.3 Inicio de la migración gradual de parsing y composición

No se movió todavía el parsing completo a `services/`, porque:

- `parse_schedule_section_with_context()` y parte del parsing extracurricular siguen usando piezas alojadas en `agents/support`;
- moverlo entero en esta fase aumentaba riesgo sin dar suficiente valor inmediato.

Sí se inició la migración en dos niveles:

Archivo creado:

- `src/services/scheduling/parsing_results.py`

Se movió:

- `SectionPipelineResult`

Archivo actualizado:

- `src/agents/support/scheduling/pipeline.py`

Resultado:

- el contrato de resultados del pipeline ya pertenece a `services/scheduling`;
- `agents/support/scheduling/pipeline.py` quedó más cerca de un adapter de parsing que de una fuente canónica de contratos.

Además, se movieron a `services/scheduling` dos piezas de composición asociadas al parsing:

- `build_schedule_pending_prompt()` en `src/services/scheduling/pending_schedule_support.py`
- `serialize_blocks_for_schedule_type()` en `src/services/scheduling/raw_input_sync.py`

Con esto, la composición posterior al parsing ya depende menos de `agents/support`.

## 4. Archivos creados

- `src/services/scheduling/raw_input_sync.py`
- `src/services/scheduling/pending_schedule_support.py`
- `src/services/scheduling/extracurricular_state.py`
- `src/services/scheduling/parsing_results.py`
- `src/services/scheduling/correction_sync.py`
- `tests/test_scheduling_domain_services.py`

## 5. Archivos actualizados

- `src/services/scheduling/__init__.py`
- `src/agents/support/scheduling/extracurricular_support.py`
- `src/agents/support/scheduling/contextual_parser.py`
- `src/agents/support/scheduling/state_helpers.py`
- `src/agents/support/scheduling/pipeline.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/flows/scheduling/schedule_parsing_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`

## 6. Qué cambió conceptualmente

Antes:

- `schedule_review_service` todavía mezclaba conversación con sincronización estructural;
- la lógica pura de extracurricular seguía atrapada en `agents/support`;
- el resultado del pipeline de parsing no estaba declarado en la capa de servicios.

Ahora:

- la sincronización de secciones fijas corregidas vive en `services/scheduling/correction_sync.py`;
- el dominio extracurricular puro vive en `services/scheduling/extracurricular_state.py`;
- `SectionPipelineResult` ya quedó declarado en `services/scheduling/parsing_results.py`;
- `agents/support` conserva la conversación, los prompts y la secuencia turn-based, pero pierde parte de la lógica estructural.

## 7. Qué no se movió todavía

No se movió todavía:

- `parse_schedule_section_with_context()`
- `complete_pending_schedule_item()`
- `parse_extracurricular_items_with_context()`
- la heurística de `normalize_schedule_section()`
- la secuencia conversacional de revisión/captura

Razón:

- siguen acoplados a adapters y helpers alojados en `agents/support`;
- moverlos en bloque requeriría una ola específica de refactor de parsing, no solo de estado.

## 8. Verificación ejecutada

Validación focalizada:

```bash
.venv/bin/python -m pytest \
  tests/test_scheduling_domain_services.py \
  tests/test_schedule_application_services.py \
  tests/test_schedule_modifications.py \
  tests/test_extracurricular_flow.py \
  tests/test_schedule_request_flow.py \
  tests/test_schedule_parsing_service.py \
  tests/test_fixed_schedule_pipeline.py \
  tests/test_refactor_guardrails.py
```

Resultado:

- `76 passed in 3.57s`

Validación amplia:

```bash
.venv/bin/python -m pytest \
  tests/test_agent_state_partitioning.py \
  tests/test_scheduling_state_helpers.py \
  tests/test_scheduling_domain_services.py \
  tests/test_message_image_utils.py \
  tests/test_out_of_scope_restart.py \
  tests/test_agent_wait_routing.py \
  tests/test_schedule_request_flow.py \
  tests/test_schedule_application_services.py \
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
  tests/test_fixed_schedule_pipeline.py \
  tests/test_study_planning_service.py \
  tests/test_reminder_policy_persistence.py
```

Resultado:

- `139 passed in 20.87s`

## 9. Riesgos restantes

- el parsing contextual académico/laboral sigue viviendo en `agents/support/scheduling/contextual_parser.py`;
- el parsing extracurricular con contexto sigue en `agents/support/nodes/collect_extracurricular_details/parsing.py`;
- los prompts siguen repartidos entre flows y adapters;
- todavía falta una ola específica para mover parsers y normalizadores sin romper la UX.

## 10. Recomendación de siguiente paso

El siguiente paso correcto ya no es tocar `AgentState` directamente.

Conviene:

1. mover gradualmente `parse_schedule_section_with_context()` y `complete_pending_schedule_item()` hacia `services/scheduling`;
2. evaluar si `parse_extracurricular_items_with_context()` puede seguir el mismo patrón;
3. dejar `agents/support/flows` solo con orquestación conversacional y routing, no con composición de dominio.

Dictamen final de la fase:

- la sincronización de correcciones ya salió de `schedule_review_service`;
- la lógica pura de extracurricular ya pertenece a `services/scheduling`;
- la migración de parsing/composición ya empezó, pero todavía de forma deliberadamente parcial y segura;
- el comportamiento visible del agente no se rompió.
