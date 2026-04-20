# Fase 1 - Estado Conversacional Operativo Minimo

Fecha: 2026-04-18

## Objetivo

Implementar la base pasiva del estado conversacional minimo definido en
`docs/2026-04-18/plan_fases_implementacion_mvp_lara.md`, alineada con
`docs/mvp_academic_agent_lara.md`, sin modificar todavia el router ni el
comportamiento de los nodos existentes.

## Alcance Implementado

- Se agrego `InteractionState` en `src/schemas/conversation.py`.
- Se agrego la clave top-level `interaction` en `AgentState`.
- Se expuso `AgentState.interaction_state` y `AgentState.partitions.interaction`.
- Se agregaron helpers en `src/services/conversation/state_helpers.py`.
- Se agregaron pruebas dedicadas en `tests/test_interaction_state.py`.
- Se extendieron las pruebas de particionado en `tests/test_agent_state_partitioning.py`.

## Campos Cubiertos

El subestado `interaction` cubre los campos minimos de fase 1:

- `active_intent`
- `current_domain`
- `interaction_mode`
- `pending_action`
- `pending_entity_type`
- `pending_entity_payload`
- `missing_fields_json`
- `confirmation_pending`
- `last_confirmation_payload`
- `noise_turn_count`
- `last_user_messages`
- `aggregated_user_text`
- `router_confidence`
- `clarification_needed`
- `is_waiting_for_oauth`
- `is_waiting_for_verification_code`
- `current_step`
- `current_section`

## Decisiones de Arquitectura

`interaction` queda separado de `conversation`.

- `conversation` conserva el runtime legacy del grafo: `messages`, `phase`,
  `timezone`, `awaiting_user_input`, `last_user_text` y campos equivalentes.
- `interaction` modela la capa operativa futura: intent activo, dominio,
  entidad pendiente, confirmaciones, buffer minimo y flags de espera.

Esta separacion evita mezclar el avance actual por fases con las reglas de
router, politicas de alcance, confirmaciones y flush que se implementaran en
fases posteriores.

## Reglas Aplicadas

- No se modifico el router.
- No se agrego logica de negocio en `AgentState`.
- No se cambiaron nodos ni flujos existentes.
- Los helpers solo normalizan, validan y serializan el subestado operativo.
- El reset por fuera de alcance reinicia `interaction` junto con el resto de
  particiones de dominio.

## Relacion con el Documento Lara

Esta fase prepara la infraestructura para implementar despues:

- intents y slots;
- reglas de router;
- politica de fuera de alcance;
- arbol de decision;
- buffer de mensajes;
- reglas de flush;
- confirmaciones;
- bloqueo activo;
- espera por OAuth;
- espera por codigo de verificacion.

La fase no activa esas politicas todavia. Solo deja el contrato de estado que
permitira agregarlas sin seguir creciendo el estado plano legacy.

## Criterios de Aceptacion

- El estado nuevo existe con defaults compatibles.
- Los estados previos siguen funcionando porque `interaction` tiene default.
- `AgentState.field_groups()` cubre todos los campos top-level exactamente una
  vez.
- `AgentState.partitions` expone la nueva vista tipada.
- Los helpers devuelven updates compatibles con LangGraph:
  `{"interaction": {...}}`.
- El reset de intento nuevo limpia `interaction`.

## Pruebas Relevantes

- `tests/test_interaction_state.py`
- `tests/test_agent_state_partitioning.py`

Resultado de verificacion:

- `uv run --with pytest python -m pytest tests/test_interaction_state.py tests/test_agent_state_partitioning.py`
  -> 13 passed
- `uv run --with pytest python -m pytest`
  -> 414 passed

## Siguiente Fase

La fase 2 deberia construir sobre este subestado para introducir el router
semantico inicial, manteniendo la politica como servicio separado y evitando
que los nodos acumulen reglas de decision.
