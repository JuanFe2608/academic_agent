# AgentState Refactor Phase 2

Fecha: 2026-04-06

Estado: implementado y validado

## 1. Objetivo de esta fase

Completar la siguiente ola incremental del refactor de `AgentState` sin romper el flujo del agente ni cambiar la arquitectura del proyecto.

Alcance ejecutado:

1. introducir helpers de update por subestado para runtime y scheduling;
2. migrar hotspots de escritura del flujo de scheduling para usar esos helpers;
3. marcar `events`, `events_validated` y `extras_has_any` como candidatos a derivación controlada;
4. encapsular más el routing sobre `conversation_state`, `onboarding_state` y `scheduling_state`;
5. dejar fuera de esta fase la migración de lógica desde `agents/support/flows` hacia `services/`.

## 2. Validación del orden propuesto

Sí, el orden era correcto.

Justificación:

- primero era necesario tener helpers de update por subestado para no seguir propagando escrituras manuales;
- después tenía sentido migrar hotspots de escritura, porque ya existía una API común para runtime y scheduling;
- solo después de eso se podían marcar campos derivables con una base técnica real;
- luego era seguro endurecer el routing sobre vistas tipadas;
- recién al final, y no en esta fase, conviene mover más lógica desde `agents/support/flows` hacia `services/`.

Dictamen:

- el orden es apropiado para terminar esta fase de estabilización de `AgentState`.

## 3. Qué se implementó

### 3.1 Helpers nuevos de runtime

Archivo creado:

- `src/agents/support/runtime_state_helpers.py`

Funciones añadidas:

- `ensure_conversation_state()`
- `conversation_state_to_update()`
- `update_conversation_state()`

Propósito:

- validar cambios contra `conversation_state`;
- devolver updates parciales compatibles con LangGraph;
- evitar duplicar mensajes antiguos bajo el reducer `add_messages`.

## 3.2 Helpers ampliados de scheduling

Archivo actualizado:

- `src/agents/support/scheduling/state_helpers.py`

Funciones añadidas o ampliadas:

- `ensure_scheduling_state()`
- `scheduling_state_to_update()`
- `update_scheduling_state()`
- `ensure_schedule_preview()`
- coerciones para `Event`, `ExtracurricularItem`, `PendingExtracurricularItem` y `PendingScheduleItem`

Propósito:

- validar cambios contra la partición `scheduling_state`;
- serializar solo los campos modificados al contrato plano del grafo;
- reutilizar la misma frontera en capture, extras, review y pendientes.

## 3.3 Campos marcados como derivables a futuro

Archivo actualizado:

- `src/agents/support/state.py`

Se añadió:

- `AgentState._DERIVATION_CANDIDATES`
- `AgentState.derivation_candidates()`

Campos marcados:

- `events`
- `events_validated`
- `extras_has_any`

Propósito:

- dejar explícito en código que siguen vivos por compatibilidad;
- documentar que no deben consolidarse como canónicos a largo plazo.

## 3.4 Hotspots de escritura migrados

Archivos actualizados:

- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`

Resultado:

- los updates de runtime y scheduling dejaron de construirse manualmente en esas zonas;
- ahora pasan por validación tipada antes de volver al grafo;
- el contrato plano del runtime se mantuvo intacto.

Observación:

- `schedule_pending_resolution_service.py` se migró también, aunque no estaba nombrado explícitamente en la lista inicial, porque forma parte real del hotspot de captura de horarios.

## 3.5 Routing más encapsulado

Archivo actualizado:

- `src/agents/support/agent.py`

Cambios:

- `_route_welcome()`
- `_route_from_phase()`
- `_route_collect_profile()`
- `_route_send_email_verification()`
- `_route_verify_email_code()`
- `_route_confirm_profile()`
- `_route_persist_profile()`
- `_route_after_parse_schedules()`
- `_route_validate()`
- `_route_after_schedule_edit()`
- `_route_after_persist_schedule()`
- `_route_collect_study_profile()`
- `_route_collect_study_profile_tiebreaker()`
- `_route_persist_study_profile()`
- `_route_collect_priorities()`
- `_route_build_study_plan()`

Resultado:

- el router ahora depende más de `conversation_state`, `onboarding_state`, `scheduling_state` y `planning_state`;
- disminuyó el acceso plano a `state.get(...)`.

## 3.6 Corrección necesaria por tipado de mensajes

Archivo actualizado:

- `src/agents/support/nodes/utils.py`

Motivo:

- al leer desde `conversation_state`, Pydantic coaccionaba mensajes a `BaseMessage`, lo que hacía que el conteo de mensajes de usuario fallara en ciertos casos.

Corrección aplicada:

- `get_last_user_text()`
- `get_last_user_images()`
- `count_user_messages()`

Ahora reconocen `BaseMessage(type="human")` además de `HumanMessage`.

## 3.7 Reset consistente ya consolidado

Archivo ya migrado y preservado:

- `src/agents/support/nodes/welcome_consent/node.py`

Se mantuvo la centralización previa de:

- `restart_payload_for_new_attempt()`

Esto sigue siendo parte del cierre correcto de la fase de `AgentState`.

## 4. Archivos modificados en esta fase

- `src/agents/support/state.py`
- `src/agents/support/runtime_state_helpers.py`
- `src/agents/support/scheduling/state_helpers.py`
- `src/agents/support/agent.py`
- `src/agents/support/nodes/utils.py`
- `src/agents/support/nodes/welcome_consent/node.py`
- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/flows/scheduling/schedule_pending_resolution_service.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `src/agents/support/flows/scheduling/schedule_review_service.py`
- `tests/test_agent_state_partitioning.py`

## 5. Qué cambió conceptualmente

Antes:

- cada hotspot armaba updates a mano mezclando runtime y scheduling;
- el router dependía demasiado del estado plano;
- los campos derivables estaban solo documentados, no marcados en código.

Ahora:

- runtime y scheduling tienen helpers propios de update;
- los hotspots principales escriben a través de esos helpers;
- el router consume más las vistas tipadas;
- los campos legacy más ambiguos ya están señalados como candidatos a derivación controlada.

## 6. Qué no se hizo todavía

No se hizo en esta fase:

- mover masivamente lógica de `agents/support/flows` hacia `services/`;
- eliminar campos legacy;
- unificar todavía `events` con una sola fuente canónica;
- deprecar formalmente `events_validated` o `extras_has_any`;
- cambiar el entrypoint o `langgraph.json`.

## 7. Verificación ejecutada

Batería amplia ejecutada:

```bash
.venv/bin/python -m pytest \
  tests/test_agent_state_partitioning.py \
  tests/test_message_image_utils.py \
  tests/test_out_of_scope_restart.py \
  tests/test_agent_wait_routing.py \
  tests/test_schedule_request_flow.py \
  tests/test_extracurricular_flow.py \
  tests/test_collect_profile_validation.py \
  tests/test_personalization_flow.py \
  tests/test_priorities_flow.py \
  tests/test_study_planning_persistence.py \
  tests/test_refactor_guardrails.py \
  tests/test_email_verification_nodes.py \
  tests/test_schedule_modifications.py \
  tests/test_schedule_draft_service.py \
  tests/test_schedule_persistence.py \
  tests/test_schedule_preview.py \
  tests/test_schedule_parsing_service.py \
  tests/test_study_planning_service.py \
  tests/test_reminder_policy_persistence.py
```

Resultado:

- `119 passed in 13.26s`

## 8. Riesgos restantes

- todavía existen múltiples writers del estado fuera de estos hotspots;
- `events` sigue siendo una vista derivada pero muy usada por replanning;
- la separación entre control conversacional y lógica de aplicación mejoró, pero aún no está completamente cerrada.

## 9. Recomendación de siguiente paso

El siguiente paso correcto ya no es seguir expandiendo helpers indiscriminadamente.

Conviene:

1. usar esta base para identificar qué partes de `schedule_review_service` y `collect_extracurricular_details` deberían salir después a `services/`;
2. estabilizar la semántica de `events` frente a `schedule.blocks`;
3. solo después iniciar la migración progresiva de lógica desde `agents/support/flows` hacia `services/`.

## 10. Conclusión

Esta fase sí puede considerarse un cierre sólido de la estabilización inicial de `AgentState`.

Se logró:

- bajar el acoplamiento operativo del estado;
- formalizar updates por subestado;
- reducir escrituras manuales en hotspots reales;
- fortalecer el router sobre vistas tipadas;
- mantener compatibilidad completa con el flujo actual.

Para este proyecto, ese era el objetivo correcto antes de seguir con refactors más profundos.
