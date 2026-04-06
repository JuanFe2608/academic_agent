# Scheduling Refactor Report

## Resumen

Esta fase refactoriza progresivamente los nodos más cargados del dominio de `scheduling` sin cambiar el grafo ni el contrato observable del flujo actual. La meta fue convertir los nodos LangGraph en coordinadores finos y mover la lógica de aplicación a servicios reutilizables, manteniendo compatibilidad con:

- `AgentState`
- fases actuales del grafo (`schedules`, `validate`, `schedule_edit`, `draft`, `extras`)
- prompts vigentes
- persistencia posterior en PostgreSQL a través del flujo existente

## Nodos intervenidos

- `request_schedules`
- `validate_schedule`
- `apply_schedule_correction`

## Responsabilidades antes y después

### `request_schedules`

**Antes**

- Detectaba nueva entrada del usuario.
- Parseaba ocupación y mensajes mixtos ocupación + horario.
- Decidía sección activa (`academic` / `work`).
- Resolvía pendientes de captura.
- Acumulaba `raw_inputs`.
- Construía prompts y updates de estado.

**Después**

- El nodo solo detecta nueva entrada y delega.
- `schedule_capture_service` coordina el flujo conversacional de captura.
- `schedule_pending_resolution_service` resuelve pendientes incrementales y serializa bloques hacia `raw_inputs`.

### `validate_schedule`

**Antes**

- Interpretaba decisiones sobre conflictos.
- Mostraba menú de corrección.
- Pedía payload de reemplazo.
- Confirmaba el horario final.
- Mutaba `review_stage`, `correction_target` y banderas de confirmación.

**Después**

- El nodo solo detecta nueva entrada y delega.
- `schedule_review_service` centraliza el flujo de revisión, aceptación de conflictos y solicitud de correcciones por sección.

### `apply_schedule_correction`

**Antes**

- Reprocesaba secciones académicas, laborales y extracurriculares.
- Resolvía pendientes derivados de correcciones.
- Actualizaba `raw_inputs`, bloques, extracurriculares y estado de revisión.
- Mezclaba normalización, reglas de negocio y mutación de estado.

**Después**

- El nodo solo delega.
- `schedule_review_service` aplica la corrección completa por sección.
- `schedule_pending_resolution_service` reutiliza lógica común para pendientes y merge de extracurriculares.

## Clasificación de la lógica extraída

### UX conversacional

- prompts de ocupación
- prompts por sección (`academic`, `work`)
- menú de corrección
- prompts de aclaración de pendientes
- prompts para continuar o agregar más bloques

### Parsing y normalización

- interpretación de respuesta de ocupación
- resolución de pendientes académicos/laborales
- parseo de payload de corrección
- reconstrucción determinista de bloques y `raw_inputs`

### Reglas de negocio

- orden de captura por ocupación
- obligatoriedad de resolver pendientes antes de avanzar
- aceptación explícita de conflictos
- corrección aislada por sección
- preservación de secciones no editadas

### Mutación de estado

- `schedule.capture_target`
- `schedule.capture_stage`
- `schedule.review_stage`
- `schedule.correction_target`
- `schedule.pending_correction_text`
- `academic_pending_items`
- `work_pending_items`
- `extras_pending_items`
- `raw_inputs`

### Persistencia

No se movió persistencia a estos servicios porque estos tres nodos no persisten directamente en PostgreSQL. La persistencia sigue ocurriendo aguas abajo del flujo existente, preservando el diseño actual.

## Servicios introducidos

### `schedule_capture_service`

Responsable de:

- coordinar la captura conversacional del horario fijo
- interpretar la ocupación del estudiante
- decidir la siguiente sección a solicitar
- avanzar entre `awaiting_input` y `awaiting_more`
- producir updates compatibles con el estado actual

### `schedule_pending_resolution_service`

Responsable de:

- coerción de pendientes del dominio
- resolución incremental de pendientes de captura
- merge de extracurriculares
- serialización auxiliar de información completada

### `schedule_review_service`

Responsable de:

- revisión final del horario
- aceptación o rechazo de cruces
- apertura del menú de corrección
- captura del payload de reemplazo
- aplicación de correcciones por sección

## Lógica extraída por nodo

### Extraída desde `request_schedules`

- parsing de ocupación
- detección de continuación vs. nuevo contenido
- resolución de pendientes de captura
- transición entre secciones
- armado de prompts por dominio

### Extraída desde `validate_schedule`

- parseo de decisiones de conflicto
- parseo de confirmación final
- menú y target de corrección
- prompt contextual para reemplazo por sección

### Extraída desde `apply_schedule_correction`

- merge y normalización de bloques corregidos
- resolución de pendientes derivados de correcciones
- reconstrucción de `raw_inputs`
- limpieza del estado de revisión tras una corrección exitosa

## Riesgos mitigados

- **Acoplamiento nodo-dominio**: la lógica central ya no vive dentro del nodo LangGraph.
- **Duplicación**: la resolución de pendientes y el merge de extracurriculares se centralizaron.
- **Regresiones por cambios futuros**: ahora es posible probar la lógica de aplicación sin pasar por el nodo.
- **Crecimiento del flujo**: la preparación para futuras integraciones o nuevos canales queda desacoplada del nodo.

## Compatibilidad preservada

- Se mantienen los nombres públicos del grafo.
- Se mantiene el contrato del `AgentState`.
- Se conservan las fases y transiciones principales del flujo.
- Se preserva la UX conversacional vigente.
- Se mantiene la naturaleza determinista del flujo de horarios.
- Se mantiene la compatibilidad con la persistencia relacional posterior.

## Observaciones y siguiente paso recomendado

La refactorización deja una base más limpia, pero aún existe oportunidad para una segunda fase enfocada en:

- extraer helpers de estado de `schedule.review_*` y `schedule.capture_*`
- reducir duplicación con `collect_extracurricular_details`
- aislar mejor la serialización estable hacia `raw_inputs`
- introducir pruebas más específicas sobre servicios de dominio y parsing contextual
