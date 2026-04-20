# Fase 15 - Replanificacion Automatica Controlada

## Objetivo

Permitir que Lara proponga ajustes al plan de estudio cuando cambian las condiciones academicas, sin aplicar cambios externos sin confirmacion.

## Logica aplicada

1. El router detecta solicitudes explicitas como `Replanifica mi semana de estudio` y las envia a `request_replan`.
2. Las senales internas de actividad academica, tracking de sesiones y horario fijo pueden dejar `replan.trigger` y `replan.change_request`.
3. El grafo solo continua a replanificacion si existe un plan semanal base; si no lo hay, conserva la senal sin forzar una propuesta vacia.
4. `StudyReplanningService` recalcula el plan con los servicios existentes de prioridades y planning.
5. Para sesiones perdidas u omitidas, intenta mover la sesion afectada al siguiente hueco semanal disponible, respetando horario fijo, sesiones ya propuestas y restricciones de sueno.
6. Antes de aplicar, Lara muestra un diff corto:
   - sesiones movidas;
   - sesiones nuevas;
   - sesiones canceladas;
   - razon del cambio.
7. El nodo `request_replan` exige confirmacion `si/no`.
8. Solo con confirmacion se persiste una nueva version del plan, se superseden instancias futuras y se re-sincronizan recordatorios si la politica operacional esta activa.
9. Outlook Calendar y Microsoft To Do quedan marcados como `not_requested`; no se sincronizan en esta fase.

## Trazabilidad

Cuando hay base durable suficiente:

- se crea `study_replan_requests`;
- se crea `study_replan_proposals`;
- al aplicar, el nuevo `study_plan_profiles` queda con `origin_type = 'replan'`;
- `supersedes_study_plan_profile_id` apunta a la version anterior;
- la propuesta queda `applied`.

Si falta perfil o plan persistido, la propuesta sigue funcionando en estado conversacional, pero sin request durable.

## Archivos principales

- `src/services/planning/replanning_service.py`
- `src/repositories/planning/replan_repository.py`
- `src/agents/support/flows/replanning/request_replan.py`
- `src/agents/support/nodes/request_replan/node.py`
- `src/agents/support/agent.py`
- `src/services/conversation/input_classifier.py`
- `src/services/conversation/router.py`
- `src/agents/support/flows/scheduling/fixed_schedule_management_service.py`

## Pruebas

```bash
uv run --with pytest python -m pytest \
  tests/test_replanning_controlled_flow.py \
  tests/test_conversation_router.py \
  tests/test_academic_update_flow.py \
  tests/test_fixed_schedule_management_flow.py \
  tests/test_replanning_apply_modifications.py
```

## Nota arquitectonica

La logica de replanificacion no queda en `handle_academic_update`. Ese nodo solo marca candidatos desde actividades y tracking. La generacion de propuesta, diff, trazabilidad y aplicacion viven en el servicio y el flujo `request_replan`, manteniendo el grafo como coordinador.
