# Scheduling Phase 4 Report

## Objetivo

La Fase 4 extrae la consolidación del draft del horario desde `build_draft_schedule` a un servicio de aplicación, manteniendo el flujo actual de preview y validación.

## Cambio principal

Se creó `src/agents/support/scheduling/schedule_draft_service.py` para centralizar:

- detección determinista de conflictos entre bloques
- generación del resumen textual del horario
- preparación de eventos derivados para preview/persistencia posterior
- transición del flujo hacia `validate`

## Antes vs después

### Antes

- `src/agents/support/nodes/build_draft_schedule/node.py` mezclaba detección de conflictos, resumen y construcción del update.

### Después

- `src/agents/support/nodes/build_draft_schedule/node.py` queda como wrapper fino.
- `src/agents/support/scheduling/schedule_draft_service.py` concentra la lógica del dominio.

## Decisión sobre `render_schedule_preview`

`render_schedule_preview` fue auditado pero no se extrajo a un servicio nuevo en esta fase porque su responsabilidad principal es de presentación e I/O:

- render de imagen
- empaquetado de mensaje multimodal
- preparación del texto de confirmación para el usuario

Sí se alineó con los helpers tipados de estado para reducir mutaciones manuales.

## Archivos involucrados

### Nuevos

- `src/agents/support/scheduling/schedule_draft_service.py`
- `tests/test_schedule_draft_service.py`
- `docs/scheduling_phase4_report.md`

### Actualizados

- `src/agents/support/nodes/build_draft_schedule/node.py`
- `src/agents/support/nodes/render_schedule_preview/node.py`

## Compatibilidad preservada

- No se cambiaron nombres públicos del grafo.
- Se conservó la transición `build_draft_schedule -> render_schedule_preview -> validate_schedule`.
- La detección de conflictos sigue siendo determinista.
- El contrato de `AgentState` permanece igual.

## Resultado arquitectónico

Tras esta fase, el pipeline principal de scheduling queda distribuido así:

- captura conversacional: `schedule_capture_service`
- resolución de pendientes: `schedule_pending_resolution_service`
- parsing/normalización inicial: `schedule_parsing_service`
- consolidación del draft: `schedule_draft_service`
- revisión y corrección: `schedule_review_service`
- preview multimodal: `render_schedule_preview` como nodo de presentación

## Siguiente paso recomendado

La siguiente fase natural sería definir el primer servicio de planificación semanal sobre bloques ya confirmados, sin mezclar todavía Microsoft, WhatsApp o RAG.
