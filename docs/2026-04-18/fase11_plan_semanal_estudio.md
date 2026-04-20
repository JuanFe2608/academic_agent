# Fase 11 - Activacion Del Plan Semanal De Estudio

## Objetivo

Activar `build_study_plan` como paso natural despues de la priorizacion semanal, usando el horario fijo, las materias priorizadas, las actividades puntuales y la tecnica principal del Radar.

## Decision de activacion

- La transicion queda detras de `ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1`.
- Si el flag esta apagado, `phase=study_plan` sigue cerrando para conservar el comportamiento base.
- `collect_priorities` ya no persiste un snapshot intermedio cuando el flujo activo va directo a `build_study_plan`; la persistencia ocurre una sola vez con el plan generado.

## Logica aplicada

1. Cuando prioridades termina en `phase=study_plan`, el grafo enruta a `build_study_plan`.
2. `build_study_plan` usa `sync_subjects_and_study_plan`, que ya mezcla:
   - materias del horario fijo;
   - materias priorizadas por el usuario;
   - actividades academicas puntuales pendientes;
   - tecnica principal del Radar.
3. Las sesiones se generan como eventos internos tentativos, respetando horario fijo y restricciones.
4. El resumen muestra materias priorizadas, numero de sesiones sugeridas y guia pedagogica RAG solo si la respuesta esta soportada por fuentes de la tecnica principal.
5. El plan queda marcado con:
   - `external_sync_status=not_requested`;
   - `external_sync_requires_confirmation=True`;
   - targets futuros `outlook_calendar` y `microsoft_todo`.
6. No se crean eventos en Outlook ni tareas en Microsoft To Do en esta fase.
7. La materializacion de instancias y recordatorios queda detras de `ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1`, para fase 12.

## Archivos principales

- `src/agents/support/agent.py`
- `src/agents/support/nodes/collect_priorities/node.py`
- `src/agents/support/nodes/build_study_plan/node.py`
- `src/agents/support/planning/formatter.py`
- `src/agents/support/flows/planning/persistence_support.py`
- `tests/test_priorities_flow.py`
- `tests/test_study_planning_service.py`
- `tests/test_study_planning_persistence.py`

## Pruebas ejecutadas

```bash
uv run --with pytest python -m pytest \
  tests/test_priorities_flow.py \
  tests/test_study_planning_service.py \
  tests/test_study_planning_persistence.py \
  tests/test_study_plan_materialization_service.py \
  tests/test_reminder_policy_persistence.py \
  tests/test_agent_wait_routing.py
```

Resultado:

```text
45 passed
```

## Como probar manualmente

1. Activar:
   ```bash
   export ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW=1
   ```
2. Completar Radar y priorizacion semanal.
3. Confirmar prioridades o responder `Despues` / `usar horario`.
4. Lara debe generar el resumen del plan semanal.
5. El mensaje debe indicar que no se han creado eventos en Outlook ni tareas en Microsoft To Do.
