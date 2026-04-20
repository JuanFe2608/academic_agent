# Fase 12 - Materializacion, Recordatorios Y Dispatch Inicial

## Objetivo

Convertir el plan semanal guardado en sesiones fechadas internas y recordatorios programables, sin crear eventos externos en Outlook ni tareas en Microsoft To Do sin confirmacion.

## Decision de activacion

- La materializacion queda detras de `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1`.
- Los recordatorios quedan activos cuando la materializacion esta activa, salvo que `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS=0`.
- El canal default del MVP es `in_app`.
- `ACADEMIC_AGENT_REMINDER_CHANNELS` acepta `in_app`, `email` y `whatsapp`, pero `whatsapp` no debe ser el default hasta completar el dispatcher real de la fase 13.

## Logica aplicada

1. `persist_planning_snapshot_for_update` guarda el snapshot de prioridades y plan.
2. Si el flag de fase 12 esta activo, se materializan instancias fechadas con `StudyPlanMaterializationService`.
3. El mismo plan no duplica instancias porque la clave `source_instance_key` es estable por perfil, posicion, evento y fecha.
4. Un plan nuevo supersede instancias futuras programadas de planes anteriores.
5. Luego se sincronizan politicas y dispatches de recordatorios con `StudyPlanRemindersService`.
6. Las politicas default del MVP son:
   - 60 minutos antes de la sesion;
   - 10 minutos antes de la sesion;
   - seguimiento 15 minutos despues de la sesion;
   - revision de sesion perdida 30 minutos despues del cierre.
7. El resumen conversacional informa:
   - plan guardado;
   - sesiones materializadas;
   - recordatorios activados;
   - confirmacion pendiente para Outlook y Microsoft To Do.
8. Si falla materializacion o reminders, la conversacion no se rompe. El estado conserva el error para reintento operativo.

## Archivos principales

- `src/services/planning/operational_policy.py`
- `src/agents/support/flows/planning/persistence_support.py`
- `src/agents/support/nodes/build_study_plan/node.py`
- `src/agents/support/planning/formatter.py`
- `src/services/reminders/service.py`
- `src/schemas/reminders.py`
- `src/services/reminders/state_helpers.py`
- `tests/test_study_planning_persistence.py`
- `tests/test_study_plan_materialization_service.py`
- `tests/test_reminder_dispatch_service.py`

## Pruebas ejecutadas

```bash
uv run --with pytest python -m pytest \
  tests/test_study_planning_persistence.py \
  tests/test_study_plan_materialization_service.py \
  tests/test_reminder_policy_persistence.py \
  tests/test_reminder_dispatch_service.py
```

Resultado:

```text
18 passed
```

```bash
uv run --with pytest python -m pytest \
  tests/test_study_planning_service.py \
  tests/test_priorities_flow.py \
  tests/test_academic_update_flow.py \
  tests/test_refactor_guardrails.py \
  tests/test_bootstrap_container.py \
  tests/test_microsoft_todo_service.py \
  tests/test_whatsapp_channel_service.py
```

Resultado:

```text
58 passed
```

```bash
uv run --with pytest python -m pytest
```

Resultado:

```text
489 passed
```

## Como probar manualmente

1. Activar el flujo posterior al Radar:
   ```bash
   export ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1
   ```
2. Activar fase 12:
   ```bash
   export ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1
   ```
3. Mantener canal interno por defecto:
   ```bash
   unset ACADEMIC_AGENT_REMINDER_CHANNELS
   ```
4. Completar Radar, priorizacion y plan semanal.
5. La respuesta de Lara debe indicar que el plan fue guardado, que hay sesiones materializadas y que los recordatorios quedaron activados por canal interno.
6. Validar en DB que existan filas pendientes en `study_plan_event_instances`, `reminder_policies` y `reminder_dispatches`.

## Observaciones arquitectonicas

- `persistence_support.py` ya formaliza la compuerta de materializacion/reminders. No conviene mover esta decision al nodo.
- `build_study_plan` sigue razonable para el MVP: coordina el caso de uso, pero delega planificacion, persistencia, materializacion y resumen.
- Para fases 14-15 conviene dividir `handle_academic_update` si se le suma tracking, replanificacion y confirmaciones complejas.
