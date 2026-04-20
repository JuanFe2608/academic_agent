# Fase 14 - Seguimiento De Sesiones De Estudio

## Objetivo

Permitir que Lara registre por conversación el estado real de sesiones materializadas del plan de estudio:

- iniciar;
- completar;
- omitir;
- reportar que no se pudo estudiar;
- registrar avance parcial.

## Logica aplicada

1. El router detecta mensajes de tracking como `Ya termine la sesion de calculo` o `No pude estudiar hoy`.
2. El nodo `handle_academic_update` intenta tracking antes de crear o editar actividades academicas.
3. La resolucion de referencia usa:
   - instancia explicita si el texto trae id;
   - ultima sesion recordada en `interaction.pending_entity_payload`;
   - coincidencia por materia/titulo;
   - fecha contextual (`hoy`, `ayer`, `manana`, dia de la semana);
   - cercania temporal y estado de la instancia.
4. La transicion durable sigue delegada a `StudySessionTrackingService`.
5. Si la sesion queda `missed` o `skipped`, se marca `replan.trigger` como candidato para fase 15.
6. El tracking solo toca `study_plan_event_instances` y `study_session_checkins`; no modifica horario fijo.

## Archivos principales

- `src/services/planning/session_tracking_flow_service.py`
- `src/services/planning/tracking_service.py`
- `src/repositories/planning/tracking_repository.py`
- `src/agents/support/nodes/handle_academic_update/node.py`
- `src/services/conversation/input_classifier.py`
- `src/services/conversation/router.py`
- `scripts/record_session_completion.py`
- `scripts/mark_missed_sessions.py`

## Ejemplos soportados

```text
Ya termine la sesion de calculo
No pude estudiar hoy
Empece la sesion de programacion
Hice el 50% de la sesion de fisica
No voy a poder hacer la sesion de calculo de mañana
```

## Comandos operativos

Registrar manualmente:

```bash
uv run python scripts/record_session_completion.py \
  --student-id 15 \
  --instance-id 42 \
  --action complete \
  --completion-pct 100
```

Marcar vencidas:

```bash
uv run python scripts/mark_missed_sessions.py --grace-minutes 30 --limit 100
```

## Pruebas

```bash
uv run --with pytest python -m pytest \
  tests/test_study_session_tracking_service.py \
  tests/test_mark_missed_sessions.py \
  tests/test_conversation_router.py \
  tests/test_academic_update_flow.py
```

## Nota arquitectonica

La fase no agrega mas ruteo pesado al grafo. El nodo coordina, pero la deteccion, resolucion de instancia y aplicacion de tracking quedan en servicios. En fase 15 la replanificacion debe consumir `replan.change_request` y proponer cambios antes de aplicar.
