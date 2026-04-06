# Scheduling Phase 3 Report

## Objetivo

La Fase 3 completa la extracción progresiva del dominio de scheduling moviendo la lógica de parseo y normalización de `parse_schedules_to_events` a un servicio de aplicación dedicado.

## Cambio principal

Se creó `src/agents/support/scheduling/schedule_parsing_service.py` para centralizar:

- validación de entradas crudas académicas y laborales
- parseo de texto hacia bloques semanales
- resolución de aclaraciones iniciales por sección
- transición a prompts de `awaiting_more`
- transición a solicitud de horario laboral cuando la ocupación es `ambos`
- avance a `extras` cuando el horario fijo queda completo

## Antes vs después

### Antes

- `src/agents/support/nodes/parse_schedules_to_events/node.py` contenía validación de entradas, parsing, actualización de bloques, decisiones de flujo y construcción de updates.

### Después

- `src/agents/support/nodes/parse_schedules_to_events/node.py` queda como wrapper delgado.
- `src/agents/support/scheduling/schedule_parsing_service.py` concentra la lógica de aplicación.

## Compatibilidad preservada

- No se cambió el nombre del nodo público `parse_schedules_to_events`.
- Se preservaron fases, prompts y updates del estado.
- Se mantuvo el contrato con `AgentState` y con los tests existentes.

## Archivos involucrados

### Nuevos

- `src/agents/support/scheduling/schedule_parsing_service.py`
- `tests/test_schedule_parsing_service.py`
- `docs/2026-04-03/scheduling_phase3_report.md`

### Actualizados

- `src/agents/support/nodes/parse_schedules_to_events/node.py`

## Resultado arquitectónico

Con esta fase, el flujo principal de scheduling queda repartido así:

- captura conversacional: `schedule_capture_service`
- resolución incremental de pendientes: `schedule_pending_resolution_service`
- parsing/normalización inicial: `schedule_parsing_service`
- revisión y corrección: `schedule_review_service`
- helpers compartidos de estado: `state_helpers`
- soporte extracurricular compartido: `extracurricular_support`

## Siguiente paso recomendado

La siguiente fase natural sería extraer un servicio específico para la consolidación del draft (`build_draft_schedule`) y empezar el módulo de planificación semanal que consuma bloques ya confirmados como entrada estable del dominio.
