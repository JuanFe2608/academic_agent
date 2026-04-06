# Refactor Fase 2

Fecha: 2026-04-03

Estado: completada

Documento rector: `docs/2026-04-03/plan_maestro_refactorizacion_arquitectura.md`

## Objetivo Ejecutado

Reducir `src/agents/support/state.py` a su responsabilidad de ensamblaje del estado conversacional y mover contratos reutilizables a `schemas/`, además de extraer utilidades de dominio de scheduling fuera de `state.py`.

## Cambios Aplicados

Nuevos schemas top-level:

- `src/schemas/common.py`
- `src/schemas/onboarding.py`
- `src/schemas/scheduling.py`
- `src/schemas/microsoft_graph.py`
- `src/schemas/personalization.py`
- `src/schemas/planning.py`
- `src/schemas/reminders.py`

Nueva capa para utilidades de dominio extraídas de `state.py`:

- `src/services/scheduling/validation.py`

Compatibilidad temporal preservada:

- `src/agents/support/state.py` sigue exponiendo `AgentState`, `Phase` y re-exports de compatibilidad para DTOs y helpers antiguos.

Migraciones de imports aplicadas:

- planning
- priorities
- reminders
- scheduling helpers
- render/parsers de scheduling
- sync Outlook

## Resultado Arquitectónico

Después de esta fase:

- `state.py` ya no define `Event`, `SubjectItem`, `StudyPlanState`, `PrioritiesState`, `Constraints`, `StudyProfile`, `RawInputs` ni `CalendarState`;
- `state.py` ya no define `normalize_day`, `normalize_time`, `validate_event`, `sort_events` ni `new_event_id`;
- los servicios y repositorios relevantes consumen `schemas/` y `services/scheduling/validation.py` como origen real;
- los nodos existentes siguen funcionando sin cambio de contrato gracias a los re-exports.

## Guardrails Añadidos

- smoke checks para validar que `state.py` reexporta los contratos movidos;
- smoke checks para asegurar que `state.py` no vuelve a definir DTOs/utilidades extraídas;
- guardrail para impedir que cualquier modulo productivo fuera de `state.py` siga importando esos contratos movidos desde `agents.support.state`.

## Cierre Operativo

- los ultimos nodos que todavia consumian re-exports temporales fueron migrados a `schemas/` y `services.scheduling.validation`;
- `agents.support.state` queda reservado para `AgentState`, `Phase`, ensamblaje del subestado y compatibilidad temporal heredada;
- la fase queda lista para iniciar Fase 3 sin mantener excepciones activas en codigo productivo.

## Siguiente Paso Recomendado

Fase 3:

- mover repositorios top-level a `src/repositories/`;
- sacar PostgreSQL e in-memory fuera de `agents/support/*`;
- dejar wrappers temporales en rutas antiguas mientras migran consumidores.
