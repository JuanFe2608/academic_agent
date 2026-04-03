# Scheduling Phase 2 Report

## Objetivo

Esta fase profundiza el refactor inicial del dominio de `scheduling` para resolver los riesgos pendientes detectados tras la Fase 1:

- exceso de manipulación ad-hoc del subestado `schedule`
- serialización de `raw_inputs` dispersa entre servicios
- duplicación de lógica extracurricular entre scheduling y el flujo de extras

La implementación mantiene intactos:

- el grafo LangGraph
- los nombres públicos de nodos
- el contrato de `AgentState`
- el comportamiento visible para el usuario

## Riesgos pendientes y solución aplicada

### 1. Subestado `schedule` manejado como `dict` disperso

**Riesgo**

- Mutaciones manuales repetidas.
- Mayor probabilidad de olvidar campos al actualizar `capture_stage`, `review_stage` o flags de conflicto.

**Solución**

Se creó `src/agents/support/scheduling/state_helpers.py` con helpers tipados para:

- coaccionar `schedule` a `ScheduleFlowState`
- devolver updates compatibles con el grafo
- resetear metadatos de revisión de forma consistente
- centralizar cambios sobre `capture_target`, `capture_stage`, `review_stage` y flags relacionados

### 2. Serialización de `raw_inputs` acoplada a servicios concretos

**Riesgo**

- Lógica de serialización repetida y propensa a inconsistencias.
- Riesgo de actualizar solo una de las ramas académica/laboral cuando cambien los bloques.

**Solución**

En `src/agents/support/scheduling/state_helpers.py` se centralizaron:

- `append_schedule_input_text`
- `replace_schedule_input_text`
- `serialize_schedule_blocks_to_raw_inputs`

Con esto, la serialización estable queda aislada y lista para reutilizarse en futuras fases.

### 3. Duplicación extracurricular entre scheduling y extras

**Riesgo**

- Merge de actividades duplicado.
- Coerción de pendientes duplicada.
- Mensajes de ayuda parcialmente duplicados.

**Solución**

Se creó `src/agents/support/scheduling/extracurricular_support.py` y se reutilizó desde:

- `src/agents/support/scheduling/schedule_review_service.py`
- `src/agents/support/nodes/collect_extracurricular_details/node.py`

La lógica consolidada incluye:

- coerción de pendientes extracurriculares
- merge de actividades
- serialización de actividades completas
- hint de respuesta mínima para pendientes

## Archivos intervenidos

### Nuevos

- `src/agents/support/scheduling/state_helpers.py`
- `src/agents/support/scheduling/extracurricular_support.py`
- `tests/test_scheduling_state_helpers.py`
- `docs/scheduling_phase2_report.md`

### Actualizados

- `src/agents/support/scheduling/schedule_capture_service.py`
- `src/agents/support/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/scheduling/schedule_review_service.py`
- `src/agents/support/nodes/collect_extracurricular_details/node.py`
- `src/agents/support/nodes/parse_schedules_to_events/node.py`
- `src/agents/support/nodes/build_draft_schedule/node.py`

## Compatibilidad preservada

- Los nodos públicos del grafo no cambiaron de nombre.
- El flujo sigue siendo determinista.
- Los updates parciales siguen siendo compatibles con el reducer del estado.
- Los tests de scheduling y extracurriculares se mantienen verdes.

## Resultado arquitectónico

Tras esta fase, el dominio queda mejor separado en tres capas internas:

1. **Nodos LangGraph**: coordinadores finos
2. **Servicios de aplicación**: captura, revisión, corrección
3. **Helpers de dominio/estado**: subestado tipado, serialización y soporte extracurricular compartido

## Siguiente paso recomendado

La siguiente fase natural sería extraer un servicio específico de parsing/normalización para `parse_schedules_to_events` y empezar a preparar un módulo de planificación semanal que consuma los bloques ya confirmados sin mezclar conversación con reglas de planificación.
