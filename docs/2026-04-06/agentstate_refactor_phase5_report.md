# AgentState Refactor Phase 5

Fecha: 2026-04-06

Estado: implementado y validado

## 1. Objetivo de esta fase

Cerrar la siguiente frontera del refactor incremental alrededor de `AgentState` y de los flows de scheduling:

1. mover gradualmente `parse_schedule_section_with_context()` y `complete_pending_schedule_item()` hacia `services/scheduling`;
2. evaluar si `parse_extracurricular_items_with_context()` podía seguir el mismo patrón;
3. dejar a `agents/support/flows` más cerca de orquestación conversacional y routing, y menos cerca de composición de dominio.

## 2. Diagnóstico previo

Después de la fase 4, la sincronización de correcciones ya había salido de `schedule_review_service`, pero la frontera de parsing aún estaba partida:

- el parsing contextual académico/laboral seguía en `src/agents/support/scheduling/contextual_parser.py`;
- el parsing extracurricular con contexto seguía en `src/agents/support/nodes/collect_extracurricular_details/parsing.py`;
- varios flows dependían todavía de esos módulos de `agents/support`, aunque conceptualmente ya no eran conversación sino dominio.

Conclusión:

- la siguiente extracción segura era mover el parsing contextual puro a `services/scheduling`;
- luego dejar adapters transitorios en `agents/support` para no romper imports ni pruebas existentes.

## 3. Qué se implementó

### 3.1 Parsing contextual académico/laboral movido a `services/scheduling`

Archivos creados:

- `src/services/scheduling/title_normalization.py`
- `src/services/scheduling/heuristic_schedule_parsing.py`
- `src/services/scheduling/contextual_schedule_parsing.py`

Responsabilidad nueva:

- `title_normalization.py` concentra la normalización estable de títulos;
- `heuristic_schedule_parsing.py` concentra helpers reutilizables de días, horas, títulos y segmentación;
- `contextual_schedule_parsing.py` ahora contiene:
  - `parse_schedule_section_with_context()`
  - `complete_pending_schedule_item()`

Evidencia:

- [contextual_schedule_parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/contextual_schedule_parsing.py#L55)
- [contextual_schedule_parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/contextual_schedule_parsing.py#L71)

Resultado:

- el parsing contextual académico/laboral ya pertenece formalmente al dominio de `services/scheduling`;
- la capa de agente dejó de ser la fuente canónica de estas funciones.

### 3.2 `parse_extracurricular_items_with_context()` sí siguió el mismo patrón

Evaluación:

- sí, el parser extracurricular con contexto seguía siendo lógica pura de dominio;
- no dependía de LangGraph ni de composición root;
- solo requería mover la normalización de títulos y conservar el contrato de `PendingExtracurricularItem`.

Archivo creado:

- `src/services/scheduling/extracurricular_parsing.py`

Funciones movidas:

- `parse_extracurricular_text()`
- `parse_extracurricular_items()`
- `parse_extracurricular_items_with_context()`
- `complete_pending_extracurricular_item()`

Evidencia:

- [extracurricular_parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/extracurricular_parsing.py#L82)
- [extracurricular_parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/extracurricular_parsing.py#L152)
- [extracurricular_parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/services/scheduling/extracurricular_parsing.py#L212)

Dictamen:

- la evaluación fue positiva;
- el patrón sí aplicaba y se implementó en esta misma fase.

### 3.3 `agents/support` quedó como adapter transitorio

Archivos convertidos en adapters finos:

- `src/agents/support/scheduling/contextual_parser.py`
- `src/agents/support/nodes/collect_extracurricular_details/parsing.py`
- `src/agents/support/scheduling/titles.py`

Evidencia:

- [contextual_parser.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/scheduling/contextual_parser.py#L1)
- [parsing.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/nodes/collect_extracurricular_details/parsing.py#L1)

Resultado:

- se preservó backward compatibility de imports;
- el código canónico ya no vive en `agents/support`.

### 3.4 Flows más orientados a orquestación

Archivos actualizados:

- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`

Cambios relevantes:

- `schedule_review_service.py` ya importa directamente:
  - `complete_pending_schedule_item()` desde `services/scheduling/contextual_schedule_parsing`
  - `complete_pending_extracurricular_item()` y `parse_extracurricular_items()` desde `services/scheduling/extracurricular_parsing`
- `schedule_pending_resolution_service.py` ya importa `complete_pending_schedule_item()` desde `services/scheduling/contextual_schedule_parsing`
- `collect_extracurricular_details.py` ya importa:
  - `complete_pending_extracurricular_item()`
  - `parse_extracurricular_items_with_context()`
  desde `services/scheduling/extracurricular_parsing`

Evidencia:

- [schedule_review_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_review_service.py#L10)
- [schedule_pending_resolution_service.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/scheduling/schedule_pending_resolution_service.py#L20)
- [collect_extracurricular_details.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/flows/extracurricular/collect_extracurricular_details.py#L27)

Resultado:

- los flows quedaron menos acoplados a módulos de soporte internos;
- la orquestación conversacional permanece en `agents/support/flows`;
- el parsing contextual puro ya no está incrustado ahí.

### 3.5 Composición de dominio movida parcialmente a `services/`

Además del parsing puro, se reforzó la frontera de dominio con:

- `services/scheduling/__init__.py` actualizado para exportar los nuevos parsers y helpers;
- `agents/support/scheduling/pipeline.py` pasando a consumir `parse_extracurricular_items_with_context()` desde `services/`;
- `agents/support/scheduling/normalizer.py` pasando a consumir `parse_extracurricular_items()` desde `services/`.

Esto no mueve todavía todo el pipeline a `services/`, pero sí reduce la composición alojada en `agents/support`.

## 4. Qué no se movió todavía

No se movió todavía:

- `normalize_schedule_section()`
- `parse_fixed_schedule_section()`
- `parse_extracurricular_section()`
- la heurística grande de normalización de secciones

Razón:

- aunque ya dependen mucho menos de `agents/support`, siguen anclados al módulo `normalizer.py`;
- mover eso sin cuidado ya sería otra ola de refactor, más amplia que este paso incremental.

## 5. Qué cambió conceptualmente

Antes:

- el parsing contextual real del dominio seguía viviendo en la capa del agente;
- `agents/support` seguía siendo fuente canónica de partes importantes del parsing;
- los flows dependían de módulos internos del agente para operaciones que ya no eran estrictamente conversacionales.

Ahora:

- el parsing contextual académico/laboral ya vive en `services/scheduling/contextual_schedule_parsing.py`;
- el parsing extracurricular con contexto ya vive en `services/scheduling/extracurricular_parsing.py`;
- `agents/support` quedó como adapter transitorio y como capa de orquestación;
- los flows consumen más servicios de dominio y menos helpers internos del agente.

## 6. Archivos creados

- `src/services/scheduling/title_normalization.py`
- `src/services/scheduling/heuristic_schedule_parsing.py`
- `src/services/scheduling/contextual_schedule_parsing.py`
- `src/services/scheduling/extracurricular_parsing.py`

## 7. Archivos actualizados

- `src/services/scheduling/__init__.py`
- `src/agents/support/scheduling/titles.py`
- `src/agents/support/scheduling/contextual_parser.py`
- `src/agents/support/nodes/collect_extracurricular_details/parsing.py`
- `src/agents/support/scheduling/normalizer.py`
- `src/agents/support/scheduling/pipeline.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `tests/test_scheduling_domain_services.py`

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
  tests/test_refactor_guardrails.py \
  tests/test_ambiguous_time_validation.py
```

Resultado:

- `86 passed in 3.48s`

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
  tests/test_ambiguous_time_validation.py \
  tests/test_study_planning_service.py \
  tests/test_reminder_policy_persistence.py
```

Resultado:

- `149 passed in 29.69s`

## 9. Riesgos restantes

- `parse_fixed_schedule_section()` y `parse_extracurricular_section()` aún dependen del `pipeline` y del `normalizer` en `agents/support`;
- `normalize_schedule_section()` sigue siendo una pieza grande de dominio fuera de `services/`;
- los adapters transitorios siguen siendo necesarios para no romper imports históricos.

## 10. Recomendación de siguiente paso

El siguiente paso razonable ya no es seguir moviendo helpers pequeños.

Conviene:

1. evaluar si `normalize_schedule_section()` puede migrar a `services/scheduling` con el mismo patrón de adapter;
2. después de eso mover `parse_fixed_schedule_section()` y `parse_extracurricular_section()` a `services/`;
3. finalmente dejar `agents/support/flows` consumiendo solo servicios de dominio y utilidades conversacionales.

Dictamen final de la fase:

- `parse_schedule_section_with_context()` y `complete_pending_schedule_item()` ya quedaron en `services/scheduling`;
- `parse_extracurricular_items_with_context()` sí pudo seguir el mismo patrón y también fue movido;
- `agents/support` quedó más cerca de adapters y orquestación, y menos cerca de parsing canónico de dominio;
- el comportamiento visible del agente no se rompió.
