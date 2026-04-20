# Fase 4 - Router Conversacional Hibrido

Fecha: 2026-04-18

## Objetivo

Agregar una capa de router por dominios e intents que complemente el router
por `phase` del grafo, sin reemplazar todavia el flujo principal.

## Alcance Implementado

- DTO `ConversationRouteDecision` en `src/schemas/conversation.py`.
- Servicio `src/services/conversation/router.py`.
- Integracion inicial solo en `phase=end`.
- Adaptador `route_name_for_conversation_decision()` para mapear decisiones a
  nombres de nodos actuales.
- Pruebas unitarias de prioridad y ruteo.

## Intents Iniciales Cubiertos

- `provide_missing_data`
- `confirm_action`
- `reject_action`
- `smalltalk_contextual`
- `out_of_scope_request`
- `wellbeing_or_crisis_signal`
- `register_academic_activity`
- `request_study_method_recommendation`

## Orden De Decision Implementado

1. Bienestar o crisis.
2. Confirmacion pendiente.
3. Politica bloqueante: solucion prohibida, solicitud generalista clara o
   riesgo humano.
4. Comando critico.
5. Dato faltante pendiente.
6. Bloque activo.
7. Politica no bloqueante o redireccion.
8. Nueva intencion.
9. Smalltalk contextual.

El orden mantiene la regla principal: el router no debe abrir una intencion
nueva si el usuario esta completando un dato pendiente, confirmando una accion
o enviando smalltalk contextual dentro de un bloque activo.

La politica sigue teniendo prioridad para casos fuertes como crisis, pedir
resolver un quiz o hacer una pregunta generalista clara. Para entradas cortas
que solo parecen fuera de alcance por falta de contexto, como `viernes` o `si`,
el estado conversacional activo decide primero.

## Integracion Con El Grafo

La integracion se limita a `phase=end` en `src/agents/support/agent.py`.

El resto de fases siguen usando el router por `phase` existente para evitar
romper `_should_wait` y los subflujos actuales. Esto deja preparado el avance
gradual hacia fases activas.

## Relacion Con Fases Previas

- Fase 1: usa `InteractionState` para leer `confirmation_pending`,
  `missing_fields_json`, `active_intent` y `current_domain`.
- Fase 2: puede recibir texto agregado desde `AggregatedInput`.
- Fase 3: usa `InputClassification` y `ScopeDecision` como capas previas.

## Riesgos Controlados

- `viernes` con `missing_fields_json=["fecha"]` se interpreta como
  `provide_missing_data`.
- `borra esa actividad` no se mezcla con una captura pendiente.
- `gracias`, `ok`, `jaja` preservan el bloque activo.
- Bienestar/crisis y fuera de alcance siguen teniendo prioridad sobre intents
  academicos normales.

## Pruebas Relevantes

- `tests/test_conversation_router.py`
- `tests/test_study_recommendation_agent_flow.py`
- `tests/test_agent_wait_routing.py`

Resultado de verificacion:

- `uv run --with pytest python -m pytest tests/test_conversation_router.py tests/test_study_recommendation_agent_flow.py tests/test_agent_wait_routing.py tests/test_scope_policy.py tests/test_input_classification.py`
  -> 38 passed
- `uv run --with pytest python -m pytest`
  -> 444 passed

## Siguiente Paso

La siguiente expansion debe integrar este router en fases activas de forma
controlada, manteniendo `_should_wait` como guardia de pausas conversacionales.
