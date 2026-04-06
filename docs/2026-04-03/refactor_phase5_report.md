# Refactor Fase 5

Fecha: 2026-04-03

Estado: completada

Documento rector: `docs/2026-04-03/plan_maestro_refactorizacion_arquitectura.md`

## Objetivo Ejecutado

Consolidar `src/services/` como capa real de casos de uso y lógica de negocio, moviendo fuera de `agents/support/` los módulos puros de onboarding, personalization, priorities, scheduling, planning, reminders y sync, sin romper el grafo ni los imports legacy.

## Cambios Aplicados

Nueva capa top-level de services:

- `src/services/onboarding/`
- `src/services/personalization/`
- `src/services/priorities/`
- `src/services/scheduling/`
- `src/services/planning/`
- `src/services/reminders/`
- `src/services/sync/`

Casos de uso y helpers puros migrados:

- onboarding service + config + email sender
- personalization service + scoring + parser + questionnaire + models + runtime
- priorities state helpers + subject prioritization
- scheduling constants + models + persistence service
- planning state helpers + study planning + sync + persistence + materialization + tracking
- reminders service + dispatcher + state helpers
- sync Outlook Calendar + Microsoft To Do

Compatibilidad temporal preservada:

- `src/agents/support/onboarding/service.py`
- `src/agents/support/personalization/*.py`
- `src/agents/support/priorities/state_helpers.py`
- `src/agents/support/priorities/subject_prioritization_service.py`
- `src/agents/support/scheduling/service.py`
- `src/agents/support/scheduling/constants.py`
- `src/agents/support/scheduling/models.py`
- `src/agents/support/planning/*service.py`
- `src/agents/support/planning/state_helpers.py`
- `src/agents/support/reminders_service.py`
- `src/agents/support/reminders_dispatcher.py`
- `src/agents/support/reminders_state_helpers.py`
- `src/agents/support/tools/calendar_outlook.py`
- `src/agents/support/tools/microsoft_todo.py`

Estas rutas quedaron como wrappers o aliases de compatibilidad y ya no son el origen real de negocio.

## Resultado Arquitectónico

Después de esta fase:

- `bootstrap.container` construye servicios desde `src/services/`;
- `src/services/` ya no depende de `agents.support.*`;
- `agents/` conserva los flujos conversacionales y sigue consumiendo wrappers legacy donde todavía conviene;
- los servicios de sync quedaron separados de `integrations/`, que ahora se limita a adapters externos.

## Guardrails Añadidos

- guardrail para impedir imports desde `src/services/` hacia `agents.support.*`;
- guardrail para impedir que `bootstrap/container.py` vuelva a importar módulos legacy de servicio;
- mantenimiento de los guardrails de fases 2, 3 y 4.

## Validación

Suite ejecutada:

- `tests/test_refactor_guardrails.py`
- `tests/test_bootstrap_container.py`
- `tests/test_onboarding_services.py`
- `tests/test_email_verification_nodes.py`
- `tests/test_personalization_service.py`
- `tests/test_personalization_flow.py`
- `tests/test_schedule_persistence.py`
- `tests/test_study_planning_service.py`
- `tests/test_study_planning_persistence.py`
- `tests/test_study_plan_materialization_service.py`
- `tests/test_study_session_tracking_service.py`
- `tests/test_mark_missed_sessions.py`
- `tests/test_reminder_policy_persistence.py`
- `tests/test_reminder_dispatch_service.py`
- `tests/test_microsoft_todo_service.py`
- `tests/test_outlook_calendar_sync_service.py`

Resultado:

- 58 pruebas pasando.

## Siguiente Paso Recomendado

Fase 6:

- limpiar `agents/` para dejar nodos y flujos conversacionales más finos;
- separar más claramente los handlers conversacionales de scheduling y priorities;
- reducir el uso de wrappers legacy creados en esta fase.
