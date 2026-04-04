# Refactor Arquitectura - Fase 6

Fecha: 2026-04-03

## Objetivo cumplido

Se dejó `agents/` alineado con su responsabilidad conversacional:

- los nodos productivos quedaron como coordinadores finos;
- los handlers conversacionales reutilizables viven ahora en `src/agents/support/flows/`;
- los módulos legacy en `scheduling/`, `priorities/` y `planning/` quedaron solo como wrappers de compatibilidad.

## Flujos movidos a `agents/support/flows`

- `flows/scheduling/schedule_capture_service.py`
- `flows/scheduling/schedule_parsing_service.py`
- `flows/scheduling/schedule_pending_resolution_service.py`
- `flows/scheduling/schedule_review_service.py`
- `flows/scheduling/schedule_draft_service.py`
- `flows/priorities/priority_capture_service.py`
- `flows/planning/persistence_support.py`
- `flows/onboarding/collect_profile.py`
- `flows/extracurricular/collect_extracurricular_details.py`
- `flows/replanning/apply_modifications.py`

## Nodos adelgazados

Se dejaron como wrappers o coordinadores mínimos:

- `nodes/collect_profile/node.py`
- `nodes/collect_extracurricular_details/node.py`
- `nodes/apply_modifications/node.py`
- `nodes/request_schedules/node.py`
- `nodes/parse_schedules_to_events/node.py`
- `nodes/validate_schedule/node.py`
- `nodes/apply_schedule_correction/node.py`
- `nodes/build_draft_schedule/node.py`
- `nodes/collect_priorities/node.py`
- `nodes/build_study_plan/node.py`
- `nodes/persist_study_profile/node.py`

## Guardrails agregados

- el código productivo ya no puede importar los módulos conversacionales legacy desde `agents.support.scheduling.*`, `agents.support.priorities.*` o `agents.support.planning.persistence_support`;
- los hotspots movidos a `flows/` quedan verificados como wrappers finos;
- los módulos legacy movidos quedan verificados como wrappers sin implementación real.
